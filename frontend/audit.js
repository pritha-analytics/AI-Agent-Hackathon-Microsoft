// Shared rendering helpers (escapeHtml, titleCase, decisionClass,
// formatTimestamp, eventCardInnerHTML, ...) come from audit-render.js,
// loaded before this file - see that file's header comment.

const timelineEl = document.getElementById("timeline");
const customerIdEl = document.getElementById("customer-id");
const eventCountEl = document.getElementById("event-count");
const integrityBadgeEl = document.getElementById("integrity-badge");
const agentFilterEl = document.getElementById("agent-filter");

const params = new URLSearchParams(window.location.search);
const customerId = params.get("customer_id") || "";

let allEvents = [];

function renderEvent(event) {
  const li = document.createElement("li");
  li.className = "event";
  li.dataset.agent = event.agent || "";
  li.innerHTML = `
    <span class="event-dot ${decisionClass(event.decision)}"></span>
    <div class="event-card">${eventCardInnerHTML(event)}</div>
  `;
  return li;
}

function renderTimeline() {
  const selectedAgent = agentFilterEl.value;
  const events = allEvents
    .filter((e) => !selectedAgent || e.agent === selectedAgent)
    .slice()
    .sort((a, b) => new Date(b.ts) - new Date(a.ts)); // newest first

  timelineEl.innerHTML = "";
  if (!events.length) {
    timelineEl.innerHTML = '<li class="empty-hint">No agent actions recorded for this customer yet.</li>';
    return;
  }
  for (const event of events) {
    timelineEl.appendChild(renderEvent(event));
  }
}

function populateAgentFilter() {
  const agents = [...new Set(allEvents.map((e) => e.agent).filter(Boolean))].sort();
  for (const agent of agents) {
    const opt = document.createElement("option");
    opt.value = agent;
    opt.textContent = titleCase(agent);
    agentFilterEl.appendChild(opt);
  }
}

async function loadIntegrity() {
  try {
    const res = await fetch("/api/audit/verify");
    const data = await res.json();
    integrityBadgeEl.textContent = data.valid
      ? `Chain verified · ${data.entries} entries`
      : "Integrity check failed";
    integrityBadgeEl.classList.add(data.valid ? "valid" : "invalid");
  } catch {
    integrityBadgeEl.textContent = "Integrity check unavailable";
  }
}

async function loadAuditTrail() {
  customerIdEl.textContent = customerId || "(none given)";

  if (!customerId) {
    timelineEl.innerHTML = '<li class="empty-hint">No customer_id given in the link.</li>';
    eventCountEl.textContent = "0";
    return;
  }

  try {
    const res = await fetch(`/api/audit/${encodeURIComponent(customerId)}`);
    const data = await res.json();
    allEvents = data.events || [];
    eventCountEl.textContent = String(allEvents.length);
    populateAgentFilter();
    renderTimeline();
  } catch {
    timelineEl.innerHTML = '<li class="empty-hint">Could not load the audit trail. Please try again.</li>';
  }
}

agentFilterEl.addEventListener("change", renderTimeline);

loadIntegrity();
loadAuditTrail();
