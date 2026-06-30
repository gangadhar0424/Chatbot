export type Role = "user" | "assistant";

export interface Message {
  role: Role;
  content: string;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Phase = "gathering" | "ready_for_prd";

export interface ChatReply {
  reply: string;
  phase: Phase;
  spec: Record<string, unknown>;
}

/**
 * Send a message for a session and return the reply, phase, and current spec.
 * The backend owns the authoritative spec + history per session_id (Milestone 2).
 */
export async function postChat(
  sessionId: string,
  message: string
): Promise<ChatReply> {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });

  if (!res.ok) {
    throw new Error(`Backend returned ${res.status}`);
  }

  return (await res.json()) as ChatReply;
}

export interface PrdReply {
  prd: string;
}

/**
 * Generate the PRD for a completed session. Called once after the user
 * confirms their answers. The backend runs its own completeness gate before
 * invoking Prompt B — returns 409 if any field is still empty.
 */
export async function generatePrd(sessionId: string): Promise<PrdReply> {
  const res = await fetch(`${API_BASE_URL}/generate-prd`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      (detail as { detail?: string }).detail ?? `Backend returned ${res.status}`
    );
  }

  return (await res.json()) as PrdReply;
}

export interface ScaffoldResult {
  output_path: string;
  template: string;
  match_exact: boolean;
  match_note: string | null;
  files_created: string[];
}

/**
 * Generate a project scaffold from the completed spec.
 * Returns the output directory path and list of files written to disk
 * (server-side). The backend runs the same completeness gate as generate-prd.
 */
export async function generateScaffold(
  sessionId: string
): Promise<ScaffoldResult> {
  const res = await fetch(`${API_BASE_URL}/generate-scaffold`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      (detail as { detail?: string }).detail ?? `Backend returned ${res.status}`
    );
  }
  return (await res.json()) as ScaffoldResult;
}
