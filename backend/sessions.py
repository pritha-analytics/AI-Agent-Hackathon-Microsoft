"""Chat session store - a thin wrapper over db.py's ChatSession/ChatMessage
tables (see there), kept as its own module because it's a distinct concept
from the NBA data db.py also stores. Used to be a plain in-memory dict here,
which reset on every server restart (including a dev `--reload`) - a chat
listed in the sidebar would silently 404 the next time someone tried to
reopen it. Backed by the same SQLite/Postgres db.py already uses, so it
survives restarts like everything else there."""

from . import db


class SessionStore:
    def get_or_create(self, session_id: str) -> dict:
        return db.get_or_create_chat_session(session_id)

    def add_message(self, session_id: str, role: str, content: str, agent_name: str | None = None) -> int:
        if role == "user":
            db.set_chat_title_if_unset(session_id, content.split("\n\n[Attached", 1)[0].strip() or "Chat")
        return db.add_chat_message(session_id, role, content, agent_name)

    def request_human(self, session_id: str) -> None:
        db.set_chat_needs_human(session_id)

    def assign_agent(self, session_id: str, agent_name: str) -> None:
        db.set_chat_assigned_agent(session_id, agent_name)

    def set_verified_customer(self, session_id: str, customer_id: str) -> None:
        """Remembers that THIS browser session verified as this customer, so
        a later request for the interaction-history panel (which only sends
        session_id, not a password) can be checked against it instead of
        trusting a customer_id the client claims - see
        /api/sessions/{session_id}/interaction-history in main.py."""
        db.set_chat_verified_customer(session_id, customer_id)

    def get_verified_customer(self, session_id: str) -> str | None:
        return db.get_chat_verified_customer(session_id)

    def messages_after(self, session_id: str, after: int) -> list[dict]:
        return db.get_chat_messages_after(session_id, after)

    def get(self, session_id: str) -> dict | None:
        return db.get_chat_session(session_id)

    def delete(self, session_id: str) -> bool:
        return db.delete_chat_session(session_id)

    def list_summaries(self) -> list[dict]:
        return db.list_chat_session_summaries()


sessions = SessionStore()
