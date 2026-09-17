"""Persistence for filled insurance forms confirmed in chat.

Each confirmed form is written as its own JSON file under
backend/data/forms/{form_id}.json, so a customer service worker can open
a link (see the /forms routes in main.py) and read exactly what the
customer submitted - no database needed for this demo-scale feature.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

FORMS_DIR = Path(__file__).resolve().parent / "data" / "forms"


def save_form(session_id: str, title: str, fields: list[dict]) -> str:
    FORMS_DIR.mkdir(parents=True, exist_ok=True)

    form_id = uuid.uuid4().hex[:12]
    form = {
        "id": form_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "title": title,
        "fields": fields,
    }

    form_path = FORMS_DIR / f"{form_id}.json"
    with form_path.open("w", encoding="utf-8") as f:
        json.dump(form, f, ensure_ascii=False, indent=2)

    return form_id


def get_form(form_id: str) -> dict | None:
    if not re.fullmatch(r"[0-9a-f]{12}", form_id):
        return None
    form_path = FORMS_DIR / f"{form_id}.json"
    if not form_path.exists():
        return None
    with form_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_forms() -> list[dict]:
    if not FORMS_DIR.exists():
        return []

    summaries = []
    for form_path in FORMS_DIR.glob("*.json"):
        with form_path.open("r", encoding="utf-8") as f:
            form = json.load(f)
        summaries.append(
            {
                "id": form["id"],
                "created_at": form["created_at"],
                "title": form["title"],
                "session_id": form["session_id"],
            }
        )

    summaries.sort(key=lambda s: s["created_at"], reverse=True)
    return summaries
