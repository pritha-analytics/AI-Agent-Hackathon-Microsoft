"""SQLite-backed transition plans. The plan is structured product state, not chat text."""

import sqlite3
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .plan_templates import PLAN_TEMPLATES

DB_PATH = Path(__file__).resolve().parent / "data" / "transition_plans.db"
VALID_STATUSES = {"todo", "in_progress", "done", "needs_human"}
PHASE_ORDER = {"this_week": 0, "before_move_in": 1, "later": 2}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Only explicit first-person completion statements can update the plan. This
# deliberately excludes questions such as "Should I arrange electricity?" and
# vague progress reports such as "I'm looking at broadband."
COMPLETION_RE = re.compile(
    r"\b(?:i(?:'ve| have)|jag har|vi har)\s+(?:already\s+)?"
    r"(?:done|completed|finished|checked|arranged|set up|chosen|reviewed|understood|built|"
    r"ordnat|gjort|checkat|valt|gatt igenom|gått igenom|förstått|byggt)\b",
    re.IGNORECASE,
)
TASK_PATTERNS = {
    "mortgage": r"\b(?:mortgage|home loan|bolån)\b",
    "home_insurance": r"\b(?:home insurance|hemförsäkring)\b",
    "condominium_add_on": r"(?:condominium\s+(?:insurance\s+)?add[- ]?on|bostadsrättstillägg)",
    "electricity": r"\b(?:electricity|elavtal|elkontrakt)\b",
    "broadband": r"\b(?:broadband|internet subscription|bredband)\b",
    "housing_fee": r"(?:housing[ -]cooperative fee|monthly fee|månadsavgift|bostadsrättsföreningens avgift)",
    "life_insurance": r"\b(?:life insurance|livförsäkring)\b",
    "loan_protection": r"\b(?:loan protection|bolåneskydd)\b",
    "emergency_savings": r"\b(?:emergency savings|emergency fund|buffert)\b",
}


class PlanStore:
    def _connect(self) -> sqlite3.Connection:
        DB_PATH.parent.mkdir(exist_ok=True)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        return connection

    def __init__(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    event_title TEXT NOT NULL,
                    key_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plan_tasks (
                    plan_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    due_offset_days INTEGER NOT NULL,
                    due_date TEXT,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (plan_id, task_id),
                    FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _due_date(key_date: str | None, offset: int) -> str | None:
        if not key_date:
            return None
        return (date.fromisoformat(key_date) + timedelta(days=offset)).isoformat()

    def get_for_session(self, session_id: str) -> dict | None:
        with self._connect() as connection:
            plan = connection.execute("SELECT * FROM plans WHERE session_id = ?", (session_id,)).fetchone()
            if not plan:
                return None
            tasks = connection.execute(
                "SELECT task_id, title, description, phase, priority, owner, due_date, status "
                "FROM plan_tasks WHERE plan_id = ? ORDER BY rowid", (plan["plan_id"],)
            ).fetchall()
        return {**dict(plan), "tasks": [dict(task) | {"id": task["task_id"]} for task in tasks]}

    def create(self, session_id: str, event_type: str, event_title: str, key_date: str | None) -> dict:
        if event_type not in PLAN_TEMPLATES:
            raise ValueError("Unsupported transition type")
        if key_date:
            date.fromisoformat(key_date)
        existing = self.get_for_session(session_id)
        if existing:
            return existing
        plan_id, now = f"PLAN-{uuid.uuid4().hex[:10].upper()}", self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO plans VALUES (?, ?, ?, ?, ?, ?, ?)",
                (plan_id, session_id, event_type, event_title.strip() or "My home purchase", key_date, now, now),
            )
            for task in PLAN_TEMPLATES[event_type]:
                connection.execute(
                    "INSERT INTO plan_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (plan_id, task["id"], task["title"], task["description"], task["phase"], task["priority"],
                     task["owner"], task["due_offset_days"], self._due_date(key_date, task["due_offset_days"]), "todo", now),
                )
        return self.get_for_session(session_id)

    def update_task(self, session_id: str, task_id: str, status: str) -> dict:
        if status not in VALID_STATUSES:
            raise ValueError("Unsupported task status")
        plan = self.get_for_session(session_id)
        if not plan:
            raise LookupError("No transition plan exists for this session")
        now = self._now()
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE plan_tasks SET status = ?, updated_at = ? WHERE plan_id = ? AND task_id = ?",
                (status, now, plan["plan_id"], task_id),
            ).rowcount
            if not updated:
                raise LookupError("Unknown plan task")
            connection.execute("UPDATE plans SET updated_at = ? WHERE plan_id = ?", (now, plan["plan_id"]))
        return self.get_for_session(session_id)

    def delete_for_session(self, session_id: str) -> bool:
        """Delete the plan and its tasks when the customer deletes its chat."""
        with self._connect() as connection:
            plan = connection.execute("SELECT plan_id FROM plans WHERE session_id = ?", (session_id,)).fetchone()
            if not plan:
                return False
            connection.execute("DELETE FROM plan_tasks WHERE plan_id = ?", (plan["plan_id"],))
            connection.execute("DELETE FROM plans WHERE plan_id = ?", (plan["plan_id"],))
        return True

    def complete_explicitly_reported_tasks(self, session_id: str | None, message: str) -> list[str]:
        """Mark only clearly completed, named tasks. This is deterministic, not LLM inference."""
        if not session_id:
            return []
        # Attachments can contain arbitrary historic text; only consider the actual chat text.
        chat_text = (message or "").split("\n\n[Attached", 1)[0]
        if not COMPLETION_RE.search(chat_text):
            return []
        plan = self.get_for_session(session_id)
        if not plan:
            return []
        matched_ids = [
            task_id for task_id, pattern in TASK_PATTERNS.items()
            if re.search(pattern, chat_text, re.IGNORECASE)
        ]
        if not matched_ids:
            return []
        open_tasks = {task["id"]: task for task in plan["tasks"] if task["status"] != "done"}
        completed = [open_tasks[task_id]["title"] for task_id in matched_ids if task_id in open_tasks]
        if not completed:
            return []
        now = self._now()
        with self._connect() as connection:
            connection.executemany(
                "UPDATE plan_tasks SET status = 'done', updated_at = ? WHERE plan_id = ? AND task_id = ?",
                [(now, plan["plan_id"], task_id) for task_id in matched_ids if task_id in open_tasks],
            )
            connection.execute("UPDATE plans SET updated_at = ? WHERE plan_id = ?", (now, plan["plan_id"]))
        return completed

    @staticmethod
    def _next_task(plan: dict) -> dict | None:
        remaining = [task for task in plan["tasks"] if task["status"] != "done"]
        if not remaining:
            return None
        return min(
            remaining,
            key=lambda task: (PHASE_ORDER.get(task["phase"], 99), PRIORITY_ORDER.get(task["priority"], 99)),
        )

    def context_for_session(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        plan = self.get_for_session(session_id)
        if not plan:
            return None
        done_count = sum(task["status"] == "done" for task in plan["tasks"])
        next_task = self._next_task(plan)
        if next_task is None:
            next_instruction = "All plan tasks are complete. Congratulate the user without proposing another plan task."
        else:
            next_instruction = (
                f"The next plan task is exactly: {next_task['title']} (phase: {next_task['phase']}, "
                f"priority: {next_task['priority']}). When the user asks what to do next or requests "
                f"priorities, recommend this task first. Do not recommend a Later task while any This week "
                f"or Before move-in task remains incomplete."
            )
        return (
            f"Active transition plan: {plan['event_title']}. Key date: {plan['key_date'] or 'not set'}. "
            f"Progress: {done_count}/{len(plan['tasks'])} tasks complete. "
            f"{next_instruction} Mention the plan only when it genuinely helps."
        )


plans = PlanStore()
