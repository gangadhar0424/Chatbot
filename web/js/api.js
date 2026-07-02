// Plain-fetch equivalent of frontend/lib/api.ts, pointed at the new
// prd_routes.py endpoints (mounted at /api/prd on this same origin, since
// web_app.py serves both the API and this static frontend).

const API_BASE_URL = "/api/prd";

export async function postChat(sessionId, message) {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) {
    throw new Error(`Backend returned ${res.status}`);
  }
  return res.json();
}

export async function generatePrd(sessionId) {
  const res = await fetch(`${API_BASE_URL}/generate-prd`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Backend returned ${res.status}`);
  }
  return res.json();
}

export async function generateScaffold(sessionId) {
  const res = await fetch(`${API_BASE_URL}/generate-scaffold`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Backend returned ${res.status}`);
  }
  return res.json();
}
