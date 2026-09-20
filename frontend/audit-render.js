// Shared "friendly audit event" rendering helpers, used by both audit.js
// (a single customer's full decision trail, linked from a CS Workspace
// case) and aihub-dashboard.js (a concise, cross-customer Audit History
// feed for managers/auditors, where clicking a row opens the same detail
// view in a modal). Kept in one file so the two never drift apart.

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function titleCase(raw) {
  return String(raw)
    .replace(/[_.]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function decisionClass(decision) {
  return "decision-" + String(decision || "").toLowerCase().replace(/[^a-z]/g, "");
}

function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function formatValue(value) {
  if (Array.isArray(value)) return value.map(formatValue).join(", ") || "None";
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return String(value);
}

// Picks the interesting scalar (non-object, non-array-of-objects) fields
// from an action's recorded details, so the card shows a few readable facts
// up front - the full structure is still one click away via "Raw details".
function pickHighlights(details) {
  const source = details && typeof details === "object"
    ? (details.outputs && typeof details.outputs === "object" ? details.outputs : details)
    : {};

  const skipKeys = new Set(["outputs", "inputs", "reasons", "extra"]);
  const highlights = [];

  for (const [key, value] of Object.entries(source)) {
    if (skipKeys.has(key)) continue;
    if (value !== null && typeof value === "object") continue; // nested - leave to raw view
    highlights.push([titleCase(key), formatValue(value)]);
  }

  // A few fields worth surfacing even when they live one level up in
  // `inputs` (e.g. the loan amount a credit assessment was run against).
  if (details && details.inputs && typeof details.inputs === "object") {
    for (const key of ["loan_amount_sek", "property_value_sek", "monthly_gross_income_sek"]) {
      if (details.inputs[key] !== undefined && !highlights.some(([label]) => label === titleCase(key))) {
        highlights.push([titleCase(key), formatValue(details.inputs[key])]);
      }
    }
  }

  return highlights.slice(0, 8);
}

function reasonsList(details) {
  const reasons = details && (details.reasons || (details.outputs && details.outputs.reasons));
  return Array.isArray(reasons) ? reasons : null;
}

// The full "detail view" for one event - a decision badge, a handful of
// highlighted facts, any policy reasons, and the raw JSON one click away.
// Used both inside audit.html's timeline cards and inside the AI Hub
// dashboard's Audit History modal.
function eventCardInnerHTML(event) {
  const dClass = decisionClass(event.decision);
  const highlights = pickHighlights(event.details);
  const reasons = reasonsList(event.details);

  const highlightsHtml = highlights.length
    ? `<ul class="event-highlights">${highlights
        .map(([label, value]) => `<li><span class="hl-label">${escapeHtml(label)}:</span>${escapeHtml(value)}</li>`)
        .join("")}</ul>`
    : "";

  const reasonsHtml = reasons && reasons.length
    ? `<ul class="event-highlights">${reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`
    : "";

  const customerLine = event.customer_id
    ? `<div class="event-customer">Customer: <strong>${escapeHtml(event.customer_id)}</strong></div>`
    : "";

  return `
    <div class="event-head">
      <span class="event-title"><span class="event-agent">${escapeHtml(titleCase(event.agent))}</span> — ${escapeHtml(titleCase(event.action))}</span>
      <span class="event-time">${escapeHtml(formatTimestamp(event.ts))}</span>
    </div>
    ${customerLine}
    <span class="event-decision ${dClass}">${escapeHtml(event.decision || "—")}</span>
    ${highlightsHtml}
    ${reasonsHtml}
    <details class="event-details">
      <summary>Raw details</summary>
      <pre>${escapeHtml(JSON.stringify(event.details, null, 2))}</pre>
    </details>
  `;
}
