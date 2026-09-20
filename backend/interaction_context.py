"""Tracks, for the current turn only, which topic and session_id the
in-flight /api/chat request belongs to - so llm_client.py's instrumented
wrapper can attribute each LLM call's token usage to a topic/session
without every agent's tool-calling loop needing to take those as an
explicit parameter (same problem, and same fix, as verified_customer.py).

A contextvar rather than a plain module-level variable, so this stays
correctly isolated per-request even when FastAPI dispatches concurrent sync
requests across threadpool workers."""

import contextvars

_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar("interaction_context", default=None)


def set_context(topic: str | None, session_id: str | None) -> None:
    _context.set({"topic": topic, "session_id": session_id})


def get_context() -> dict:
    return _context.get() or {}
