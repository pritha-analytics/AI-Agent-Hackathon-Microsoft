"""In-memory chat session store, so a human employee can view/join a live
chat. Good enough for a hackathon demo (single process, no persistence
across restarts) - a real deployment would swap this for a database."""

from datetime import datetime, timezone


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_or_create(self, session_id: str) -> dict:
        return self._sessions.setdefault(
            session_id, {"messages": [], "needs_human": False, "assigned_agent": None}
        )

    def add_message(self, session_id: str, role: str, content: str, agent_name: str | None = None) -> int:
        session = self.get_or_create(session_id)
        message = {"role": role, "content": content, "ts": self._now()}
        if agent_name:
            message["agent_name"] = agent_name
        session["messages"].append(message)
        return len(session["messages"])

    def request_human(self, session_id: str) -> None:
        self.get_or_create(session_id)["needs_human"] = True

    def assign_agent(self, session_id: str, agent_name: str) -> None:
        self.get_or_create(session_id)["assigned_agent"] = agent_name

    def messages_after(self, session_id: str, after: int) -> list[dict]:
        messages = self.get_or_create(session_id)["messages"]
        return messages[after:]

    def get(self, session_id: str) -> dict | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        """Remove a customer's transient chat transcript from this demo store."""
        return self._sessions.pop(session_id, None) is not None

    def list_summaries(self) -> list[dict]:
        summaries = []
        for session_id, session in self._sessions.items():
            messages = session["messages"]
            last = messages[-1] if messages else None
            summaries.append(
                {
                    "session_id": session_id,
                    "needs_human": session["needs_human"],
                    "message_count": len(messages),
                    "last_message": last["content"][:120] if last else "",
                    "last_ts": last["ts"] if last else "",
                }
            )
        summaries.sort(key=lambda s: s["last_ts"], reverse=True)
        return summaries


sessions = SessionStore()
