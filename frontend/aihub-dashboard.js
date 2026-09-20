// escapeHtml, titleCase, decisionClass, formatTimestamp, eventCardInnerHTML
// come from audit-render.js, loaded before this file.

const $ = (id) => document.getElementById(id);

function formatNumber(n) {
  return Number(n || 0).toLocaleString();
}

function formatDuration(seconds) {
  if (!seconds) return "0s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function shortDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function renderVerticalBars(container, items, { valueKey, labelFn, countLabel }) {
  const max = Math.max(1, ...items.map((i) => i[valueKey]));
  container.innerHTML = items
    .map((item) => {
      const heightPct = Math.round((item[valueKey] / max) * 100);
      return `
        <div class="vbar">
          <span class="vbar-count">${countLabel ? countLabel(item) : item[valueKey]}</span>
          <div class="vbar-fill" style="height:${Math.max(heightPct, 2)}%"></div>
          <span class="vbar-label">${escapeHtml(labelFn(item))}</span>
        </div>`;
    })
    .join("");
}

function renderHorizontalBars(container, items, { valueKey, labelKey, valueFormatter }) {
  if (!items.length) {
    container.innerHTML = '<div class="empty-hint">No interactions recorded yet.</div>';
    return;
  }
  const max = Math.max(1, ...items.map((i) => i[valueKey]));
  container.innerHTML = items
    .map((item) => {
      const widthPct = Math.round((item[valueKey] / max) * 100);
      const value = valueFormatter ? valueFormatter(item) : item[valueKey];
      return `
        <div class="hbar-row">
          <span class="hbar-label" title="${escapeHtml(item[labelKey])}">${escapeHtml(item[labelKey])}</span>
          <div class="hbar-track"><div class="hbar-fill" style="width:${Math.max(widthPct, 2)}%"></div></div>
          <span class="hbar-value">${escapeHtml(String(value))}</span>
        </div>`;
    })
    .join("");
}

function renderMiniList(container, items) {
  if (!items.length) {
    container.innerHTML = '<li class="empty-hint">None yet</li>';
    return;
  }
  container.innerHTML = items
    .map((i) => `<li><span>${escapeHtml(i.label)}</span><span class="count">${formatNumber(i.count)}</span></li>`)
    .join("");
}

function starString(avg) {
  if (avg === null || avg === undefined) return "—";
  const full = Math.round(avg);
  return "★".repeat(full) + "☆".repeat(5 - full);
}

// --- RBAC: which dashboard sections each role can see. Mirrors
// backend/roles.py's SECTION_ACCESS - this copy is a UX convenience only
// (which sections to even bother fetching/showing); the server enforces
// the real boundary and refuses a role's request for a section it can't
// see regardless of what this file does. ---

const ROLE_SECTIONS = {
  MANAGER: ["interactions"],
  AI_ENGINEER: ["ai_analytics"],
  AUDITOR: ["audit_trail"],
  MARKETING: ["contact_rules"],
};

const roleSelectEl = $("role-select");

function currentRole() {
  return roleSelectEl.value;
}

function canAccess(section) {
  return (ROLE_SECTIONS[currentRole()] || []).includes(section);
}

function roleHeaders() {
  return { "X-Dashboard-Role": currentRole() };
}

function applyRoleVisibility() {
  const sections = document.querySelectorAll("[data-role-section]");
  let anyVisible = false;
  sections.forEach((el) => {
    const ok = canAccess(el.dataset.roleSection);
    el.hidden = !ok;
    if (ok) anyVisible = true;
  });
  $("no-access-hint").hidden = anyVisible;
}

roleSelectEl.value = localStorage.getItem("ai-hub-role") || "MANAGER";
roleSelectEl.addEventListener("change", () => {
  localStorage.setItem("ai-hub-role", currentRole());
  loadDashboard().catch(console.error);
});

// --- Audit History: a concise, cross-customer feed for managers/auditors.
// Each row is deliberately terse (time, customer, agent -> action,
// decision) - the full picture (highlights, policy reasons, raw JSON) is
// one click away in a modal, using the same renderer audit.html uses for
// a single customer's full trail (audit-render.js). ---

const auditListEl = $("audit-history-list");
const auditAgentFilterEl = $("audit-agent-filter");
const auditModalOverlayEl = $("audit-modal-overlay");
const auditModalBodyEl = $("audit-modal-body");

let auditEvents = [];

function renderAuditList() {
  const selectedAgent = auditAgentFilterEl.value;
  const events = selectedAgent ? auditEvents.filter((e) => e.agent === selectedAgent) : auditEvents;

  auditListEl.innerHTML = "";
  if (!events.length) {
    auditListEl.innerHTML = '<div class="empty-hint">No agent actions recorded yet.</div>';
    return;
  }

  for (const event of events) {
    const row = document.createElement("div");
    row.className = "audit-row";
    row.innerHTML = `
      <span class="audit-row-time">${escapeHtml(formatTimestamp(event.ts))}</span>
      <span class="audit-row-customer">${escapeHtml(event.customer_id || "—")}</span>
      <span class="audit-row-action"><strong>${escapeHtml(titleCase(event.agent))}</strong> — ${escapeHtml(titleCase(event.action))}</span>
      <span class="audit-row-decision ${decisionClass(event.decision)}">${escapeHtml(event.decision || "—")}</span>
    `;
    row.addEventListener("click", () => openAuditModal(event));
    auditListEl.appendChild(row);
  }
}

function populateAuditAgentFilter() {
  const previous = auditAgentFilterEl.value;
  const agents = [...new Set(auditEvents.map((e) => e.agent).filter(Boolean))].sort();
  auditAgentFilterEl.innerHTML = '<option value="">All agents</option>';
  for (const agent of agents) {
    const opt = document.createElement("option");
    opt.value = agent;
    opt.textContent = titleCase(agent);
    auditAgentFilterEl.appendChild(opt);
  }
  if (agents.includes(previous)) auditAgentFilterEl.value = previous;
}

function openAuditModal(event) {
  auditModalBodyEl.innerHTML = `<div class="event-card">${eventCardInnerHTML(event)}</div>`;
  auditModalOverlayEl.hidden = false;
}

function closeAuditModal() {
  auditModalOverlayEl.hidden = true;
}

auditAgentFilterEl.addEventListener("change", renderAuditList);
$("audit-modal-close").addEventListener("click", closeAuditModal);
auditModalOverlayEl.addEventListener("click", (e) => {
  if (e.target === auditModalOverlayEl) closeAuditModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !auditModalOverlayEl.hidden) closeAuditModal();
});

async function loadAuditHistory() {
  const res = await fetch("/api/audit/recent?limit=30", { headers: roleHeaders() });
  if (!res.ok) {
    auditEvents = [];
    renderAuditList();
    return;
  }
  const data = await res.json();
  auditEvents = data.events || [];
  populateAuditAgentFilter();
  renderAuditList();
}

const TOKEN_ROWS = [
  ["today", "Today"],
  ["last_7d", "Last 7 days"],
  ["last_30d", "Last 30 days"],
  ["last_365d", "Last 365 days"],
  ["all_time", "All time"],
];

// --- New: tokens by chat subject, week over week (AI Analytics). A hand-
// rolled heat table (no charting library) so a topic's row is scannable
// left-to-right for trend, and the darkest cell in the grid jumps out as
// "this is what's costing the most, this week." ---

function renderTokenTopicTrend(trend) {
  const container = $("token-topic-trend");
  if (!trend || !trend.series || !trend.series.length) {
    container.innerHTML = '<div class="empty-hint">No token usage recorded yet.</div>';
    return;
  }

  const max = Math.max(1, ...trend.series.flatMap((s) => s.tokens_by_week));
  const weekHeaders = trend.weeks.map((w) => `<th>${escapeHtml(w.replace(/^\d{4}-/, ""))}</th>`).join("");

  const rows = trend.series
    .map((series) => {
      const cells = series.tokens_by_week
        .map((tokens) => {
          const intensity = tokens ? Math.min(1, tokens / max) : 0;
          const bg = tokens ? `rgba(13, 59, 102, ${0.12 + intensity * 0.7})` : "transparent";
          const color = intensity > 0.55 ? "#ffffff" : "var(--text-main)";
          return `<td style="background:${bg}; color:${color}">${formatNumber(tokens)}</td>`;
        })
        .join("");
      return `
        <tr>
          <td class="token-trend-topic">${escapeHtml(series.label)}</td>
          ${cells}
          <td class="token-trend-total">${formatNumber(series.total_tokens)}</td>
        </tr>`;
    })
    .join("");

  container.innerHTML = `
    <table class="token-trend-inner">
      <thead><tr><th>Topic</th>${weekHeaders}<th>Total</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// --- New: does a slower reply correlate with a lower satisfaction rating?
// A Pearson coefficient (computed server-side, metrics.py) plus a bar per
// rating showing that rating's average latency. ---

function renderCorrelation(corr) {
  const valueEl = $("stat-correlation");
  const labelEl = $("stat-correlation-label");

  if (!corr || corr.correlation_coefficient === null) {
    valueEl.textContent = "—";
    labelEl.textContent = `Not enough rated sessions yet (${corr ? corr.sample_size : 0} so far)`;
  } else {
    valueEl.textContent = corr.correlation_coefficient.toFixed(2);
    const direction = corr.correlation_coefficient < 0
      ? "slower replies tend to mean lower ratings"
      : "no evidence slower replies hurt ratings here";
    labelEl.textContent = `${direction} · n=${corr.sample_size}`;
  }

  const items = (corr ? corr.by_rating : []).map((b) => ({
    rating: b.rating,
    avg_latency_ms: b.avg_latency_ms || 0,
    hasData: b.avg_latency_ms !== null,
  }));
  renderVerticalBars($("correlation-chart"), items, {
    valueKey: "avg_latency_ms",
    labelFn: (i) => "★".repeat(i.rating),
    countLabel: (i) => (i.hasData ? `${Math.round(i.avg_latency_ms)}ms` : "—"),
  });
}

// --- New: Contact Rules (Marketing) - cooldown + per-offer tier targeting.
// Genuinely editable, not just a read-only view: saving calls the
// role-gated /api/contact-rules/* endpoints, which take effect immediately
// (nba_engine reads them fresh on every offer decision, no restart). ---

let currentOfferRules = [];
let validTiers = [];

function renderOfferRulesTable() {
  const body = $("offer-rules-body");
  if (!currentOfferRules.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty-hint">No offers configured.</td></tr>';
    return;
  }
  body.innerHTML = currentOfferRules
    .map((offer) => {
      const checkboxes = validTiers
        .map((tier) => {
          const checked = offer.tiers.length === 0 || offer.tiers.includes(tier);
          return `
            <label class="tier-checkbox">
              <input type="checkbox" data-offer="${escapeHtml(offer.code)}" data-tier="${escapeHtml(tier)}" ${checked ? "checked" : ""} />
              ${escapeHtml(tier)}
            </label>`;
        })
        .join("");
      return `
        <tr data-offer-row="${escapeHtml(offer.code)}">
          <td>${escapeHtml(offer.title)}</td>
          <td>${escapeHtml(offer.category)}</td>
          <td>${escapeHtml(offer.product_family || "—")}</td>
          <td><div class="tier-checkbox-group">${checkboxes}</div></td>
          <td><button type="button" class="save-tier-btn" data-offer="${escapeHtml(offer.code)}">Save</button><span class="rule-status" data-status-for="${escapeHtml(offer.code)}"></span></td>
        </tr>`;
    })
    .join("");

  body.querySelectorAll(".save-tier-btn").forEach((btn) => {
    btn.addEventListener("click", () => saveOfferTiers(btn.dataset.offer));
  });
}

async function saveOfferTiers(offerCode) {
  const row = document.querySelector(`tr[data-offer-row="${CSS.escape(offerCode)}"]`);
  const statusEl = row.querySelector(`[data-status-for="${CSS.escape(offerCode)}"]`);
  const checked = [...row.querySelectorAll("input[type=checkbox]:checked")].map((cb) => cb.dataset.tier);
  // Every box checked is treated the same as none restricted (all tiers).
  const tiers = checked.length === validTiers.length ? [] : checked;

  statusEl.textContent = "Saving…";
  try {
    const res = await fetch("/api/contact-rules/offer-tiers", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...roleHeaders() },
      body: JSON.stringify({ offer_code: offerCode, tiers }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    statusEl.textContent = "Saved";
    setTimeout(() => { statusEl.textContent = ""; }, 2000);
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Failed to save";
  }
}

$("cooldown-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const statusEl = $("cooldown-status");
  const seconds = Number($("cooldown-input").value);
  statusEl.textContent = "Saving…";
  try {
    const res = await fetch("/api/contact-rules/cooldown", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...roleHeaders() },
      body: JSON.stringify({ cooldown_seconds: seconds }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    statusEl.textContent = "Saved";
    setTimeout(() => { statusEl.textContent = ""; }, 2000);
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Failed to save";
  }
});

async function loadContactRules() {
  const res = await fetch("/api/contact-rules", { headers: roleHeaders() });
  if (!res.ok) return;
  const data = await res.json();
  $("cooldown-input").value = data.cooldown_seconds;
  validTiers = data.valid_tiers;
  currentOfferRules = data.offers;
  renderOfferRulesTable();
}

function renderAuditIntegrity(integrity) {
  if (integrity) {
    $("stat-audit-integrity").innerHTML = integrity.valid
      ? '<span class="badge valid">Verified</span>'
      : '<span class="badge invalid">Broken</span>';
    $("stat-audit-entries").textContent = `${formatNumber(integrity.entries)} audit entries`;
    return;
  }

  $("stat-audit-integrity").textContent = "Unavailable";
  $("stat-audit-entries").textContent = "";
}

async function loadDashboard() {
  applyRoleVisibility();

  const wantsMetrics = canAccess("interactions") || canAccess("ai_analytics");
  const wantsAudit = canAccess("audit_trail");
  const wantsContactRules = canAccess("contact_rules");

  const [summaryRes, integrityRes] = await Promise.all([
    wantsMetrics ? fetch("/api/metrics/summary?days=14", { headers: roleHeaders() }) : Promise.resolve(null),
    wantsAudit ? fetch("/api/audit/verify", { headers: roleHeaders() }).catch(() => null) : Promise.resolve(null),
    wantsAudit ? loadAuditHistory().catch(console.error) : Promise.resolve(),
    wantsContactRules ? loadContactRules().catch(console.error) : Promise.resolve(),
  ]);

  const data = summaryRes && summaryRes.ok ? await summaryRes.json() : null;
  const integrity = integrityRes && integrityRes.ok ? await integrityRes.json() : null;

  // --- Section A: customer interaction performance ---
  if (data && canAccess("interactions")) {
    $("stat-total-interactions").textContent = formatNumber(data.interactions.total);
    $("stat-total-sessions").textContent = `${formatNumber(data.interactions.total_sessions)} conversations`;

    $("stat-avg-duration").textContent = formatDuration(data.avg_session_duration_seconds);

    $("stat-handoff-pct").textContent = `${data.handoffs.pct_of_sessions}%`;
    $("stat-handoff-count").textContent = `${formatNumber(data.handoffs.sessions)} of ${formatNumber(data.interactions.total_sessions)} conversations`;

    $("stat-cases-pct").textContent = `${data.cases_triggered.pct_of_interactions}%`;
    $("stat-cases-count").textContent = `${formatNumber(data.cases_triggered.count)} of ${formatNumber(data.interactions.total)} interactions`;

    $("stat-satisfaction").textContent = data.satisfaction.average !== null ? data.satisfaction.average.toFixed(2) : "No ratings yet";
    $("satisfaction-stars").textContent = starString(data.satisfaction.average);
    $("stat-satisfaction-count").textContent = `${formatNumber(data.satisfaction.count)} ratings submitted`;

    renderVerticalBars($("volume-chart"), data.interactions.by_day, {
      valueKey: "count",
      labelFn: (i) => shortDate(i.date),
    });

    const satisfactionItems = [1, 2, 3, 4, 5].map((n) => ({
      stars: n,
      count: data.satisfaction.distribution[String(n)] || 0,
    }));
    renderVerticalBars($("satisfaction-chart"), satisfactionItems, {
      valueKey: "count",
      labelFn: (i) => "★".repeat(i.stars),
    });

    renderHorizontalBars($("topics-chart"), data.topics, {
      valueKey: "count",
      labelKey: "label",
      valueFormatter: (i) => `${formatNumber(i.count)} (${i.pct}%)`,
    });

    renderMiniList($("handoff-list"), data.handoffs.by_topic);
    renderMiniList($("cases-list"), data.cases_triggered.by_topic);

    $("customer-insights-body").innerHTML = data.customer_insights.length
      ? data.customer_insights
          .map(
            (i) => `
        <tr>
          <td>${escapeHtml(i.label)}</td>
          <td>${formatNumber(i.count)}</td>
          <td>${i.average.toFixed(2)} ${starString(i.average)}</td>
          <td>${i.needs_attention ? '<span class="badge warn">Needs attention</span>' : ""}</td>
        </tr>`
          )
          .join("")
      : '<tr><td colspan="4" class="empty-hint">No ratings submitted yet.</td></tr>';
  }

  // --- Section B: agent performance / technical ---
  if (data && canAccess("ai_analytics")) {
    $("stat-total-calls").textContent = formatNumber(data.technical.total_llm_calls);
    const models = Object.entries(data.technical.models_used || {});
    $("stat-models-used").textContent = models.length
      ? models.map(([m, c]) => `${m} (${c})`).join(", ")
      : "No calls yet";

    $("stat-avg-latency").textContent = data.technical.avg_latency_ms !== null
      ? `${Math.round(data.technical.avg_latency_ms)} ms`
      : "—";
    $("stat-avg-tokens").textContent = formatNumber(Math.round(data.technical.avg_tokens_per_call));

    $("token-table-body").innerHTML = TOKEN_ROWS.map(([key, label]) => {
      const t = data.tokens[key];
      return `
        <tr>
          <td>${label}</td>
          <td>${formatNumber(t.calls)}</td>
          <td>${formatNumber(t.prompt_tokens)}</td>
          <td>${formatNumber(t.completion_tokens)}</td>
          <td>${formatNumber(t.total_tokens)}</td>
        </tr>`;
    }).join("");

    renderTokenTopicTrend(data.token_trend_by_topic);
    renderCorrelation(data.satisfaction_latency_correlation);
  }

  if (canAccess("audit_trail")) {
    renderAuditIntegrity(integrity);
  }

  $("last-updated").textContent = data ? `Updated ${new Date(data.generated_at).toLocaleTimeString()}` : `Updated ${new Date().toLocaleTimeString()}`;
}

$("refresh-btn").addEventListener("click", () => loadDashboard().catch(console.error));

loadDashboard().catch((err) => {
  console.error(err);
  $("last-updated").textContent = "Could not load metrics";
});

// Keep the dashboard reasonably live for anyone leaving it open on a screen.
setInterval(() => loadDashboard().catch(console.error), 30000);
