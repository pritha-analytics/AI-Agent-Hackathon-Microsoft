"""Turns a customer's raw interaction log (db.py) plus whatever case status
cs-service knows about into the customer-friendly "mini-portfolio" the chat
widget's interaction-history panel renders - what they've talked to Sara
about, how far each thing has gotten, and what still needs attention.

Deliberately does no deciding of its own: topic labels and priority are
read off data other layers already computed (topic_classifier.py's
routing-derived topic, cs-service's case status) - narration over the
existing record, same principle as the LLM layer elsewhere in this app.
"""

from . import cs_client, db

# Customer-facing label for each topic string topic_classifier.py can
# produce - kept here, not there, since that module's job is classification
# for the AI Hub metrics, not wording for a customer-facing panel.
TOPIC_LABELS = {
    "human_contact": "Requested to speak with someone",
    "mortgage_loan_promise": "Mortgage pre-approval",
    "mortgage_loan_offer": "Mortgage application",
    "fraud_report": "Fraud report",
    "transaction_dispute": "Transaction dispute",
    "portfolio_inquiry": "Reviewed your products",
    "callback_request": "Callback request",
    "case_status": "Checked a case status",
    "car_repair": "Car damage claim",
    "home_repair": "Home damage claim",
    "health_care": "Personal injury claim",
    "home_purchase_advisory": "Home purchase advice",
    "general_advisory": "General question",
}

# Case statuses cs-service can return, worded for a customer rather than a
# CS rep - see cs-service's CaseStatus.java for the underlying enum.
STATUS_LABELS = {
    "NEW": "Received",
    "IN_PROGRESS": "In progress",
    "SUBMITTED": "With our team",
    "RESOLVED": "Completed",
}

# Topics that are urgent by nature (money at risk, security), regardless of
# where the underlying case currently stands - the customer-facing "high
# priority" flag other open items don't get.
URGENT_TOPICS = {"fraud_report", "transaction_dispute"}


def _priority(topic: str, status: str | None) -> str:
    if status == "RESOLVED":
        return "done"
    if topic in URGENT_TOPICS:
        return "high"
    if status is not None:
        return "open"
    return "info"


def build_customer_history(customer_id: str, limit: int = 10) -> list[dict]:
    """One item per recent interaction, most recent first, each with a
    friendly label, the underlying case's progress (if any), and a
    priority the panel uses to flag what needs the customer's attention."""
    interactions = db.get_customer_interactions(customer_id, limit=limit)

    case_cache: dict[str, dict | None] = {}
    items = []
    for row in interactions:
        case_id = row["case_id"]
        status = None
        case_type = None
        if case_id:
            if case_id not in case_cache:
                case_cache[case_id] = cs_client.get_case_for_customer(case_id, customer_id)
            case = case_cache[case_id]
            if case:
                status = case.get("status")
                case_type = case.get("type")

        topic = row["topic"]
        items.append({
            "topic": topic,
            "label": TOPIC_LABELS.get(topic, topic.replace("_", " ").capitalize()),
            "date": row["ts"].isoformat() if row["ts"] else None,
            "case_id": case_id,
            "case_type": case_type,
            "status": status,
            "status_label": STATUS_LABELS.get(status) if status else None,
            "priority": _priority(topic, status),
        })

    return items


# Buckets STATUS_LABELS' four cs-service statuses into the three the "Your
# Activity" summary counts by - see build_activity_summary.
_CASE_BUCKET = {"NEW": "open", "SUBMITTED": "open", "IN_PROGRESS": "in_progress", "RESOLVED": "closed"}


def build_activity_summary(customer_id: str, limit: int = 50) -> dict:
    """The "Your Activity" sidebar panel: a summary view rather than the raw
    per-interaction list build_customer_history above returns - total chats,
    case counts by status, top topics, and top urgent cases. Urgency is
    derived from the same signals _priority already uses (fraud/dispute
    topics and open status), ranked by recency - cs-service has no separate
    numeric urgency field."""
    interactions = db.get_customer_interactions(customer_id, limit=limit)

    case_cache: dict[str, dict | None] = {}
    cases: dict[str, dict] = {}  # case_id -> {topic, status, ts}
    topic_counts: dict[str, int] = {}

    for row in interactions:
        topic_counts[row["topic"]] = topic_counts.get(row["topic"], 0) + 1

        case_id = row["case_id"]
        if not case_id:
            continue
        if case_id not in case_cache:
            case_cache[case_id] = cs_client.get_case_for_customer(case_id, customer_id)
        case = case_cache[case_id]
        status = case.get("status") if case else None
        if case_id not in cases or (row["ts"] and row["ts"] > cases[case_id]["ts"]):
            cases[case_id] = {"topic": row["topic"], "status": status, "ts": row["ts"]}

    case_counts = {"open": 0, "in_progress": 0, "closed": 0}
    for info in cases.values():
        bucket = _CASE_BUCKET.get(info["status"])
        if bucket:
            case_counts[bucket] += 1

    top_topics = [
        TOPIC_LABELS.get(topic, topic.replace("_", " ").capitalize())
        for topic, _ in sorted(topic_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    ]

    def urgency_key(item: tuple[str, dict]) -> tuple[int, int, str]:
        case_id, info = item
        is_urgent = info["topic"] in URGENT_TOPICS
        is_open = info["status"] != "RESOLVED"
        ts = info["ts"].isoformat() if info["ts"] else ""
        return (int(is_urgent), int(is_open), ts)

    top_urgent = sorted(cases.items(), key=urgency_key, reverse=True)[:3]
    top_urgent_cases = [
        {
            "case_id": case_id,
            "label": TOPIC_LABELS.get(info["topic"], info["topic"].replace("_", " ").capitalize()),
            "status_label": STATUS_LABELS.get(info["status"]) if info["status"] else None,
        }
        for case_id, info in top_urgent
    ]

    return {
        "total_chats": db.count_verified_chat_sessions(customer_id),
        "cases": case_counts,
        "top_topics": top_topics,
        "top_urgent_cases": top_urgent_cases,
    }
