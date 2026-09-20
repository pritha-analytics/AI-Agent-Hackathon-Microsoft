import html
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (
    agent,
    audit,
    cs_client,
    db,
    forms_store,
    interaction_context,
    interaction_history,
    metrics,
    nba_engine,
    roles,
    verified_customer,
)
from .agent import compute_transition_progress, run_agent
from .plans import plans
from .sessions import sessions
from .topic_classifier import classify_topic
from .uploads import extract_text

CASE_ID_RE = re.compile(r"CASE-\d{6}")
# See the home-insurance branch below, right after case_id is computed.
HOME_INSURANCE_MENTION_RE = re.compile(r"home insurance|hemförsäkring|villaförsäkring", re.IGNORECASE)

# Next Best Action offers should only ever appear at the natural end of a
# conversation - when Sara asks a closing question like "anything else I
# can help with?" and the customer declines - never mid-conversation, even
# right after an identity check. See the offer-surfacing block in chat()
# below for how this pairs with db.verified_customer_id (set once, kept for
# the rest of the session, since verification and the closing moment are
# usually several turns apart).
CLOSING_QUESTION_RE = re.compile(
    r"anything else|any (?:other )?questions?|further questions?|"
    r"help (?:you )?with (?:anything|something) else|something else i can help|"
    r"(?:några|fler) frågor|något annat (?:jag|vi) kan hjälpa|hjälpa dig med något annat",
    re.IGNORECASE,
)
DECLINE_RE = re.compile(
    r"^\s*(?:"
    r"no\s*,?\s*(?:thanks?|thank you)?"
    r"|nope|nah"
    r"|that'?s (?:all|everything)|thats (?:all|everything)"
    r"|nothing else"
    r"|i'?m good|im good|i am good|we'?re (?:all )?good"
    r"|nej\s*(?:tack)?|inget (?:mer|annat)|det var allt|det räcker"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)


def _is_closing_decline(history: list[dict]) -> bool:
    """True when the customer's latest message declines a closing question
    Sara just asked (e.g. "anything else?" / "No thanks") - the one moment
    Next Best Action offers are allowed to appear."""
    if not history or history[-1].get("role") != "user":
        return False
    if not DECLINE_RE.match(history[-1].get("content", "")):
        return False
    prior_assistant = next(
        (m for m in reversed(history[:-1]) if m.get("role") == "assistant"), None
    )
    if not prior_assistant:
        return False
    # Only look near the end of Sara's reply - a long checklist reply can
    # mention "questions" or "anything else" mid-explanation for unrelated
    # reasons, but a genuine closing question is always the sign-off.
    tail = (prior_assistant.get("content") or "")[-200:]
    return bool(CLOSING_QUESTION_RE.search(tail))

app = FastAPI(title="Life Transition Navigator")
db.init_db()

# Lets the separate Customer Service (Java) app poll a session's transcript
# directly from its own browser page after picking up a chat hand-off - a
# different origin/port, demo-permissive like the CS app's own CORS config.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Without this, a browser can end up with an updated style.css/app.js
    but a stale cached index.html (or vice versa) after a frontend change -
    each file revalidates independently, so a page reload doesn't guarantee
    a *consistent* set. That mismatch is exactly what produced a real bug
    once: a leftover flex rule from new CSS applied to old HTML markup
    ballooned a button's height. `no-cache` forces every frontend file to
    revalidate with the server on each load (still fast via 304s - this
    doesn't disable caching, just the "trust it without asking" part), so
    the files in a page load are always from the same version."""
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    session_id: str | None = None
    lang: str | None = None


class HumanMessage(BaseModel):
    content: str
    agent_name: str | None = None


class CustomerMessage(BaseModel):
    content: str


class AssignAgent(BaseModel):
    agent_name: str


class RatingRequest(BaseModel):
    rating: int


class OfferClickRequest(BaseModel):
    customer_id: str
    offer_code: str


class SaveFormRequest(BaseModel):
    session_id: str
    title: str
    fields: list[dict]


class CreatePlanRequest(BaseModel):
    session_id: str
    event_type: str = "home_purchase"
    event_title: str = "My home purchase"
    key_date: str | None = None


class UpdateTaskRequest(BaseModel):
    status: str


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    history = [m.model_dump() for m in req.messages]
    verified_customer.get_and_clear()  # discard any stale value from an earlier request

    # Classified from the input history (never the reply, so this is safe
    # to compute before run_agent) and stashed in a contextvar so
    # llm_client.py's instrumented wrapper can attribute each LLM call this
    # turn makes to this topic/session - see interaction_context.py and the
    # AI Analytics dashboard's per-topic token trend (metrics.py).
    topic = classify_topic(history)
    interaction_context.set_context(topic, req.session_id)

    completed_plan_tasks: list[str] = []
    if req.session_id and history:
        completed_plan_tasks = plans.complete_explicitly_reported_tasks(
            req.session_id, history[-1]["content"]
        )
    reply, suggestions, extra = run_agent(
        history, lang=req.lang, plan_context=plans.context_for_session(req.session_id)
    )

    if req.session_id and history:
        sessions.add_message(req.session_id, "user", history[-1]["content"])
        sessions.add_message(req.session_id, "assistant", reply)

    case_match = CASE_ID_RE.search(reply)
    case_id = case_match.group(0) if case_match else None
    metrics.record_interaction(
        session_id=req.session_id, topic=topic, lang=req.lang,
        case_created=bool(case_match), case_id=case_id,
    )

    if req.session_id and case_id:
        # Documents are always attached BEFORE a case exists in every
        # current flow, so this is the first point case_id is known.
        db.link_session_documents_to_case(req.session_id, case_id)
        # Auto check-off: a just-created case answers one of the sidebar
        # checklist's own questions, so tick it without waiting for the
        # customer to separately say "I've done that" (see plans.mark_task_done).
        if topic in ("mortgage_loan_promise", "mortgage_loan_offer"):
            plans.mark_task_done(req.session_id, "mortgage")
        elif HOME_INSURANCE_MENTION_RE.search(reply):
            # No dedicated topic value exists for this (submit_insurance_application
            # in agent.py creates a generic "OTHER"-typed case, not classified by
            # topic_classifier.py the way the mortgage flows are), so this checks
            # the reply text itself for the product name alongside the fresh
            # case_id above, rather than a topic string that would never match.
            plans.mark_task_done(req.session_id, "home_insurance")

    if req.session_id and not plans.get_for_session(req.session_id) and agent.mentions_home_purchase(history):
        # Auto-create the home-purchase checklist the moment it's clearly
        # relevant, instead of requiring the sidebar's manual button (see
        # createHomePurchasePlan in app.js, kept as a harmless fallback).
        # The frontend's own loadPlan() call after every turn picks this up.
        plans.create(req.session_id, "home_purchase", "My home purchase", None)

    # Identity verification is recorded on every verified turn regardless of
    # whether NBA offers end up firing (see below) - it's what the NBA
    # engine's own learning data and the interaction-history panel need.
    customer_id = verified_customer.get_and_clear()
    if customer_id and req.session_id:
        db.set_chat_verified_customer(req.session_id, customer_id)
        db.record_interaction(customer_id, req.session_id, topic, case_id)
        sessions.set_verified_customer(req.session_id, customer_id)
        # Links this session's home-purchase plan (if any) to her customer
        # record, so a LATER chat where she verifies again finds the SAME
        # plan instead of starting blank - see plans.claim_for_customer.
        plans.claim_for_customer(req.session_id, customer_id)
        # Lets the chat widget open the interaction-history panel right on
        # the turn that verified the customer, without waiting for the next
        # message - independent of whether an NBA offer happens to fire.
        extra["verified_customer_id"] = customer_id

    # Next Best Action offers: the customer must have been identity-verified
    # at some point in this chat (this turn or an earlier one - see
    # db.verified_customer_id) AND the conversation must be at its closing
    # moment (Sara just asked "anything else?" and the customer declined -
    # see _is_closing_decline above). Never mid-conversation, even right
    # after a fresh identity check. Never for fraud/dispute topics either -
    # the customer is dealing with a security problem, not browsing
    # products, and `topic` stays "fraud_report"/"transaction_dispute" for
    # the whole flow (see fraud_dispute_agent.wants_fraud_or_dispute), not
    # just its first turn. Interaction history itself is still recorded on
    # every verified turn regardless, for the NBA engine's own learning data.
    verified_customer_id = db.get_chat_verified_customer(req.session_id) if req.session_id else None
    if (
        verified_customer_id
        and _is_closing_decline(history)
        and topic not in ("fraud_report", "transaction_dispute")
    ):
        offers = nba_engine.get_offers_for_customer(verified_customer_id, topic)
        if offers:
            extra["offers"] = offers
            extra["offers_customer_id"] = verified_customer_id

    return {
        "role": "assistant",
        "content": reply,
        "suggestions": suggestions,
        "plan_updates": completed_plan_tasks,
        **extra,
    }


@app.get("/api/plans/session/{session_id}")
def get_plan_for_session(session_id: str) -> dict:
    plan = plans.get_for_session(session_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No transition plan exists for this session")
    return plan


@app.post("/api/plans")
def create_plan(body: CreatePlanRequest) -> dict:
    try:
        return plans.create(body.session_id, body.event_type, body.event_title, body.key_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/plans/session/{session_id}/tasks/{task_id}")
def update_plan_task(session_id: str, task_id: str, body: UpdateTaskRequest) -> dict:
    try:
        return plans.update_task(session_id, task_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/offers/click")
def click_offer(body: OfferClickRequest) -> dict:
    ok = nba_engine.record_click(body.customer_id, body.offer_code)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Unknown offer_code '{body.offer_code}'")
    return {"ok": True}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), session_id: str | None = Form(None)) -> dict:
    filename = file.filename or "document"
    extension = Path(filename).suffix.lower()
    if extension and extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Please attach a PDF, Word, Excel, text, or image file.",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")
    text = extract_text(filename, data)
    if session_id:
        db.save_document(session_id, filename, file.content_type, text)
    return {"filename": filename, "text": text}


@app.post("/api/sessions/{session_id}/request-human")
def request_human(session_id: str) -> dict:
    sessions.request_human(session_id)

    session = sessions.get(session_id) or {}
    transcript = [
        {"role": m["role"], "content": m["content"]}
        for m in session.get("messages", [])
        if m["role"] in ("user", "assistant", "human")
    ]
    first_user_msg = next((m["content"] for m in transcript if m["role"] == "user"), "")
    customer_summary = first_user_msg[:80] if first_user_msg else "Customer chat"
    notified = cs_client.notify_chat_request(session_id, customer_summary, transcript)

    metrics.record_handoff(session_id, classify_topic(transcript))

    return {"ok": True, "cs_app_notified": notified}


@app.post("/api/sessions/{session_id}/rating")
def rate_session(session_id: str, body: RatingRequest) -> dict:
    """Customer satisfaction rating for the AI Hub dashboard - 1 to 5,
    submitted from the chat widget at any point in (or after) a conversation.
    Not required, not forced - just recorded if given."""
    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=422, detail="rating must be between 1 and 5")
    metrics.record_rating(session_id, body.rating)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/poll")
def poll_session(session_id: str, after: int = 0) -> dict:
    new_messages = sessions.messages_after(session_id, after)
    total = after + len(new_messages)
    all_messages = sessions.messages_after(session_id, 0)
    session = sessions.get(session_id) or {}
    return {
        "messages": new_messages,
        "next_after": total,
        "assigned_agent": session.get("assigned_agent"),
        "progress": compute_transition_progress(all_messages),
    }


@app.post("/api/sessions/{session_id}/customer-message")
def send_customer_message(session_id: str, body: CustomerMessage) -> dict:
    """Appends a customer message to a session that's already been handed
    off to a human - does NOT invoke the AI agent, unlike /api/chat."""
    count = sessions.add_message(session_id, "user", body.content)
    return {"ok": True, "message_count": count}


@app.post("/api/sessions/{session_id}/assign-agent")
def assign_agent(session_id: str, body: AssignAgent) -> dict:
    sessions.assign_agent(session_id, body.agent_name)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/interaction-history")
def get_interaction_history(session_id: str) -> dict:
    """The chat widget's left-panel mini-portfolio: what this customer has
    talked to Sara about, and how far each thing has gotten. Keyed by
    session_id, not a customer_id the client could pass directly - only a
    session that actually verified as a customer (via verify_customer_identity
    earlier in THIS chat) gets that customer's data back, so one browser
    tab can't fetch another customer's history by guessing an id."""
    customer_id = sessions.get_verified_customer(session_id)
    if not customer_id:
        return {"verified": False, "items": []}
    return {"verified": True, "customer_id": customer_id, "items": interaction_history.build_customer_history(customer_id)}


@app.get("/api/sessions/{session_id}/activity-summary")
def get_activity_summary(session_id: str) -> dict:
    """The sidebar's "Your Activity" panel - a summary view (chat count,
    case counts by status, top topics, top urgent cases), not the raw
    interaction list get_interaction_history above returns. Gated on
    identity verification the same way - see that endpoint's docstring."""
    customer_id = sessions.get_verified_customer(session_id)
    if not customer_id:
        return {"verified": False}
    return {"verified": True, "customer_id": customer_id, **interaction_history.build_activity_summary(customer_id)}


@app.get("/api/customers/{customer_id}/sessions")
def list_customer_sessions(customer_id: str, session_id: str) -> dict:
    """The sidebar's per-customer chat history (see item 4's "Chats" list) -
    gated the same way as interaction-history/activity-summary: the caller
    must pass a session_id that has ALREADY verified as this exact
    customer_id in THIS browser, so one customer can't list another's chats
    by guessing an id."""
    if sessions.get_verified_customer(session_id) != customer_id:
        return {"sessions": []}
    return {"sessions": db.list_chat_session_summaries_for_customer(customer_id)}


@app.get("/api/sessions")
def list_sessions() -> dict:
    return {"sessions": sessions.list_summaries()}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """Delete this demo's transient transcript and the transition plan linked to it."""
    session_deleted = sessions.delete(session_id)
    plan_deleted = plans.delete_for_session(session_id)
    return {"ok": True, "session_deleted": session_deleted, "plan_deleted": plan_deleted}


@app.post("/api/sessions/{session_id}/human-message")
def send_human_message(session_id: str, body: HumanMessage) -> dict:
    count = sessions.add_message(session_id, "human", body.content, agent_name=body.agent_name)
    return {"ok": True, "message_count": count}


# Metrics/summary keys that belong to each RBAC-gated dashboard section -
# see roles.py. /api/metrics/summary spans both sections in one payload
# (they're computed from the same event log in one pass), so the endpoint
# itself decides which keys to include rather than gating the whole call
# to a single section like the audit endpoints below do.
INTERACTIONS_SUMMARY_KEYS = {
    "interactions", "topics", "avg_session_duration_seconds",
    "handoffs", "cases_triggered", "satisfaction",
}
AI_ANALYTICS_SUMMARY_KEYS = {
    "tokens", "technical", "token_trend_by_topic", "satisfaction_latency_correlation",
}


@app.get("/api/metrics/summary")
def get_metrics_summary(days: int = 14, x_dashboard_role: str | None = Header(default=None)) -> dict:
    """Everything the AI Hub monitoring dashboard renders - interaction
    volumes, topics, handoffs, cases, satisfaction, and token consumption.
    RBAC (self-declared X-Dashboard-Role, same demo-scope caveat as
    cs-service's X-CS-Role): MANAGER sees the interactions section,
    AI_ENGINEER sees AI Analytics (technical/token data) - a role with
    access to neither gets a 403, not a trimmed-but-still-200 response."""
    role = roles.parse_role(x_dashboard_role)
    summary = metrics.build_summary(days=days)

    result = {"generated_at": summary["generated_at"]}
    if roles.can_access(role, "interactions"):
        result.update({k: v for k, v in summary.items() if k in INTERACTIONS_SUMMARY_KEYS})
    if roles.can_access(role, "ai_analytics"):
        result.update({k: v for k, v in summary.items() if k in AI_ANALYTICS_SUMMARY_KEYS})

    if len(result) == 1:
        raise HTTPException(status_code=403, detail=f"{role} is not authorized for any dashboard analytics section.")
    return result


@app.get("/api/audit/recent")
def get_recent_audit_events(limit: int = 50, x_dashboard_role: str | None = Header(default=None)) -> dict:
    """Concise, cross-customer feed of recent agent actions/decisions for
    the AI Hub dashboard's Audit History section. MANAGER and AUDITOR only."""
    roles.require_role(x_dashboard_role, "audit_trail")
    return {"events": audit.read_recent_events(limit=limit)}


@app.get("/api/audit/verify")
def verify_audit_chain() -> dict:
    """Recomputes the hash chain over the whole audit log and reports
    whether it's intact - the check an auditor would run first. Not
    RBAC-gated like /api/audit/recent above: it's also called (with no
    role header) by frontend/audit.js, the standalone per-customer audit
    viewer linked from a case in the separate CS Workspace app - that page
    has no AI Hub dashboard role to send, and the result carries no PII
    anyway (just a valid/entries/broken_at summary)."""
    return audit.verify_chain()


@app.get("/api/audit/{customer_id}")
def get_audit_trail(customer_id: str) -> dict:
    """Every logged agent decision for one customer_id, in order - the
    underlying data behind any mortgage/credit/document decision made about
    them. Not RBAC-gated (see verify_audit_chain above) - this is the same
    endpoint frontend/audit.js calls when a CS Workspace case's "View full
    decision history" link is opened, which never sends a dashboard role;
    scoping to one already-known customer_id is this endpoint's own access
    boundary, same as the cs-service case link it's reached from."""
    return {"customer_id": customer_id, "events": audit.read_events(customer_id)}


@app.post("/api/forms")
def create_form(body: SaveFormRequest) -> dict:
    form_id = forms_store.save_form(body.session_id, body.title, body.fields)
    return {"id": form_id, "url": f"/forms/{form_id}"}


@app.get("/api/forms")
def api_list_forms() -> dict:
    return {"forms": forms_store.list_forms()}


@app.get("/api/forms/{form_id}")
def api_get_form(form_id: str) -> dict:
    form = forms_store.get_form(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="Unknown form")
    return form


def _format_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _forms_list_page() -> str:
    forms = forms_store.list_forms()

    if forms:
        rows = "\n".join(
            f"""
            <tr>
                <td class="ts">{html.escape(_format_timestamp(f["created_at"]))}</td>
                <td class="id-cell"><a class="id-link" href="/forms/{html.escape(f["id"])}">{html.escape(f["id"])}</a></td>
                <td>{html.escape(f["title"])}</td>
                <td><a class="link" href="/forms/{html.escape(f["id"])}">Öppna &rarr;</a></td>
            </tr>
            """
            for f in forms
        )
        body = f"""
        <table>
            <thead>
                <tr><th>Datum</th><th>Form ID</th><th>Ansökan</th><th></th></tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """
    else:
        body = '<p class="empty">Inga ansökningar ännu</p>'

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>Inkomna ansökningar</title>
<style>
    body {{
        font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        background: #ffffff;
        color: #1f2937;
        margin: 0;
        padding: 40px;
    }}
    h1 {{
        color: #002f5f;
        margin-bottom: 4px;
    }}
    .subtitle {{
        color: #6b7280;
        font-size: 13px;
        margin-top: 0;
        margin-bottom: 32px;
    }}
    table {{
        width: 100%;
        max-width: 800px;
        border-collapse: collapse;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        overflow: hidden;
    }}
    th, td {{
        text-align: left;
        padding: 14px 16px;
        border-bottom: 1px solid #e5e7eb;
    }}
    th {{
        color: #6b7280;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        background: #f9fafb;
    }}
    tr:last-child td {{
        border-bottom: none;
    }}
    .ts {{
        color: #6b7280;
        font-size: 13px;
        white-space: nowrap;
    }}
    .id-cell {{
        font-family: ui-monospace, Menlo, Consolas, monospace;
        font-size: 13px;
    }}
    .id-link {{
        color: #6b7280;
        text-decoration: none;
    }}
    .id-link:hover {{
        text-decoration: underline;
    }}
    .link {{
        color: #002f5f;
        text-decoration: none;
        font-weight: 600;
    }}
    .link:hover {{
        text-decoration: underline;
    }}
    .empty {{
        color: #6b7280;
        max-width: 800px;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 32px;
        text-align: center;
    }}
</style>
</head>
<body>
    <h1>Inkomna ansökningar</h1>
    <p class="subtitle">Submitted applications</p>
    {body}
</body>
</html>"""


def _form_detail_page(form: dict) -> str:
    fields_html = "\n".join(
        f"""
        <div class="field">
            <div class="field-label">{html.escape(str(field.get("label", "")))}</div>
            <div class="field-value">{html.escape(str(field.get("value", "")))}</div>
        </div>
        """
        for field in form.get("fields", [])
    )

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>{html.escape(form["title"])}</title>
<style>
    body {{
        font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
        background: #ffffff;
        color: #1f2937;
        margin: 0;
        padding: 40px;
    }}
    .page {{
        max-width: 640px;
        margin: 0 auto;
    }}
    .top-row {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
    }}
    .eyebrow {{
        color: #6b7280;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin: 0 0 4px 0;
    }}
    h2 {{
        color: #002f5f;
        margin: 0 0 24px 0;
    }}
    .print-btn {{
        background: #ffffff;
        color: #002f5f;
        border: 1px solid #002f5f;
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        font-family: inherit;
    }}
    .print-btn:hover {{
        background: #f0f4f8;
    }}
    .field {{
        margin-bottom: 18px;
    }}
    .field-label {{
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.02em;
        color: #6b7280;
        margin-bottom: 6px;
    }}
    .field-value {{
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        background: #f9fafb;
        padding: 10px 12px;
        color: #1f2937;
        min-height: 1.2em;
    }}
    .meta {{
        margin-top: 32px;
        padding-top: 16px;
        border-top: 1px solid #e5e7eb;
        color: #9ca3af;
        font-size: 12px;
    }}
    @media print {{
        .print-btn {{ display: none; }}
    }}
</style>
</head>
<body>
    <div class="page">
        <div class="top-row">
            <p class="eyebrow">LF Bergslagen &mdash; Inkommen ansökan</p>
            <button class="print-btn" onclick="window.print()">Skriv ut</button>
        </div>
        <h2>{html.escape(form["title"])}</h2>
        {fields_html}
        <div class="meta">
            Form ID: {html.escape(form["id"])} &middot; Created at: {html.escape(form["created_at"])}
        </div>
    </div>
</body>
</html>"""


@app.get("/forms", response_class=HTMLResponse)
def forms_list_page() -> str:
    return _forms_list_page()


@app.get("/forms/{form_id}", response_class=HTMLResponse)
def form_detail_page(form_id: str) -> str:
    form = forms_store.get_form(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail="Unknown form")
    return _form_detail_page(form)


class OfferTierRulesRequest(BaseModel):
    offer_code: str
    tiers: list[str]


class CooldownRequest(BaseModel):
    cooldown_seconds: int


@app.get("/api/contact-rules")
def get_contact_rules(x_dashboard_role: str | None = Header(default=None)) -> dict:
    """Everything the Marketing team's Contact Rules panel edits: the
    offer-click cooldown, and each offer's current tier targeting. MARKETING
    role only - see roles.py and nba_engine.get_offers_for_customer for
    where these settings actually take effect."""
    roles.require_role(x_dashboard_role, "contact_rules")
    return {
        "cooldown_seconds": db.get_cooldown_seconds(),
        "valid_tiers": nba_engine.VALID_TIERS,
        "offers": nba_engine.list_offers_for_admin(),
    }


@app.post("/api/contact-rules/cooldown")
def set_contact_rules_cooldown(body: CooldownRequest, x_dashboard_role: str | None = Header(default=None)) -> dict:
    roles.require_role(x_dashboard_role, "contact_rules")
    if body.cooldown_seconds < 0 or body.cooldown_seconds > 86400:
        raise HTTPException(status_code=422, detail="cooldown_seconds must be between 0 and 86400 (24h).")
    db.set_cooldown_seconds(body.cooldown_seconds)
    return {"ok": True, "cooldown_seconds": body.cooldown_seconds}


@app.post("/api/contact-rules/offer-tiers")
def set_contact_rules_offer_tiers(body: OfferTierRulesRequest, x_dashboard_role: str | None = Header(default=None)) -> dict:
    roles.require_role(x_dashboard_role, "contact_rules")
    if body.offer_code not in nba_engine._BY_CODE:
        raise HTTPException(status_code=404, detail=f"Unknown offer_code '{body.offer_code}'.")
    unknown_tiers = set(body.tiers) - set(nba_engine.VALID_TIERS)
    if unknown_tiers:
        raise HTTPException(status_code=422, detail=f"Unknown tier(s): {', '.join(sorted(unknown_tiers))}.")
    db.set_offer_tier_restrictions(body.offer_code, body.tiers)
    return {"ok": True, "offer_code": body.offer_code, "tiers": body.tiers}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
