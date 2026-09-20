"""Operational/BI telemetry for the AI Hub monitoring dashboard - distinct
from audit.py, which is a compliance/decision trail scoped to one customer.
This log is anonymized (session_id only, never a customer_id or personnummer)
and answers a different question: how is Sara performing as a system, across
everyone, over time.

Append-only JSONL, same "just a file" honesty as audit.py: good enough for a
hackathon demo (single process), not a real metrics warehouse. A production
deployment would ship these events to whatever the AI Hub already uses
(a time-series DB, an events pipeline) instead of a local file.
"""

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

METRICS_LOG_PATH = Path(__file__).resolve().parent / "metrics_log.jsonl"

_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write(event: dict) -> None:
    event.setdefault("ts", _now().isoformat())
    with _lock:
        METRICS_LOG_PATH.parent.mkdir(exist_ok=True)
        with METRICS_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def record_interaction(
    session_id: str | None,
    topic: str,
    lang: str | None,
    case_created: bool,
    case_id: str | None,
) -> None:
    """One event per /api/chat turn - the unit "interaction volumes" and
    "topics covered" are counted from."""
    _write({
        "type": "interaction",
        "session_id": session_id,
        "topic": topic,
        "lang": lang or "en",
        "case_created": case_created,
        "case_id": case_id,
    })


def record_handoff(session_id: str | None, topic: str) -> None:
    """A customer actually asked to be connected to a human agent (not just
    that Sara offered the option) - the request-human endpoint records this."""
    _write({"type": "handoff", "session_id": session_id, "topic": topic})


def record_rating(session_id: str | None, rating: int) -> None:
    """Also tags the rating with whatever topic that session was last about
    (from its own interaction events) - a bare 1-5 number isn't actionable
    on its own; knowing WHICH kind of conversation earned a 3 or a 4 is what
    turns it into real customer insight (see build_summary's
    customer_insights, which groups by this field)."""
    topic = None
    if session_id:
        session_interactions = [e for e in read_events("interaction") if e.get("session_id") == session_id]
        if session_interactions:
            topic = session_interactions[-1].get("topic")
    _write({"type": "rating", "session_id": session_id, "rating": rating, "topic": topic})


def record_llm_usage(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    duration_ms: float | None,
    topic: str | None = None,
    session_id: str | None = None,
) -> None:
    """Logged automatically for every LLM call, from a single wrapper point
    in llm_client.py - see the note there. topic/session_id come from
    interaction_context.py's per-request contextvar (set in main.py's
    /api/chat before calling run_agent), not a parameter every agent has to
    thread through its own tool-calling loop - this is what makes the
    per-topic token trend and the satisfaction/latency correlation below
    possible without touching every agent's call sites."""
    _write({
        "type": "llm_call",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
        "topic": topic,
        "session_id": session_id,
    })


def read_events(event_type: str | None = None) -> list[dict]:
    if not METRICS_LOG_PATH.exists():
        return []
    events = []
    with METRICS_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if event_type is None or entry.get("type") == event_type:
                events.append(entry)
    return events


TOPIC_LABELS = {
    "mortgage_loan_promise": "Loan Promise application",
    "mortgage_loan_offer": "Loan Offer application",
    "fraud_report": "Fraud report",
    "transaction_dispute": "Transaction dispute",
    "portfolio_inquiry": "Product portfolio lookup",
    "callback_request": "Callback request",
    "case_status": "Case status lookup",
    "human_contact": "Ask to talk to a human",
    "car_repair": "Car damage / repair",
    "home_repair": "Home damage / repair",
    "health_care": "Accident / health claim",
    "home_purchase_advisory": "Buying a home - general advice",
    "general_advisory": "General advisory",
}


def _parse_ts(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _tokens_bucket(llm_events: list[dict], since: datetime | None) -> dict:
    bucket = [e for e in llm_events if since is None or _parse_ts(e["ts"]) >= since]
    prompt = sum(e.get("prompt_tokens") or 0 for e in bucket)
    completion = sum(e.get("completion_tokens") or 0 for e in bucket)
    total = sum(e.get("total_tokens") or (e.get("prompt_tokens") or 0) + (e.get("completion_tokens") or 0) for e in bucket)
    return {"calls": len(bucket), "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}


def _iso_week_label(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def token_trend_by_topic(weeks: int = 6, top_n: int = 5) -> dict:
    """Total tokens consumed per topic, per week, for the AI Analytics
    section's "which chat subjects are costing the most tokens, and is
    that going up or down" trend. Only topics attributed after
    interaction_context.py started threading topic through llm_client.py
    show up here - older llm_call rows (topic missing) fall into
    "unclassified" rather than being dropped, so historical totals still
    show up somewhere instead of silently vanishing."""
    now = _now()
    week_labels = [_iso_week_label(now - timedelta(weeks=i)) for i in range(weeks - 1, -1, -1)]
    week_index = {label: i for i, label in enumerate(week_labels)}

    llm_calls = read_events("llm_call")
    cutoff = now - timedelta(weeks=weeks)
    per_topic_week: dict[str, list[int]] = {}
    topic_totals: Counter[str] = Counter()

    for e in llm_calls:
        ts = _parse_ts(e["ts"])
        if ts < cutoff:
            continue
        label = _iso_week_label(ts)
        idx = week_index.get(label)
        if idx is None:
            continue
        topic = e.get("topic") or "unclassified"
        tokens = e.get("total_tokens") or 0
        per_topic_week.setdefault(topic, [0] * weeks)[idx] += tokens
        topic_totals[topic] += tokens

    top_topics = [t for t, _ in topic_totals.most_common(top_n)]
    other_topics = [t for t in per_topic_week if t not in top_topics]

    series = []
    for topic in top_topics:
        series.append({
            "topic": topic,
            "label": TOPIC_LABELS.get(topic, topic.replace("_", " ").title()) if topic != "unclassified" else "Unclassified (older data)",
            "tokens_by_week": per_topic_week[topic],
            "total_tokens": topic_totals[topic],
        })
    if other_topics:
        other_by_week = [0] * weeks
        for topic in other_topics:
            for i, v in enumerate(per_topic_week[topic]):
                other_by_week[i] += v
        series.append({
            "topic": "other",
            "label": "Other topics",
            "tokens_by_week": other_by_week,
            "total_tokens": sum(other_by_week),
        })

    return {"weeks": week_labels, "series": series}


def _pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = (variance_x * variance_y) ** 0.5
    if denominator == 0:
        return None
    return round(covariance / denominator, 3)


def satisfaction_latency_correlation() -> dict:
    """Does a slower Sara correlate with a less happy customer? Pairs each
    rated session with that session's average LLM round-trip latency (both
    keyed by session_id via interaction_context.py) and reports a Pearson
    correlation coefficient plus an avg-latency-per-rating breakdown for
    the chart. A negative coefficient is the expected direction (higher
    rating, lower latency); near zero means latency isn't what's driving
    satisfaction in this data."""
    ratings_by_session: dict[str, int] = {}
    for e in read_events("rating"):
        sid = e.get("session_id")
        if sid and isinstance(e.get("rating"), int):
            ratings_by_session[sid] = e["rating"]  # last rating wins if a session rated twice

    latency_by_session: dict[str, list[float]] = {}
    for e in read_events("llm_call"):
        sid = e.get("session_id")
        duration = e.get("duration_ms")
        if sid and isinstance(duration, (int, float)):
            latency_by_session.setdefault(sid, []).append(duration)

    pairs = [
        (sum(latency_by_session[sid]) / len(latency_by_session[sid]), rating)
        for sid, rating in ratings_by_session.items()
        if sid in latency_by_session
    ]

    by_rating = []
    for rating in range(1, 6):
        latencies = [lat for lat, r in pairs if r == rating]
        by_rating.append({
            "rating": rating,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "session_count": len(latencies),
        })

    coefficient = _pearson_correlation([lat for lat, _ in pairs], [r for _, r in pairs])

    return {
        "by_rating": by_rating,
        "correlation_coefficient": coefficient,
        "sample_size": len(pairs),
    }


def build_summary(days: int = 14) -> dict:
    """Everything the AI Hub dashboard renders, computed fresh from the
    event log on every call - there are no separate read/write models to
    keep in sync, and the log is small enough (JSONL, append-only) that a
    full scan per request is simple and fast enough for a demo."""
    now = _now()
    interactions = read_events("interaction")
    handoffs = read_events("handoff")
    ratings = read_events("rating")
    llm_calls = read_events("llm_call")

    # --- Interaction volumes, by day -------------------------------------
    by_day_counts: Counter[str] = Counter()
    for e in interactions:
        day = _parse_ts(e["ts"]).date().isoformat()
        by_day_counts[day] += 1
    by_day = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        by_day.append({"date": day, "count": by_day_counts.get(day, 0)})

    session_ids = {e.get("session_id") for e in interactions if e.get("session_id")}

    # --- Topics -------------------------------------------------------------
    topic_counts = Counter(e.get("topic", "general_advisory") for e in interactions)
    total_interactions = len(interactions) or 1
    topics = [
        {
            "topic": topic,
            "label": TOPIC_LABELS.get(topic, topic.replace("_", " ").title()),
            "count": count,
            "pct": round(count / total_interactions * 100, 1),
        }
        for topic, count in topic_counts.most_common()
    ]

    # --- Average time spent per session (first-to-last interaction) --------
    session_span: dict[str, list[datetime]] = {}
    for e in interactions:
        sid = e.get("session_id")
        if not sid:
            continue
        ts = _parse_ts(e["ts"])
        span = session_span.setdefault(sid, [ts, ts])
        span[0] = min(span[0], ts)
        span[1] = max(span[1], ts)
    durations = [(end - start).total_seconds() for start, end in session_span.values() if end > start]
    avg_duration_seconds = round(sum(durations) / len(durations), 1) if durations else 0.0

    # --- Manual handoffs ------------------------------------------------
    handoff_sessions = {e.get("session_id") for e in handoffs if e.get("session_id")}
    handoff_topic_counts = Counter(e.get("topic", "general_advisory") for e in handoffs)

    # --- Cases triggered ---------------------------------------------------
    case_events = [e for e in interactions if e.get("case_created")]
    case_topic_counts = Counter(e.get("topic", "general_advisory") for e in case_events)

    # --- Satisfaction --------------------------------------------------
    rating_values = [e["rating"] for e in ratings if isinstance(e.get("rating"), int)]
    rating_distribution = {str(n): rating_values.count(n) for n in range(1, 6)}
    avg_rating = round(sum(rating_values) / len(rating_values), 2) if rating_values else None

    # --- Customer insight: satisfaction broken down by topic, worst first -
    # this is the actionable view (which kinds of conversations are leaving
    # customers only "OK" or worse), not just one global average. A topic
    # needs at least 2 ratings before it's flagged, so a single fluke score
    # doesn't brand a whole topic as a problem.
    topic_ratings: dict[str, list[int]] = {}
    for e in ratings:
        rating_value = e.get("rating")
        if not isinstance(rating_value, int):
            continue
        topic_ratings.setdefault(e.get("topic") or "general_advisory", []).append(rating_value)
    customer_insights = sorted(
        (
            {
                "topic": topic,
                "label": TOPIC_LABELS.get(topic, topic.replace("_", " ").title()),
                "count": len(values),
                "average": round(sum(values) / len(values), 2),
                "needs_attention": len(values) >= 2 and (sum(values) / len(values)) < 3.5,
            }
            for topic, values in topic_ratings.items()
        ),
        key=lambda item: item["average"],
    )

    # --- Token consumption rollups -----------------------------------------
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tokens = {
        "today": _tokens_bucket(llm_calls, today_start),
        "last_7d": _tokens_bucket(llm_calls, now - timedelta(days=7)),
        "last_30d": _tokens_bucket(llm_calls, now - timedelta(days=30)),
        "last_365d": _tokens_bucket(llm_calls, now - timedelta(days=365)),
        "all_time": _tokens_bucket(llm_calls, None),
    }
    latencies = [e["duration_ms"] for e in llm_calls if isinstance(e.get("duration_ms"), (int, float))]
    avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else None
    models_used = Counter(e.get("model") or "unknown" for e in llm_calls)

    return {
        "generated_at": now.isoformat(),
        "interactions": {
            "total": len(interactions),
            "total_sessions": len(session_ids),
            "by_day": by_day,
        },
        "topics": topics,
        "avg_session_duration_seconds": avg_duration_seconds,
        "handoffs": {
            "sessions": len(handoff_sessions),
            "pct_of_sessions": round(len(handoff_sessions) / len(session_ids) * 100, 1) if session_ids else 0.0,
            "by_topic": [
                {"topic": t, "label": TOPIC_LABELS.get(t, t.replace("_", " ").title()), "count": c}
                for t, c in handoff_topic_counts.most_common()
            ],
        },
        "cases_triggered": {
            "count": len(case_events),
            "pct_of_interactions": round(len(case_events) / total_interactions * 100, 1),
            "by_topic": [
                {"topic": t, "label": TOPIC_LABELS.get(t, t.replace("_", " ").title()), "count": c}
                for t, c in case_topic_counts.most_common()
            ],
        },
        "satisfaction": {
            "count": len(rating_values),
            "average": avg_rating,
            "distribution": rating_distribution,
        },
        "customer_insights": customer_insights,
        "tokens": tokens,
        "technical": {
            "total_llm_calls": len(llm_calls),
            "avg_latency_ms": avg_latency_ms,
            "avg_tokens_per_call": round(tokens["all_time"]["total_tokens"] / len(llm_calls), 1) if llm_calls else 0,
            "models_used": dict(models_used),
        },
        "token_trend_by_topic": token_trend_by_topic(),
        "satisfaction_latency_correlation": satisfaction_latency_correlation(),
    }
