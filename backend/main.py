import html
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit, cs_client, forms_store, metrics
from .agent import run_agent
from .sessions import sessions
from .topic_classifier import classify_topic
from .uploads import extract_text

CASE_ID_RE = re.compile(r"CASE-\d{6}")

app = FastAPI(title="Life Transition Navigator")

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


class SaveFormRequest(BaseModel):
    session_id: str
    title: str
    fields: list[dict]


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    history = [m.model_dump() for m in req.messages]
    reply, suggestions, extra = run_agent(history, lang=req.lang)

    if req.session_id and history:
        sessions.add_message(req.session_id, "user", history[-1]["content"])
        sessions.add_message(req.session_id, "assistant", reply)

    case_match = CASE_ID_RE.search(reply)
    metrics.record_interaction(
        session_id=req.session_id,
        topic=classify_topic(history),
        lang=req.lang,
        case_created=bool(case_match),
        case_id=case_match.group(0) if case_match else None,
    )

    return {"role": "assistant", "content": reply, "suggestions": suggestions, **extra}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
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
    session = sessions.get(session_id) or {}
    return {
        "messages": new_messages,
        "next_after": total,
        "assigned_agent": session.get("assigned_agent"),
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


@app.get("/api/sessions")
def list_sessions() -> dict:
    return {"sessions": sessions.list_summaries()}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session


@app.post("/api/sessions/{session_id}/human-message")
def send_human_message(session_id: str, body: HumanMessage) -> dict:
    count = sessions.add_message(session_id, "human", body.content, agent_name=body.agent_name)
    return {"ok": True, "message_count": count}


@app.get("/api/metrics/summary")
def get_metrics_summary(days: int = 14) -> dict:
    """Everything the AI Hub monitoring dashboard renders - interaction
    volumes, topics, handoffs, cases, satisfaction, and token consumption.
    Demo-only: a real deployment would put real access control (internal
    AI Hub staff only) in front of this endpoint, same caveat as /api/audit."""
    return metrics.build_summary(days=days)


@app.get("/api/audit/verify")
def verify_audit_chain() -> dict:
    """Recomputes the hash chain over the whole audit log and reports
    whether it's intact - the check an auditor would run first."""
    return audit.verify_chain()


@app.get("/api/audit/{customer_id}")
def get_audit_trail(customer_id: str) -> dict:
    """Every logged agent decision for one customer_id, in order - the
    underlying data behind any mortgage/credit/document decision made about
    them. Demo-only: a real deployment would put real access control (only
    auditors/compliance, not any caller) in front of this endpoint."""
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
                <td>{html.escape(f["title"])}</td>
                <td><a class="link" href="/forms/{html.escape(f["id"])}">Öppna &rarr;</a></td>
            </tr>
            """
            for f in forms
        )
        body = f"""
        <table>
            <thead>
                <tr><th>Datum</th><th>Ansökan</th><th></th></tr>
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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
