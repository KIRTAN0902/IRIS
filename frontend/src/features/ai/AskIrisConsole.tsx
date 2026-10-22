import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
} from "react";
import { AlertTriangle, ArrowUpRight, CornerDownLeft, ImagePlus, X } from "lucide-react";
import { useAIStatus, useAskIRIS, useIngestVision, useTodayState } from "@/hooks/queries";
import { useUiStore } from "@/stores";
import { Button } from "@/components/ui/Button";
import { Lamp } from "@/components/ui/Panel";
import { cn } from "@/lib/format";
import type { VisualContext } from "@/types/api";

const SUGGESTIONS = [
  "What should I do tonight?",
  "How am I doing this week?",
  "What deadlines are coming?",
  "Am I spending enough time on my startup?",
  "Why am I behind?",
  "Plan tomorrow.",
];

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp"];

interface ThreadMessage {
  role: "USER" | "ASSISTANT";
  content: string;
  source?: "AI" | "DETERMINISTIC";
  visualContext?: VisualContext;
  badge?: boolean;
}

/**
 * ASK IRIS — the intelligence layer's universal console.
 * Not a chat page: an overlay reachable from EVERY module via Cmd/Ctrl+K,
 * grounded in live context by the backend.
 */
export function AskIrisConsole() {
  const open = useUiStore((s) => s.askOpen);
  const setOpen = useUiStore((s) => s.setAskOpen);
  const ask = useAskIRIS();
  const vision = useIngestVision();
  const aiStatusQuery = useAIStatus();
  const todayState = useTodayState();
  const aiStatus = aiStatusQuery.data ?? todayState.data?.ai_status;
  const isAiOffline = aiStatus && (!aiStatus.responding || aiStatus.status === "NOT_RESPONDING");

  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [image, setImage] = useState<{ file: File; preview: string } | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const busy = ask.isPending || vision.isPending || submitting;

  useEffect(() => {
    if (open) {
      setQuestion("");
      setTimeout(() => inputRef.current?.focus(), 30);
    } else {
      setImage(null);
      setImageError(null);
    }
  }, [open]);

  useEffect(() => {
    return () => {
      if (image) URL.revokeObjectURL(image.preview);
    };
  }, [image]);

  // Escape closes from anywhere while the console is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const selectImage = (file: File) => {
    if (!IMAGE_TYPES.includes(file.type)) {
      setImageError("Use a PNG, JPEG or WebP image.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError("Image is larger than 10 MB.");
      return;
    }
    setImageError(null);
    setImage({ file, preview: URL.createObjectURL(file) });
  };

  const removeImage = () => {
    setImage(null);
    setImageError(null);
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const handlePaste = (e: ClipboardEvent<HTMLFormElement>) => {
    const file = Array.from(e.clipboardData.files).find((f) => f.type.startsWith("image/"));
    if (!file) return;
    e.preventDefault();
    selectImage(file);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = Array.from(e.dataTransfer.files).find((f) => f.type.startsWith("image/"));
    if (file) selectImage(file);
  };

  const submit = (q: string) => {
    const text = q.trim();
    if (busy || (!text && !image)) return;

    setImageError(null);
    if (image) {
      const currentImage = image;
      const prompt = text || "Extract the useful context from this image and act on it.";
      setQuestion("");
      setThread((t) => [
        ...t.slice(-8),
        { role: "USER", content: text || "Shared an image", badge: true },
      ]);
      setImage(null);
      setSubmitting(true);

      const reader = new FileReader();
      reader.onload = () => {
        vision.mutate(
          {
            image_base64: String(reader.result),
            mime_type: currentImage.file.type,
            prompt,
            conversation_id: conversationId,
          },
          {
            onSuccess: (res) => {
              setConversationId(res.conversation_id);
              setThread((t) => [
                ...t,
                {
                  role: "ASSISTANT",
                  content: res.answer,
                  source: res.source === "AI" ? "AI" : "DETERMINISTIC",
                  visualContext: res.visual_context,
                },
              ]);
            },
            onError: (err) => {
              setThread((t) => [
                ...t,
                { role: "ASSISTANT", content: `IRIS couldn't read that image: ${err.message}` },
              ]);
            },
            onSettled: () => setSubmitting(false),
          },
        );
      };
      reader.onerror = () => {
        setSubmitting(false);
        setThread((t) => [...t, { role: "ASSISTANT", content: "IRIS couldn't read that image." }]);
      };
      reader.readAsDataURL(currentImage.file);
      return;
    }

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
          <div
            className="w-full max-w-2xl border border-ops-line-bright bg-ops-panel"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            <form
              onClick={() => inputRef.current?.focus()}
              onPaste={handlePaste}
              onSubmit={(e) => {
                e.preventDefault();
                submit(question);
              }}
              className="flex items-center gap-3 border-b border-ops-line px-4 py-3 cursor-text"
            >
              <Lamp tone="ai" pulse />
              <input
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={image ? "Add a question about this image (optional)…" : "Ask IRIS anything about your life…"}
                maxLength={120000}
                aria-label="Ask IRIS"
                className="flex-1 bg-transparent text-[15px] text-ink placeholder:text-ink-faint focus:outline-none"
              />
              <input
                ref={imageInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) selectImage(file);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  imageInputRef.current?.click();
                }}
                aria-label="Attach a temporary image"
                title="Attach a temporary image"
                className="text-ink-faint hover:text-ai"
              >
                <ImagePlus size={16} />
              </button>
              <kbd className="border border-ops-line px-1.5 text-[10px] text-ink-faint select-none">
                esc
              </kbd>
            </form>

            {image && (
              <div className="flex items-center gap-3 border-b border-ops-line bg-ops-raised/40 px-4 py-2">
                <img src={image.preview} alt="" className="h-10 w-10 border border-ops-line object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] text-ink">{image.file.name}</p>
                  <p className="text-[10px] text-ink-faint">Processed in memory · never stored</p>
                </div>
                <button
                  type="button"
                  onClick={removeImage}
                  aria-label="Remove image"
                  className="text-ink-faint hover:text-ink"
                >
                  <X size={14} />
                </button>
              </div>
            )}

            {imageError && (
              <div className="border-b border-caution/30 bg-caution/10 px-4 py-2 text-[12px] text-caution">
                {imageError}
              </div>
            )}

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
                  <p className="mt-3 text-[11px] text-ink-faint">
                    Tip: paste or drop a screenshot, receipt or code snippet. IRIS reads it once and keeps only the text context.
                  </p>
                </div>
              ) : (
                <div className="max-h-[50vh] space-y-3 overflow-y-auto px-4 py-4">
                  {thread.map((m, i) => (
                    <div key={i} className="space-y-1">
                      <p className="label-caps flex items-center gap-2">
                        {m.role === "USER" ? (
                          <>
                            You
                            {m.badge && <span className="text-ai">· 📷 image</span>}
                          </>
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
                      {m.visualContext && (
                        <details className="border border-ops-line bg-ops-raised/30 px-2 py-1.5">
                          <summary className="cursor-pointer text-[11px] text-ink-faint">
                            Vision telemetry · {m.visualContext.detected_domain} · {m.visualContext.model}
                          </summary>
                          <div className="mt-1 space-y-1 text-[11px] text-ink-dim">
                            <p>{m.visualContext.summary}</p>
                            {m.visualContext.extracted_text_or_code && (
                              <p className="whitespace-pre-wrap text-ink-faint">
                                {m.visualContext.extracted_text_or_code}
                              </p>
                            )}
                            {m.visualContext.actionable_items.length > 0 && (
                              <p>
                                Actions:{" "}
                                {m.visualContext.actionable_items
                                  .map((item) => item.title || item.kind)
                                  .join(", ")}
                              </p>
                            )}
                          </div>
                        </details>
                      )}
                    </div>
                  ))}
                  {busy && (
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
