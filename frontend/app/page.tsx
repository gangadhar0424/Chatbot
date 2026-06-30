"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { generatePrd, postChat, type Message } from "@/lib/api";
import SpecSummary from "@/app/components/SpecSummary";

// Canned reply the "Not sure / skip" button sends. Prompt A treats it as a
// deliberate "unspecified" answer for the current field. Kept in sync with
// SKIP_MESSAGE in backend/app/flow.py.
const SKIP_MESSAGE = "I'm not sure, let's move on.";

type UiState = "chat" | "confirm" | "prd";

function newSessionId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ChatPage() {
  const [uiState, setUiState] = useState<UiState>("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [spec, setSpec] = useState<Record<string, unknown>>({});
  const [prd, setPrd] = useState("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // One stable session id per browser tab; backend keys spec + history on it.
  const sessionIdRef = useRef<string>(newSessionId());

  useEffect(() => {
    if (uiState === "chat") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, uiState]);

  async function sendMessage(text: string) {
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setError(null);
    setLoading(true);
    try {
      const { reply, phase, spec: nextSpec } = await postChat(
        sessionIdRef.current,
        text
      );
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      setSpec(nextSpec);
      // phase drives the view: ready_for_prd → review screen, otherwise stay in chat.
      setUiState(phase === "ready_for_prd" ? "confirm" : "chat");
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

  async function handleGeneratePrd() {
    setGenerating(true);
    setError(null);
    try {
      const { prd: markdown } = await generatePrd(sessionIdRef.current);
      setPrd(markdown);
      setUiState("prd");
    } catch (err) {
      setError(err instanceof Error ? err.message : "PRD generation failed");
    } finally {
      setGenerating(false);
    }
  }

  function handleDownload() {
    const blob = new Blob([prd], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "project-prd.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleStartOver() {
    sessionIdRef.current = newSessionId();
    setMessages([]);
    setInput("");
    setSpec({});
    setPrd("");
    setError(null);
    setUiState("chat");
  }

  // ── Chat view ──────────────────────────────────────────────────────────────
  if (uiState === "chat") {
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

        <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message…"
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => sendMessage(SKIP_MESSAGE)}
            disabled={loading}
            title="Skip this question — I'm not sure / no preference"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
          >
            Not sure
          </button>
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </main>
    );
  }

  // ── Confirm view ───────────────────────────────────────────────────────────
  if (uiState === "confirm") {
    return (
      <main className="mx-auto max-w-2xl p-4 pb-16">
        <h1 className="mb-1 text-xl font-semibold">Review your answers</h1>
        <p className="mb-6 text-sm text-slate-500">
          Everything below will go into your PRD. Go back to correct anything
          before generating.
        </p>

        <SpecSummary spec={spec} />

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        <div className="mt-8 flex gap-3">
          <button
            onClick={() => setUiState("chat")}
            disabled={generating}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Edit answers
          </button>
          <button
            onClick={handleGeneratePrd}
            disabled={generating}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate PRD"}
          </button>
        </div>
      </main>
    );
  }

  // ── PRD view ───────────────────────────────────────────────────────────────
  return (
    <main className="mx-auto max-w-3xl p-4 pb-16">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Your PRD</h1>
        <div className="flex gap-2">
          <button
            onClick={handleDownload}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Download .md
          </button>
          <button
            onClick={handleStartOver}
            className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
          >
            Start over
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 sm:p-8">
        <article className="prose prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{prd}</ReactMarkdown>
        </article>
      </div>
    </main>
  );
}
