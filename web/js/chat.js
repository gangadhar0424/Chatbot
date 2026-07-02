// ES module shaped like reference/ai-system's static/js/notes.js: exports
// openPanel/closePanel/togglePanel/isPanelOpen, and self-registers with
// panelManager.js the same way notes.js registers with modalManager.js.
// notes.js itself has no window.* assignment; window.ChatModule is added
// here per this project's explicit convention.
//
// Reproduces frontend/app/page.tsx's behavior exactly: chat / confirm / prd
// views, the "Not sure / skip" button, loading state, and error handling.

import PanelManager from "./panelManager.js";
import { postChat, generatePrd, generateScaffold } from "./api.js";
import { renderSpecSummary } from "./specSummary.js";

// Kept in sync with SKIP_MESSAGE in backend/app/flow.py.
const SKIP_MESSAGE = "I'm not sure, let's move on.";

function newSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

const state = {
  uiState: "chat", // "chat" | "confirm" | "prd"
  messages: [],
  spec: {},
  prd: "",
  loading: false,
  generating: false,
  scaffolding: false,
  scaffoldResult: null,
  error: null,
  sessionId: newSessionId(),
};

let _open = false;
let _root = null;

export function openPanel() {
  _open = true;
  const panel = document.getElementById("chat-panel");
  panel?.classList.remove("hidden");
  render();
}

export function closePanel() {
  _open = false;
  document.getElementById("chat-panel")?.classList.add("hidden");
}

export function togglePanel() {
  if (_open) {
    closePanel();
  } else {
    openPanel();
  }
}

export function isPanelOpen() {
  return _open;
}

function _ensureChatPanelRegistered() {
  if (PanelManager.isRegistered("chat-panel")) return;
  PanelManager.register("chat-panel", {
    restoreFn: () => openPanel(),
    closeFn: () => closePanel(),
  });
}

// ── DOM helpers ──────────────────────────────────────────────────────────

function el(tag, className, children, attrs) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (k === "disabled") {
      if (v) node.setAttribute("disabled", "");
    } else {
      node.setAttribute(k, v);
    }
  }
  for (const child of children ?? []) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function button(label, className, onClick, opts) {
  const btn = el("button", className, [label], {
    type: opts?.type ?? "button",
    disabled: opts?.disabled,
    title: opts?.title,
  });
  btn.addEventListener("click", onClick);
  return btn;
}

// ── Actions ──────────────────────────────────────────────────────────────

async function sendMessage(text) {
  if (!text || state.loading) return;
  state.messages.push({ role: "user", content: text });
  state.error = null;
  state.loading = true;
  render();
  try {
    const { reply, phase, spec } = await postChat(state.sessionId, text);
    state.messages.push({ role: "assistant", content: reply });
    state.spec = spec;
    state.uiState = phase === "ready_for_prd" ? "confirm" : "chat";
  } catch (err) {
    state.error = err instanceof Error ? err.message : "Something went wrong";
  } finally {
    state.loading = false;
    render();
  }
}

async function handleGeneratePrd() {
  state.generating = true;
  state.error = null;
  render();
  try {
    const { prd } = await generatePrd(state.sessionId);
    state.prd = prd;
    state.uiState = "prd";
  } catch (err) {
    state.error = err instanceof Error ? err.message : "PRD generation failed";
  } finally {
    state.generating = false;
    render();
  }
}

function handleDownload() {
  const blob = new Blob([state.prd], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "project-prd.md";
  a.click();
  URL.revokeObjectURL(url);
}

async function handleGenerateScaffold() {
  state.scaffolding = true;
  state.error = null;
  render();
  try {
    state.scaffoldResult = await generateScaffold(state.sessionId);
  } catch (err) {
    state.error = err instanceof Error ? err.message : "Scaffold generation failed";
  } finally {
    state.scaffolding = false;
    render();
  }
}

function handleStartOver() {
  state.sessionId = newSessionId();
  state.messages = [];
  state.spec = {};
  state.prd = "";
  state.scaffoldResult = null;
  state.error = null;
  state.uiState = "chat";
  render();
}

// ── Views ────────────────────────────────────────────────────────────────

function renderChatView() {
  const main = el("main", "view view-chat");
  main.appendChild(el("h1", "view-title", ["Project Intake Chatbot"]));

  const messageList = el("div", "message-list");
  if (state.messages.length === 0) {
    messageList.appendChild(el("p", "message-list-empty", ["Say hello to start the conversation."]));
  }
  for (const m of state.messages) {
    const row = el("div", m.role === "user" ? "message-row message-row-user" : "message-row message-row-assistant");
    row.appendChild(el("span", m.role === "user" ? "bubble bubble-user" : "bubble bubble-assistant", [m.content]));
    messageList.appendChild(row);
  }
  if (state.loading) {
    const row = el("div", "message-row message-row-assistant");
    row.appendChild(el("span", "bubble bubble-assistant bubble-loading", ["thinking…"]));
    messageList.appendChild(row);
  }
  main.appendChild(messageList);

  if (state.error) {
    main.appendChild(el("p", "error-text", [state.error]));
  }

  const form = el("form", "chat-form");
  const input = el("input", "chat-input", [], {
    type: "text",
    placeholder: "Type a message…",
    disabled: state.loading,
  });
  input.value = "";

  form.appendChild(input);
  form.appendChild(
    button("Not sure", "btn btn-secondary", () => sendMessage(SKIP_MESSAGE), {
      disabled: state.loading,
      title: "Skip this question — I'm not sure / no preference",
    })
  );
  const submitBtn = button("Send", "btn btn-primary", () => {}, {
    type: "submit",
    disabled: state.loading || !input.value.trim(),
  });
  form.appendChild(submitBtn);

  input.addEventListener("input", () => {
    submitBtn.disabled = state.loading || !input.value.trim();
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || state.loading) return;
    input.value = "";
    sendMessage(text);
  });

  main.appendChild(form);

  requestAnimationFrame(() => {
    messageList.scrollTop = messageList.scrollHeight;
  });

  return main;
}

function renderConfirmView() {
  const main = el("main", "view view-confirm");
  main.appendChild(el("h1", "view-title", ["Review your answers"]));
  main.appendChild(
    el("p", "view-subtitle", [
      "Everything below will go into your PRD. Go back to correct anything before generating.",
    ])
  );
  main.appendChild(renderSpecSummary(state.spec));

  if (state.error) {
    main.appendChild(el("p", "error-text", [state.error]));
  }

  const actions = el("div", "action-row");
  actions.appendChild(
    button(
      "Edit answers",
      "btn btn-secondary",
      () => {
        state.uiState = "chat";
        render();
      },
      { disabled: state.generating }
    )
  );
  actions.appendChild(
    button(state.generating ? "Generating…" : "Generate PRD", "btn btn-primary", handleGeneratePrd, {
      disabled: state.generating,
    })
  );
  main.appendChild(actions);

  return main;
}

function renderPrdView() {
  const main = el("main", "view view-prd");

  const header = el("div", "prd-header");
  header.appendChild(el("h1", "view-title", ["Your PRD"]));
  const headerActions = el("div", "action-row");
  headerActions.appendChild(button("Download .md", "btn btn-secondary", handleDownload));
  headerActions.appendChild(button("Start over", "btn btn-muted", handleStartOver));
  header.appendChild(headerActions);
  main.appendChild(header);

  const doc = el("div", "prd-doc");
  const article = el("article", "prose");
  if (window.marked) {
    article.innerHTML = window.marked.parse(state.prd);
  } else {
    article.textContent = state.prd;
  }
  doc.appendChild(article);
  main.appendChild(doc);

  const scaffoldBox = el("div", "scaffold-box");
  scaffoldBox.appendChild(el("h2", "scaffold-title", ["Generate project scaffold"]));
  scaffoldBox.appendChild(
    el("p", "scaffold-desc", [
      "Creates a starter file tree on the server based on your spec — no packages installed, no commands run.",
    ])
  );

  if (!state.scaffoldResult) {
    if (state.error) scaffoldBox.appendChild(el("p", "error-text", [state.error]));
    scaffoldBox.appendChild(
      button(
        state.scaffolding ? "Generating…" : "Generate Project Scaffold",
        "btn btn-primary",
        handleGenerateScaffold,
        { disabled: state.scaffolding }
      )
    );
  } else {
    const r = state.scaffoldResult;
    const info = el("div", "scaffold-info");

    const templateRow = el("div", null, [
      el("span", "field-label-inline", ["Template: "]),
      el("code", "code-chip", [r.template]),
    ]);
    if (!r.match_exact) {
      templateRow.appendChild(el("span", "tag tag-warn", ["approximate match"]));
    }
    info.appendChild(templateRow);

    if (r.match_note) {
      info.appendChild(el("p", "scaffold-note", [r.match_note]));
    }

    info.appendChild(
      el("div", null, [el("span", "field-label-inline", ["Output: "]), el("code", "code-inline", [r.output_path])])
    );

    const details = el("details", "scaffold-files");
    details.appendChild(el("summary", null, [`${r.files_created.length} files created`]));
    const list = el(
      "ul",
      "scaffold-file-list",
      r.files_created.map((f) => el("li", null, [el("code", "code-inline", [f])]))
    );
    details.appendChild(list);
    info.appendChild(details);

    scaffoldBox.appendChild(info);
  }

  main.appendChild(scaffoldBox);
  return main;
}

// ── Root render ──────────────────────────────────────────────────────────

function render() {
  if (!_root) return;
  _root.innerHTML = "";
  if (state.uiState === "chat") {
    _root.appendChild(renderChatView());
  } else if (state.uiState === "confirm") {
    _root.appendChild(renderConfirmView());
  } else {
    _root.appendChild(renderPrdView());
  }
}

_ensureChatPanelRegistered();
_root = document.getElementById("chat-panel");
openPanel();

const chatModule = { openPanel, closePanel, togglePanel, isPanelOpen };
export default chatModule;
window.ChatModule = chatModule;
