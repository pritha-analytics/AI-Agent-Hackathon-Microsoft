"""Tracks, for the current turn only, which customer_id (if any) was just
successfully identity-verified - so main.py can decide whether to surface
Next Best Action offers this turn, without needing tool-call results
(which aren't persisted in conversation history - see the note repeated
throughout agent.py/mortgage_agent.py/fraud_dispute_agent.py) threaded all
the way back up through every agent's return value.

A contextvar rather than a plain module-level variable, so this stays
correctly isolated per-request even when FastAPI dispatches concurrent sync
requests across threadpool workers - each request's call stack (verify
tool -> agent -> main.py, all on one worker thread) gets its own value."""

import contextvars

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("verified_customer_id", default=None)


def mark_verified(customer_id: str) -> None:
    _current.set(customer_id)


def get_and_clear() -> str | None:
    value = _current.get()
    _current.set(None)
    return value
