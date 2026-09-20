const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const chipsEl = document.getElementById("chips");
const attachBtn = document.getElementById("attach-btn");
const fileInput = document.getElementById("file-input");
const attachmentPreviewEl = document.getElementById("attachment-preview");
const fillFormBtn = document.getElementById("fill-form-btn");
const micBtn = document.getElementById("mic-btn");
const humanBtn = document.getElementById("human-btn");
const humanBtnLabel = document.getElementById("human-btn-label");
const langToggleEl = document.getElementById("lang-toggle");
let greetingLabelEl = document.getElementById("greeting-label");
let greetingTextEl = document.getElementById("greeting-text");
const sendBtn = document.getElementById("send-btn");
const homeBtn = document.getElementById("home-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const chatsSectionEl = document.getElementById("chats-section");
const chatsSectionBodyEl = document.getElementById("chats-section-body");
const chatsToggleBtn = document.getElementById("chats-toggle-btn");
const chatListEl = document.getElementById("chat-list");
const planPanelEl = document.getElementById("plan-panel");
const chatSearchInputEl = document.getElementById("chat-search-input");
const sidebarHideBtn = document.getElementById("sidebar-hide-btn");
const sidebarShowBtn = document.getElementById("sidebar-show-btn");
const chatShellEl = document.querySelector(".chat-shell");
const ratingBarEl = document.getElementById("rating-bar");
const ratingLabelEl = document.getElementById("rating-label");
const ratingStarsEl = document.getElementById("rating-stars");
const progressRingBarEl = document.getElementById("progress-ring-bar");
const progressRingFillEl = document.getElementById("progress-ring-fill");
const progressRingPercentEl = document.getElementById("progress-ring-percent");
const progressRingTitleEl = document.getElementById("progress-ring-title");
const progressStepsEl = document.getElementById("progress-steps");
const PROGRESS_RING_CIRCUMFERENCE = 2 * Math.PI * 28;
const portfolioPanelEl = document.getElementById("portfolio-panel");
const portfolioTitleEl = document.getElementById("portfolio-title");
const portfolioItemsEl = document.getElementById("portfolio-items");
const portfolioToggleBtn = document.getElementById("portfolio-toggle-btn");
const chatListHeadingEl = document.getElementById("chat-list-heading");

// Persisted per-browser, same pattern as the plan panel's own collapse
// state (ltn-plan-collapsed) - see buildPlanPanelShell below.
let portfolioCollapsed = localStorage.getItem("ltn-portfolio-collapsed") === "1";
function applyPortfolioCollapsed() {
  portfolioItemsEl.hidden = portfolioCollapsed;
  portfolioToggleBtn.textContent = portfolioCollapsed ? "+" : "−";
  portfolioToggleBtn.title = portfolioCollapsed ? "Expand" : "Minimize";
  portfolioToggleBtn.setAttribute("aria-expanded", String(!portfolioCollapsed));
}
portfolioToggleBtn.addEventListener("click", () => {
  portfolioCollapsed = !portfolioCollapsed;
  localStorage.setItem("ltn-portfolio-collapsed", portfolioCollapsed ? "1" : "0");
  applyPortfolioCollapsed();
});
applyPortfolioCollapsed();

// The toggle sets the UI language and is a fallback for ambiguous messages,
// but the backend still matches whatever language the user actually types
// whenever that's clear -- see the LANGUAGE RULE in backend/agent.py.
const I18N = {
  en: {
    brandSub: "LF Bergslagen",
    greetingLabel: "Sara · Digital Companion",
    greeting:
      "Hej! I'm Sara, LF Bergslagen's digital companion. Tell me what's changing in your life, and I'll help you think it through.",
    placeholder: "Tell me what's happening in your life...",
    send: "Send",
    humanBtn: "Contact us",
    humanConnecting: "Connecting...",
    humanNote:
      "You've asked to speak with a colleague at LF Bergslagen. They'll join this chat as soon as they're available — keep this page open.",
    agentJoinedSuffix: "has joined the chat and will respond shortly.",
    attachTitle: "Attach a document",
    micTitle: "Speak instead of typing",
    sidebarHideTitle: "Hide previous chats",
    sidebarShowTitle: "Show previous chats",
    chatsHeading: "Chats",
    chatSearchPlaceholder: "Search previous chats...",
    chatSearchEmpty: "No chats match your search.",
    chatGoneNotice: "That chat is no longer available on the server and was removed from this list.",
    supportLabel: "LF Bergslagen · Support",
    aiLabel: "Sara · Digital Companion",
    thinking: "Thinking...",
    authComplete: "Authentication Complete",
    uploadError: "Couldn't read one of those files. Try files under 5MB each.",
    chatError: "Something went wrong reaching the navigator. Please try again.",
    speechLang: "en-US",
    rateLabel: "How helpful was this chat?",
    rateThanks: "Thanks for your feedback!",
    offersHeading: "You might also be interested in",
    topicPrompt: "Not sure where to start? Choose a topic",
    portfolioTitle: "Your activity",
    portfolioEmpty: "Nothing here yet.",
    portfolioUrgent: "Urgent",
    portfolioCompleted: "Completed",
    activityChats: "Chats with Sara",
    activityCasesOpen: "Open",
    activityCasesInProgress: "In progress",
    activityCasesClosed: "Closed",
    activityTopTopics: "Top topics",
    activityTopUrgent: "Most urgent cases",
    activityNoCases: "No cases yet.",
    activityNoTopics: "No topics yet.",
    planEmptyHeading: "My transition plan",
    planEmptyCopy: "Buying a home? Create a checklist you can update as you go.",
    planCreateBtn: "Create home-purchase plan",
    planToggleExpand: "Expand",
    planToggleMinimize: "Minimize",
    planProgress: "complete",
    planKeyDate: "Key date",
    planDue: "Due",
    planPriorityHigh: "high priority",
    planPriorityMedium: "medium priority",
    planPriorityLow: "low priority",
    planPhaseThisWeek: "First week",
    planPhaseSecureMortgage: "Secure mortgage",
    planPhaseBeforeMoveIn: "Before move-in",
    planPhaseLater: "Later",
    planTitleHomePurchase: "My home purchase",
    chips: [
      { label: "Buying a house", text: "I'd like help with buying a house" },
      { label: "Moving in together", text: "My partner and I are moving in together" },
      { label: "Having a child", text: "We're having a baby soon" },
      { label: "Divorce", text: "I'm going through a divorce" },
      { label: "Starting a business", text: "I'm starting my own business" },
      { label: "Retirement", text: "I'm retiring soon" },
      { label: "Buying a holiday home", text: "I'd like help with buying a holiday home" },
      { label: "Buying a car", text: "I'd like help with buying a car" },
      { label: "Report Fraud", text: "I want to report fraud" },
      { label: "Dispute a Transaction", text: "I want to dispute a transaction" },
      { label: "My product portfolio", text: "I'd like to see my current products with Länsförsäkringar" },
      { label: "Request a callback", text: "I'd like to request a callback" },
      { label: "Check case status", text: "I'd like to check the status of my case" },
      { label: "Apply for a mortgage", text: "I want to apply for a mortgage" },
    ],
  },
  sv: {
    brandSub: "LF Bergslagen",
    greetingLabel: "Sara · Digital följeslagare",
    greeting:
      "Hej! Jag heter Sara och är LF Bergslagens digitala följeslagare. Berätta vad som händer i ditt liv, så hjälper jag dig tänka igenom det.",
    placeholder: "Berätta vad som händer i ditt liv...",
    send: "Skicka",
    humanBtn: "Kontakta oss",
    humanConnecting: "Kopplar upp...",
    humanNote:
      "Du har bett om att prata med en kollega på LF Bergslagen. De ansluter till chatten så snart de kan — håll sidan öppen.",
    agentJoinedSuffix: "har anslutit till chatten och svarar snart.",
    attachTitle: "Bifoga ett dokument",
    micTitle: "Prata istället för att skriva",
    sidebarHideTitle: "Dölj tidigare chattar",
    sidebarShowTitle: "Visa tidigare chattar",
    chatsHeading: "Chattar",
    chatSearchPlaceholder: "Sök i tidigare chattar...",
    chatSearchEmpty: "Inga chattar matchar din sökning.",
    chatGoneNotice: "Den chatten finns inte längre på servern och togs bort från listan.",
    supportLabel: "LF Bergslagen · Support",
    aiLabel: "Sara · Digital följeslagare",
    thinking: "Tänker...",
    authComplete: "Autentisering slutförd",
    uploadError: "Kunde inte läsa en av filerna. Prova filer under 5 MB styck.",
    chatError: "Något gick fel. Försök igen.",
    speechLang: "sv-SE",
    rateLabel: "Hur hjälpsam var den här chatten?",
    rateThanks: "Tack för din feedback!",
    offersHeading: "Detta kan också intressera dig",
    topicPrompt: "Osäker på var du ska börja? Välj ett ämne",
    portfolioTitle: "Din aktivitet",
    portfolioEmpty: "Inget här ännu.",
    portfolioUrgent: "Brådskande",
    portfolioCompleted: "Klart",
    activityChats: "Chattar med Sara",
    activityCasesOpen: "Öppna",
    activityCasesInProgress: "Pågående",
    activityCasesClosed: "Avslutade",
    activityTopTopics: "Vanligaste ämnen",
    activityTopUrgent: "Mest brådskande ärenden",
    activityNoCases: "Inga ärenden ännu.",
    activityNoTopics: "Inga ämnen ännu.",
    planEmptyHeading: "Min övergångsplan",
    planEmptyCopy: "Ska du köpa bostad? Skapa en checklista du kan uppdatera efter hand.",
    planCreateBtn: "Skapa checklista för bostadsköp",
    planToggleExpand: "Visa",
    planToggleMinimize: "Minimera",
    planProgress: "klara",
    planKeyDate: "Nyckeldatum",
    planDue: "Förfaller",
    planPriorityHigh: "hög prioritet",
    planPriorityMedium: "medelhög prioritet",
    planPriorityLow: "låg prioritet",
    planPhaseThisWeek: "Första veckan",
    planPhaseSecureMortgage: "Säkra bolånet",
    planPhaseBeforeMoveIn: "Före inflyttning",
    planPhaseLater: "Senare",
    planTitleHomePurchase: "Mitt bostadsköp",
    chips: [
      { label: "Köpa hus", text: "Jag skulle vilja ha hjälp med att köpa hus" },
      { label: "Flytta ihop", text: "Min partner och jag ska flytta ihop" },
      { label: "Väntar barn", text: "Vi ska snart få barn" },
      { label: "Skilsmässa", text: "Jag går igenom en skilsmässa" },
      { label: "Starta eget", text: "Jag ska starta eget företag" },
      { label: "Pension", text: "Jag ska snart gå i pension" },
      { label: "Köpa fritidshus", text: "Jag skulle vilja ha hjälp med att köpa ett fritidshus" },
      { label: "Köpa bil", text: "Jag skulle vilja ha hjälp med att köpa en bil" },
      { label: "Anmäl bedrägeri", text: "Jag vill anmäla ett bedrägeri" },
      { label: "Bestrid en transaktion", text: "Jag vill bestrida en transaktion" },
      { label: "Min produktportfölj", text: "Jag skulle vilja se mina nuvarande produkter hos Länsförsäkringar" },
      { label: "Begär återuppringning", text: "Jag skulle vilja begära en återuppringning" },
      { label: "Kolla ärendestatus", text: "Jag skulle vilja kolla status på mitt ärende" },
      { label: "Ansök om bolån", text: "Jag vill ansöka om ett bolån" },
    ],
  },
};

// Parenthesized deliberately: `? :` binds looser than `||`, so without the
// parens this evaluated as (A || B) ? "sv" : "en" - any truthy saved
// preference (even "en" itself) short-circuited straight to "sv" on every
// later reload, silently overriding an explicit English choice.
let currentLang = localStorage.getItem("ltn-lang") || ((navigator.language || "").startsWith("sv") ? "sv" : "en");
if (!I18N[currentLang]) currentLang = "en";

function t() {
  return I18N[currentLang];
}

function applyLanguage(lang) {
  currentLang = I18N[lang] ? lang : "en";
  localStorage.setItem("ltn-lang", currentLang);
  const strings = t();

  document.querySelectorAll(".brand-sub").forEach((el) => (el.textContent = strings.brandSub));
  chatListHeadingEl.textContent = strings.chatsHeading;
  applyChatsCollapsed();
  greetingLabelEl.textContent = strings.greetingLabel;
  greetingTextEl.textContent = strings.greeting;
  inputEl.placeholder = strings.placeholder;
  sendBtn.textContent = strings.send;
  humanBtnLabel.textContent = strings.humanBtn;
  attachBtn.title = strings.attachTitle;
  micBtn.title = strings.micTitle;
  sidebarHideBtn.title = strings.sidebarHideTitle;
  sidebarShowBtn.title = strings.sidebarShowTitle;
  chatSearchInputEl.placeholder = strings.chatSearchPlaceholder;
  renderChatList();
  if (!ratingSubmitted) ratingLabelEl.textContent = strings.rateLabel;
  portfolioTitleEl.textContent = strings.portfolioTitle;
  // Plan/activity panel content is rendered client-side from t() (see
  // renderPlan/renderActivitySummary), so switching languages needs to
  // re-render them explicitly - they don't otherwise refresh until the
  // next chat turn. Both are cheap and no-ops when nothing's loaded yet.
  loadPlan();
  refreshPortfolioPanel();

  chipsEl.innerHTML = "";
  const dropdown = document.createElement("div");
  dropdown.className = "topic-dropdown";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "topic-dropdown-toggle";
  toggle.innerHTML = `<span>${strings.topicPrompt}</span><span class="caret">▾</span>`;

  const menu = document.createElement("div");
  menu.className = "topic-dropdown-menu";
  menu.hidden = true;

  for (const chip of strings.chips) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "topic-dropdown-item";
    item.dataset.text = chip.text;
    item.textContent = chip.label;
    menu.appendChild(item);
  }

  toggle.addEventListener("click", () => {
    menu.hidden = !menu.hidden;
    toggle.classList.toggle("open", !menu.hidden);
  });

  dropdown.append(toggle, menu);
  chipsEl.appendChild(dropdown);

  langToggleEl.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === currentLang);
  });
}

langToggleEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".lang-btn");
  if (!btn) return;
  applyLanguage(btn.dataset.lang);
});

let history = [];
let stagedFiles = [];
let ratingSubmitted = false; // this session already sent a satisfaction rating
let sessionMessageCount = 0; // how many session-store messages we've already accounted for
let humanHandoffActive = false; // once true, the composer talks to a human, not the AI
let lastKnownAgent = null; // name of the CS agent assigned to this session, if any
let activeForm = null; // control handle for the most recently rendered inline form (see addForm), or null once there's nothing pending to confirm/correct
// Embedded in the marketing site's widget iframe (site.js sets
// frameEl.src = "index.html")? sessionStorage is scoped to the OUTER TAB,
// not to this iframe's own lifetime - it survives across separate visits
// to the marketing site in the same browser tab, long after any earlier
// widget conversation should be considered over. A directly-visited
// standalone page (window === window.top) is the opposite case: reloading
// THAT page should keep resuming its own conversation (see
// restoreCurrentSession below), so only the embedded case skips reusing a
// leftover session id.
const isEmbeddedWidget = window.self !== window.top;
let sessionId =
  (isEmbeddedWidget ? null : sessionStorage.getItem("ltn-session-id")) ||
  (() => {
    const id = crypto.randomUUID();
    sessionStorage.setItem("ltn-session-id", id);
    return id;
  })();

// The last session_id in THIS browser tab that actually verified identity
// (see refreshPortfolioPanel). Once set, it's used as a FALLBACK source for
// the plan/activity/chats panels whenever the currently-viewed chat
// (sessionId, which can be a completely different, never-verified past
// chat the customer just clicked open) hasn't itself verified - otherwise
// switching to any old, unverified chat would hide those panels entirely
// and make it look like the customer had been logged out, even though
// she's still the same verified person browsing her own chat history.
// Cleared only by startNewChat, matching the "verify every new chat" rule.
let verifiedSessionId = null;

// Phase/title/priority labels are rendered client-side from t() (see I18N
// above) rather than trusting plan.event_title etc from the server, so the
// left panel's language always matches the chat language toggle - the
// server only stores stable, language-neutral identifiers (phase id,
// event_type, priority id).
const PLAN_PHASE_KEYS = {
  this_week: "planPhaseThisWeek",
  secure_mortgage: "planPhaseSecureMortgage",
  before_move_in: "planPhaseBeforeMoveIn",
  later: "planPhaseLater",
};
const PLAN_TITLE_KEYS = {
  home_purchase: "planTitleHomePurchase",
};
const PLAN_PRIORITY_KEYS = {
  high: "planPriorityHigh",
  medium: "planPriorityMedium",
  low: "planPriorityLow",
};

// Persisted per-browser so the panel stays collapsed/expanded across the
// repeated re-renders every chat reply triggers (loadPlan runs after each
// turn) and across page reloads - a per-viewer convenience, not shared
// state, so plain localStorage is the right fit here.
let planPanelCollapsed = localStorage.getItem("ltn-plan-collapsed") === "1";

function clearPlanPanel() {
  planPanelEl.innerHTML = "";
}

// Shared by renderEmptyPlan/renderPlan below: a header row with the title
// plus a collapse/expand toggle, and a body wrapper whose visibility
// reflects planPanelCollapsed. Returns the body element for the caller to
// append its own content into.
function buildPlanPanelShell(titleText) {
  const header = document.createElement("div");
  header.className = "plan-panel-header";

  const heading = document.createElement("h2");
  heading.className = "plan-heading";
  heading.textContent = titleText;

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "plan-panel-toggle-btn";
  toggleBtn.setAttribute("aria-expanded", String(!planPanelCollapsed));
  toggleBtn.title = planPanelCollapsed ? t().planToggleExpand : t().planToggleMinimize;
  toggleBtn.textContent = planPanelCollapsed ? "+" : "−";

  const body = document.createElement("div");
  body.className = "plan-panel-body";
  body.hidden = planPanelCollapsed;

  toggleBtn.addEventListener("click", () => {
    planPanelCollapsed = !planPanelCollapsed;
    localStorage.setItem("ltn-plan-collapsed", planPanelCollapsed ? "1" : "0");
    body.hidden = planPanelCollapsed;
    toggleBtn.textContent = planPanelCollapsed ? "+" : "−";
    toggleBtn.title = planPanelCollapsed ? t().planToggleExpand : t().planToggleMinimize;
    toggleBtn.setAttribute("aria-expanded", String(!planPanelCollapsed));
  });

  header.append(heading, toggleBtn);
  planPanelEl.append(header, body);
  return body;
}

function renderEmptyPlan() {
  clearPlanPanel();
  const body = buildPlanPanelShell(t().planEmptyHeading);
  const copy = document.createElement("p");
  copy.className = "plan-empty-copy";
  copy.textContent = t().planEmptyCopy;
  const button = document.createElement("button");
  button.className = "plan-create-btn";
  button.type = "button";
  button.textContent = t().planCreateBtn;
  button.addEventListener("click", createHomePurchasePlan);
  body.append(copy, button);
}

function renderPlan(plan) {
  clearPlanPanel();
  const strings = t();
  const title = PLAN_TITLE_KEYS[plan.event_type] ? strings[PLAN_TITLE_KEYS[plan.event_type]] : plan.event_title;
  const body = buildPlanPanelShell(title);
  const completed = plan.tasks.filter((task) => task.status === "done").length;
  const progress = document.createElement("p");
  progress.className = "plan-progress";
  progress.textContent = `${completed} / ${plan.tasks.length} ${strings.planProgress}`;
  body.append(progress);
  if (plan.key_date) {
    const date = document.createElement("p");
    date.className = "plan-date";
    date.textContent = `${strings.planKeyDate}: ${plan.key_date}`;
    body.appendChild(date);
  }

  for (const phase of ["this_week", "secure_mortgage", "before_move_in", "later"]) {
    const tasks = plan.tasks.filter((task) => task.phase === phase);
    if (!tasks.length) continue;
    const phaseHeading = document.createElement("h3");
    phaseHeading.className = "plan-phase";
    phaseHeading.textContent = strings[PLAN_PHASE_KEYS[phase]];
    body.appendChild(phaseHeading);
    tasks.forEach((task) => {
      const row = document.createElement("div");
      row.className = `plan-task${task.status === "done" ? " done" : ""}`;
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = task.status === "done";
      checkbox.id = `plan-${task.id}`;
      checkbox.addEventListener("change", () => updatePlanTask(task.id, checkbox.checked, checkbox));
      const label = document.createElement("label");
      label.className = "plan-task-label";
      label.htmlFor = checkbox.id;
      label.title = task.description;
      const title = document.createElement("span");
      title.className = "plan-task-title";
      title.textContent = task.title;
      const meta = document.createElement("span");
      meta.className = "plan-task-meta";
      meta.textContent = task.due_date
        ? `${strings.planDue} ${task.due_date}`
        : strings[PLAN_PRIORITY_KEYS[task.priority]] || task.priority;
      label.append(title, meta);
      row.append(checkbox, label);
      body.appendChild(row);
    });
  }
}

async function fetchPlanFor(forSessionId) {
  const res = await fetch(`/api/plans/session/${forSessionId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Plan request failed: ${res.status}`);
  return res.json();
}

async function loadPlan() {
  const requestedSessionId = sessionId;
  try {
    let plan = await fetchPlanFor(requestedSessionId);
    // The user can switch/start a chat while this request is in flight (e.g.
    // clicking "+ New chat" right after sending a message) - a late response
    // for the OLD session must never clobber the panel now showing a
    // DIFFERENT session, so it's discarded rather than rendered.
    if (sessionId !== requestedSessionId) return;

    // This exact chat has no plan of its own - if an EARLIER chat in this
    // browser tab verified identity, fall back to that customer's plan
    // instead of showing empty, so browsing a different (possibly
    // never-verified) past chat doesn't make her home-purchase progress
    // disappear (see verifiedSessionId above).
    if (!plan && verifiedSessionId && verifiedSessionId !== requestedSessionId) {
      plan = await fetchPlanFor(verifiedSessionId);
      if (sessionId !== requestedSessionId) return;
    }

    if (!plan) {
      renderEmptyPlan();
      return;
    }
    renderPlan(plan);
  } catch (err) {
    console.error(err);
  }
}

async function createHomePurchasePlan() {
  try {
    const res = await fetch("/api/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, event_type: "home_purchase" }),
    });
    if (!res.ok) throw new Error(`Plan creation failed: ${res.status}`);
    renderPlan(await res.json());
  } catch (err) {
    console.error(err);
  }
}

async function updatePlanTask(taskId, checked, checkbox) {
  checkbox.disabled = true;
  try {
    const res = await fetch(`/api/plans/session/${sessionId}/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: checked ? "done" : "todo" }),
    });
    if (!res.ok) throw new Error(`Plan update failed: ${res.status}`);
    renderPlan(await res.json());
  } catch (err) {
    checkbox.checked = !checked;
    checkbox.disabled = false;
    console.error(err);
  }
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Applied to already-escaped text, so only well-formed http(s)/tel/mailto
// URLs get turned into real links -- no way to smuggle a javascript: URI.
function linkify(text) {
  return text.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+|tel:[^\s)]+|mailto:[^\s)]+)\)/g,
    (_match, label, url) =>
      `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
  );
}

function boldify(text) {
  return text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function inline(text) {
  return boldify(linkify(text));
}

// Minimal markdown: headings, paragraphs, bullet/numbered lists, **bold**,
// [text](url). Enough for the agent's structured replies without a full lib.
function renderMarkdown(raw) {
  const lines = escapeHtml(raw).split("\n");
  let html = "";
  let listType = null;
  let listItems = [];
  let paraLines = [];

  function flushList() {
    if (listItems.length) {
      const tag = listType === "ol" ? "ol" : "ul";
      html += `<${tag}>${listItems.map((li) => `<li>${inline(li)}</li>`).join("")}</${tag}>`;
    }
    listItems = [];
    listType = null;
  }

  function flushPara() {
    if (paraLines.length) {
      html += `<p>${paraLines.map(inline).join("<br>")}</p>`;
    }
    paraLines = [];
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const heading = line.match(/^#{1,6}\s+(.*)/);
    const bullet = line.match(/^[-*]\s+(.*)/);
    const numbered = line.match(/^\d+\.\s+(.*)/);

    if (heading) {
      flushList();
      flushPara();
      html += `<p><strong>${inline(heading[1])}</strong></p>`;
    } else if (bullet) {
      flushPara();
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listItems.push(bullet[1]);
    } else if (numbered) {
      flushPara();
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listItems.push(numbered[1]);
    } else if (line === "") {
      // Deliberately does NOT flush the list here: an LLM commonly puts a
      // blank line between numbered/bulleted items for readability, and
      // flushing on every one of those would split one list into a run of
      // single-item lists (each starting back at "1."). The list closes
      // naturally below, when real non-list content follows, or via the
      // final flushList() once the message ends.
      flushPara();
    } else {
      flushList();
      paraLines.push(line);
    }
  }
  flushList();
  flushPara();
  return html;
}

// --- Read-aloud (browser text-to-speech, no backend involved) ---

const speechSupported = "speechSynthesis" in window;
let speakingBtn = null;
let cachedVoices = [];

if (speechSupported) {
  const refreshVoices = () => {
    cachedVoices = window.speechSynthesis.getVoices();
  };
  refreshVoices();
  window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
}

// Prefer a natural-sounding, clearly-female voice matching the reply's
// language (Sara is presented as a woman) over whatever default voice the
// browser would otherwise pick, which is often a flat/robotic fallback.
function pickVoice(lang) {
  if (!cachedVoices.length) return null;
  const prefix = lang.split("-")[0];
  const sameLang = cachedVoices.filter((v) => v.lang && v.lang.toLowerCase().startsWith(prefix));
  const pool = sameLang.length ? sameLang : cachedVoices;
  const female = pool.find((v) => /female|zira|susan|hedda|elsa|alva|natural/i.test(v.name));
  return female || pool[0] || null;
}

// Strip markdown syntax so the reply is actually spoken as natural language
// instead of literal symbols ("asterisk asterisk", raw URLs, "hashtag", ...).
function stripMarkdownForSpeech(text) {
  return text
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|tel:|mailto:)[^\s)]+\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .replace(/^\d+\.\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function speak(text, lang, btn) {
  if (!speechSupported) return;
  if (speakingBtn === btn) {
    window.speechSynthesis.cancel();
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(stripMarkdownForSpeech(text));
  utterance.lang = lang;
  const voice = pickVoice(lang);
  if (voice) utterance.voice = voice;
  utterance.onend = utterance.onerror = () => {
    if (speakingBtn) speakingBtn.classList.remove("speaking");
    speakingBtn = null;
  };
  speakingBtn = btn;
  btn.classList.add("speaking");
  window.speechSynthesis.speak(utterance);
}

function addSpeakButton(labelEl, text) {
  if (!speechSupported) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "speak-btn";
  btn.title = "Listen to this answer";
  btn.textContent = "🔊";
  btn.addEventListener("click", () => speak(text, t().speechLang, btn));
  labelEl.appendChild(btn);
}

function addBubble(role, text, { markdown = false, label = "", speakable = false } = {}) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  let labelEl = null;
  if (label) {
    labelEl = document.createElement("span");
    labelEl.className = "msg-label";
    const labelText = document.createElement("span");
    labelText.className = "msg-label-text";
    labelText.textContent = label;
    labelEl.appendChild(labelText);
    div.appendChild(labelEl);
  }
  if (markdown) {
    div.insertAdjacentHTML("beforeend", renderMarkdown(text));
  } else {
    div.appendChild(document.createTextNode(text));
  }
  if (speakable && labelEl) {
    addSpeakButton(labelEl, text);
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

// Small muted status bubble styled like the auth card above it. Inserted
// before `before` when given, otherwise appended.
function addStatusMessage(text, before = null) {
  const div = document.createElement("div");
  div.className = "chat-status-message";
  div.textContent = text;
  messagesEl.insertBefore(div, before);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Set by the auth card's Continue click; consumed by the next
// getAssistantReply so "Authentication Complete" shows once per chat session.
let authStatusPending = false;
const authStatusShownFor = new Set();

// Which family a file belongs to, used both to pick an icon and to decide
// how (or whether) the browser can actually render the original file.
function getFileKind(filename, mimeType) {
  const lower = (filename || "").toLowerCase();
  if ((mimeType && mimeType.startsWith("image/")) || /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(lower)) {
    return "image";
  }
  if (lower.endsWith(".pdf")) return "pdf";
  if (lower.endsWith(".docx") || lower.endsWith(".doc")) return "doc";
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) return "sheet";
  if (lower.endsWith(".txt")) return "text";
  return "other";
}

const FILE_KIND_ICON = {
  image: "🖼️",
  pdf: "📕",
  doc: "📄",
  sheet: "📊",
  text: "📃",
  other: "📎",
};

function addAttachmentBubble(attachments) {
  if (!attachments.length) return;

  const div = document.createElement("div");
  div.className = "msg attachment";

  const title = document.createElement("div");
  title.className = "sent-attachment-title";
  title.textContent = `Attached ${attachments.length} file${attachments.length === 1 ? "" : "s"}`;
  div.appendChild(title);

  for (const attachment of attachments) {
    const row = document.createElement("div");
    row.className = "sent-attachment";

    if (attachment.kind === "image" && attachment.previewUrl) {
      const preview = document.createElement("img");
      preview.className = "sent-attachment-thumb";
      preview.src = attachment.previewUrl;
      preview.alt = attachment.filename;
      row.appendChild(preview);
    } else {
      const icon = document.createElement("span");
      icon.className = "sent-attachment-icon";
      icon.textContent = FILE_KIND_ICON[attachment.kind] || FILE_KIND_ICON.other;
      row.appendChild(icon);
    }

    const name = document.createElement("span");
    name.className = "sent-attachment-name";
    name.textContent = attachment.filename;
    name.title = attachment.filename;
    row.appendChild(name);

    const view = document.createElement("button");
    view.type = "button";
    view.className = "sent-attachment-view";
    view.textContent = "View";
    view.addEventListener("click", () => showAttachmentViewer(attachment));
    row.appendChild(view);

    div.appendChild(row);
  }

  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Shows the actual attached file whenever the browser can render it natively
// (images, PDFs). For formats browsers can't display inline (Word, Excel,
// legacy .doc/.xls, ...) it offers the real original file to open/download,
// plus the plain-text version Sara read, clearly labelled as a fallback --
// never presenting extracted text as if it were the document itself.
function showAttachmentViewer(attachment) {
  const overlay = document.createElement("div");
  overlay.className = "attachment-viewer";

  const modal = document.createElement("div");
  modal.className = "attachment-viewer-modal";

  const header = document.createElement("div");
  header.className = "attachment-viewer-header";

  const title = document.createElement("strong");
  title.textContent = attachment.filename;

  const headerActions = document.createElement("div");
  headerActions.className = "attachment-viewer-actions";

  if (attachment.previewUrl) {
    const openLink = document.createElement("a");
    openLink.className = "attachment-viewer-open";
    openLink.href = attachment.previewUrl;
    openLink.download = attachment.filename;
    openLink.textContent = "Download";
    headerActions.appendChild(openLink);
  }

  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => overlay.remove());
  headerActions.appendChild(close);

  header.append(title, headerActions);
  modal.appendChild(header);

  const canRenderNatively = attachment.previewUrl && (attachment.kind === "image" || attachment.kind === "pdf");

  if (attachment.kind === "image" && attachment.previewUrl) {
    const image = document.createElement("img");
    image.className = "attachment-viewer-image";
    image.src = attachment.previewUrl;
    image.alt = attachment.filename;
    modal.appendChild(image);
  } else if (attachment.kind === "pdf" && attachment.previewUrl) {
    const frame = document.createElement("iframe");
    frame.className = "attachment-viewer-frame";
    frame.src = attachment.previewUrl;
    frame.title = attachment.filename;
    modal.appendChild(frame);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "attachment-viewer-placeholder";
    const icon = document.createElement("span");
    icon.className = "attachment-viewer-placeholder-icon";
    icon.textContent = FILE_KIND_ICON[attachment.kind] || FILE_KIND_ICON.other;
    placeholder.appendChild(icon);
    const note = document.createElement("p");
    note.textContent = attachment.previewUrl
      ? "This file type can't be previewed in the browser. Download it to open the original."
      : "The original file isn't available to preview in this chat history -- here's the text Sara read from it.";
    placeholder.appendChild(note);
    modal.appendChild(placeholder);
  }

  if (attachment.text && !canRenderNatively) {
    const contentLabel = document.createElement("div");
    contentLabel.className = "attachment-viewer-content-label";
    contentLabel.textContent = "Text Sara read from this file";
    modal.appendChild(contentLabel);

    const content = document.createElement("pre");
    content.className = "attachment-viewer-content";
    content.textContent = attachment.text;
    modal.appendChild(content);
  }

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) overlay.remove();
  });

  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Escape") overlay.remove();
    },
    { once: true }
  );

  overlay.appendChild(modal);
  document.body.appendChild(overlay);
}

// --- Follow-up suggestion chips shown under an assistant reply ---

function addSuggestions(suggestions, humanChatOption) {
  if (!suggestions || !suggestions.length) return;
  const div = document.createElement("div");
  div.className = "suggestions";
  for (const suggestion of suggestions) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "suggestion-chip";
    btn.textContent = suggestion;
    if (humanChatOption && suggestion === humanChatOption) {
      btn.addEventListener("click", () => {
        div.remove();
        requestHumanHandoff();
      });
    } else {
      btn.addEventListener("click", () => {
        div.remove();
        sendMessage(suggestion);
      });
    }
    div.appendChild(btn);
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Next Best Action offer cards: shown right after the backend has just
// identity-verified the customer (see backend/verified_customer.py) and
// picked a handful of relevant offers (backend/nba_engine.py). Clicking
// "Learn more" opens the real LF Bergslagen page AND reports the click back
// so the underlying bandit model learns from it - see /api/offers/click. ---
function addOffers(offers, customerId) {
  if (!offers || !offers.length || !customerId) return;

  const wrapper = document.createElement("div");
  wrapper.className = "offers-wrapper";

  const heading = document.createElement("div");
  heading.className = "offers-heading";
  heading.textContent = t().offersHeading;
  wrapper.appendChild(heading);

  const row = document.createElement("div");
  row.className = "offers-row";

  for (const offer of offers) {
    const card = document.createElement("div");
    card.className = "offer-card";
    card.innerHTML = `
      <img class="offer-card-image" src="${offer.image}" alt="${escapeHtml(offer.category)}" />
      <div class="offer-card-body">
        <span class="offer-card-category">${escapeHtml(offer.category)}</span>
        <h4 class="offer-card-title">${escapeHtml(offer.title)}</h4>
        <p class="offer-card-teaser">${escapeHtml(offer.teaser)}</p>
        <a class="offer-card-cta" href="${offer.cta_url || '#'}" target="_blank" rel="noopener noreferrer">${escapeHtml(offer.cta_label)}</a>
      </div>
    `;
    const cta = card.querySelector(".offer-card-cta");
    cta.addEventListener("click", () => {
      fetch("/api/offers/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customer_id: customerId, offer_code: offer.code }),
      }).catch((err) => console.error(err));
    });
    row.appendChild(card);
  }

  wrapper.appendChild(row);
  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Link shown in chat after a confirmed form is saved via POST /api/forms ---

function addFormSavedLink(url) {
  const div = document.createElement("div");
  div.className = "msg form-saved-note";
  const link = document.createElement("a");
  link.className = "form-saved-link";
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = currentLang === "sv" ? "Visa inlämnad ansökan →" : "View submitted form →";
  div.appendChild(link);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addFormSaveError() {
  const div = document.createElement("div");
  div.className = "msg form-save-error";
  div.textContent =
    currentLang === "sv"
      ? "Kunde inte spara ansökan — försök igen"
      : "Could not save the form — please try again";
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- "Your Activity" panel (left sidebar) ---
//
// Shown once this browser session has verified a customer's identity (see
// verify_customer_identity in backend/tools.py). Backed by
// GET /api/sessions/{sessionId}/activity-summary, which only returns data
// if the SERVER remembers this session_id as verified - the panel never
// sends or trusts a customer_id itself, so switching to a chat that was
// never verified in this browser just hides the panel instead of showing
// someone else's activity.

// Renders the "Your Activity" summary: chat count, case counts by status,
// top topics, top urgent cases - NOT the raw interaction-by-interaction
// list this panel used to show (see build_activity_summary in
// backend/interaction_history.py).
function renderActivitySummary(summary) {
  portfolioItemsEl.innerHTML = "";
  const strings = t();

  const chatsRow = document.createElement("div");
  chatsRow.className = "activity-stat-row";
  chatsRow.innerHTML = `<span class="activity-stat-label">${escapeHtml(strings.activityChats)}</span><span class="activity-stat-value">${summary.total_chats}</span>`;
  portfolioItemsEl.appendChild(chatsRow);

  const cases = summary.cases || { open: 0, in_progress: 0, closed: 0 };
  const casesSection = document.createElement("div");
  casesSection.className = "activity-section";
  casesSection.innerHTML = `
    <div class="activity-stat-row"><span class="activity-stat-label">${escapeHtml(strings.activityCasesOpen)}</span><span class="activity-stat-value">${cases.open}</span></div>
    <div class="activity-stat-row"><span class="activity-stat-label">${escapeHtml(strings.activityCasesInProgress)}</span><span class="activity-stat-value">${cases.in_progress}</span></div>
    <div class="activity-stat-row"><span class="activity-stat-label">${escapeHtml(strings.activityCasesClosed)}</span><span class="activity-stat-value">${cases.closed}</span></div>
  `;
  portfolioItemsEl.appendChild(casesSection);

  const topicsSection = document.createElement("div");
  topicsSection.className = "activity-section";
  const topicsHeading = document.createElement("div");
  topicsHeading.className = "activity-section-heading";
  topicsHeading.textContent = strings.activityTopTopics;
  topicsSection.appendChild(topicsHeading);
  if (summary.top_topics && summary.top_topics.length) {
    for (const topic of summary.top_topics) {
      const row = document.createElement("div");
      row.className = "activity-list-row";
      row.textContent = topic;
      topicsSection.appendChild(row);
    }
  } else {
    const empty = document.createElement("div");
    empty.className = "portfolio-empty";
    empty.textContent = strings.activityNoTopics;
    topicsSection.appendChild(empty);
  }
  portfolioItemsEl.appendChild(topicsSection);

  const urgentSection = document.createElement("div");
  urgentSection.className = "activity-section";
  const urgentHeading = document.createElement("div");
  urgentHeading.className = "activity-section-heading";
  urgentHeading.textContent = strings.activityTopUrgent;
  urgentSection.appendChild(urgentHeading);
  if (summary.top_urgent_cases && summary.top_urgent_cases.length) {
    for (const item of summary.top_urgent_cases) {
      const row = document.createElement("div");
      row.className = "activity-list-row";
      row.innerHTML = `${escapeHtml(item.label)}${item.status_label ? ` <span class="portfolio-case-id">${escapeHtml(item.status_label)}</span>` : ""}`;
      urgentSection.appendChild(row);
    }
  } else {
    const empty = document.createElement("div");
    empty.className = "portfolio-empty";
    empty.textContent = strings.activityNoCases;
    urgentSection.appendChild(empty);
  }
  portfolioItemsEl.appendChild(urgentSection);
}

// The "Chats" list (sidebar history) and "My Home Purchase" plan panel are
// both per-browser/per-conversation content that's meaningless to show to a
// visitor who hasn't verified their identity in THIS chat yet - the plan
// can be auto-created from chat text alone with no identity check (see
// agent.mentions_home_purchase), but the persisted, cross-chat CHECKLIST
// view of it is gated the same way "Your Activity" already is: hidden by
// default, revealed only once this session's customer has verified.
function setAuthenticatedSidebarVisible(visible) {
  chatsSectionEl.hidden = !visible;
  planPanelEl.hidden = !visible;
}

// Collapse/expand for the "Chats" section - same persisted-per-browser
// pattern as the plan panel's own toggle (ltn-plan-collapsed) and the
// portfolio panel's (ltn-portfolio-collapsed).
let chatsCollapsed = localStorage.getItem("ltn-chats-collapsed") === "1";
function applyChatsCollapsed() {
  chatsSectionBodyEl.hidden = chatsCollapsed;
  chatsToggleBtn.textContent = chatsCollapsed ? "+" : "−";
  chatsToggleBtn.title = chatsCollapsed ? t().planToggleExpand : t().planToggleMinimize;
  chatsToggleBtn.setAttribute("aria-expanded", String(!chatsCollapsed));
}
chatsToggleBtn.addEventListener("click", () => {
  chatsCollapsed = !chatsCollapsed;
  localStorage.setItem("ltn-chats-collapsed", chatsCollapsed ? "1" : "0");
  applyChatsCollapsed();
});
applyChatsCollapsed();

async function fetchActivityFor(forSessionId) {
  const res = await fetch(`/api/sessions/${forSessionId}/activity-summary`);
  if (!res.ok) return { verified: false };
  return res.json();
}

async function refreshPortfolioPanel() {
  const requestedSessionId = sessionId;
  try {
    let data = await fetchActivityFor(requestedSessionId);
    if (sessionId !== requestedSessionId) return; // see loadPlan's same guard
    let sourceSessionId = requestedSessionId;

    // This exact chat never verified - fall back to whichever session in
    // this browser tab DID, same reasoning as loadPlan's fallback above,
    // so the Chats/Activity/Plan panels stay up the whole time she's
    // browsing her own chat history, not just in the one chat where she
    // happened to verify.
    if (!data.verified && verifiedSessionId && verifiedSessionId !== requestedSessionId) {
      data = await fetchActivityFor(verifiedSessionId);
      if (sessionId !== requestedSessionId) return;
      sourceSessionId = verifiedSessionId;
    }

    if (!data.verified) {
      verifiedSessionId = null;
      portfolioPanelEl.hidden = true;
      setAuthenticatedSidebarVisible(false);
      return;
    }
    verifiedSessionId = sourceSessionId;
    portfolioPanelEl.hidden = false;
    setAuthenticatedSidebarVisible(true);
    renderActivitySummary(data);
    mergeCustomerChatHistory(data.customer_id);
  } catch (err) {
    console.error(err);
    portfolioPanelEl.hidden = true;
    setAuthenticatedSidebarVisible(false);
  }
}

// --- Inline structured form (e.g. fraud/dispute follow-up questions) ---
//
// The backend can't reliably free-parse an answer to "suspected place of
// fraud / block card? / block account?" from open text, so instead of
// asking those as chat questions, it sends a form schema and expects the
// answer back as one specific composed message it can regex-parse. The
// field->phrase mapping here has to match backend/agents/fraud_dispute_agent.py's
// FORM_ANSWER_RE exactly, or the backend won't recognize the answer.
const FORM_FIELD_ANSWER_PREFIX = {
  place: "Suspected place of fraud",
  block_card: "Block debit card",
  block_account: "Block debits on account",
  full_name: "Full name",
  personnummer: "Personnummer",
  dob: "Date of birth",
};

// The user's own confirmation text is too free-form (esp. in Swedish) to match
// reliably, so the primary signal is the agent's *reply*: backend/agent.py's
// FORM FILLING prompt (rule 1) always has the model mention a case officer/
// "handläggare" reviewing the details and that the form is ready for review
// once it treats the form as confirmed -- a fixed-enough phrase to detect,
// and one that isn't used anywhere else in the agent's replies. The user-text
// regexes below are a secondary check for the (less reliable) case where the
// reply doesn't happen to include that phrasing.
const FORM_CONFIRM_REPLY_RE = /(handl[äa]ggare|case officer|redo f[öo]r granskning|ready for review)/i;
const FORM_CONFIRM_RE = /\b(yes|that'?s (correct|right)|looks good|looks right|submit|confirmed?|tack|det st[äa]mmer|ja)\b/i;
const FORM_CHANGE_RE = /\b(change|update|fix|wrong|incorrect|[äa]ndra|byt|fel|uppdatera)\b/i;

function renderForm(form) {
  if (!form) return;
  if (form.type === "auth_choice") {
    addAuthChoice(form);
  } else if (form.type === "transaction_select") {
    addTransactionSelectForm(form);
  } else {
    addForm(form);
  }
}

// Fraud/dispute transaction picker: a real table with a checkbox per row,
// so the customer can flag one or several suspicious charges at once,
// instead of typing a row number or Transaction ID from a plain-text list.
// Submitting composes "Selected transactions: TXN-..., TXN-..." - the exact
// phrase backend/agents/fraud_dispute_agent.py's SELECTED_TXN_RE expects.
function addTransactionSelectForm(form) {
  if (!form || !form.transactions || !form.transactions.length) return;

  const wrapper = document.createElement("form");
  wrapper.className = "inline-form txn-select-form";

  const table = document.createElement("table");
  table.className = "txn-select-table";
  table.innerHTML = `
    <thead>
      <tr><th></th><th>Date</th><th>Merchant</th><th>Amount</th></tr>
    </thead>
  `;
  const tbody = document.createElement("tbody");

  const checkboxes = [];
  for (const txn of form.transactions) {
    const row = document.createElement("tr");

    const checkboxCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = txn.id;
    checkbox.id = `txn-${txn.id}`;
    checkboxes.push(checkbox);
    checkboxCell.appendChild(checkbox);
    row.appendChild(checkboxCell);

    const dateCell = document.createElement("td");
    dateCell.textContent = txn.date;
    row.appendChild(dateCell);

    const merchantCell = document.createElement("td");
    merchantCell.textContent = txn.merchant;
    row.appendChild(merchantCell);

    const amountCell = document.createElement("td");
    amountCell.textContent = txn.amount;
    amountCell.className = "txn-select-amount";
    row.appendChild(amountCell);

    row.addEventListener("click", (e) => {
      if (e.target !== checkbox) {
        checkbox.checked = !checkbox.checked;
      }
      row.classList.toggle("selected", checkbox.checked);
      updateSubmitState();
    });
    checkbox.addEventListener("click", (e) => e.stopPropagation());
    checkbox.addEventListener("change", () => {
      row.classList.toggle("selected", checkbox.checked);
      updateSubmitState();
    });

    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  wrapper.appendChild(table);

  const errorEl = document.createElement("p");
  errorEl.className = "inline-form-error";
  wrapper.appendChild(errorEl);

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "Dispute selected transactions";
  submitBtn.disabled = true;
  wrapper.appendChild(submitBtn);

  function updateSubmitState() {
    submitBtn.disabled = !checkboxes.some((cb) => cb.checked);
    errorEl.textContent = "";
  }

  wrapper.addEventListener("submit", (e) => {
    e.preventDefault();
    const selectedIds = checkboxes.filter((cb) => cb.checked).map((cb) => cb.value);
    if (!selectedIds.length) {
      errorEl.textContent = "Select at least one transaction.";
      return;
    }
    wrapper.remove();
    sendMessage(`Selected transactions: ${selectedIds.join(", ")}`);
  });

  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addForm(form) {
  if (!form || !form.fields || !form.fields.length) return;

  const wrapper = document.createElement("form");
  wrapper.className = "inline-form";

  const values = {};
  let formSubmitted = false;
  let formSaved = false; // guards against POSTing the same confirmed form twice

  if (form.title) {
    const title = document.createElement("h3");
    title.textContent = form.title;
    wrapper.appendChild(title);
  }

  const fieldsContainer = document.createElement("div");
  fieldsContainer.className = "inline-form-fields";
  wrapper.appendChild(fieldsContainer);

  const errorEl = document.createElement("p");
  errorEl.className = "inline-form-error";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "Submit";

  function renderEditableFields() {
    fieldsContainer.innerHTML = "";
    for (const field of form.fields) {
      const fieldEl = document.createElement("div");
      fieldEl.className = "inline-form-field";

      const label = document.createElement("label");
      label.textContent = field.label;
      fieldEl.appendChild(label);

      if (field.type === "yesno") {
        const group = document.createElement("div");
        group.className = "inline-form-yesno";
        for (const option of ["Yes", "No"]) {
          const optId = `${field.name}-${option}`;
          const radioLabel = document.createElement("label");
          radioLabel.className = "inline-form-radio";
          const radio = document.createElement("input");
          radio.type = "radio";
          radio.name = field.name;
          radio.value = option;
          radio.id = optId;
          radio.checked = values[field.name] === option;
          radio.addEventListener("change", () => {
            values[field.name] = option;
          });
          radioLabel.appendChild(radio);
          radioLabel.append(` ${option}`);
          group.appendChild(radioLabel);
        }
        fieldEl.appendChild(group);
      } else {
        const input = document.createElement("input");
        input.type = "text";
        input.required = field.required !== false;
        if (values[field.name] !== undefined) {
          input.value = values[field.name];
        } else if (field.value !== null && field.value !== undefined) {
          input.value = String(field.value);
          values[field.name] = input.value;
        }
        if (field.placeholder) input.placeholder = field.placeholder;
        input.addEventListener("input", () => {
          values[field.name] = input.value;
        });
        fieldEl.appendChild(input);
      }

      fieldsContainer.appendChild(fieldEl);
    }
    wrapper.classList.remove("inline-form-submitted");
    errorEl.textContent = "";
    wrapper.append(errorEl, submitBtn);
  }

  function renderSummary() {
    fieldsContainer.innerHTML = "";
    for (const field of form.fields) {
      const row = document.createElement("div");
      row.className = "inline-form-summary-row";
      const label = document.createElement("span");
      label.className = "inline-form-summary-label";
      label.textContent = field.label;
      const value = document.createElement("span");
      value.className = "inline-form-summary-value";
      value.textContent = values[field.name] || "—";
      row.append(label, value);
      fieldsContainer.appendChild(row);
    }
    wrapper.classList.add("inline-form-submitted");
    errorEl.remove();
    submitBtn.remove();
  }

  async function saveForm(caseId) {
    if (formSaved) return;
    formSaved = true;
    try {
      const res = await fetch("/api/forms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          title: form.title || "Insurance application",
          case_id: caseId,
          fields: form.fields.map((f) => ({
            name: f.name,
            label: f.label,
            value: values[f.name] || "",
          })),
        }),
      });
      if (!res.ok) throw new Error(`Server responded with ${res.status}`);
      const data = await res.json();
      addFormSavedLink(data.url);
    } catch (err) {
      console.error(err);
      addFormSaveError();
    }
  }

  renderEditableFields();

  wrapper.addEventListener("submit", (e) => {
    e.preventDefault();
    const missing = form.fields.filter((f) => f.required !== false && !values[f.name]);
    if (missing.length) {
      errorEl.textContent = "Please fill in all fields before submitting.";
      return;
    }
    const composed = form.fields
      .map((f) => `${FORM_FIELD_ANSWER_PREFIX[f.name] || f.label}: ${values[f.name]}`)
      .join("\n");
    formSubmitted = true;
    renderSummary();
    saveForm();
    sendMessage(composed);
  });

  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  activeForm = {
    get submitted() {
      return formSubmitted;
    },
    markSubmitted(caseId) {
      if (formSubmitted) return;
      formSubmitted = true;
      renderSummary();
      saveForm(caseId);
    },
    markEditable() {
      if (!formSubmitted) return;
      formSubmitted = false;
      formSaved = false;
      renderEditableFields();
    },
  };
}

// --- Auth choice card - a styled picker for the Loan Promise identity step,
// modeled after a real Swedish bank login screen rather than plain
// suggestion chips. Pressing Continue sends the chosen option's own
// "message" text as the next chat message, exactly like clicking a
// suggestion chip would - the backend's own keyword detection (see
// _bankid_chosen in mortgage_agent.py) doesn't know or care which UI
// produced it. With a single option (currently just BankID) the row is
// shown as plain info text rather than a redundant one-item radio group. ---
function addAuthChoice(form) {
  if (!form || !form.options || !form.options.length) return;

  const wrapper = document.createElement("div");
  wrapper.className = "auth-choice-card";

  const heading = document.createElement("h3");
  heading.className = "auth-choice-heading";
  heading.textContent = (form.heading && form.heading[currentLang]) || form.heading?.en || "";
  wrapper.appendChild(heading);

  const optionsWrap = document.createElement("div");
  optionsWrap.className = "auth-choice-options";
  wrapper.appendChild(optionsWrap);

  const singleOption = form.options.length === 1;
  let selected = form.default || form.options[0].value;
  let submitted = false;

  form.options.forEach((option) => {
    const row = document.createElement(singleOption ? "div" : "label");
    row.className = "auth-choice-option";

    let radio = null;
    if (!singleOption) {
      radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `auth-choice-${Math.random().toString(36).slice(2)}`;
      radio.value = option.value;
      radio.checked = option.value === selected;
      radio.addEventListener("change", () => {
        selected = option.value;
      });
    }

    const text = document.createElement("span");
    text.className = "auth-choice-option-text";
    const title = document.createElement("span");
    title.className = "auth-choice-option-label";
    title.textContent = option.label;
    text.appendChild(title);
    if (option.helper) {
      const helper = document.createElement("span");
      helper.className = "auth-choice-option-helper";
      helper.textContent = option.helper[currentLang] || option.helper.en || "";
      text.appendChild(helper);
    }

    if (radio) row.appendChild(radio);
    row.appendChild(text);
    optionsWrap.appendChild(row);
  });

  const continueBtn = document.createElement("button");
  continueBtn.type = "button";
  continueBtn.className = "auth-choice-continue-btn";
  continueBtn.textContent = (form.continue_label && form.continue_label[currentLang]) || form.continue_label?.en || "Continue";
  continueBtn.addEventListener("click", () => {
    if (submitted) return;
    submitted = true;
    continueBtn.disabled = true;
    wrapper.classList.add("auth-choice-submitted");
    const chosen = form.options.find((option) => option.value === selected);
    authStatusPending = !authStatusShownFor.has(sessionId);
    sendMessage(chosen ? chosen.message : selected);
  });
  wrapper.appendChild(continueBtn);

  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Comparison table (e.g. car insurance tiers) - real, structured data
// the backend scraped from LF Bergslagen's own live page (see
// compare_car_insurance / fetch_car_insurance_comparison in the backend),
// rendered as an actual table instead of the model re-typing every row as
// prose. Mirrors addForm/addOffers above: reads one more field off the
// same /api/chat response and appends its own element to #messages. ---
function addComparisonTable(table) {
  if (!table || !table.columns || !table.rows || !table.rows.length) return;

  const wrapper = document.createElement("div");
  wrapper.className = "comparison-table-wrapper";

  if (table.type === "home_insurance_tiers") {
    renderTierComparisonTable(wrapper, table);
  } else {
    renderBooleanComparisonTable(wrapper, table);
  }

  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderBooleanComparisonTable(wrapper, table) {
  const scroller = document.createElement("div");
  scroller.className = "comparison-table-scroll";

  const headCells = table.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const bodyRows = table.rows
    .map((row) => {
      const cells = row.values
        .map((v) => `<td class="${v ? "cmp-yes" : "cmp-no"}">${v ? "✓" : "—"}</td>`)
        .join("");
      return `<tr><th scope="row">${escapeHtml(row.feature)}</th>${cells}</tr>`;
    })
    .join("");

  scroller.innerHTML = `
    <table class="comparison-table">
      <thead><tr><th></th>${headCells}</tr></thead>
      <tbody>${bodyRows}</tbody>
    </table>
  `;
  wrapper.appendChild(scroller);
}

// --- Home insurance tier comparison (Bas/Mellan/Stor) - text-per-cell
// rather than checkmarks, an optional "Could be a good fit" badge above
// whichever column compare_home_insurance (backend) flagged as matching
// signals in this conversation - deliberately not phrased as Sara making
// the choice for the customer (see that function's docstring) - a footnote
// explaining why, and a client-side Single/Co-living toggle that swaps the
// price row using values already present in the response (no extra
// round-trip needed). See compare_home_insurance in backend/tools.py for
// where recommended_column/recommendation_note and the price row's
// co_living_values come from. ---
function renderTierComparisonTable(wrapper, table) {
  const recommendedIndex = table.recommended_column;
  const priceRowIndex = table.rows.findIndex((row) => row.co_living_values);

  if (priceRowIndex !== -1) {
    const toggle = document.createElement("div");
    toggle.className = "tier-toggle";
    toggle.innerHTML = `
      <button type="button" class="tier-toggle-btn active" data-mode="values">Single Person</button>
      <button type="button" class="tier-toggle-btn" data-mode="co_living_values">Co-living / Partner</button>
    `;
    wrapper.appendChild(toggle);
  }

  const scroller = document.createElement("div");
  scroller.className = "comparison-table-scroll";

  const badgeCells = table.columns
    .map(
      (_, i) =>
        `<th class="tier-badge-table-cell">${
          i === recommendedIndex ? '<span class="tier-badge">\u2728 Could be a good fit for you</span>' : ""
        }</th>`
    )
    .join("");
  const headCells = table.columns
    .map((c, i) => `<th class="${i === recommendedIndex ? "tier-recommended" : ""}">${escapeHtml(c)}</th>`)
    .join("");
  const bodyRows = table.rows
    .map((row, rowIndex) => {
      const cells = row.values
        .map(
          (v, i) =>
            `<td class="${i === recommendedIndex ? "tier-recommended" : ""}" data-row="${rowIndex}">${escapeHtml(v)}</td>`
        )
        .join("");
      return `<tr><th scope="row">${escapeHtml(row.feature)}</th>${cells}</tr>`;
    })
    .join("");

  scroller.innerHTML = `
    <table class="comparison-table comparison-table-detail">
      <thead>
        ${recommendedIndex != null ? `<tr class="tier-badge-table-row"><th></th>${badgeCells}</tr>` : ""}
        <tr><th></th>${headCells}</tr>
      </thead>
      <tbody>${bodyRows}</tbody>
    </table>
  `;
  wrapper.appendChild(scroller);

  if (priceRowIndex !== -1) {
    const buttons = wrapper.querySelectorAll(".tier-toggle-btn");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((b) => b.classList.toggle("active", b === btn));
        const values = table.rows[priceRowIndex][btn.dataset.mode];
        scroller.querySelectorAll(`td[data-row="${priceRowIndex}"]`).forEach((cell, i) => {
          cell.textContent = values[i];
        });
      });
    });
  }

  if (table.recommendation_note) {
    const note = document.createElement("div");
    note.className = "tier-recommendation-note";
    note.innerHTML = `<strong>Why we suggest this:</strong> ${escapeHtml(table.recommendation_note)}`;
    wrapper.appendChild(note);
  }
}

// --- Task Completion Ring: gamifies progress through a mortgage flow (Loan
// Promise / Loan Offer) once the customer has actually started one - see
// compute_transition_progress in backend/agents/mortgage_agent.py, which
// derives it from the conversation transcript itself (no separate session
// state). Sticky above #messages instead of appended per-turn, since it
// reflects one running total rather than a one-off event like a table. ---
function updateProgressRing(progress) {
  if (!progress) {
    progressRingBarEl.hidden = true;
    return;
  }

  progressRingBarEl.hidden = false;
  progressRingTitleEl.textContent = progress.flow;
  progressRingPercentEl.textContent = `${progress.percent}%`;

  const offset = PROGRESS_RING_CIRCUMFERENCE * (1 - progress.percent / 100);
  progressRingFillEl.style.strokeDasharray = String(PROGRESS_RING_CIRCUMFERENCE);
  progressRingFillEl.style.strokeDashoffset = String(offset);

  progressStepsEl.innerHTML = "";
  progress.steps.forEach((step, index) => {
    const stepEl = document.createElement("div");
    stepEl.className = "progress-step" + (step.done ? " done" : "");
    const dot = document.createElement("span");
    dot.className = "progress-step-dot";
    dot.textContent = step.done ? "✓" : String(index + 1);
    const label = document.createElement("span");
    label.className = "progress-step-label";
    label.textContent = step.label;
    stepEl.appendChild(dot);
    stepEl.appendChild(label);
    progressStepsEl.appendChild(stepEl);
  });
}

function addDocumentReview(review) {
  if (!review) return;

  const wrapper = document.createElement("div");
  wrapper.className = "document-review-card";

  const heading = document.createElement("strong");
  heading.textContent = review.needs_review ? "Documents need review" : "Documents read and verified";
  wrapper.appendChild(heading);

  const income = review.income_statement || {};
  const expenses = review.expenses || {};
  const rows = [
    ["Monthly gross income", income.monthly_gross_income_sek, "SEK"],
    ["Monthly expenses", expenses.monthly_expenses_total_sek, "SEK"],
    ["Employment", income.employment_type, ""],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");

  if (rows.length) {
    const list = document.createElement("dl");
    for (const [label, value, suffix] of rows) {
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = `${value}${suffix ? ` ${suffix}` : ""}`;
      list.append(term, detail);
    }
    wrapper.appendChild(list);
  }

  if (review.needs_review && review.review_reason) {
    const note = document.createElement("p");
    note.textContent = review.review_reason;
    wrapper.appendChild(note);
  }

  if (review.unclassified_documents && review.unclassified_documents.length) {
    const note = document.createElement("p");
    note.textContent = `Could not classify: ${review.unclassified_documents.join(", ")}`;
    wrapper.appendChild(note);
  }

  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Satisfaction rating: a small, optional "how helpful was this chat"
// star control. Never blocks the conversation - it just becomes visible
// once there's been at least one reply, and can be clicked at any time. ---
for (let n = 1; n <= 5; n++) {
  const star = document.createElement("button");
  star.type = "button";
  star.className = "star-btn";
  star.dataset.value = String(n);
  star.textContent = "★";
  star.title = `${n} / 5`;
  ratingStarsEl.appendChild(star);
}

function paintStars(selected) {
  ratingStarsEl.querySelectorAll(".star-btn").forEach((star) => {
    star.classList.toggle("filled", Number(star.dataset.value) <= selected);
  });
}

async function submitRating(value) {
  if (ratingSubmitted) return;
  ratingSubmitted = true;
  paintStars(value);
  ratingLabelEl.textContent = t().rateThanks;
  try {
    await fetch(`/api/sessions/${sessionId}/rating`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating: value }),
    });
  } catch (err) {
    console.error(err);
  }
}

ratingStarsEl.addEventListener("click", (e) => {
  const star = e.target.closest(".star-btn");
  if (!star) return;
  submitRating(Number(star.dataset.value));
});

function showRatingBar() {
  ratingBarEl.hidden = false;
}

function resetRatingWidget() {
  ratingSubmitted = false;
  ratingBarEl.hidden = true;
  ratingLabelEl.textContent = t().rateLabel;
  paintStars(0);
}

async function getAssistantReply() {
  const pending = addBubble("assistant pending", t().thinking, { label: t().aiLabel });
  const showAuthStatus = authStatusPending;
  authStatusPending = false;
  inputEl.disabled = true;
  sendBtn.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history, session_id: sessionId, lang: currentLang }),
    });

    if (!res.ok) {
      throw new Error(`Server responded with ${res.status}`);
    }

    const data = await res.json();
    if (showAuthStatus) {
      authStatusShownFor.add(sessionId);
      addStatusMessage(t().authComplete, pending);
    }
    pending.innerHTML = "";
    const labelEl = document.createElement("span");
    labelEl.className = "msg-label";
    const labelText = document.createElement("span");
    labelText.className = "msg-label-text";
    labelText.textContent = t().aiLabel;
    labelEl.appendChild(labelText);
    pending.appendChild(labelEl);
    pending.insertAdjacentHTML("beforeend", renderMarkdown(data.content));
    addSpeakButton(labelEl, data.content);
    pending.className = "msg assistant";
    history.push({ role: "assistant", content: data.content });
    sessionMessageCount += 2; // the server just appended one user + one assistant message
    upsertChatListEntry();
    // The auth card is the interaction; its BankID chip would just duplicate it.
    addSuggestions(data.form?.type === "auth_choice" ? [] : data.suggestions, data.human_chat_option);
    if (activeForm && !activeForm.submitted && (data.case_id || FORM_CONFIRM_REPLY_RE.test(data.content))) {
      // A case ID in the reply is the reliable sign the application was
      // submitted - the confirmation wording varies too much for the regexes
      // alone (kept as a fallback). The backend also forces a tool call on the
      // first round of every turn, which sometimes makes it re-invoke
      // fill_customer_form on this very confirmation turn even though nothing
      // changed -- treat the reply as the confirmation it is instead of
      // popping up a duplicate form.
      activeForm.markSubmitted(data.case_id);
    } else {
      renderForm(data.form);
    }
    addOffers(data.offers, data.offers_customer_id);
    addComparisonTable(data.comparison_table);
    addDocumentReview(data.document_review);
    updateProgressRing(data.progress);
    if (data.plan_updates && data.plan_updates.length) {
      addBubble(
        "system-note",
        `Marked complete in your plan: ${data.plan_updates.join(", ")}.`
      );
    }
    loadPlan();
    showRatingBar();
    refreshPortfolioPanel();
  } catch (err) {
    pending.textContent = t().chatError;
    pending.className = "msg assistant";
    console.error(err);
  } finally {
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderAttachmentPreview(status = "") {
  attachmentPreviewEl.innerHTML = "";
  fillFormBtn.hidden = !stagedFiles.length;
  fillFormBtn.disabled = !stagedFiles.length;
  if (!stagedFiles.length && !status) {
    attachmentPreviewEl.hidden = true;
    return;
  }

  attachmentPreviewEl.hidden = false;
  const header = document.createElement("div");
  header.className = "attachment-preview-header";
  header.textContent = status || `${stagedFiles.length} attachment${stagedFiles.length === 1 ? "" : "s"} ready`;
  attachmentPreviewEl.appendChild(header);

  const list = document.createElement("div");
  list.className = "attachment-list";
  stagedFiles.forEach((file, index) => {
    const item = document.createElement("div");
    item.className = "attachment-item";

    const name = document.createElement("span");
    name.className = "attachment-name";
    name.textContent = file.name;
    name.title = file.name;

    const size = document.createElement("span");
    size.className = "attachment-size";
    size.textContent = formatFileSize(file.size);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.title = "Remove attachment";
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      stagedFiles.splice(index, 1);
      renderAttachmentPreview();
    });

    item.append(name, size, remove);
    list.appendChild(item);
  });
  attachmentPreviewEl.appendChild(list);
}

function stageFiles(files) {
  const existing = new Set(stagedFiles.map(fileKey));
  for (const file of Array.from(files || [])) {
    if (!existing.has(fileKey(file))) {
      stagedFiles.push(file);
      existing.add(fileKey(file));
    }
  }
  renderAttachmentPreview();
}

async function uploadFiles(files) {
  const uploads = [];
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    renderAttachmentPreview(`Uploading ${index + 1} of ${files.length}...`);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("session_id", sessionId);
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    if (!res.ok) throw new Error(`Upload failed with ${res.status}`);
    const upload = await res.json();
    uploads.push({
      ...upload,
      // The original bytes stay in the browser as a blob URL so the viewer
      // can show/download the real file, not just the text extracted from it.
      previewUrl: URL.createObjectURL(file),
      kind: getFileKind(upload.filename || file.name, file.type),
    });
  }
  return uploads;
}

function buildMessageText(text, attachments) {
  const parts = [];
  if (text.trim()) parts.push(text.trim());

  for (const attachment of attachments) {
    const extractedText = attachment.text || "No readable text was extracted from this file.";
    parts.push(`[Attached document: ${attachment.filename}]\n\n${extractedText}`);
  }

  return parts.join("\n\n");
}

function showSubmittedMessage(text, attachments) {
  if (text.trim()) addBubble("user", text.trim());
  if (attachments.length) {
    addAttachmentBubble(attachments);
  }
}

function setComposerBusy(busy) {
  inputEl.disabled = busy;
  sendBtn.disabled = busy;
  attachBtn.disabled = busy;
  micBtn.disabled = busy;
  fillFormBtn.disabled = busy || !stagedFiles.length;
}

fillFormBtn.addEventListener("click", () => {
  sendMessage("Fill the form", stagedFiles.slice());
});

async function sendMessage(text, files = []) {
  const textToSend = text.trim();
  if (!textToSend && !files.length) return;

  if (activeForm && textToSend) {
    if (!activeForm.submitted && FORM_CONFIRM_RE.test(textToSend)) {
      activeForm.markSubmitted();
    } else if (activeForm.submitted && FORM_CHANGE_RE.test(textToSend)) {
      activeForm.markEditable();
    }
  }

  chipsEl.style.display = "none";
  setComposerBusy(true);

  try {
    const attachments = files.length ? await uploadFiles(files) : [];
    const content = buildMessageText(textToSend, attachments);
    showSubmittedMessage(textToSend, attachments);
    inputEl.value = "";
    inputEl.style.height = "auto";

    stagedFiles = [];
    renderAttachmentPreview();

    if (humanHandoffActive) {
      const res = await fetch(`/api/sessions/${sessionId}/customer-message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = await res.json();
      if (typeof data.message_count === "number") sessionMessageCount = data.message_count;
      return;
    }

    history.push({ role: "user", content });
    await getAssistantReply();
  } catch (err) {
    console.error(err);
    renderAttachmentPreview(t().uploadError);
  } finally {
    setComposerBusy(false);
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value;
  const filesToSend = stagedFiles.slice();
  sendMessage(text, filesToSend);
});

// Enter sends the message; Shift+Enter inserts a newline instead.
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

// Auto-grow the textarea as the user types multiple lines.
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = `${inputEl.scrollHeight}px`;
});

chipsEl.addEventListener("click", (e) => {
  const btn = e.target.closest(".topic-dropdown-item");
  if (!btn) return;
  sendMessage(btn.dataset.text);
});

// Close the topic dropdown when clicking outside it or pressing Escape.
document.addEventListener("click", (e) => {
  const toggle = chipsEl.querySelector(".topic-dropdown-toggle");
  const menu = chipsEl.querySelector(".topic-dropdown-menu");
  if (!toggle || !menu || menu.hidden) return;
  if (!e.target.closest(".topic-dropdown")) {
    menu.hidden = true;
    toggle.classList.remove("open");
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const toggle = chipsEl.querySelector(".topic-dropdown-toggle");
  const menu = chipsEl.querySelector(".topic-dropdown-menu");
  if (menu && !menu.hidden) {
    menu.hidden = true;
    toggle.classList.remove("open");
  }
});

// --- Document upload ---

attachBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  stageFiles(fileInput.files);
  fileInput.value = "";
});

["dragenter", "dragover"].forEach((eventName) => {
  chatShellEl.addEventListener(eventName, (event) => {
    event.preventDefault();
    chatShellEl.classList.add("drag-over");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  chatShellEl.addEventListener(eventName, (event) => {
    event.preventDefault();
    if (eventName === "drop") stageFiles(event.dataTransfer.files);
    chatShellEl.classList.remove("drag-over");
  });
});

// --- Voice input (browser speech-to-text, no backend involved) ---

const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognitionImpl) {
  micBtn.hidden = false;
  const recognition = new SpeechRecognitionImpl();
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  let listening = false;

  recognition.addEventListener("result", (event) => {
    const transcript = event.results[0][0].transcript;
    inputEl.value = transcript;
    inputEl.style.height = "auto";
    inputEl.style.height = `${inputEl.scrollHeight}px`;
    inputEl.focus();
  });

  recognition.addEventListener("end", () => {
    listening = false;
    micBtn.classList.remove("recording");
  });

  recognition.addEventListener("error", () => {
    listening = false;
    micBtn.classList.remove("recording");
  });

  micBtn.addEventListener("click", () => {
    if (listening) {
      recognition.stop();
      return;
    }
    recognition.lang = t().speechLang;
    listening = true;
    micBtn.classList.add("recording");
    recognition.start();
  });
}

// --- Talk to a real person ---

async function requestHumanHandoff() {
  humanBtn.disabled = true;
  humanBtnLabel.textContent = t().humanConnecting;
  try {
    await fetch(`/api/sessions/${sessionId}/request-human`, { method: "POST" });
    addBubble("system-note", t().humanNote);
    humanHandoffActive = true;
  } catch (err) {
    console.error(err);
    humanBtn.disabled = false;
    humanBtnLabel.textContent = t().humanBtn;
  }
}

humanBtn.addEventListener("click", requestHumanHandoff);

// --- Poll for messages a human support colleague sends from the dashboard ---

async function pollForHumanMessages() {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/poll?after=${sessionMessageCount}`);
    if (!res.ok) return;
    const data = await res.json();
    updateProgressRing(data.progress);

    if (data.assigned_agent && data.assigned_agent !== lastKnownAgent) {
      lastKnownAgent = data.assigned_agent;
      addBubble("system-note", `${lastKnownAgent} ${t().agentJoinedSuffix}`);
    }

    for (const msg of data.messages) {
      if (msg.role === "human") {
        addBubble("human", msg.content, {
          markdown: true,
          label: msg.agent_name || t().supportLabel,
          speakable: true,
        });
      }
    }
    sessionMessageCount = data.next_after;
  } catch (err) {
    // silent -- this is a background poll, not a user-initiated action
  }
}

setInterval(pollForHumanMessages, 3000);

// --- Brief, self-dismissing status message - currently only used to explain
// why a sidebar chat just vanished (see loadChat's 404 branch below), rather
// than leaving that silent and looking like a bug. ---
let toastTimer = null;
function showToast(message) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 4000);
}

// --- Chat history sidebar (past chats, persisted locally; full transcript
// lives server-side in the session store and is refetched when reopened) ---

function loadChatList() {
  try {
    return JSON.parse(localStorage.getItem("ltn-chat-list") || "[]");
  } catch (err) {
    return [];
  }
}

function saveChatList(list) {
  localStorage.setItem("ltn-chat-list", JSON.stringify(list));
}

// searchText holds every message in the conversation so far (not just the
// title) - kept alongside title/ts precisely so the search box below can
// find a past chat by anything said in it, not only by its opening line.
function buildSearchText(messages) {
  return messages.map((m) => m.content || "").join(" \n ").toLowerCase();
}

function upsertChatListEntry() {
  if (!history.length) return;
  const list = loadChatList();
  const existing = list.find((c) => c.id === sessionId);
  if (existing) {
    existing.ts = Date.now();
    existing.searchText = buildSearchText(history);
  } else {
    const firstUserMsg = history.find((m) => m.role === "user");
    const title = firstUserMsg ? firstUserMsg.content.slice(0, 60) : "Chat";
    list.unshift({ id: sessionId, title, ts: Date.now(), searchText: buildSearchText(history) });
  }
  saveChatList(list);
  renderChatList();
}

// Once this browser's current session verifies as a customer, pull the
// REST of her chat history from the server (other chats, possibly from a
// different browser/device) and merge it into this browser's own
// localStorage list - see GET /api/customers/{customer_id}/sessions in
// main.py. Local-only entries (not yet verified in any session) are left
// untouched; this only ever adds server-known chats it doesn't have yet.
async function mergeCustomerChatHistory(customerId) {
  if (!customerId) return;
  const requestedSessionId = sessionId;
  // Always the session that actually verified (see refreshPortfolioPanel,
  // which sets this right before calling here) - the CURRENTLY viewed chat
  // (sessionId) may be a different, never-verified one, which this
  // customer-scoped endpoint would otherwise correctly refuse.
  const authSessionId = verifiedSessionId || requestedSessionId;
  try {
    const res = await fetch(`/api/customers/${customerId}/sessions?session_id=${encodeURIComponent(authSessionId)}`);
    if (sessionId !== requestedSessionId) return; // see loadPlan's same guard
    if (!res.ok) return;
    const data = await res.json();
    if (sessionId !== requestedSessionId) return;
    const local = loadChatList();
    const localIds = new Set(local.map((chat) => chat.id));
    let changed = false;
    for (const remote of data.sessions || []) {
      if (localIds.has(remote.session_id)) continue;
      local.push({
        id: remote.session_id,
        title: remote.title || "Chat",
        ts: Date.parse(remote.last_ts) || Date.now(),
        searchText: "",
      });
      changed = true;
    }
    if (changed) {
      saveChatList(local);
      renderChatList();
    }
  } catch (err) {
    console.error(err);
  }
}

function renderChatList() {
  const query = (chatSearchInputEl.value || "").trim().toLowerCase();
  const list = loadChatList().sort((a, b) => b.ts - a.ts);
  const filtered = query
    ? list.filter(
        (chat) =>
          (chat.title || "").toLowerCase().includes(query) || (chat.searchText || "").includes(query)
      )
    : list;

  chatListEl.innerHTML = "";

  if (query && !filtered.length) {
    const empty = document.createElement("div");
    empty.className = "chat-search-empty";
    empty.textContent = t().chatSearchEmpty;
    chatListEl.appendChild(empty);
    return;
  }

  for (const chat of filtered) {
    const item = document.createElement("div");
    item.className = "chat-item" + (chat.id === sessionId ? " active" : "");

    const title = document.createElement("div");
    title.className = "chat-item-title";
    title.textContent = chat.title || "Chat";
    title.title = chat.title || "Chat";
    title.setAttribute("role", "button");
    title.tabIndex = 0;
    title.addEventListener("click", () => loadChat(chat.id));
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        loadChat(chat.id);
      }
    });

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chat-delete-btn";
    remove.title = "Delete chat";
    remove.setAttribute("aria-label", `Delete chat: ${chat.title || "Chat"}`);
    remove.textContent = "×";
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteChat(chat.id, chat.title || "Chat");
    });

    item.append(title, remove);
    chatListEl.appendChild(item);
  }
}

async function deleteChat(chatId, title) {
  const confirmed = window.confirm(
    `Delete "${title}"? This removes its chat transcript and transition plan from this demo.`
  );
  if (!confirmed) return;
  try {
    const response = await fetch(`/api/sessions/${chatId}`, { method: "DELETE" });
    if (!response.ok) throw new Error(`Chat deletion failed: ${response.status}`);
    saveChatList(loadChatList().filter((chat) => chat.id !== chatId));
    if (chatId === sessionId) {
      startNewChat();
    } else {
      renderChatList();
    }
  } catch (err) {
    console.error(err);
    window.alert("Could not delete this chat. Please try again.");
  }
}

chatSearchInputEl.addEventListener("input", () => renderChatList());

function resetChatView() {
  messagesEl.innerHTML = "";
  activeForm = null;
  const greetingDiv = document.createElement("div");
  greetingDiv.className = "msg assistant";
  greetingDiv.innerHTML = `<span class="msg-label" id="greeting-label"></span><p id="greeting-text"></p>`;
  messagesEl.appendChild(greetingDiv);
  greetingLabelEl = document.getElementById("greeting-label");
  greetingTextEl = document.getElementById("greeting-text");

  chipsEl.style.display = "";
  stagedFiles = [];
  attachmentPreviewEl.hidden = true;
  attachmentPreviewEl.innerHTML = "";
  fillFormBtn.hidden = true;
  fillFormBtn.disabled = true;
  inputEl.value = "";
  inputEl.style.height = "auto";
  humanBtn.disabled = false;
  humanBtnLabel.textContent = t().humanBtn;
  resetRatingWidget();
  updateProgressRing(null);

  applyLanguage(currentLang);
}

function startNewChat() {
  if (speechSupported) window.speechSynthesis.cancel();
  history = [];
  sessionMessageCount = 0;
  humanHandoffActive = false;
  lastKnownAgent = null;
  sessionId = crypto.randomUUID();
  sessionStorage.setItem("ltn-session-id", sessionId);
  // Must happen before resetChatView (which triggers loadPlan/
  // refreshPortfolioPanel via applyLanguage) - otherwise those calls would
  // fall back to the just-abandoned chat's verified session and show her
  // plan/activity in this brand new, not-yet-verified chat.
  verifiedSessionId = null;
  resetChatView();
  chatSearchInputEl.value = "";
  renderEmptyPlan();
  renderChatList();
  portfolioPanelEl.hidden = true;
  setAuthenticatedSidebarVisible(false);
}

function parseUserMessageContent(content) {
  const attachmentRegex = /\[Attached (?:document|file): (.+?)\]\n\n([\s\S]*?)(?=\n\n\[Attached (?:document|file): |\s*$)/g;
  const attachments = [];
  let firstAttachmentIndex = content.length;
  let match;

  while ((match = attachmentRegex.exec(content)) !== null) {
    firstAttachmentIndex = Math.min(firstAttachmentIndex, match.index);
    attachments.push({
      filename: match[1],
      text: match[2].trim(),
      kind: getFileKind(match[1], ""),
    });
  }

  return {
    text: content.slice(0, firstAttachmentIndex).trim(),
    attachments,
  };
}

// Renders a fetched session's transcript, and refreshes everything derived
// from it (plan, activity, chat list) - shared by loadChat (explicit
// navigation to a past chat) and restoreCurrentSession (re-opening this
// browser tab's own persisted session_id on page load), so both end up
// with a consistent view instead of the plan/activity panels quietly
// reflecting a session whose transcript was never actually rendered.
async function applySessionData(id, data) {
    sessionId = id;
    sessionStorage.setItem("ltn-session-id", sessionId);
    sessionMessageCount = data.messages.length;
    humanHandoffActive = Boolean(data.needs_human);
    lastKnownAgent = data.assigned_agent || null;
    activeForm = null;
    history = data.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: m.content }));

    messagesEl.innerHTML = "";
    if (!data.messages.length) {
      // A session row can exist server-side with no messages yet (e.g. only
      // "talk to a person" was clicked before anything was said) - show the
      // greeting rather than leaving the panel blank, same as a new chat.
      const greetingDiv = document.createElement("div");
      greetingDiv.className = "msg assistant";
      greetingDiv.innerHTML = `<span class="msg-label">${escapeHtml(t().greetingLabel)}</span><p>${escapeHtml(t().greeting)}</p>`;
      messagesEl.appendChild(greetingDiv);
    }
    chipsEl.style.display = "none";
    for (const msg of data.messages) {
      if (msg.role === "user") {
        const parsed = parseUserMessageContent(msg.content);
        if (parsed.text) addBubble("user", parsed.text);
        if (parsed.attachments.length) addAttachmentBubble(parsed.attachments);
        if (!parsed.text && !parsed.attachments.length) addBubble("user", msg.content);
      } else if (msg.role === "assistant") {
        addBubble("assistant", msg.content, { markdown: true, label: t().aiLabel, speakable: true });
      } else if (msg.role === "human") {
        addBubble("human", msg.content, {
          markdown: true,
          label: msg.agent_name || t().supportLabel,
          speakable: true,
        });
      }
    }
    resetRatingWidget();
    if (history.some((m) => m.role === "assistant")) showRatingBar();
    updateProgressRing(null);

    // Backfills searchText for chats saved before the search box existed
    // (or reopened after a page reload without a new message sent yet).
    const list = loadChatList();
    const entry = list.find((c) => c.id === sessionId);
    if (entry) {
      entry.searchText = buildSearchText(history);
      saveChatList(list);
    }
    await loadPlan();
    renderChatList();
    refreshPortfolioPanel();
}

async function loadChat(id) {
  if (id === sessionId) return;
  if (speechSupported) window.speechSynthesis.cancel();
  try {
    const res = await fetch(`/api/sessions/${id}`);
    if (!res.ok) {
      // The server no longer knows this chat (e.g. it predates this
      // browser's chat history being made durable server-side) - drop it
      // from the sidebar instead of leaving a dead entry that does nothing
      // when clicked.
      if (res.status === 404) {
        saveChatList(loadChatList().filter((c) => c.id !== id));
        renderChatList();
        showToast(t().chatGoneNotice);
      }
      return;
    }
    const data = await res.json();
    await applySessionData(id, data);
  } catch (err) {
    console.error(err);
  }
}

// Re-opens THIS browser tab's own persisted session_id on page load, if the
// server actually has a transcript for it - otherwise the plan/activity
// panels and the background poll (which drives the progress ring) would
// silently reflect that old session's state while the visible chat area
// still showed nothing but the default greeting. A 404 here (brand new
// tab, session_id never sent a message yet) is normal, not an error - it
// falls through to the same empty-state loadPlan/refreshPortfolioPanel
// calls a fresh chat gets.
async function restoreCurrentSession() {
  try {
    const res = await fetch(`/api/sessions/${sessionId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.messages.length) {
        await applySessionData(sessionId, data);
        return;
      }
    }
  } catch (err) {
    console.error(err);
  }
  loadPlan();
  refreshPortfolioPanel();
}

// --- Embeddable widget integration: lets a parent marketing page (see
// site.html/site.js) trigger a message in this chat from the outside,
// e.g. when a visitor clicks a "life moment" card on the public site. ---
window.addEventListener("message", (event) => {
  const data = event.data;
  if (data && data.type === "ltn-send" && typeof data.text === "string") {
    sendMessage(data.text);
  } else if (data && data.type === "ltn-widget-mode") {
    // Sent by site.js: "compact" (small bubble -- no room for the
    // sidebar) or "full" (maximized -- show the normal full interface).
    document.body.classList.toggle("widget-compact", data.mode === "compact");
  }
});

homeBtn.addEventListener("click", startNewChat);
homeBtn.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    startNewChat();
  }
});
newChatBtn.addEventListener("click", startNewChat);

// --- Sidebar collapse: hides the previous-chats list and widens the chat
// column into the freed space (see body.sidebar-collapsed rules in
// style.css), similar to collapsing the left nav in Claude's UI. Persisted
// so the choice survives a reload. ---
function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  sidebarShowBtn.hidden = !collapsed;
  localStorage.setItem("ltn-sidebar-collapsed", collapsed ? "1" : "");
}
sidebarHideBtn.addEventListener("click", () => setSidebarCollapsed(true));
sidebarShowBtn.addEventListener("click", () => setSidebarCollapsed(false));
setSidebarCollapsed(localStorage.getItem("ltn-sidebar-collapsed") === "1");

setAuthenticatedSidebarVisible(false);
applyLanguage(currentLang);
renderChatList();
restoreCurrentSession();
