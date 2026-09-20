"""Transition plans - business logic (task templates, completion-phrase
matching, next-task recommendation) on top of db.py's plain persistence
(TransitionPlan/TransitionPlanTask), which lives in the same shared,
Supabase-capable database as the rest of the app.

Plans are keyed primarily by session_id (a plan can start before identity
verification - see agent.mentions_home_purchase, which triggers plan
creation from chat text alone). Once that session's customer verifies,
claim_for_customer stamps customer_id onto the plan so a LATER session for
the SAME customer resolves to this same plan instead of starting blank -
see get_for_session's customer_id fallback below."""

import re
import uuid
from datetime import date, timedelta

from . import db
from .plan_templates import PLAN_TEMPLATES

VALID_STATUSES = {"todo", "in_progress", "done", "needs_human"}
PHASE_ORDER = {"this_week": 0, "secure_mortgage": 1, "before_move_in": 2, "later": 3}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Only explicit first-person completion statements can update the plan. This
# deliberately excludes questions such as "Should I arrange electricity?" and
# vague progress reports such as "I'm looking at broadband."
COMPLETION_RE = re.compile(
    r"\b(?:i(?:'ve| have)|jag har|vi har)\s+(?:already\s+)?"
    r"(?:done|completed|finished|checked|arranged|set up|chosen|reviewed|understood|built|"
    r"received|got|signed|ordnat|gjort|checkat|valt|gatt igenom|gått igenom|förstått|byggt|fått|skrivit under)\b",
    re.IGNORECASE,
)
TASK_PATTERNS = {
    "mortgage": r"\b(?:mortgage|home loan|bolån)\b",
    "purchase_agreement": r"\b(?:purchase agreement|köpekontrakt)\b",
    "loan_offer": r"\b(?:loan offer|bolånelöfte|slutligt lån)\b",
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
    @staticmethod
    def _due_date(key_date: str | None, offset: int) -> str | None:
        if not key_date:
            return None
        return (date.fromisoformat(key_date) + timedelta(days=offset)).isoformat()

    def get_for_session(self, session_id: str) -> dict | None:
        plan = db.get_transition_plan_by_session(session_id)
        if plan is not None:
            return plan
        # No plan under this exact session yet - if this session's customer
        # already has a plan from an earlier session, that's the one to show
        # (see module docstring), not a blank slate.
        customer_id = db.get_chat_verified_customer(session_id)
        if not customer_id:
            return None
        return db.get_transition_plan_by_customer(customer_id)

    def create(self, session_id: str, event_type: str, event_title: str, key_date: str | None) -> dict:
        if event_type not in PLAN_TEMPLATES:
            raise ValueError("Unsupported transition type")
        if key_date:
            date.fromisoformat(key_date)
        existing = self.get_for_session(session_id)
        if existing:
            return existing
        plan_id = f"PLAN-{uuid.uuid4().hex[:10].upper()}"
        tasks = [
            {**task, "due_date": self._due_date(key_date, task["due_offset_days"])}
            for task in PLAN_TEMPLATES[event_type]
        ]
        db.create_transition_plan(
            plan_id, session_id, event_type, event_title.strip() or "My home purchase", key_date, tasks,
        )
        return self.get_for_session(session_id)

    def claim_for_customer(self, session_id: str, customer_id: str) -> None:
        """Called right when a session's customer verifies (see main.py) -
        links this session's own plan (if any) to their customer record so
        a later session finds it. If they already have a plan from an
        earlier session, this session's own (blank) plan row, if any, is
        simply left unclaimed - get_for_session's fallback already finds
        the right one by customer_id."""
        db.claim_transition_plan_for_customer(session_id, customer_id)

    def update_task(self, session_id: str, task_id: str, status: str) -> dict:
        if status not in VALID_STATUSES:
            raise ValueError("Unsupported task status")
        plan = self.get_for_session(session_id)
        if not plan:
            raise LookupError("No transition plan exists for this session")
        if not db.update_transition_plan_task(plan["plan_id"], task_id, status):
            raise LookupError("Unknown plan task")
        return self.get_for_session(session_id)

    def delete_for_session(self, session_id: str) -> bool:
        """Delete the plan and its tasks when the customer deletes its chat."""
        return db.delete_transition_plan_for_session(session_id)

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
        completed_ids = [task_id for task_id in matched_ids if task_id in open_tasks]
        if not completed_ids:
            return []
        completed_titles = [open_tasks[task_id]["title"] for task_id in completed_ids]
        db.complete_transition_plan_tasks(plan["plan_id"], completed_ids)
        return completed_titles

    def mark_task_done(self, session_id: str, task_id: str) -> None:
        """Best-effort auto check-off (e.g. a related case just got created)
        - a no-op if there's no plan yet or the task's already done, never
        raises, since this is always incidental to some other action
        succeeding (see main.py's case-creation handling)."""
        plan = self.get_for_session(session_id)
        if not plan:
            return
        task = next((t for t in plan["tasks"] if t["id"] == task_id), None)
        if task and task["status"] != "done":
            db.update_transition_plan_task(plan["plan_id"], task_id, "done")

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
                f"priorities, recommend this task first. Do not recommend a Later task while any First week, "
                f"Secure mortgage, or Before move-in task remains incomplete."
            )
        return (
            f"Active transition plan: {plan['event_title']}. Key date: {plan['key_date'] or 'not set'}. "
            f"Progress: {done_count}/{len(plan['tasks'])} tasks complete. "
            f"{next_instruction} Mention the plan only when it genuinely helps."
        )


plans = PlanStore()
