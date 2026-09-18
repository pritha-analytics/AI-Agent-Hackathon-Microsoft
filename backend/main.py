from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit, cs_client
from .agent import run_agent
from .plans import plans
from .sessions import sessions
from .uploads import extract_text

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
async def prevent_stale_frontend_assets(request: Request, call_next):
    """A single-page demo can otherwise keep an old app.js after a backend restart."""
    response = await call_next(request)
    if request.url.path in {"/", "/index.html", "/app.js", "/style.css"}:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
    completed_plan_tasks = []
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

    return {"ok": True, "cs_app_notified": notified}


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


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
