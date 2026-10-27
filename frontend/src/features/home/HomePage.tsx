import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { ArrowUp, Mic, Play, Plus, X } from "lucide-react";
import {
  useCompleteTask,
  useConversation,
  useCreateConversation,
  useSendMessage,
  useStartFocus,
} from "@/hooks/queries";
import { Markdown } from "@/components/ui/Markdown";
import { Skeleton } from "@/components/ui/Overlay";
import { cn, fmtTime, humanDuration, urgencyLabel } from "@/lib/format";
import type { RankedTasksResponse } from "@/api/endpoints";
import type { ChatMessageOut, TaskOut } from "@/types/api";
import { useVoiceConversation, type VoicePhase } from "@/features/home/voice";
import { IrisSphere } from "@/features/home/IrisSphere";
import { TodayDashboard } from "@/features/home/TodayDashboard";

/**
 * HOME: a new chat by default, showing only "IRIS" and the composer (like
 * ChatGPT). Past conversations open from the sidebar via ?c=<id>.
 */
export function HomePage() {
  const [params, setParams] = useSearchParams();
  const activeId = Number(params.get("c")) || null;

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-1 flex-col">
      <Conversation
        conversationId={activeId}
        onCreated={(id) => setParams({ c: String(id) }, { replace: true })}
      />
    </div>
  );
}

interface AttachedImage {
  id: string;
  file: File;
  preview: string;
}

// --- Conversation ------------------------------------------------------------------

function Conversation({
  conversationId,
  onCreated,
}: {
  conversationId: number | null;
  onCreated: (id: number) => void;
}) {
  const conv = useConversation(conversationId);
  const createConv = useCreateConversation();
  const sendMsg = useSendMessage();
  const [input, setInput] = useState("");
  const [lastSent, setLastSent] = useState("");
  const [lastSentImages, setLastSentImages] = useState<string[]>([]);
  const [images, setImages] = useState<AttachedImage[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const objectUrlsRef = useRef<Set<string>>(new Set());
  // The conversation this component just created from a new chat: switching to
  // it must not reset the in-flight reply.
  const createdRef = useRef<number | null>(null);
  // The conversation to send to, kept current for the voice loop's async turns.
  const idRef = useRef(conversationId);
  useEffect(() => {
    idRef.current = conversationId;
  }, [conversationId]);

  const messages = conv.data?.messages ?? [];

  // Clean up object URLs only when Conversation unmounts
  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  useEffect(() => {
    if (conversationId !== null && conversationId === createdRef.current) return;
    setInput("");
    setLastSent("");
    setLastSentImages([]);
    images.forEach((img) => {
      URL.revokeObjectURL(img.preview);
      objectUrlsRef.current.delete(img.preview);
    });
    setImages([]);
    setImageError(null);
    sendMsg.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    if (messages.length || sendMsg.isPending) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, sendMsg.isPending]);

  const addImages = (files: File[]) => {
    const validExtensions = /\.(png|jpe?g|webp)$/i;
    const validMimes = ["image/png", "image/jpeg", "image/jpg", "image/webp"];
    const maxBytes = 10 * 1024 * 1024;
    const newImages: AttachedImage[] = [];
    let err: string | null = null;

    for (const file of files) {
      const type = (file.type || "").toLowerCase();
      if (!validMimes.includes(type) && !validExtensions.test(file.name)) {
        err = "Please upload PNG, JPEG, or WebP images.";
        continue;
      }
      if (file.size > maxBytes) {
        err = `${file.name} is larger than 10 MB limit.`;
        continue;
      }
      const previewUrl = URL.createObjectURL(file);
      objectUrlsRef.current.add(previewUrl);
      newImages.push({
        id: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 7)}`,
        file,
        preview: previewUrl,
      });
    }

    if (err && newImages.length === 0) {
      setImageError(err);
      return;
    }
    setImageError(null);
    setImages((prev) => [...prev, ...newImages]);
  };

  const removeImage = (id: string) => {
    setImages((prev) => {
      const target = prev.find((img) => img.id === id);
      if (target) {
        URL.revokeObjectURL(target.preview);
        objectUrlsRef.current.delete(target.preview);
      }
      return prev.filter((img) => img.id !== id);
    });
  };

  /** Send a message (creating the conversation first if needed); resolves with IRIS's reply. */
  const send = async (text?: string, voice = false): Promise<ChatMessageOut | null> => {
    const content = (text ?? input).trim();
    if ((!content && images.length === 0) || sendMsg.isPending) return null;

    const currentImages = [...images];
    let imagePayloads: Array<{ image_base64: string; mime_type: string }> = [];

    if (currentImages.length > 0) {
      try {
        imagePayloads = await Promise.all(
          currentImages.map(async (img) => {
            const b64 = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => resolve(String(reader.result));
              reader.onerror = reject;
              reader.readAsDataURL(img.file);
            });
            return { image_base64: b64, mime_type: img.file.type };
          })
        );
      } catch {
        setImageError("Failed to read image files.");
        return null;
      }
    }

    const effectiveContent =
      content ||
      (currentImages.length > 1
        ? "Analyze these images"
        : currentImages.length === 1
        ? "Analyze this image"
        : "");
    let id = idRef.current;
    if (!id) {
      try {
        const title = (
          content ||
          (currentImages.length > 1 ? `${currentImages.length} images inquiry` : currentImages[0]?.file.name) ||
          "Image inquiry"
        ).slice(0, 60);
        id = (await createConv.mutateAsync(title)).id;
        createdRef.current = id;
        idRef.current = id;
        onCreated(id);
      } catch {
        return null;
      }
    }
    setLastSent(effectiveContent);
    setLastSentImages(currentImages.map((img) => img.preview));
    setInput("");
    setImages([]);
    setImageError(null);
    try {
      return await sendMsg.mutateAsync({
        conversationId: id,
        content: effectiveContent,
        voice,
        image_base64: imagePayloads.length === 1 ? imagePayloads[0]?.image_base64 : undefined,
        mime_type: imagePayloads.length === 1 ? imagePayloads[0]?.mime_type : undefined,
        images: imagePayloads,
      });
    } catch {
      return null;
    }
  };

  const voice = useVoiceConversation(async (text) => (await send(text, true))?.content ?? null);
  const talking = voice.phase !== "off";

  const busy = sendMsg.isPending || createConv.isPending;
  const isNewChat = !conversationId && !busy;

  const composer = (
    <>
      <Composer
        value={input}
        onChange={setInput}
        onSend={() => send()}
        onVoice={voice.start}
        disabled={busy}
        images={images}
        onAddImages={addImages}
        onRemoveImage={removeImage}
        imageError={imageError}
      />
      {voice.notice && !talking && (
        <p className="mt-2 px-4 text-center text-[13px] text-ink-faint" role="status">
          {voice.notice}
        </p>
      )}
      {talking && <VoiceOverlay voice={voice} />}
    </>
  );

  if (isNewChat) {
    // Home: the day at a glance, with IRIS one message away.
    return (
      <div className="flex flex-1 flex-col">
        <div className="flex-1">
          <TodayDashboard />
        </div>
        <div
          className="sticky z-20 relative bg-gradient-to-t from-ops-ground from-75% to-transparent pb-3 pt-5 md:bottom-0"
          style={{ bottom: "calc(3.5rem + max(env(safe-area-inset-bottom, 0px), var(--safe-bottom, 0px)))" }}
        >
          {composer}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex-1 space-y-8 pb-8">
        {conversationId && conv.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
          </div>
        ) : (
          messages.map((m) => <Message key={m.id} m={m} />)
        )}

        {busy && (
          <>
            {lastSent && !messages.some((m) => m.role === "USER" && m.content === lastSent) && (
              <UserNote content={lastSent} imagePreviews={lastSentImages} />
            )}
            <p className="text-[14px] text-ink-faint animate-pulse">IRIS is thinking…</p>
          </>
        )}

        {sendMsg.isError && (
          <p className="text-[13px] text-critical">
            Couldn't reach IRIS.{" "}
            {lastSent && (
              <button onClick={() => send(lastSent)} className="underline cursor-pointer">
                Try again
              </button>
            )}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <div
        className="sticky z-20 relative bg-gradient-to-t from-ops-ground from-75% to-transparent pb-3 pt-5 md:bottom-0"
        style={{ bottom: "calc(3.5rem + max(env(safe-area-inset-bottom, 0px), var(--safe-bottom, 0px)))" }}
      >
        {composer}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  onVoice,
  disabled,
  autoFocus = true,
  images,
  onAddImages,
  onRemoveImage,
  imageError,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onVoice: () => void;
  disabled: boolean;
  autoFocus?: boolean;
  images: AttachedImage[];
  onAddImages: (files: File[]) => void;
  onRemoveImage: (id: string) => void;
  imageError?: string | null;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const ready = (Boolean(value.trim()) || images.length > 0) && !disabled;

  const handlePaste = (e: React.ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith("image/"));
    if (files.length > 0) {
      e.preventDefault();
      onAddImages(files);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (files.length > 0) {
      onAddImages(files);
    }
  };

  return (
    <form
      onClick={() => ref.current?.focus()}
      onPaste={handlePaste}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) onSend();
      }}
      className="flex flex-col rounded-3xl border border-ops-line-bright bg-ops-void p-2.5 focus-within:border-ink-faint cursor-text relative z-10 transition-colors shadow-sm"
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/png,image/jpeg,image/webp,image/jpg"
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length > 0) onAddImages(files);
          e.target.value = "";
        }}
      />

      {images.length > 0 && (
        <div className="mb-2 ml-1 flex flex-wrap items-center gap-2 max-w-[95%]">
          {images.map((img) => (
            <div
              key={img.id}
              className="flex items-center gap-2 rounded-2xl border border-ops-line bg-ops-raised/60 px-2.5 py-1.5"
            >
              <img
                src={img.preview}
                alt={img.file.name}
                className="h-9 w-9 shrink-0 rounded-lg border border-ops-line object-cover"
              />
              <div className="min-w-0 pr-1">
                <p className="truncate text-[12px] text-ink font-medium max-w-[130px] sm:max-w-[180px]">
                  {img.file.name}
                </p>
                <p className="text-[10px] text-ink-faint">
                  {(img.file.size / 1024).toFixed(0)} KB
                </p>
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveImage(img.id);
                }}
                aria-label={`Remove ${img.file.name}`}
                title="Remove image"
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-ink-faint hover:bg-ops-raised hover:text-ink transition-colors cursor-pointer"
              >
                <X size={13} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
            title="Add more images"
            className="flex items-center gap-1.5 rounded-2xl border border-dashed border-ops-line hover:border-ops-line-bright px-3 py-1.5 text-[12px] text-ink-dim hover:text-ink transition-colors cursor-pointer"
          >
            <Plus size={14} />
            <span>Add more</span>
          </button>
        </div>
      )}

      {imageError && (
        <p className="mb-1.5 px-3 text-[12px] text-caution">{imageError}</p>
      )}

      <div className="flex items-end gap-1.5">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            fileInputRef.current?.click();
          }}
          disabled={disabled}
          aria-label="Upload images"
          title={images.length > 0 ? "Add more images (+)" : "Upload images (+)"}
          className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-dim transition-colors hover:bg-ops-raised hover:text-ink disabled:opacity-40 cursor-pointer"
        >
          <Plus size={18} strokeWidth={2.2} />
        </button>

        <textarea
          ref={ref}
          value={value}
          autoFocus={autoFocus}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (ready) onSend();
            }
          }}
          placeholder={images.length > 0 ? "Ask a question about these images (or press send)…" : "Ask IRIS anything"}
          rows={1}
          className="min-h-[28px] max-h-52 flex-1 resize-none bg-transparent py-1 px-1 text-[15px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
        />

        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onVoice();
          }}
          disabled={disabled}
          aria-label="Talk to IRIS"
          title="Talk to IRIS"
          className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-dim transition-colors hover:bg-ops-raised hover:text-ink disabled:opacity-40 cursor-pointer"
        >
          <Mic size={17} strokeWidth={2} />
        </button>

        <button
          type="submit"
          disabled={!ready}
          onClick={(e) => e.stopPropagation()}
          aria-label="Send"
          className={cn(
            "mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-opacity",
            ready ? "bg-ink text-ops-ground cursor-pointer hover:opacity-85" : "bg-ops-raised text-ink-faint",
          )}
        >
          <ArrowUp size={16} strokeWidth={2.5} />
        </button>
      </div>
    </form>
  );
}

const PHASE_LABEL: Record<VoicePhase, string> = {
  off: "",
  starting: "Starting",
  listening: "Listening",
  transcribing: "Got it",
  thinking: "Thinking",
  speaking: "Speaking",
};

const PHASE_HINT: Partial<Record<VoicePhase, string>> = {
  listening: "Tap the sphere when you're done",
  speaking: "Tap to interrupt",
};

/** Full-screen voice mode: the IRIS sphere, live captions and an end button. */
function VoiceOverlay({ voice }: { voice: ReturnType<typeof useVoiceConversation> }) {
  const sphereSize = () => Math.round(Math.min(window.innerWidth * 0.8, window.innerHeight * 0.45, 380));
  const [size, setSize] = useState(sphereSize);

  useEffect(() => {
    const onResize = () => setSize(sphereSize());
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && voice.end();
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const caption = voice.phase === "speaking" ? voice.said : voice.heard;
  // Portaled to <body>: the composer's sticky container would trap it under the app bars.
  return createPortal(
    <div
      role="dialog"
      aria-label="Voice conversation with IRIS"
      className="fixed inset-0 z-50 flex flex-col items-center bg-black px-6"
      style={{ paddingTop: "max(16px, env(safe-area-inset-top))", paddingBottom: "max(24px, env(safe-area-inset-bottom))" }}
    >
      <div className="flex w-full max-w-[720px] items-center justify-between">
        <span className="neon select-none text-[14px] font-semibold tracking-[0.35em] text-ink">IRIS</span>
        <button
          onClick={voice.end}
          aria-label="End voice conversation"
          title="End"
          className="rounded-full p-2 text-ink-faint hover:bg-ops-raised hover:text-ink cursor-pointer"
        >
          <X size={20} />
        </button>
      </div>

      <div className="flex w-full flex-1 flex-col items-center justify-center">
        <button
          onClick={voice.tap}
          aria-label={voice.phase === "speaking" ? "Interrupt IRIS" : "Done speaking"}
          className="rounded-full cursor-pointer"
        >
          <IrisSphere phase={voice.phase} level={voice.level} size={size} />
        </button>
        <p className="mt-6 text-[12px] uppercase tracking-[0.3em] text-ink-dim" role="status">
          {PHASE_LABEL[voice.phase]}
        </p>
        <p className="mt-1 h-4 text-[12px] text-ink-faint">{PHASE_HINT[voice.phase] ?? ""}</p>
        <p
          className={cn(
            "mt-5 min-h-[3.5em] max-w-[560px] text-center text-[17px] leading-relaxed line-clamp-4",
            voice.phase === "speaking" ? "text-ink" : "italic text-ink-dim",
          )}
        >
          {caption && (voice.phase === "speaking" ? caption : `“${caption}”`)}
        </p>
        {voice.notice && <p className="mt-3 max-w-[480px] text-center text-[13px] text-caution">{voice.notice}</p>}
      </div>

      <button
        onClick={voice.end}
        className="rounded-full border border-ops-line-bright px-6 py-2.5 text-[14px] text-ink hover:bg-ops-raised cursor-pointer"
      >
        End conversation
      </button>
    </div>,
    document.body,
  );
}

function UserNote({
  content,
  time,
  imagePreview,
  imagePreviews,
}: {
  content: string;
  time?: string;
  imagePreview?: string | null;
  imagePreviews?: string[];
}) {
  const previews =
    imagePreviews && imagePreviews.length > 0
      ? imagePreviews
      : imagePreview
      ? [imagePreview]
      : [];
  const hasVisionTag = content.includes("[📷 Visual Context Processed:");
  const displayContent = hasVisionTag
    ? content.split("[📷 Visual Context Processed:")[0].trim() ||
      (previews.length > 1 ? "Shared images" : "Shared an image")
    : content;
  const visionSummary = hasVisionTag
    ? content.split("[📷 Visual Context Processed:")[1]?.replace(/\]$/, "").trim()
    : null;

  return (
    <div className="flex flex-col items-end max-w-[85%] ml-auto">
      {time && <p className="mb-1 text-[12px] text-ink-faint tnum">{time}</p>}
      <div className="rounded-3xl bg-ops-raised px-4 py-2.5 text-[15px] leading-relaxed text-ink space-y-2">
        {previews.length > 0 && (
          <div
            className={cn(
              "grid gap-2",
              previews.length === 1 ? "grid-cols-1" : "grid-cols-2 max-w-sm"
            )}
          >
            {previews.map((src, i) => (
              <img
                key={i}
                src={src}
                alt="Uploaded preview"
                className="max-h-48 w-full rounded-2xl border border-ops-line object-cover"
              />
            ))}
          </div>
        )}
        {hasVisionTag && previews.length === 0 && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-ai font-medium">
            <span>📷 Visual context attached</span>
          </div>
        )}
        <p className="whitespace-pre-wrap">{displayContent}</p>
        {visionSummary && (
          <p className="text-[11px] text-ink-faint border-t border-ops-line/50 pt-1">
            Context: {visionSummary}
          </p>
        )}
      </div>
    </div>
  );
}

function Message({ m }: { m: ChatMessageOut }) {
  const startFocus = useStartFocus();

  if (m.role === "USER") return <UserNote content={m.content} time={fmtTime(m.created_at)} />;

  // Show what IRIS changed, not what it looked up.
  const actions = (m.actions_taken ?? []).filter(
    (a) => !/^(get|list|search)_/.test(a.tool_name) && (a.summary || !a.success),
  );
  const rec = m.recommended_action;

  return (
    <div>
      <p className="mb-1 text-[12px] text-ink-faint tnum">
        IRIS · {fmtTime(m.created_at)}
        {m.source === "DETERMINISTIC" && " · offline engine"}
      </p>
      <Markdown text={m.content} className="text-[15px] leading-relaxed text-ink" />

      {m.visual_context && (
        <details className="mt-3 border border-ops-line bg-ops-raised/30 px-3 py-2 rounded-xl text-[12px]">
          <summary className="cursor-pointer text-ink-faint font-medium select-none">
            Vision Context · {m.visual_context.detected_domain} · {m.visual_context.model}
          </summary>
          <div className="mt-2 space-y-1.5 text-ink-dim">
            <p>{m.visual_context.summary}</p>
            {m.visual_context.extracted_text_or_code && (
              <pre className="whitespace-pre-wrap font-mono text-[11px] text-ink-faint bg-ops-void p-2 rounded border border-ops-line/50">
                {m.visual_context.extracted_text_or_code}
              </pre>
            )}
            {m.visual_context.actionable_items && m.visual_context.actionable_items.length > 0 && (
              <p className="text-ai">
                Action items:{" "}
                {m.visual_context.actionable_items
                  .map((item) => item.title || item.kind)
                  .join(", ")}
              </p>
            )}
          </div>
        </details>
      )}

      {(actions.length > 0 || (m.memories_updated?.length ?? 0) > 0) && (
        <ul className="mt-3 space-y-0.5 text-[13px]">
          {actions.map((a, i) => (
            <li key={i} className={a.success ? "text-ink-faint" : "text-critical"}>
              {a.success ? "✓" : "✕"} {a.summary || a.tool_name}
              {!a.success && a.error ? ` (${a.error.slice(0, 80)})` : ""}
            </li>
          ))}
          {m.memories_updated?.map((mem) => (
            <li key={mem.id} className="text-ai">
              Remembered: {mem.content}
            </li>
          ))}
        </ul>
      )}

      {rec?.duration_minutes && (
        <button
          onClick={() =>
            startFocus.mutate({
              task_id: rec.task_id ?? undefined,
              planned_duration: rec.duration_minutes ?? 45,
            })
          }
          disabled={startFocus.isPending}
          className="mt-3 inline-flex items-center gap-1.5 text-[14px] text-ai hover:underline disabled:opacity-50 cursor-pointer"
        >
          <Play size={11} fill="currentColor" />
          Start {rec.duration_minutes}m focus{rec.title ? ` on ${rec.title}` : ""}
        </button>
      )}
    </div>
  );
}

// --- Shared task rows (used by Today and Area pages) -----------------------------------

export function RankedRows({ rows }: { rows: RankedTasksResponse[] }) {
  return (
    <ol>
      {rows.map((r) => (
        <li key={r.task.id}>
          <TaskRow task={r.task} score={r.score} />
        </li>
      ))}
    </ol>
  );
}

export function TaskRow({ task, score }: { task: TaskOut; score?: number }) {
  const complete = useCompleteTask();
  const urgency = task.deadline ? urgencyLabel(task.deadline) : null;

  return (
    <div className="group flex items-start gap-3 py-2">
      <button
        aria-label={`Mark "${task.title}" complete`}
        title="Mark done"
        onClick={() => complete.mutate({ id: task.id })}
        disabled={complete.isPending}
        className="mt-[3px] h-[18px] w-[18px] shrink-0 rounded-full border-[1.5px] border-ops-line-bright hover:border-go hover:bg-go-dim transition-colors cursor-pointer"
      />
      <div className="min-w-0 flex-1">
        <p className="text-[15px] leading-snug text-ink">{task.title}</p>
        <p className="flex flex-wrap items-center gap-x-2.5 text-[12px] text-ink-faint">
          <span>{task.area.charAt(0) + task.area.slice(1).toLowerCase()}</span>
          {urgency && (
            <span
              className={cn(
                "tnum",
                urgency.tone === "critical" && "text-critical",
                urgency.tone === "caution" && "text-caution",
              )}
            >
              {urgency.text}
            </span>
          )}
          {task.estimated_duration != null && <span className="tnum">{humanDuration(task.estimated_duration)}</span>}
        </p>
      </div>
      {score !== undefined && (
        <span className="tnum hidden pt-0.5 text-[12px] text-ink-faint sm:block" title="Priority score">
          {score.toFixed(0)}
        </span>
      )}
    </div>
  );
}
