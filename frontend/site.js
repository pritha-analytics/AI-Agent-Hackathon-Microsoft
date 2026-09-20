// Demo LF Bergslagen marketing site. The chat itself is NOT reimplemented
// here -- it's the real app (index.html) embedded in an iframe, so every
// feature (bilingual replies, attachments, human handoff, ...) works
// exactly as it does standalone. This file only wires up the widget
// open/close behavior and lets page content (nav, hero, "life moment"
// cards) hand a starter message to that chat via postMessage.

const fabBtn = document.getElementById("chat-widget-fab");
const widgetEl = document.getElementById("chat-widget");
const closeBtn = document.getElementById("chat-widget-close");
const maximizeBtn = document.getElementById("chat-widget-maximize");
const fullscreenBtn = document.getElementById("chat-widget-fullscreen");
const frameEl = document.getElementById("chat-widget-frame");

let frameReady = false;
let pendingText = null;

// Three panel sizes: "compact" (the small corner bubble), "medium" (the
// existing maximize target), and "fullscreen" (the whole viewport, for
// customers who'd rather use the chat as its own full page). Only
// "compact" tells the embedded app to hide its sidebar -- both "medium"
// and "fullscreen" have enough room to show it normally.
let sizeMode = "compact";

function postToFrame(message) {
  if (!frameReady) return;
  frameEl.contentWindow.postMessage(message, window.location.origin);
}

frameEl.addEventListener("load", () => {
  if (frameEl.src === "about:blank") return;
  frameReady = true;
  postToFrame({ type: "ltn-widget-mode", mode: sizeMode === "compact" ? "compact" : "full" });
  if (pendingText) {
    sendToChat(pendingText);
    pendingText = null;
  }
});

function sendToChat(text) {
  if (!frameReady) {
    pendingText = text;
    return;
  }
  postToFrame({ type: "ltn-send", text });
}

function openWidget(text) {
  if (frameEl.src === "about:blank" || frameEl.getAttribute("src") === null) {
    frameEl.src = "index.html";
  }
  widgetEl.hidden = false;
  if (text) sendToChat(text);
}

function closeWidget() {
  widgetEl.hidden = true;
}

function setSizeMode(mode) {
  sizeMode = mode;
  widgetEl.classList.toggle("expanded", mode === "medium");
  widgetEl.classList.toggle("fullscreen", mode === "fullscreen");

  maximizeBtn.textContent = mode === "compact" ? "⤢" : "⤡";
  maximizeBtn.title = mode === "compact" ? "Expand" : "Shrink";
  maximizeBtn.setAttribute("aria-label", mode === "compact" ? "Expand chat" : "Shrink chat");

  fullscreenBtn.textContent = mode === "fullscreen" ? "🗗" : "⛶";
  fullscreenBtn.title = mode === "fullscreen" ? "Exit full screen" : "Full screen";
  fullscreenBtn.setAttribute("aria-label", mode === "fullscreen" ? "Exit full screen" : "Full screen chat");

  // The fab has nowhere sensible to sit once the panel covers the whole
  // viewport, and the panel's own close button is still reachable there.
  fabBtn.hidden = mode === "fullscreen";

  postToFrame({ type: "ltn-widget-mode", mode: mode === "compact" ? "compact" : "full" });
}

fabBtn.addEventListener("click", () => {
  if (widgetEl.hidden) {
    openWidget();
  } else {
    closeWidget();
  }
});

closeBtn.addEventListener("click", closeWidget);
maximizeBtn.addEventListener("click", () => setSizeMode(sizeMode === "compact" ? "medium" : "compact"));
fullscreenBtn.addEventListener("click", () => setSizeMode(sizeMode === "fullscreen" ? "medium" : "fullscreen"));

document.getElementById("hero-chat-btn").addEventListener("click", () => openWidget());

document.getElementById("footer-chat-link").addEventListener("click", (event) => {
  event.preventDefault();
  openWidget();
});

// Every card/button that carries a data-text opens the chat with that
// starter message - covers the "life moments" grid, the product icon grid,
// the "Popular" quick-link buttons, and the become-a-customer CTA band.
// Purely decorative elements (search, log in, the Private/Business tabs,
// the app/BankID quick links) intentionally have no handler - this demo
// doesn't implement real search, auth, or those linked products.
document.querySelectorAll("[data-text]").forEach((btn) => {
  btn.addEventListener("click", () => openWidget(btn.dataset.text));
});
