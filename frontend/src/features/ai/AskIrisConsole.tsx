import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowUpRight, CornerDownLeft } from "lucide-react";
import { useAIStatus, useAskIRIS, useTodayState } from "@/hooks/queries";
import { useUiStore } from "@/stores";
import { Button } from "@/components/ui/Button";
import { Lamp } from "@/components/ui/Panel";
import { cn } from "@/lib/format";

const SUGGESTIONS = [
  "What should I do tonight?",
  "How am I doing this week?",
  "What deadlines are coming?",
  "Am I spending enough time on my startup?",
  "Why am I behind?",
  "Plan tomorrow.",
];

/**
 * ASK IRIS — the intelligence layer's universal console.
 * Not a chat page: an overlay reachable from EVERY module via Cmd/Ctrl+K,
 * grounded in live context by the backend.
 */
export function AskIrisConsole() {
  const open = useUiStore((s) => s.askOpen);
  const setOpen = useUiStore((s) => s.setAskOpen);
  const ask = useAskIRIS();
  const aiStatusQuery = useAIStatus();
  const todayState = useTodayState();
  const aiStatus = aiStatusQuery.data ?? todayState.data?.ai_status;
  const isAiOffline = aiStatus && (!aiStatus.responding || aiStatus.status === "NOT_RESPONDING");

  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [thread, setThread] = useState<{ role: "USER" | "ASSISTANT"; content: string; source?: "AI" | "DETERMINISTIC" }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuestion("");
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  // Escape closes from anywhere while the console is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const submit = (q: string) => {
    const text = q.trim();
    if (!text || ask.isPending) return;
    setQuestion("");
    setThread((t) => [...t.slice(-8), { role: "USER", content: text }]);
    ask.mutate(
      { question: text, conversation_id: conversationId },
      {
        onSuccess: (res) => {
          setConversationId(res.conversation_id);
          setThread((t) => [...t, { role: "ASSISTANT", content: res.answer, source: res.source }]);
        },
        onError: (err) => {
          setThread((t) => [...t, { role: "ASSISTANT", content: `IRIS couldn't answer: ${err.message}` }]);
        },
      },
    );
  };

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-[2px] px-4 pt-[12vh]"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="w-full max-w-2xl border border-ops-line-bright bg-ops-panel">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submit(question);
              }}
              className="flex items-center gap-3 border-b border-ops-line px-4 py-3"
            >
              <Lamp tone="ai" pulse />
              <input
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask IRIS anything about your life…"
                maxLength={2000}
                minLength={3}
                aria-label="Ask IRIS"
                className="flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-faint focus:outline-none"
              />
              <kbd className="border border-ops-line px-1.5 text-[10px] text-ink-faint">
                esc
              </kbd>
            </form>

            {isAiOffline && (
              <div className="flex items-center gap-2 border-b border-caution/30 bg-caution/10 px-4 py-2 text-[12px] text-caution">
                <AlertTriangle size={13} className="shrink-0 text-caution" />
                <span className="truncate">
                  AI provider offline ({aiStatus?.provider}: {aiStatus?.model}) · IRIS is answering via deterministic fallback rules.
                </span>
              </div>
            )}

            <button onClick={() => setOpen(false)} className="sr-only">Close</button>
            <div
              onKeyDown={(e) => {
                if (e.key === "Escape") setOpen(false);
              }}
            >
              {thread.length === 0 ? (
                <div className="px-4 py-4">
                  <p className="label-caps mb-2.5">Try asking</p>
                  <ul className="space-y-1">
                    {SUGGESTIONS.map((s) => (
                      <li key={s}>
                        <button
                          onClick={() => submit(s)}
                          className="group flex w-full items-center gap-2 px-2 py-1.5 text-left text-[14px] text-ink-dim hover:bg-ops-raised hover:text-ink"
                        >
                          <ArrowUpRight size={13} className="text-ink-faint group-hover:text-ai" />
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="max-h-[50vh] space-y-3 overflow-y-auto px-4 py-4">
                  {thread.map((m, i) => (
                    <div key={i} className="space-y-1">
                      <p className="label-caps flex items-center gap-2">
                        {m.role === "USER" ? (
                          "You"
                        ) : (
                          <>
                            IRIS
                            {m.source && (
                              <span
                                className={cn(
                                  "font-[family-name:var(--font-body)] normal-case tracking-normal text-[10px]",
                                  m.source === "AI" ? "text-ai" : "text-ink-faint",
                                )}
                              >
                                · {m.source === "AI" ? "AI reasoning" : "deterministic data"}
                              </span>
                            )}
                          </>
                        )}
                      </p>
                      <p
                        className={cn(
                          "whitespace-pre-wrap text-[14px] leading-relaxed",
                          m.role === "USER" ? "text-ink-dim" : "text-ink",
                        )}
                      >
                        {m.content}
                      </p>
                    </div>
                  ))}
                  {ask.isPending && (
                    <p className="tnum animate-pulse text-[12px] text-ai">IRIS is thinking…</p>
                  )}
                </div>
              )}

              {thread.length > 0 && (
                <div className="border-t border-ops-line px-4 py-2">
                  <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
                    Close <CornerDownLeft size={11} />
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
