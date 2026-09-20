"""Shared quick-reply suggestion generator, used by both Sara and the
Mortgage Agent so the two don't drift into different quality bars. Grounds
suggestions in the actual conversation (both the customer's last message
and the assistant's reply) rather than the reply alone, and pushes hard
against generic filler - the earlier version tended to produce vague
options like "Tell me more" that don't reflect what was actually said."""

import json
import re

from . import config
from .llm_client import client

SUGGESTIONS_JSON_RE = re.compile(r"\[.*\]", re.DOTALL)

PROMPT_TEMPLATE = """You generate quick-reply suggestion chips for a chat UI.
Below is the customer's last message and the assistant's reply to it.
Suggest exactly 3 short follow-up messages (max 6 words each) the CUSTOMER
could tap to continue the conversation, written in the same language as the
reply, from the customer's point of view.

Ground every suggestion in something SPECIFIC the reply actually said - a
number, a named document, a specific option offered, a question it asked, a
case ID, a named choice. Never fall back to generic filler like "Tell me
more" or "What's next?" unless the reply truly gives nothing concrete to
react to.

If the reply explicitly offers the customer a choice between named options
(e.g. call vs. chat, which transaction, a numbered list of items), your 3
suggestions should mostly BE those exact choices, phrased as the customer
would tap them - not vague reactions to having been given a choice.

If the reply is asking the customer to ATTACH or UPLOAD a document, never
suggest the action itself (e.g. "Attach income statement") - tapping a chip
only sends text, it cannot open a file picker or attach anything, so that
chip would be a dead end. Instead suggest clarifying questions the customer
might actually have about the request - e.g. what counts as that document,
where to get it, what format is accepted, or what to do if they don't have
it - grounded in the specific document(s) named in the reply.

The reply may cite Swedish product names or markdown links whose visible
label text is itself in Swedish (e.g. "Lånelöfte", "[Se ditt pris på
hemförsäkring](url)") even while the reply's own surrounding sentences are
in English - that's intentional, real terminology, not a language switch.
When grounding a suggestion in one of these, write the suggestion as a
normal sentence in the SAME language the reply's prose is in, keeping only
the Swedish product name/proper noun inline where natural (e.g. "Apply for
a Lånelöfte" is correct in an English conversation) - never copy a Swedish
link label or sentence wholesale as the entire suggestion.

"Written in the same language as the reply" means the language the reply's
OWN sentences are written in, not the language of a product name or a link
label quoted within it.

Customer's last message:
{last_user_message}

Assistant's reply:
{reply}

Return ONLY a JSON array of 3 strings, nothing else - no markdown, no
explanation.
"""


def generate_suggestions(last_user_message: str, reply: str) -> list[str]:
    prompt = PROMPT_TEMPLATE.format(
        last_user_message=(last_user_message or "").strip() or "(none - this is the first message)",
        reply=reply,
    )
    try:
        response = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=150,
        )
        content = response.choices[0].message.content or "[]"
        match = SUGGESTIONS_JSON_RE.search(content)
        data = json.loads(match.group(0) if match else content)
        return [str(item).strip() for item in data if str(item).strip()][:3]
    except Exception:
        return []
