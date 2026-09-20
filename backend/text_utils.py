"""Small text helpers shared across agents - kept dependency-free (no
imports from any agent module) so every agent can use it without risking a
circular import."""

import re

# Mirrors the frontend's own attachment-splitting regex (see
# parseUserMessageContent in app.js) so both sides agree on where one
# attachment block ends and the next begins.
_ATTACHMENT_BLOCK_RE = re.compile(
    r"\[Attached (?:document|file):\s*.*?\]\n\n.*?(?=\n\n\[Attached (?:document|file):|\Z)",
    re.DOTALL,
)


def strip_attachments(text: str) -> str:
    """Remove attached-document blocks from a composed chat message, leaving
    only what the customer actually typed. A document's own text (a
    payslip's footer boilerplate, an expense summary's fine print) is
    content the customer didn't write and chose to attach, not something
    they said - it shouldn't be able to trigger intent-keyword matches like
    wants_human_contact just because it happens to contain a phrase like
    "a representative" or "customer service"."""
    return _ATTACHMENT_BLOCK_RE.sub("", text or "").strip()


_ATTACHMENT_MARKER_RE = re.compile(r"\[Attached (?:document|file):")


def has_attachment(history: list[dict]) -> bool:
    """True if any user message anywhere in the conversation carries an
    attached document - used to gate document-aware behaviour (reading,
    summarising, filling a form from it) behind identity verification, so a
    document's contents can never be inspected before the customer has
    proven who they are."""
    return any(
        m.get("role") == "user" and _ATTACHMENT_MARKER_RE.search(m.get("content") or "")
        for m in history
    )
