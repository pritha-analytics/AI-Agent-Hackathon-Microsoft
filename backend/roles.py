"""Role-based access to the AI Hub dashboard's sections.

Mirrors cs-service's X-CS-Role convention (see RolePermissions.java) on
purpose, for the same reason and with the same limitation: the caller's
role is a self-declared header (X-Dashboard-Role), not a verified login -
a real deployment would back this with actual authentication. What this
DOES genuinely provide is server-side enforcement: the dashboard hiding a
section for a role it doesn't recognize is only a convenience, this module
is what actually refuses the data regardless of what the client sends.

Roles:
  MANAGER      - Interactions analytics
  AI_ENGINEER  - AI Analytics (the technical/LLM-ops section)
  AUDITOR      - Audit Trail
  MARKETING    - Contact Rules (offer cooldown, tier targeting)
"""

from fastapi import HTTPException

MANAGER = "MANAGER"
AI_ENGINEER = "AI_ENGINEER"
AUDITOR = "AUDITOR"
MARKETING = "MARKETING"

ALL_ROLES = {MANAGER, AI_ENGINEER, AUDITOR, MARKETING}

# Which roles may see which dashboard section - the single source of truth
# both main.py's endpoints and (mirrored, for UX only) aihub-dashboard.js
# check against.
SECTION_ACCESS = {
    "interactions": {MANAGER},
    "ai_analytics": {AI_ENGINEER},
    "audit_trail": {AUDITOR},
    "contact_rules": {MARKETING},
}


def parse_role(role_header: str | None) -> str:
    """Validates the header is present and a known role; doesn't check
    section access yet (some endpoints, like /api/metrics/summary, span
    more than one section and filter their own response by role)."""
    if not role_header or not role_header.strip():
        raise HTTPException(status_code=400, detail="Missing X-Dashboard-Role header.")
    role = role_header.strip().upper().replace(" ", "_")
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"Unknown role '{role_header}'.")
    return role


def can_access(role: str, section: str) -> bool:
    return role in SECTION_ACCESS[section]


def require_role(role_header: str | None, section: str) -> str:
    """Validates the header AND that this role may see this section - use
    this for endpoints that belong to exactly one section."""
    role = parse_role(role_header)
    if not can_access(role, section):
        raise HTTPException(status_code=403, detail=f"{role} is not authorized for {section}.")
    return role
