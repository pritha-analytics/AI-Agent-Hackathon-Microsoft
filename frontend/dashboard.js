const sessionListEl = document.getElementById("session-list");
const conversationHeaderEl = document.getElementById("conversation-header");
const conversationMessagesEl = document.getElementById("conversation-messages");
const replyFormEl = document.getElementById("reply-form");
const replyInputEl = document.getElementById("reply-input");
const replyNameEl = document.getElementById("reply-name");

let activeSessionId = null;

replyNameEl.value = localStorage.getItem("ltn-support-name") || "";
replyNameEl.addEventListener("change", () => {
  localStorage.setItem("ltn-support-name", replyNameEl.value.trim());
});

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function linkify(text) {
  return text.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+|tel:[^\s)]+|mailto:[^\s)]+)\)/g,
    (_match, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
  );
}

function boldify(text) {
  return text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderInline(raw) {
  return raw
    .split("\n")
    .map((line) => boldify(linkify(escapeHtml(line))))
    .join("<br>");
}

function roleLabel(role) {
  if (role === "assistant") return "Sara · Digital Companion";
  if (role === "human") return "Support (human)";
  return "Customer";
}

async function refreshSessionList() {
  try {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    sessionListEl.innerHTML = "";

    if (!data.sessions.length) {
      sessionListEl.innerHTML = '<p class="empty-hint">No chats yet.</p>';
      return;
    }

    for (const session of data.sessions) {
      const item = document.createElement("div");
      item.className = "session-item" + (session.session_id === activeSessionId ? " active" : "");
      item.innerHTML = `
        <div class="session-id">${session.session_id.slice(0, 8)}</div>
        <div class="session-preview">${escapeHtml(session.last_message || "(no messages)")}</div>
        ${session.needs_human ? '<span class="needs-human-badge">WANTS HUMAN</span>' : ""}
      `;
      item.addEventListener("click", () => selectSession(session.session_id));
      sessionListEl.appendChild(item);
    }
  } catch (err) {
    console.error(err);
  }
}

async function selectSession(sessionId) {
  activeSessionId = sessionId;
  replyFormEl.hidden = false;
  conversationHeaderEl.textContent = `Chat ${sessionId.slice(0, 8)}`;
  await refreshConversation();
  await refreshSessionList();
}

async function refreshConversation() {
  if (!activeSessionId) return;
  try {
    const res = await fetch(`/api/sessions/${activeSessionId}`);
    if (!res.ok) return;
    const data = await res.json();
    conversationMessagesEl.innerHTML = "";
    for (const msg of data.messages) {
      const div = document.createElement("div");
      div.className = `msg ${msg.role === "user" ? "user" : msg.role === "human" ? "human" : "assistant"}`;
      div.innerHTML = `<span class="msg-label">${roleLabel(msg.role)}</span>${renderInline(msg.content)}`;
      conversationMessagesEl.appendChild(div);
    }
    conversationMessagesEl.scrollTop = conversationMessagesEl.scrollHeight;
  } catch (err) {
    console.error(err);
  }
}

replyFormEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = replyInputEl.value.trim();
  if (!text || !activeSessionId) return;
  const name = replyNameEl.value.trim();
  const content = name ? `**${name}, LF Bergslagen:** ${text}` : text;
  replyInputEl.value = "";

  try {
    await fetch(`/api/sessions/${activeSessionId}/human-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    await refreshConversation();
  } catch (err) {
    console.error(err);
  }
});

refreshSessionList();
setInterval(refreshSessionList, 3000);
setInterval(refreshConversation, 3000);
