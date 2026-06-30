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
