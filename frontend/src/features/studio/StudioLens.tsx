import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowUp,
  Compass,
  History,
  Mic,
  Monitor,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Search,
  ShieldAlert,
  Sparkles,
  Square,
  Trash2,
  Users,
  X,
  Zap,
} from "lucide-react";
import {
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useSendMessage,
} from "@/hooks/queries";
import { useVoiceSession } from "@/features/home/VoiceSession";
import { Markdown } from "@/components/ui/Markdown";
import { Skeleton } from "@/components/ui/Overlay";
import { cn, fmtTime } from "@/lib/format";
import type { ChatMessageOut } from "@/types/api";
import { useLensStore } from "@/stores/lensStore";
import { captureCurrentScreen } from "@/lib/screenCapture";
import { api } from "@/api/client";
import { useQuery } from "@tanstack/react-query";

interface AttachedImage {
  id: string;
  file: File;
  preview: string;
}

const SUGGESTIONS = [
  "What are my highest priorities today?",
  "Review my upcoming schedule commitments.",
  "Check Windows companion and desktop status.",
  "What work are my coworkers currently handling?",
  "Search the knowledge vault for recent decisions.",
];

export function StudioLens() {
  const [params, setParams] = useSearchParams();
  const activeId = Number(params.get("c")) || null;
  const voice = useVoiceSession();

  const {
    studioInspectorOpen,
    toggleStudioInspector,
    historyDrawerOpen,
    setHistoryDrawerOpen,
    setActiveLens,
    setHorizonTab,
  } = useLensStore();

  useEffect(() => {
    if (voice.conversationId && !activeId) {
      setParams({ c: String(voice.conversationId) }, { replace: true });
    }
  }, [activeId, setParams, voice.conversationId]);

  return (
    <div className="relative flex h-[calc(100vh-3.5rem)] w-full overflow-hidden">
      {/* 1. Conversation Stream & Composer (Main Stage) */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Studio Top Context Header */}
        <div className="flex h-11 shrink-0 items-center justify-between border-b border-ops-line/80 px-4 text-xs">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setHistoryDrawerOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-ops-line bg-ops-panel px-2.5 py-1 text-ink-dim hover:text-ink hover:bg-ops-raised transition cursor-pointer"
              title="Recent Conversations"
            >
              <History size={13} />
              <span>History</span>
            </button>
            <button
              type="button"
              onClick={() => setParams({}, { replace: true })}
              className="flex items-center gap-1.5 rounded-lg border border-ops-line bg-ops-panel px-2.5 py-1 text-ink-dim hover:text-ink hover:bg-ops-raised transition cursor-pointer"
              title="New Conversation"
            >
              <Plus size={13} />
              <span>New Chat</span>
            </button>
            {activeId && (
              <span className="text-[11px] text-ink-faint font-mono hidden sm:inline">
                Thread #{activeId}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleStudioInspector}
              className={cn(
                "flex items-center gap-1.5 rounded-lg border px-2.5 py-1 transition cursor-pointer",
                studioInspectorOpen
                  ? "border-ai/40 bg-ai/10 text-ai font-medium"
                  : "border-ops-line bg-ops-panel text-ink-dim hover:text-ink hover:bg-ops-raised",
              )}
              title={studioInspectorOpen ? "Hide Context Inspector" : "Show Context Inspector"}
            >
              {studioInspectorOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
              <span className="hidden sm:inline">Context Deck</span>
            </button>
          </div>
        </div>

        {/* Conversation Thread */}
        <ConversationArea
          conversationId={activeId}
          onCreated={(id) => setParams({ c: String(id) }, { replace: true })}
        />
      </div>

      {/* 2. Context Inspector Panel (Right Drawer) */}
      {studioInspectorOpen && (
        <aside className="w-80 shrink-0 border-l border-ops-line bg-ops-panel/95 backdrop-blur-md overflow-y-auto hidden lg:flex flex-col p-4 space-y-4 animate-in slide-in-from-right-2 duration-150">
          <ContextInspector onNavigateLens={setActiveLens} onSelectHorizon={setHorizonTab} />
        </aside>
      )}

      {/* 3. Sliding History Drawer */}
      {historyDrawerOpen && (
        <ConversationHistoryDrawer
          activeId={activeId}
          onSelect={(id) => {
            setParams(id ? { c: String(id) } : {}, { replace: true });
            setHistoryDrawerOpen(false);
          }}
          onClose={() => setHistoryDrawerOpen(false)}
        />
      )}
    </div>
  );
}

// --- Conversation Area Component ----------------------------------------------------

function ConversationArea({
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
  const [images, setImages] = useState<AttachedImage[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [capturingScreen, setCapturingScreen] = useState(false);

  const endRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const voice = useVoiceSession();

  const messages = conv.data?.messages ?? [];
  const busy = sendMsg.isPending || createConv.isPending;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  const handleCaptureScreen = async () => {
    try {
      setCapturingScreen(true);
      const res = await captureCurrentScreen();
      if (res) {
        setImages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), file: res.file, preview: res.preview },
        ]);
      }
    } catch {
      setImageError("Screen capture was canceled or unavailable.");
    } finally {
      setCapturingScreen(false);
    }
  };

  const handleSend = async (overrideText?: string) => {
    const textToSend = (overrideText ?? input).trim();
    if (!textToSend && images.length === 0) return;

    let targetConvId = conversationId;
    if (!targetConvId) {
      try {
        const created = await createConv.mutateAsync("Conversation");
        targetConvId = created.id;
        onCreated(created.id);
      } catch {
        setSubmissionError("Could not create conversation. Please try again.");
        return;
      }
    }

    const imagePayloads: { image_base64: string; mime_type: string }[] = [];
    for (const img of images) {
      const buf = await img.file.arrayBuffer();
      const b64 = btoa(
        new Uint8Array(buf).reduce((data, byte) => data + String.fromCharCode(byte), ""),
      );
      imagePayloads.push({ image_base64: b64, mime_type: img.file.type });
    }

    setInput("");
    setImages([]);
    setImageError(null);
    setSubmissionError(null);

    try {
      await sendMsg.mutateAsync({
        conversationId: targetConvId,
        content: textToSend || (imagePayloads.length > 0 ? "Inspect image" : ""),
        images: imagePayloads,
      });
    } catch {
      setSubmissionError("Message could not be processed. Please retry.");
    }
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden relative">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 space-y-6">
        {messages.length === 0 && !busy ? (
          <div className="mx-auto max-w-xl py-12 text-center space-y-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-ai/10 border border-ai/25 text-ai shadow-sm">
              <Sparkles size={28} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-ink">What would you like to achieve?</h2>
              <p className="mt-1 text-xs text-ink-dim max-w-md mx-auto">
                IRIS is ready to coordinate your schedule, delegate tasks to specialized coworkers,
                query your knowledge vault, or control your Windows PC.
              </p>
            </div>

            {/* Quick Suggestion Chips */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 text-left">
              {SUGGESTIONS.map((sug, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleSend(sug)}
                  className="rounded-xl border border-ops-line bg-ops-panel/60 p-3 text-xs text-ink-dim hover:text-ink hover:border-ai/40 hover:bg-ops-raised transition cursor-pointer text-left"
                >
                  <span className="font-medium">{sug}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}

        {busy && (
          <div className="flex items-center gap-3 text-xs text-ink-faint animate-pulse">
            <div className="h-6 w-6 rounded-full bg-ai/10 border border-ai/30 flex items-center justify-center text-ai">
              <Sparkles size={12} />
            </div>
            <span>IRIS is thinking and formulating actions…</span>
          </div>
        )}

        {imageError && (
          <div className="rounded-xl border border-critical/30 bg-critical/10 p-3 text-xs text-critical">
            {imageError}
          </div>
        )}

        {submissionError && (
          <div className="rounded-xl border border-critical/30 bg-critical/10 p-3 text-xs text-critical">
            {submissionError}
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Floating Bottom Composer */}
      <div className="p-3 md:p-5 bg-gradient-to-t from-ops-ground via-ops-ground/90 to-transparent">
        <div className="mx-auto max-w-3xl rounded-2xl border border-ops-line-bright bg-ops-panel/95 backdrop-blur-md p-2.5 shadow-lg focus-within:border-ai/60 transition-colors">
          {/* Image Previews */}
          {images.length > 0 && (
            <div className="flex flex-wrap gap-2 pb-2">
              {images.map((img) => (
                <div key={img.id} className="relative group">
                  <img
                    src={img.preview}
                    alt="attachment"
                    className="h-14 w-14 rounded-lg object-cover border border-ops-line"
                  />
                  <button
                    type="button"
                    onClick={() => setImages((prev) => prev.filter((x) => x.id !== img.id))}
                    className="absolute -top-1.5 -right-1.5 rounded-full bg-critical text-white p-0.5 shadow-xs cursor-pointer"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                for (const f of files) {
                  setImages((prev) => [
                    ...prev,
                    { id: crypto.randomUUID(), file: f, preview: URL.createObjectURL(f) },
                  ]);
                }
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach image"
              title="Attach image"
              className="rounded-lg p-2 text-ink-faint hover:text-ink hover:bg-ops-raised transition cursor-pointer"
            >
              <Plus size={16} />
            </button>
            <button
              type="button"
              onClick={handleCaptureScreen}
              disabled={capturingScreen}
              aria-label="Capture screen"
              title="Capture screen preview"
              className={cn(
                "rounded-lg p-2 text-ink-faint hover:text-ink hover:bg-ops-raised transition cursor-pointer",
                capturingScreen && "animate-pulse text-ai",
              )}
            >
              <Monitor size={16} />
            </button>

            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask IRIS anything or give an instruction…"
              rows={1}
              className="min-h-[36px] max-h-36 flex-1 resize-none bg-transparent py-2 px-1 text-sm text-ink outline-none placeholder:text-ink-faint leading-relaxed"
            />

            <button
              type="button"
              onClick={() => voice.start()}
              aria-label="Voice conversation"
              title="Start voice session"
              className="rounded-lg p-2 text-ink-faint hover:text-ink hover:bg-ops-raised transition cursor-pointer"
            >
              <Mic size={16} />
            </button>

            <button
              type="button"
              onClick={() => handleSend()}
              disabled={!input.trim() && images.length === 0}
              aria-label="Send message"
              className={cn(
                "rounded-lg p-2 transition cursor-pointer",
                input.trim() || images.length > 0
                  ? "bg-ai text-white shadow-xs hover:bg-ai/90"
                  : "text-ink-faint/40 bg-ops-raised cursor-not-allowed",
              )}
            >
              <ArrowUp size={16} strokeWidth={2.2} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Message Bubble Component -------------------------------------------------------

function MessageBubble({ message }: { message: ChatMessageOut }) {
  const isUser = message.role === "USER";

  return (
    <div className={cn("flex flex-col", isUser ? "items-end" : "items-start")}>
      <div className="flex items-center gap-1.5 mb-1 px-1">
        <span className="text-[11px] font-semibold text-ink-faint uppercase tracking-wider">
          {isUser ? "You" : "IRIS"}
        </span>
        {message.created_at && (
          <span className="text-[10px] text-ink-faint/60">
            {fmtTime(message.created_at)}
          </span>
        )}
      </div>

      <div
        className={cn(
          "max-w-[88%] md:max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-ops-raised text-ink border border-ops-line"
            : "bg-ops-panel text-ink border border-ops-line-bright shadow-xs",
        )}
      >
        <Markdown text={message.content} />

        {/* Display actions taken if any */}
        {message.actions_taken && message.actions_taken.length > 0 && (
          <div className="mt-3 pt-2.5 border-t border-ops-line/60 space-y-1.5">
            <span className="text-[10px] uppercase tracking-wider font-semibold text-ai">
              Actions Executed
            </span>
            <div className="flex flex-wrap gap-1.5">
              {message.actions_taken.map((act, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 rounded-md bg-ops-ground px-2 py-0.5 text-[11px] font-mono text-ink-dim border border-ops-line"
                >
                  <Zap size={11} className="text-amber-500" />
                  <span>{act.tool_name || act.summary || "Tool execution"}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// --- Context Inspector Panel --------------------------------------------------------

function ContextInspector({
  onNavigateLens,
  onSelectHorizon,
}: {
  onNavigateLens: (lens: "studio" | "horizon" | "fleet" | "vault") => void;
  onSelectHorizon: (tab: "overview" | "priorities" | "schedule" | "routines") => void;
}) {
  const computer = useQuery({
    queryKey: ["computer-status"],
    queryFn: () => api.get<any>("/computer/status"),
    staleTime: 5_000,
  });

  const approvals = useQuery({
    queryKey: ["coworker-approvals", "pending"],
    queryFn: () => api.get<any[]>("/coworkers/approvals?status=pending"),
    staleTime: 10_000,
  });

  const coworkerTasks = useQuery({
    queryKey: ["coworker-active-tasks"],
    queryFn: () => api.get<any[]>("/coworkers"),
    staleTime: 15_000,
  });

  const allActiveTasks = (coworkerTasks.data ?? []).flatMap((c: any) =>
    (c.tasks ?? [])
      .filter((t: any) => ["running", "queued", "working"].includes(t.status))
      .map((t: any) => ({ ...t, coworkerName: c.name })),
  );

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-ink-faint">
          Context Deck
        </h3>
        <p className="text-[11px] text-ink-dim mt-0.5">
          Ambient state, companion telemetry, and running operations.
        </p>
      </div>

      {/* 1. Computer Control Sentinel Card */}
      <div className="rounded-xl border border-ops-line bg-ops-void p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Monitor size={14} className="text-ai" />
            <span className="text-xs font-semibold text-ink">Computer Control</span>
          </div>
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              computer.data?.companion_online ? "bg-emerald-500" : "bg-gray-400",
            )}
          />
        </div>
        <div className="text-[11px] text-ink-dim space-y-1">
          <p>
            Status:{" "}
            <strong className="text-ink">
              {computer.data?.session?.state === "active"
                ? "Active Session"
                : computer.data?.companion_online
                ? "Companion Ready"
                : "Companion Offline"}
            </strong>
          </p>
          <p className="text-ink-faint">
            Target OS: {computer.data?.is_windows ? "Windows 11 Laptop" : "Local Environment"}
          </p>
        </div>
        {computer.data?.session?.state === "active" && (
          <div className="rounded-lg bg-critical/10 border border-critical/20 p-2 text-[11px] text-critical flex items-center justify-between">
            <span>Operating Desktop</span>
            <Square size={12} className="fill-current animate-pulse" />
          </div>
        )}
      </div>

      {/* 2. Pending Approvals Card (if any) */}
      {(approvals.data ?? []).length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-amber-500">
            <ShieldAlert size={14} />
            <span className="text-xs font-bold">
              Approvals Pending ({(approvals.data ?? []).length})
            </span>
          </div>
          <p className="text-[11px] text-ink">
            A coworker has requested privileged action execution.
          </p>
          <button
            type="button"
            onClick={() => onNavigateLens("fleet")}
            className="w-full rounded-lg bg-amber-500 text-white py-1.5 text-xs font-semibold hover:bg-amber-600 transition cursor-pointer"
          >
            Review in Fleet
          </button>
        </div>
      )}

      {/* 3. Live Coworker Fleet Activity */}
      <div className="rounded-xl border border-ops-line bg-ops-void p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Users size={14} className="text-ai" />
            <span className="text-xs font-semibold text-ink">Coworker Fleet</span>
          </div>
          <button
            type="button"
            onClick={() => onNavigateLens("fleet")}
            className="text-[11px] text-ai hover:underline cursor-pointer"
          >
            Open Fleet →
          </button>
        </div>

        {allActiveTasks.length === 0 ? (
          <p className="text-[11px] text-ink-faint">No sub-agent tasks currently executing.</p>
        ) : (
          <div className="space-y-1.5 pt-1">
            {allActiveTasks.map((t: any) => (
              <div key={t.id} className="rounded-lg bg-ops-raised p-2 text-xs space-y-0.5">
                <p className="font-semibold text-ink text-[11px]">{t.coworkerName}</p>
                <p className="text-ink-dim text-[11px] truncate">{t.instruction}</p>
                <span className="inline-block rounded-full bg-ai/10 px-1.5 py-0.2 text-[9px] font-semibold text-ai">
                  {t.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Quick Horizon Shortcuts */}
      <div className="rounded-xl border border-ops-line bg-ops-void p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Compass size={14} className="text-ai" />
            <span className="text-xs font-semibold text-ink">Life & Priorities</span>
          </div>
          <button
            type="button"
            onClick={() => onNavigateLens("horizon")}
            className="text-[11px] text-ai hover:underline cursor-pointer"
          >
            View →
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1.5 pt-1 text-xs">
          <button
            type="button"
            onClick={() => {
              onNavigateLens("horizon");
              onSelectHorizon("priorities");
            }}
            className="rounded-lg bg-ops-raised p-2 text-left hover:bg-ops-raised/70 transition cursor-pointer"
          >
            <span className="text-[11px] text-ink font-medium">Priorities</span>
          </button>
          <button
            type="button"
            onClick={() => {
              onNavigateLens("horizon");
              onSelectHorizon("schedule");
            }}
            className="rounded-lg bg-ops-raised p-2 text-left hover:bg-ops-raised/70 transition cursor-pointer"
          >
            <span className="text-[11px] text-ink font-medium">Schedule</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// --- History Drawer Component -------------------------------------------------------

function ConversationHistoryDrawer({
  activeId,
  onSelect,
  onClose,
}: {
  activeId: number | null;
  onSelect: (id: number | null) => void;
  onClose: () => void;
}) {
  const convs = useConversations();
  const deleteConv = useDeleteConversation();
  const [search, setSearch] = useState("");

  const list = (convs.data ?? []).filter((c) =>
    (c.title || `Conversation ${c.id}`).toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <>
      <button
        aria-label="Close history drawer backdrop"
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-2xs cursor-default"
        onClick={onClose}
      />
      <div className="fixed inset-y-0 left-0 z-50 w-80 border-r border-ops-line-bright bg-ops-panel p-4 shadow-2xl flex flex-col space-y-3 animate-in slide-in-from-left duration-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={16} className="text-ai" />
            <h2 className="text-sm font-bold text-ink">Conversations</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close drawer"
            className="rounded-lg p-1 text-ink-faint hover:bg-ops-raised cursor-pointer"
          >
            <X size={15} />
          </button>
        </div>

        {/* Search */}
        <div className="flex items-center gap-2 rounded-xl border border-ops-line bg-ops-void px-2.5 py-1.5 text-xs">
          <Search size={13} className="text-ink-faint" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations…"
            className="w-full bg-transparent text-xs text-ink outline-none placeholder:text-ink-faint"
          />
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {convs.isLoading ? (
            <div className="space-y-2 pt-2">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-10 w-full rounded-xl" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <p className="py-8 text-center text-xs text-ink-faint">No conversations found.</p>
          ) : (
            list.map((c) => (
              <div
                key={c.id}
                className={cn(
                  "group flex items-center justify-between rounded-xl p-2.5 text-xs transition cursor-pointer",
                  c.id === activeId
                    ? "bg-ops-raised text-ink font-semibold border border-ops-line"
                    : "text-ink-dim hover:bg-ops-raised/60 hover:text-ink",
                )}
                onClick={() => onSelect(c.id)}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate">{c.title || `Conversation #${c.id}`}</p>
                  <p className="text-[10px] text-ink-faint">{fmtTime(c.created_at)}</p>
                </div>
                <button
                  type="button"
                  aria-label="Delete conversation"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("Delete this conversation?")) {
                      deleteConv.mutate(c.id);
                      if (c.id === activeId) onSelect(null);
                    }
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 text-ink-faint hover:text-critical transition cursor-pointer"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
