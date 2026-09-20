"""Centralized, shared storage for customer interaction history and Next
Best Action (offer impression/click) data - see nba_engine.py.

This is deliberately NOT the same store as sessions.py (in-memory chat
transcripts, resets on restart) or metrics.py/audit.py (anonymized JSONL
files, local to whoever's machine runs the app). Those work fine for their
own purposes, but the NBA engine needs something that (a) survives a
restart and (b) is shared across everyone running this app - two people
running it on their own laptops should see the SAME customer history and
the SAME learned offer performance, not two separate copies.

Configured via the DATABASE_URL env var (see config.py) - point it at a
shared, hosted Postgres instance (a free Neon/Supabase/Railway project all
work fine with plain SQLAlchemy) so this is genuinely centralized. Falls
back to a local SQLite file if unset, so the app still runs standalone
without any setup - see the README note this module's docstring is paired
with for the recommended hosted option and why.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


class CustomerInteraction(Base):
    """One row per /api/chat turn where the customer was identity-verified
    - the "previous interactions" and "latest interaction" history the NBA
    engine reads to decide which offers are relevant to this customer."""

    __tablename__ = "customer_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(32), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    topic = Column(String(64), nullable=False)
    case_id = Column(String(32), nullable=True)
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class OfferStat(Base):
    """Thompson-sampling (Beta-Bernoulli) parameters for one (segment,
    offer) pair - the "adaptive ML model" the NBA engine samples from to
    rank offers, and updates as impressions resolve/clicks arrive. Global
    across customers rather than per-customer: at the data volume a handful
    of demo customers can generate, per-customer bandit state would never
    accumulate enough signal to mean anything, whereas segment-level state
    reflects everyone's behaviour in that context - the standard scoping
    choice for a cold-start recommender."""

    __tablename__ = "offer_stats"

    segment = Column(String(64), primary_key=True)
    offer_code = Column(String(64), primary_key=True)
    alpha = Column(Float, nullable=False, default=1.0)
    beta = Column(Float, nullable=False, default=1.0)


class ContactRuleSettings(Base):
    """Marketing-editable Contact Rules that used to be hardcoded constants
    in nba_engine.py - a singleton row (id=1) so every process reads the
    SAME live settings from the shared database instead of whatever value
    was baked in at import time on whichever machine happens to be running.
    See /api/contact-rules in main.py (MARKETING role only)."""

    __tablename__ = "contact_rule_settings"

    id = Column(Integer, primary_key=True)
    offer_click_cooldown_seconds = Column(Integer, nullable=False, default=120)


class OfferTierRestriction(Base):
    """Presence of a (offer_code, tier) row means that offer IS eligible
    for that customer tier. An offer with NO rows at all is eligible for
    every tier (the default, unrestricted, backward-compatible state) -
    see nba_engine.get_offers_for_customer."""

    __tablename__ = "offer_tier_restrictions"

    offer_code = Column(String(64), primary_key=True)
    tier = Column(String(32), primary_key=True)


class OfferEvent(Base):
    """An impression or a click, per customer per offer - the raw feedback
    log the bandit's alpha/beta updates are derived from, and itself useful
    for reporting (e.g. "which offers actually get clicked")."""

    __tablename__ = "offer_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(32), nullable=False, index=True)
    offer_code = Column(String(64), nullable=False)
    segment = Column(String(64), nullable=False)
    event_type = Column(String(16), nullable=False)  # "impression" | "click"
    resolved = Column(Boolean, nullable=False, default=False)  # impressions only
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ChatSession(Base):
    """One row per chat widget session - see sessions.py, which used to keep
    this purely in-memory (wiped on every server restart, including a dev
    `--reload`). Persisting it here means a customer's chat, and an agent's
    in-progress hand-off, survives a restart instead of silently 404ing the
    next time the sidebar tries to reopen it."""

    __tablename__ = "chat_sessions"

    session_id = Column(String(64), primary_key=True)
    needs_human = Column(Boolean, nullable=False, default=False)
    assigned_agent = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    # Set once this chat's customer has been identity-verified (any flow) -
    # kept for the rest of the session so Next Best Action offers can be
    # shown later, at the natural end of the conversation, without needing
    # the customer to re-verify right at that moment. See main.py's
    # closing-question gate around nba_engine.get_offers_for_customer.
    verified_customer_id = Column(String(32), nullable=True)
    # Set once, from the first user message in the chat (see
    # set_chat_title_if_unset) - lets the sidebar list a customer's past
    # chats by title straight from the server instead of depending on each
    # browser's own localStorage copy (see list_chat_session_summaries_for_customer).
    title = Column(String(200), nullable=True)


class ChatMessage(Base):
    """One row per message in a chat session (user/assistant/human) - see
    ChatSession above."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    agent_name = Column(String(128), nullable=True)
    ts = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Document(Base):
    """One row per document a customer attaches to the chat - see
    /api/upload in main.py. Linked to the session it was attached in, to the
    customer if that session had already verified identity at upload time,
    and to a case_id once one exists in that same session (see
    link_session_documents_to_case - documents are always attached before a
    case is created in every current flow, so this is filled in
    retroactively rather than known at upload time)."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(32), nullable=True, index=True)
    case_id = Column(String(32), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    extracted_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TransitionPlan(Base):
    """A customer's life-transition checklist (e.g. home purchase) - see
    plans.py. Keyed by the session_id it was created in (transition plans
    can start before identity verification - see agent.mentions_home_purchase),
    with an optional customer_id stamped in once that session verifies (see
    plans.claim_for_customer) so the SAME plan is found again from a later,
    different session for the same customer instead of starting blank."""

    __tablename__ = "transition_plans"

    plan_id = Column(String(24), primary_key=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    customer_id = Column(String(32), nullable=True, index=True)
    event_type = Column(String(32), nullable=False)
    event_title = Column(String(200), nullable=False)
    key_date = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TransitionPlanTask(Base):
    """One checklist task within a TransitionPlan - see plan_templates.py
    for the fixed task definitions a plan is seeded from."""

    __tablename__ = "transition_plan_tasks"

    plan_id = Column(String(24), ForeignKey("transition_plans.plan_id"), primary_key=True)
    task_id = Column(String(32), primary_key=True)
    # Position within plan_templates.py's task list - task_id itself sorts
    # alphabetically, which scrambled the intended First Week / Secure
    # Mortgage / etc. sequence (e.g. "condominium_add_on" < "mortgage").
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    phase = Column(String(32), nullable=False)
    priority = Column(String(16), nullable=False)
    owner = Column(String(32), nullable=False)
    due_offset_days = Column(Integer, nullable=False)
    due_date = Column(String(10), nullable=True)
    status = Column(String(16), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def _local_sqlite_url() -> str:
    return "sqlite:///" + str(Path(__file__).resolve().parent / "nba.db")


def _make_engine(database_url: str):
    connect_args = {}
    if database_url.startswith(("postgresql://", "postgresql+")):
        # Keep a bad/unreachable hosted DB from blocking the whole API startup.
        connect_args["connect_timeout"] = 3
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


_engine = _make_engine(config.DATABASE_URL)
_SessionLocal = sessionmaker(bind=_engine)


def init_db() -> None:
    global _engine, _SessionLocal
    try:
        Base.metadata.create_all(_engine)
    except SQLAlchemyError:
        if config.DATABASE_URL.startswith("sqlite:///"):
            raise
        fallback_url = _local_sqlite_url()
        _engine = _make_engine(fallback_url)
        _SessionLocal.configure(bind=_engine)
        Base.metadata.create_all(_engine)

    # create_all only creates missing TABLES, not missing columns on a table
    # that already existed from before verified_customer_id was added here -
    # patch it in for anyone with an existing local chat_sessions.db.
    inspector = inspect(_engine)
    if "chat_sessions" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("chat_sessions")}
        if "verified_customer_id" not in existing_columns:
            with _engine.begin() as conn:
                conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN verified_customer_id VARCHAR(32)"))
        if "title" not in existing_columns:
            with _engine.begin() as conn:
                conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN title VARCHAR(200)"))
    if "transition_plan_tasks" in inspector.get_table_names():
        existing_task_columns = {col["name"] for col in inspector.get_columns("transition_plan_tasks")}
        if "sort_order" not in existing_task_columns:
            with _engine.begin() as conn:
                conn.execute(text("ALTER TABLE transition_plan_tasks ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))


def _session() -> Session:
    return _SessionLocal()


def record_interaction(
    customer_id: str, session_id: str | None, topic: str, case_id: str | None
) -> None:
    with _session() as db:
        db.add(CustomerInteraction(
            customer_id=customer_id, session_id=session_id, topic=topic, case_id=case_id,
        ))
        db.commit()


def get_customer_topics(customer_id: str, lookback_days: int = 180) -> set[str]:
    """Every topic this customer has engaged with recently - the "previous
    interactions" half of the NBA eligibility check."""
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    with _session() as db:
        rows = (
            db.query(CustomerInteraction.topic)
            .filter(CustomerInteraction.customer_id == customer_id, CustomerInteraction.ts >= since)
            .distinct()
            .all()
        )
        return {r[0] for r in rows}


def get_customer_interactions(customer_id: str, limit: int = 25) -> list[dict]:
    """Most recent interactions for one customer - the raw material for the
    chat widget's interaction-history panel (see interaction_history.py),
    which turns this into a customer-friendly mini-portfolio view."""
    with _session() as db:
        rows = (
            db.query(CustomerInteraction)
            .filter(CustomerInteraction.customer_id == customer_id)
            .order_by(CustomerInteraction.ts.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "topic": r.topic,
                "case_id": r.case_id,
                "session_id": r.session_id,
                "ts": r.ts,
            }
            for r in rows
        ]


def get_recently_clicked_offer_codes(customer_id: str, within_seconds: int = 120) -> set[str]:
    """Offer codes this customer clicked within the last `within_seconds` -
    used to suppress re-showing the exact same offer right after they just
    clicked it (e.g. they open a new chat a minute later). A short, fixed
    cooldown rather than a permanent "never show again": the click is a
    positive signal (already counted via alpha in offer_stats), not a
    request to stop seeing it forever."""
    since = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    with _session() as db:
        rows = (
            db.query(OfferEvent.offer_code)
            .filter(
                OfferEvent.customer_id == customer_id,
                OfferEvent.event_type == "click",
                OfferEvent.ts >= since,
            )
            .distinct()
            .all()
        )
        return {r[0] for r in rows}


def get_or_create_offer_stat(db: Session, segment: str, offer_code: str) -> OfferStat:
    stat = db.get(OfferStat, {"segment": segment, "offer_code": offer_code})
    if stat is None:
        stat = OfferStat(segment=segment, offer_code=offer_code, alpha=1.0, beta=1.0)
        db.add(stat)
        db.flush()
    return stat


def resolve_stale_impressions(customer_id: str) -> None:
    """An offer impression that's still unresolved by the time this
    customer is shown offers again (i.e. they didn't click it in between)
    counts as a "not clicked" signal - increment that (segment, offer)
    pair's beta and mark it resolved so it's never counted twice."""
    with _session() as db:
        stale = (
            db.query(OfferEvent)
            .filter(
                OfferEvent.customer_id == customer_id,
                OfferEvent.event_type == "impression",
                OfferEvent.resolved.is_(False),
            )
            .all()
        )
        for event in stale:
            stat = get_or_create_offer_stat(db, event.segment, event.offer_code)
            stat.beta += 1.0
            event.resolved = True
        db.commit()


def record_offer_impression(customer_id: str, segment: str, offer_code: str) -> None:
    with _session() as db:
        db.add(OfferEvent(
            customer_id=customer_id, offer_code=offer_code, segment=segment,
            event_type="impression", resolved=False,
        ))
        db.commit()


def record_offer_click(customer_id: str, offer_code: str) -> str | None:
    """Marks the most recent unresolved impression of this offer for this
    customer as a click (alpha += 1), so the bandit gets a strong positive
    signal. Returns the segment it was shown under, if found."""
    with _session() as db:
        impression = (
            db.query(OfferEvent)
            .filter(
                OfferEvent.customer_id == customer_id,
                OfferEvent.offer_code == offer_code,
                OfferEvent.event_type == "impression",
                OfferEvent.resolved.is_(False),
            )
            .order_by(OfferEvent.ts.desc())
            .first()
        )
        segment = impression.segment if impression else "general"

        if impression:
            impression.resolved = True
            stat = get_or_create_offer_stat(db, segment, offer_code)
            stat.alpha += 1.0

        db.add(OfferEvent(
            customer_id=customer_id, offer_code=offer_code, segment=segment,
            event_type="click", resolved=True,
        ))
        db.commit()
        return segment


def sample_offer_score(segment: str, offer_code: str) -> float:
    """One Thompson-sampling draw for this (segment, offer) pair - the
    "adaptive" part of the model: pairs with more clicks relative to
    impressions get a higher expected score and win more often over time,
    while still leaving room for less-proven offers to occasionally surface
    (exploration), rather than freezing onto whatever looked best early on."""
    import random

    with _session() as db:
        stat = get_or_create_offer_stat(db, segment, offer_code)
        db.commit()
        return random.betavariate(stat.alpha, stat.beta)


# --- Chat session persistence (see ChatSession/ChatMessage above) ----------

def _message_to_dict(message: ChatMessage) -> dict:
    result = {"role": message.role, "content": message.content, "ts": message.ts.isoformat()}
    if message.agent_name:
        result["agent_name"] = message.agent_name
    return result


def _ensure_chat_session(db: Session, session_id: str) -> ChatSession:
    row = db.get(ChatSession, session_id)
    if row is None:
        row = ChatSession(session_id=session_id)
        db.add(row)
        db.flush()
    return row


def get_or_create_chat_session(session_id: str) -> dict:
    with _session() as db:
        row = _ensure_chat_session(db, session_id)
        db.commit()
        return {"messages": [], "needs_human": row.needs_human, "assigned_agent": row.assigned_agent}


def add_chat_message(session_id: str, role: str, content: str, agent_name: str | None = None) -> int:
    with _session() as db:
        _ensure_chat_session(db, session_id)
        db.add(ChatMessage(session_id=session_id, role=role, content=content, agent_name=agent_name))
        db.commit()
        return db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()


def set_chat_needs_human(session_id: str) -> None:
    with _session() as db:
        row = _ensure_chat_session(db, session_id)
        row.needs_human = True
        db.commit()


def set_chat_assigned_agent(session_id: str, agent_name: str) -> None:
    with _session() as db:
        row = _ensure_chat_session(db, session_id)
        row.assigned_agent = agent_name
        db.commit()


def set_chat_verified_customer(session_id: str, customer_id: str) -> None:
    with _session() as db:
        row = _ensure_chat_session(db, session_id)
        row.verified_customer_id = customer_id
        db.commit()


def get_chat_verified_customer(session_id: str) -> str | None:
    with _session() as db:
        row = db.get(ChatSession, session_id)
        return row.verified_customer_id if row else None


def set_chat_title_if_unset(session_id: str, title: str) -> None:
    """Called once, from this chat's first user message (see sessions.py) -
    a later call is a no-op, same as the client's own title-derivation logic
    (frontend/app.js's upsertChatListEntry) it mirrors."""
    with _session() as db:
        row = _ensure_chat_session(db, session_id)
        if not row.title:
            row.title = title[:200]
            db.commit()


def get_chat_messages_after(session_id: str, after: int) -> list[dict]:
    with _session() as db:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all()
        )
        return [_message_to_dict(m) for m in messages[after:]]


def get_chat_session(session_id: str) -> dict | None:
    with _session() as db:
        row = db.get(ChatSession, session_id)
        if row is None:
            return None
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all()
        )
        return {
            "messages": [_message_to_dict(m) for m in messages],
            "needs_human": row.needs_human,
            "assigned_agent": row.assigned_agent,
        }


def delete_chat_session(session_id: str) -> bool:
    """Remove a chat's transcript (and its session row) entirely - used by the
    sidebar's delete-chat option. Messages are removed first since they
    reference the session row via a foreign key."""
    with _session() as db:
        row = db.get(ChatSession, session_id)
        if row is None:
            return False
        db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
        db.delete(row)
        db.commit()
        return True


def list_chat_session_summaries() -> list[dict]:
    with _session() as db:
        summaries = []
        for row in db.query(ChatSession).all():
            last = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == row.session_id)
                .order_by(ChatMessage.id.desc())
                .first()
            )
            count = db.query(ChatMessage).filter(ChatMessage.session_id == row.session_id).count()
            summaries.append({
                "session_id": row.session_id,
                "needs_human": row.needs_human,
                "message_count": count,
                "last_message": last.content[:120] if last else "",
                "last_ts": last.ts.isoformat() if last else "",
            })
        summaries.sort(key=lambda s: s["last_ts"], reverse=True)
        return summaries


def list_chat_session_summaries_for_customer(customer_id: str) -> list[dict]:
    """Same shape as list_chat_session_summaries, scoped to one customer's
    verified chats - the sidebar's per-customer "Chats" history (see
    GET /api/customers/{customer_id}/sessions in main.py), as opposed to
    list_chat_session_summaries's unfiltered, CS-dashboard-only listing."""
    with _session() as db:
        summaries = []
        rows = db.query(ChatSession).filter(ChatSession.verified_customer_id == customer_id).all()
        for row in rows:
            last = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == row.session_id)
                .order_by(ChatMessage.id.desc())
                .first()
            )
            if last is None:
                continue
            summaries.append({
                "session_id": row.session_id,
                "title": row.title or (last.content[:60] if last else "Chat"),
                "last_message": last.content[:120],
                "last_ts": last.ts.isoformat(),
            })
        summaries.sort(key=lambda s: s["last_ts"], reverse=True)
        return summaries


def count_verified_chat_sessions(customer_id: str) -> int:
    with _session() as db:
        return db.query(ChatSession).filter(ChatSession.verified_customer_id == customer_id).count()


# --- Documents (see Document above, and /api/upload in main.py) -----------

def save_document(session_id: str, filename: str, content_type: str | None, extracted_text: str) -> int:
    customer_id = get_chat_verified_customer(session_id)
    with _session() as db:
        doc = Document(
            session_id=session_id, customer_id=customer_id, filename=filename,
            content_type=content_type, extracted_text=extracted_text,
        )
        db.add(doc)
        db.commit()
        return doc.id


def link_session_documents_to_case(session_id: str, case_id: str) -> None:
    """Backfills case_id onto this session's documents that don't have one
    yet - every current flow (Loan Promise/Loan Offer/fraud-dispute) attaches
    documents BEFORE a case exists, so this is only ever known after the
    fact, right when /api/chat sees a fresh CASE-###### in the reply."""
    with _session() as db:
        db.query(Document).filter(
            Document.session_id == session_id, Document.case_id.is_(None)
        ).update({"case_id": case_id})
        db.commit()


# --- Transition plans (see TransitionPlan/TransitionPlanTask above, and
# plans.py, which owns the business logic - task templates, completion
# phrase matching - on top of this plain persistence) ----------------------

def _plan_to_dict(row: TransitionPlan, tasks: list[TransitionPlanTask]) -> dict:
    return {
        "plan_id": row.plan_id,
        "session_id": row.session_id,
        "customer_id": row.customer_id,
        "event_type": row.event_type,
        "event_title": row.event_title,
        "key_date": row.key_date,
        "tasks": [
            {
                "id": t.task_id,
                "task_id": t.task_id,
                "title": t.title,
                "description": t.description,
                "phase": t.phase,
                "priority": t.priority,
                "owner": t.owner,
                "due_date": t.due_date,
                "status": t.status,
            }
            for t in tasks
        ],
    }


def get_transition_plan_by_session(session_id: str) -> dict | None:
    with _session() as db:
        row = db.query(TransitionPlan).filter(TransitionPlan.session_id == session_id).first()
        if row is None:
            return None
        tasks = (
            db.query(TransitionPlanTask)
            .filter(TransitionPlanTask.plan_id == row.plan_id)
            .order_by(TransitionPlanTask.sort_order)
            .all()
        )
        return _plan_to_dict(row, tasks)


def get_transition_plan_by_customer(customer_id: str) -> dict | None:
    with _session() as db:
        row = (
            db.query(TransitionPlan)
            .filter(TransitionPlan.customer_id == customer_id)
            .order_by(TransitionPlan.updated_at.desc())
            .first()
        )
        if row is None:
            return None
        tasks = (
            db.query(TransitionPlanTask)
            .filter(TransitionPlanTask.plan_id == row.plan_id)
            .order_by(TransitionPlanTask.sort_order)
            .all()
        )
        return _plan_to_dict(row, tasks)


def create_transition_plan(
    plan_id: str, session_id: str, event_type: str, event_title: str,
    key_date: str | None, tasks: list[dict],
) -> None:
    now = datetime.now(timezone.utc)
    with _session() as db:
        db.add(TransitionPlan(
            plan_id=plan_id, session_id=session_id, event_type=event_type,
            event_title=event_title, key_date=key_date, created_at=now, updated_at=now,
        ))
        for index, task in enumerate(tasks):
            db.add(TransitionPlanTask(
                plan_id=plan_id, task_id=task["id"], sort_order=index, title=task["title"],
                description=task["description"], phase=task["phase"], priority=task["priority"],
                owner=task["owner"], due_offset_days=task["due_offset_days"],
                due_date=task.get("due_date"), status="todo", updated_at=now,
            ))
        db.commit()


def update_transition_plan_task(plan_id: str, task_id: str, status: str) -> bool:
    now = datetime.now(timezone.utc)
    with _session() as db:
        updated = (
            db.query(TransitionPlanTask)
            .filter(TransitionPlanTask.plan_id == plan_id, TransitionPlanTask.task_id == task_id)
            .update({"status": status, "updated_at": now})
        )
        if updated:
            db.query(TransitionPlan).filter(TransitionPlan.plan_id == plan_id).update({"updated_at": now})
        db.commit()
        return bool(updated)


def complete_transition_plan_tasks(plan_id: str, task_ids: list[str]) -> None:
    now = datetime.now(timezone.utc)
    with _session() as db:
        db.query(TransitionPlanTask).filter(
            TransitionPlanTask.plan_id == plan_id, TransitionPlanTask.task_id.in_(task_ids)
        ).update({"status": "done", "updated_at": now}, synchronize_session=False)
        db.query(TransitionPlan).filter(TransitionPlan.plan_id == plan_id).update({"updated_at": now})
        db.commit()


def claim_transition_plan_for_customer(session_id: str, customer_id: str) -> None:
    """Stamps customer_id onto this session's plan the first time it
    verifies, so a LATER session for the same customer finds this plan
    instead of starting a blank one - see plans.claim_for_customer."""
    with _session() as db:
        row = db.query(TransitionPlan).filter(TransitionPlan.session_id == session_id).first()
        if row is not None and row.customer_id is None:
            row.customer_id = customer_id
            db.commit()


def delete_transition_plan_for_session(session_id: str) -> bool:
    with _session() as db:
        row = db.query(TransitionPlan).filter(TransitionPlan.session_id == session_id).first()
        if row is None:
            return False
        db.query(TransitionPlanTask).filter(TransitionPlanTask.plan_id == row.plan_id).delete()
        db.delete(row)
        db.commit()
        return True


# --- Contact Rules (Marketing role, see /api/contact-rules in main.py) ----

DEFAULT_OFFER_CLICK_COOLDOWN_SECONDS = 120


def get_cooldown_seconds() -> int:
    with _session() as db:
        row = db.get(ContactRuleSettings, 1)
        if row is None:
            row = ContactRuleSettings(id=1, offer_click_cooldown_seconds=DEFAULT_OFFER_CLICK_COOLDOWN_SECONDS)
            db.add(row)
            db.commit()
        return row.offer_click_cooldown_seconds


def set_cooldown_seconds(seconds: int) -> None:
    with _session() as db:
        row = db.get(ContactRuleSettings, 1)
        if row is None:
            row = ContactRuleSettings(id=1, offer_click_cooldown_seconds=seconds)
            db.add(row)
        else:
            row.offer_click_cooldown_seconds = seconds
        db.commit()


def get_offer_tier_restrictions() -> dict[str, list[str]]:
    """offer_code -> list of tiers it's eligible for. An offer with no key
    here has no restriction (eligible for every tier) - see
    OfferTierRestriction's docstring."""
    with _session() as db:
        rows = db.query(OfferTierRestriction).all()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row.offer_code, []).append(row.tier)
        return result


def set_offer_tier_restrictions(offer_code: str, tiers: list[str]) -> None:
    """Replaces the full set of eligible tiers for one offer. An empty
    list removes the restriction entirely (eligible for every tier again)."""
    with _session() as db:
        db.query(OfferTierRestriction).filter(OfferTierRestriction.offer_code == offer_code).delete()
        for tier in tiers:
            db.add(OfferTierRestriction(offer_code=offer_code, tier=tier))
        db.commit()
