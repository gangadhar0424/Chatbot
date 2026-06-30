"use client";

import { useEffect, useRef, useState } from "react";
import { postChat, type Message, type Phase } from "@/lib/api";

// Canned reply the "Not sure / skip" button sends. Prompt A is instructed to
// treat this as a deliberate "unspecified" answer for the current field rather
// than a non-answer to keep probing.
const SKIP_MESSAGE = "I'm not sure, let's move on.";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("gathering");
  const bottomRef = useRef<HTMLDivElement>(null);

  // One stable session id per browser tab, created on first render. The backend
  // keys the persisted spec + history on this.
  const sessionIdRef = useRef<string | null>(null);
  if (sessionIdRef.current === null) {
    sessionIdRef.current =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const ready = phase === "ready_for_prd";

  async function sendMessage(text: string) {
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setError(null);
    setLoading(true);

    try {
      const { reply, phase: nextPhase } = await postChat(
        sessionIdRef.current!,
        text
      );
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      setPhase(nextPhase);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    await sendMessage(text);
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col p-4">
      <h1 className="mb-4 text-xl font-semibold">Project Intake Chatbot</h1>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-lg border border-slate-300 bg-white p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            Say hello to start the conversation.
          </p>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "text-right" : "text-left"}
          >
            <span
              className={
                "inline-block max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm " +
                (m.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-200 text-slate-900")
              }
            >
              {m.content}
            </span>
          </div>
        ))}

        {loading && (
          <div className="text-left">
            <span className="inline-block rounded-2xl bg-slate-200 px-4 py-2 text-sm text-slate-500">
              thinking…
            </span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {ready && (
        <p className="mt-3 rounded-lg bg-green-100 px-4 py-2 text-sm font-medium text-green-800">
          ✓ All set — I have everything I need. Preparing your PRD…
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={ready ? "Intake complete" : "Type a message…"}
          disabled={loading || ready}
        />
        <button
          type="button"
          onClick={() => sendMessage(SKIP_MESSAGE)}
          disabled={loading || ready}
          title="Skip this question — I'm not sure / no preference"
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
        >
          Not sure
        </button>
        <button
          type="submit"
          disabled={loading || ready || !input.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </main>
  );
}
