const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const chipsEl = document.getElementById("chips");
const attachBtn = document.getElementById("attach-btn");
const fileInput = document.getElementById("file-input");
const attachmentPreviewEl = document.getElementById("attachment-preview");
const micBtn = document.getElementById("mic-btn");
const humanBtn = document.getElementById("human-btn");
const langToggleEl = document.getElementById("lang-toggle");
let greetingLabelEl = document.getElementById("greeting-label");
let greetingTextEl = document.getElementById("greeting-text");
const sendBtn = document.getElementById("send-btn");
const homeBtn = document.getElementById("home-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const chatListEl = document.getElementById("chat-list");
const chatShellEl = document.querySelector(".chat-shell");
const planPanelEl = document.getElementById("plan-panel");

// The toggle sets the UI language and is a fallback for ambiguous messages,
// but the backend still matches whatever language the user actually types
// whenever that's clear -- see the LANGUAGE RULE in backend/agent.py.
const I18N = {
  en: {
    brandSub: "Digital assistant · LF Bergslagen",
    greetingLabel: "Sara · AI assistant",
    greeting:
      "Hej! I'm Sara, LF Bergslagen's digital assistant. Tell me what's changing in your life, and I'll help you think it through.",
    placeholder: "Tell me what's happening in your life...",
    send: "Send",
    humanBtn: "Talk to a person",
    humanConnecting: "Connecting...",
    humanNote:
      "You've asked to speak with a colleague at LF Bergslagen. They'll join this chat as soon as they're available — keep this page open.",
    agentJoinedSuffix: "has joined the chat and will respond shortly.",
    attachTitle: "Attach a document",
    micTitle: "Speak instead of typing",
    supportLabel: "LF Bergslagen · Support",
    aiLabel: "Sara · AI assistant",
    thinking: "Thinking...",
    uploadError: "Couldn't read one of those files. Try files under 5MB each.",
    chatError: "Something went wrong reaching the navigator. Please try again.",
    speechLang: "en-US",
    topicPrompt: "Not sure where to start? Choose a topic",
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
    brandSub: "Digital assistent · LF Bergslagen",
    greetingLabel: "Sara · AI-assistent",
    greeting:
      "Hej! Jag heter Sara och är LF Bergslagens digitala assistent. Berätta vad som händer i ditt liv, så hjälper jag dig tänka igenom det.",
    placeholder: "Berätta vad som händer i ditt liv...",
    send: "Skicka",
    humanBtn: "Prata med en person",
    humanConnecting: "Kopplar upp...",
    humanNote:
      "Du har bett om att prata med en kollega på LF Bergslagen. De ansluter till chatten så snart de kan — håll sidan öppen.",
    agentJoinedSuffix: "har anslutit till chatten och svarar snart.",
    attachTitle: "Bifoga ett dokument",
    micTitle: "Prata istället för att skriva",
    supportLabel: "LF Bergslagen · Support",
    aiLabel: "Sara · AI-assistent",
    thinking: "Tänker...",
    uploadError: "Kunde inte läsa en av filerna. Prova filer under 5 MB styck.",
    chatError: "Något gick fel. Försök igen.",
    speechLang: "sv-SE",
    topicPrompt: "Osäker på var du ska börja? Välj ett ämne",
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

let currentLang = localStorage.getItem("ltn-lang") || (navigator.language || "").startsWith("sv") ? "sv" : "en";
if (!I18N[currentLang]) currentLang = "en";

function t() {
  return I18N[currentLang];
}

function applyLanguage(lang) {
  currentLang = I18N[lang] ? lang : "en";
  localStorage.setItem("ltn-lang", currentLang);
  const strings = t();

  document.querySelectorAll(".brand-sub").forEach((el) => (el.textContent = strings.brandSub));
  greetingLabelEl.textContent = strings.greetingLabel;
  greetingTextEl.textContent = strings.greeting;
  inputEl.placeholder = strings.placeholder;
  sendBtn.textContent = strings.send;
  humanBtn.textContent = strings.humanBtn;
  attachBtn.title = strings.attachTitle;
  micBtn.title = strings.micTitle;

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
let sessionMessageCount = 0; // how many session-store messages we've already accounted for
let humanHandoffActive = false; // once true, the composer talks to a human, not the AI
let lastKnownAgent = null; // name of the CS agent assigned to this session, if any
let sessionId =
  sessionStorage.getItem("ltn-session-id") ||
  (() => {
    const id = crypto.randomUUID();
    sessionStorage.setItem("ltn-session-id", id);
    return id;
  })();

const PLAN_PHASE_LABELS = {
  this_week: "This week",
  before_move_in: "Before move-in",
  later: "Later",
};

function clearPlanPanel() {
  planPanelEl.innerHTML = "";
}

function renderEmptyPlan() {
  clearPlanPanel();
  const heading = document.createElement("h2");
  heading.className = "plan-heading";
  heading.textContent = "My transition plan";
  const copy = document.createElement("p");
  copy.className = "plan-empty-copy";
  copy.textContent = "Buying a home? Create a checklist you can update as you go.";
  const button = document.createElement("button");
  button.className = "plan-create-btn";
  button.type = "button";
  button.textContent = "Create home-purchase plan";
  button.addEventListener("click", createHomePurchasePlan);
  planPanelEl.append(heading, copy, button);
}

function renderPlan(plan) {
  clearPlanPanel();
  const heading = document.createElement("h2");
  heading.className = "plan-heading";
  heading.textContent = plan.event_title;
  const completed = plan.tasks.filter((task) => task.status === "done").length;
  const progress = document.createElement("p");
  progress.className = "plan-progress";
  progress.textContent = `${completed} / ${plan.tasks.length} complete`;
  planPanelEl.append(heading, progress);
  if (plan.key_date) {
    const date = document.createElement("p");
    date.className = "plan-date";
    date.textContent = `Key date: ${plan.key_date}`;
    planPanelEl.appendChild(date);
  }

  for (const phase of ["this_week", "before_move_in", "later"]) {
    const tasks = plan.tasks.filter((task) => task.phase === phase);
    if (!tasks.length) continue;
    const phaseHeading = document.createElement("h3");
    phaseHeading.className = "plan-phase";
    phaseHeading.textContent = PLAN_PHASE_LABELS[phase];
    planPanelEl.appendChild(phaseHeading);
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
      meta.textContent = task.due_date ? `Due ${task.due_date}` : task.priority + " priority";
      label.append(title, meta);
      row.append(checkbox, label);
      planPanelEl.appendChild(row);
    });
  }
}

async function loadPlan() {
  try {
    const res = await fetch(`/api/plans/session/${sessionId}`);
    if (res.status === 404) {
      renderEmptyPlan();
      return;
    }
    if (!res.ok) throw new Error(`Plan request failed: ${res.status}`);
    renderPlan(await res.json());
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
    addBubble("system-note", "Your home-purchase plan is ready. Tell Sara your move-in date when you know it.");
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
      flushList();
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

function addForm(form) {
  if (!form || !form.fields || !form.fields.length) return;

  const wrapper = document.createElement("form");
  wrapper.className = "inline-form";

  const values = {};
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
      input.required = true;
      if (field.placeholder) input.placeholder = field.placeholder;
      input.addEventListener("input", () => {
        values[field.name] = input.value;
      });
      fieldEl.appendChild(input);
    }

    wrapper.appendChild(fieldEl);
  }

  const errorEl = document.createElement("p");
  errorEl.className = "inline-form-error";
  wrapper.appendChild(errorEl);

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "Submit";
  wrapper.appendChild(submitBtn);

  wrapper.addEventListener("submit", (e) => {
    e.preventDefault();
    const missing = form.fields.filter((f) => !values[f.name]);
    if (missing.length) {
      errorEl.textContent = "Please fill in all fields before submitting.";
      return;
    }
    const composed = form.fields
      .map((f) => `${FORM_FIELD_ANSWER_PREFIX[f.name] || f.label}: ${values[f.name]}`)
      .join("\n");
    wrapper.remove();
    sendMessage(composed);
  });

  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function getAssistantReply() {
  const pending = addBubble("assistant pending", t().thinking, { label: t().aiLabel });
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
    addSuggestions(data.suggestions, data.human_chat_option);
    addForm(data.form);
    if (data.plan_updates && data.plan_updates.length) {
      addBubble(
        "system-note",
        `Marked complete in your plan: ${data.plan_updates.join(", ")}.`
      );
    }
    loadPlan();
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
    parts.push(`[Attached file: ${attachment.filename}]\n\n${extractedText}`);
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
}

async function sendMessage(text, files = []) {
  const textToSend = text.trim();
  if (!textToSend && !files.length) return;

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
  humanBtn.textContent = t().humanConnecting;
  try {
    await fetch(`/api/sessions/${sessionId}/request-human`, { method: "POST" });
    addBubble("system-note", t().humanNote);
    humanHandoffActive = true;
  } catch (err) {
    console.error(err);
    humanBtn.disabled = false;
    humanBtn.textContent = t().humanBtn;
  }
}

humanBtn.addEventListener("click", requestHumanHandoff);

// --- Poll for messages a human support colleague sends from the dashboard ---

async function pollForHumanMessages() {
  try {
    const res = await fetch(`/api/sessions/${sessionId}/poll?after=${sessionMessageCount}`);
    if (!res.ok) return;
    const data = await res.json();

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

function upsertChatListEntry() {
  if (!history.length) return;
  const list = loadChatList();
  const existing = list.find((c) => c.id === sessionId);
  if (existing) {
    existing.ts = Date.now();
  } else {
    const firstUserMsg = history.find((m) => m.role === "user");
    const title = firstUserMsg ? firstUserMsg.content.slice(0, 60) : "Chat";
    list.unshift({ id: sessionId, title, ts: Date.now() });
  }
  saveChatList(list);
  renderChatList();
}

function renderChatList() {
  const list = loadChatList().sort((a, b) => b.ts - a.ts);
  chatListEl.innerHTML = "";
  for (const chat of list) {
    const item = document.createElement("div");
    item.className = "chat-item" + (chat.id === sessionId ? " active" : "");
    const title = document.createElement("div");
    title.className = "chat-item-title";
    title.textContent = chat.title || "Chat";
    title.title = chat.title || "Chat";
    title.setAttribute("role", "button");
    title.tabIndex = 0;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chat-delete-btn";
    remove.title = "Delete chat";
    remove.setAttribute("aria-label", `Delete chat: ${chat.title || "Chat"}`);
    remove.textContent = "×";
    title.addEventListener("click", () => loadChat(chat.id));
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        loadChat(chat.id);
      }
    });
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
    `Delete “${title}”? This removes its chat transcript and transition plan from this demo.`
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

function resetChatView() {
  messagesEl.innerHTML = "";
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
  inputEl.value = "";
  inputEl.style.height = "auto";
  humanBtn.disabled = false;
  humanBtn.textContent = t().humanBtn;

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
  resetChatView();
  renderEmptyPlan();
  renderChatList();
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

async function loadChat(id) {
  if (id === sessionId) return;
  if (speechSupported) window.speechSynthesis.cancel();
  try {
    const res = await fetch(`/api/sessions/${id}`);
    if (!res.ok) return;
    const data = await res.json();

    sessionId = id;
    sessionStorage.setItem("ltn-session-id", sessionId);
    sessionMessageCount = data.messages.length;
    humanHandoffActive = Boolean(data.needs_human);
    lastKnownAgent = data.assigned_agent || null;
    history = data.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: m.content }));

    messagesEl.innerHTML = "";
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
    await loadPlan();
    renderChatList();
  } catch (err) {
    console.error(err);
  }
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

applyLanguage(currentLang);
renderChatList();
loadPlan();
