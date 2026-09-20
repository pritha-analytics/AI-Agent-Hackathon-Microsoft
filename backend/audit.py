"""Append-only, hash-chained audit trail for agent decisions.

Every mortgage-agent step (document extraction, credit assessment, rate/
terms calculation, loan promise, operations hand-off) writes one entry here.
Each entry includes the SHA-256 hash of the previous entry, so the whole
chain can be verified afterwards - if any past entry is edited, every hash
after it breaks. That's the property an auditor actually needs: proof the
record wasn't quietly altered after the fact, not just a log line.

IMPORTANT: this is a demonstration of the pattern, not a certified compliant
audit system. Real GDPR/BASEL/ECB credit-risk audit trails need: a tamper-
proof storage backend (WORM storage / an actual ledger, not a local file),
retention-period policy, access controls, and legal/compliance sign-off.
Treat this as scaffolding to build on, not as compliance itself.

GDPR note: personnummer is never written here in full - only masked, since
the audit log's purpose is decision traceability, not another copy of PII.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_log.jsonl"
GENESIS_HASH = "0" * 64

_lock = Lock()


def mask_personnummer(personnummer: str) -> str:
    digits = re.sub(r"\D", "", personnummer or "")
    if len(digits) < 4:
        return "****"
    return f"****{digits[-4:]}"


def _hash_entry(entry: dict) -> str:
    canonical = json.dumps(entry, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _last_hash() -> str:
    if not AUDIT_LOG_PATH.exists():
        return GENESIS_HASH
    last_line = None
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line
    if not last_line:
        return GENESIS_HASH
    return json.loads(last_line)["entry_hash"]


def record_event(
    agent: str,
    action: str,
    customer_id: str | None,
    decision: str,
    details: dict,
) -> str:
    """Append one audit entry. Returns the new entry's audit_id.

    - agent: which agent made this decision (e.g. "credit_agent")
    - action: what step this is (e.g. "credit_assessment")
    - customer_id: the internal customer_id (never the personnummer)
    - decision: the outcome (e.g. "APPROVE", "NEEDS_REVIEW", "CALCULATED")
    - details: structured, JSON-serializable inputs/outputs behind the
      decision - the actual thing an auditor would want to inspect
    """
    with _lock:
        prev_hash = _last_hash()
        entry = {
            "audit_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "action": action,
            "customer_id": customer_id,
            "decision": decision,
            "details": details,
            "prev_hash": prev_hash,
        }
        entry["entry_hash"] = _hash_entry(entry)

        AUDIT_LOG_PATH.parent.mkdir(exist_ok=True)
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry["audit_id"]


def read_events(customer_id: str | None = None) -> list[dict]:
    if not AUDIT_LOG_PATH.exists():
        return []
    events = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if customer_id is None or entry.get("customer_id") == customer_id:
                events.append(entry)
    return events


def read_recent_events(limit: int = 50) -> list[dict]:
    """Most recent audit events across every customer, newest first - the
    concise "Audit History" feed the AI Hub dashboard shows managers/
    auditors (as opposed to /api/audit/{customer_id}, which is the full,
    single-customer decision trail linked from a CS Workspace case)."""
    events = read_events()
    events.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return events[:limit]


def verify_chain() -> dict:
    """Recomputes every entry's hash and checks the prev_hash links.
    Returns {"valid": bool, "entries": int, "broken_at": audit_id | None}."""
    if not AUDIT_LOG_PATH.exists():
        return {"valid": True, "entries": 0, "broken_at": None}

    expected_prev = GENESIS_HASH
    count = 0
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            count += 1

            if entry.get("prev_hash") != expected_prev:
                return {"valid": False, "entries": count, "broken_at": entry.get("audit_id")}

            claimed_hash = entry.get("entry_hash")
            recomputed = _hash_entry({k: v for k, v in entry.items() if k != "entry_hash"})
            if claimed_hash != recomputed:
                return {"valid": False, "entries": count, "broken_at": entry.get("audit_id")}

            expected_prev = claimed_hash

    return {"valid": True, "entries": count, "broken_at": None}
