// Minimal local equivalent of reference/ai-system's static/js/modalManager.js
// registration shape — just the register()/_AUTO_WIRE contract this app
// actually uses, not a port of the full file (which assumes rail/sidebar
// dashboard UI elements this single-page app doesn't have).

const _state = new Map();

const _AUTO_WIRE = {
  "chat-panel": { rail: null, sidebar: null },
};

export function register(id, { restoreFn, closeFn, railBtnId, sidebarBtnId } = {}) {
  _state.set(id, {
    restoreFn: restoreFn || (() => {}),
    closeFn: closeFn || (() => {}),
    railBtnId: railBtnId || null,
    sidebarBtnId: sidebarBtnId || null,
    isMinimized: false,
  });
}

export function isRegistered(id) {
  return _state.has(id);
}

function _autoRegister(id) {
  if (_state.has(id)) return _state.get(id);
  const wire = _AUTO_WIRE[id];
  if (!wire) return null;
  register(id, { railBtnId: wire.rail, sidebarBtnId: wire.sidebar });
  return _state.get(id);
}

export function restore(id) {
  const entry = _state.get(id) || _autoRegister(id);
  if (!entry) return;
  entry.isMinimized = false;
  entry.restoreFn();
}

export function close(id) {
  const entry = _state.get(id);
  if (!entry) return;
  entry.closeFn();
}

export function isMinimized(id) {
  const entry = _state.get(id);
  return entry ? entry.isMinimized : false;
}

export function minimize(id) {
  const entry = _state.get(id);
  if (entry) entry.isMinimized = true;
}

const panelManager = { register, isRegistered, restore, close, isMinimized, minimize };
export default panelManager;
window.PanelManager = panelManager;
