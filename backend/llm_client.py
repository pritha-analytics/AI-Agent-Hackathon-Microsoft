"""Shared OpenAI client, split out from agent.py so the specialist agents
(document_agent, credit_agent, mortgage_agent) can use it without importing
agent.py itself and creating a circular import."""

import time

from openai import OpenAI

from . import config, interaction_context, metrics

client = OpenAI(api_key=config.OPENROUTER_API_KEY, base_url=config.OPENROUTER_BASE_URL)

# Every agent in this app calls client.chat.completions.create the same way
# (imported from here), so wrapping it once here logs token usage for the
# AI Hub dashboard's token-consumption metrics without touching every call
# site individually - see metrics.py.
_original_create = client.chat.completions.create


def _instrumented_create(*args, **kwargs):
    start = time.monotonic()
    response = _original_create(*args, **kwargs)
    duration_ms = (time.monotonic() - start) * 1000
    usage = getattr(response, "usage", None)
    ctx = interaction_context.get_context()
    metrics.record_llm_usage(
        model=kwargs.get("model"),
        prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
        total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        duration_ms=duration_ms,
        topic=ctx.get("topic"),
        session_id=ctx.get("session_id"),
    )
    return response


client.chat.completions.create = _instrumented_create
