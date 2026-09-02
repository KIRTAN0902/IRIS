import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  Briefcase,
  CheckCircle2,
  Clock,
  Moon,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  useAvailability,
  useCompleteTask,
  useConversation,
  useConversations,
  useCreateConversation,
  useRecommendation,
  useSendMessage,
  useStartFocus,
  useTodayState,
} from "@/hooks/queries";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Overlay";
import { Lamp } from "@/components/ui/Panel";
import { cn, fmtTime, humanDuration, urgencyLabel } from "@/lib/format";
import type { RankedTasksResponse } from "@/api/endpoints";
import type { TaskOut } from "@/types/api";
import { IrisMark } from "@/components/layout/Sidebar";

/**
 * HOME — Chat-First Reliable Intelligence Assistant Workspace.
 *
 * Visual Hierarchy:
 * 1. CURRENT TASK (Minimal typographic situation context header at top)
 * 2. IRIS CONVERSATION (Open, focused, highly legible conversational workspace)
 * 3. ANCHORED CHAT COMPOSER (Floating glassmorphic pill at bottom)
 */
export function HomePage() {
  return (
    <div className="mx-auto flex max-w-[760px] flex-1 flex-col py-2 px-2 sm:px-0">
      {/* 1. Current Task Context Header */}
      <CurrentTaskHeader />

      {/* 2. Chat-First Conversational Workspace */}
      <ChatAssistantWorkspace />
    </div>
  );
}

// --- 1. Current Task Context Header (Minimal & Typographic) ------------------

function CurrentTaskHeader() {
  const todayState = useTodayState();
  const recommendation = useRecommendation();
  const availability = useAvailability({ hours_ahead: 12 });
  const startFocus = useStartFocus();

  const curWin = todayState.data?.current_window;
  const isInHard = curWin?.is_in_hard_constraint ?? false;
  const activeName = curWin?.active_block_name;
  const activeType = curWin?.active_block_type;
  const minRem = curWin?.minutes_remaining_in_block;
  const rec = recommendation.data;
  const freeMins =
    availability.data?.total_free_minutes ?? todayState.data?.available_minutes_today ?? 0;

  // Local hour to detect late night sleep context
  const nowHour = new Date().getHours();
  const isLateNight = nowHour >= 23 || nowHour < 6;

  // Determine current situation
  let categoryLabel = "CURRENT SITUATION";
  let title = "Flexible Work Window";
  let subtitle = `${freeMins > 0 ? humanDuration(freeMins) + " available today" : "No urgent obligations"} · IRIS is ready to direct your focus.`;
  let tone: "go" | "caution" | "dim" | "ai" = "dim";
  let actionBtn: React.ReactNode = null;
  let icon = <Clock size={13} className="text-ink-faint" />;

  if (isInHard && (activeName?.toLowerCase() === "sleep" || isLateNight)) {
    categoryLabel = "REST & RECOVERY";
    title = "Sleep Window";
    subtitle = "23:00 — 06:00 · Rest and cognitive recovery for tomorrow.";
    tone = "dim";
    icon = <Moon size={13} className="text-ink-faint" />;
  } else if (isInHard && activeName) {
    categoryLabel = `SCHEDULED ${activeType ? activeType.toUpperCase() : "COMMITMENT"}`;
    title = activeName;
    subtitle = minRem
      ? `${humanDuration(minRem)} remaining · Fixed scheduled commitment`
      : "Fixed scheduled commitment";
    tone = "caution";
    icon = <Briefcase size={13} className="text-caution" />;
  } else if (activeType === "FOCUS" && activeName) {
    categoryLabel = "CURRENT FOCUS";
    title = activeName;
    subtitle = minRem ? `${humanDuration(minRem)} remaining · Scheduled session` : "Scheduled focus session";
    tone = "go";
    icon = <Clock size={13} className="text-go" />;
  } else if (rec && rec.recommendation_type === "TASK" && rec.title) {
    categoryLabel = "TOP RECOMMENDATION";
    title = rec.title;
    subtitle = `${rec.duration_minutes ? humanDuration(rec.duration_minutes) : "45m"} · ${rec.reason || "Recommended next focus"}`;
    tone = "go";
    icon = <Sparkles size={13} className="text-go" />;
    actionBtn = (
      <Button
        size="sm"
        variant="go"
        disabled={startFocus.isPending}
        onClick={() => startFocus.mutate({ task_id: rec.task_id ?? undefined })}
        className="h-6 max-w-full gap-1.5 rounded-full px-3 text-[11px] font-medium tracking-wide shadow-xs whitespace-normal"
      >
        <Play size={10} fill="currentColor" className="shrink-0" />
        <span className="truncate">Start {rec.duration_minutes ? humanDuration(rec.duration_minutes) : "Focus"}</span>
      </Button>
    );
  }

  return (
    <header className="mb-6 flex flex-col items-center text-center animate-in fade-in duration-200">
      {/* Tracking label */}
      <div className="mb-1.5 flex items-center justify-center gap-1.5">
        <Lamp tone={tone} pulse={tone === "go"} />
        <span className="font-[family-name:var(--font-display)] text-[10px] font-bold uppercase tracking-[0.22em] text-ink-faint">
          {categoryLabel}
        </span>
      </div>

      {/* Main Task Title */}
      <h2 className="text-[18px] sm:text-[20px] font-semibold tracking-tight text-ink">
        {todayState.isLoading ? <Skeleton className="mx-auto h-5 w-48" /> : title}
      </h2>

      {/* Subtitle / Details + Optional Quick Action */}
      <div className="mt-1.5 flex flex-wrap items-center justify-center gap-2">
        <span className="flex items-center gap-1.5 text-[12px] text-ink-dim">
          {icon}
          <span>{subtitle}</span>
        </span>
        {actionBtn}
      </div>
    </header>
  );
}

// --- 2. Chat-First Conversational Workspace -----------------------------------

function ChatAssistantWorkspace() {
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [inputVal, setInputVal] = useState("");
  const [lastSentText, setLastSentText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const startFocus = useStartFocus();

  const convs = useConversations(15);
  const createConv = useCreateConversation();
  const activeConv = useConversation(activeConvId);
  const sendMsg = useSendMessage();

  // Initialize active conversation
  useEffect(() => {
    if (activeConvId === null && convs.data && convs.data.length > 0) {
      setActiveConvId(convs.data[0].id);
    }
  }, [convs.data, activeConvId]);

  // Auto-scroll on new messages or loading
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConv.data?.messages, sendMsg.isPending]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [inputVal]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || inputVal).trim();
    if (!text || sendMsg.isPending) return;

    let targetConvId = activeConvId;
    if (!targetConvId) {
      try {
        const created = await createConv.mutateAsync(text.slice(0, 60));
        targetConvId = created.id;
        setActiveConvId(created.id);
      } catch {
        return;
      }
    }

    setLastSentText(text);
    setInputVal("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    sendMsg.mutate({ conversationId: targetConvId, content: text });
  };

  const handleNewConversation = async () => {
    try {
      const created = await createConv.mutateAsync("New thread");
      setActiveConvId(created.id);
      setInputVal("");
    } catch {
      // Fallback
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const defaultSuggestions = [
    "What should I do right now?",
    "What's currently falling behind?",
    "Plan my deep work session for today.",
  ];

  const messages = activeConv.data?.messages ?? [];

  return (
    <div className="flex flex-1 flex-col">
      {/* Top Thread Controls */}
      <div className="mb-3 flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          {convs.data && convs.data.length > 1 && (
            <select
              value={activeConvId ?? ""}
              onChange={(e) => setActiveConvId(Number(e.target.value))}
              aria-label="Select conversation thread"
              className="max-w-[180px] sm:max-w-[260px] truncate border border-ops-line-bright/60 bg-ops-panel/90 px-2.5 py-1 text-[11px] text-ink-dim rounded-lg focus:border-ai focus:outline-none"
            >
              {convs.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || `Thread #${c.id}`}
                </option>
              ))}
            </select>
          )}
        </div>

        <button
          onClick={handleNewConversation}
          className="flex items-center gap-1.5 rounded-lg border border-ops-line-bright/60 bg-ops-panel/80 px-2.5 py-1 text-[11px] font-semibold text-ink-dim hover:text-ink hover:border-ai/50 hover:bg-ops-raised transition-all cursor-pointer"
        >
          <Plus size={12} className="text-ai" />
          <span>New chat</span>
        </button>
      </div>

      {/* Main Conversation Stream */}
      <div className="flex flex-1 flex-col space-y-6 pb-28 pt-2">
        {activeConv.isLoading && !messages.length ? (
          <div className="space-y-4 py-8">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-12 w-3/4" />
          </div>
        ) : messages.length === 0 ? (
          /* Empty State — Monastic Graphite Style */
          <div className="my-auto flex flex-col items-center justify-center py-12 text-center animate-in fade-in duration-200">
            {/* Crisp Solid Aperture Mark */}
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-ops-line-bright bg-ops-panel shadow-sm">
              <IrisMark size={24} />
            </div>

            <h1 className="font-[family-name:var(--font-display)] text-[22px] sm:text-[24px] font-bold tracking-tight text-ink">
              IRIS
            </h1>
            <p className="mt-1 text-[15px] font-medium text-ink-dim">
              What can I help you accomplish?
            </p>
            <p className="mt-1 max-w-sm text-[13px] text-ink-faint">
              Ask about your schedule, tasks, priorities, or what deserves your focus right now.
            </p>

            {/* 3 Subtle Suggestion Pills */}
            <div className="mt-8 flex flex-wrap justify-center gap-2 max-w-lg">
              {defaultSuggestions.map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(suggestion)}
                  disabled={sendMsg.isPending}
                  className="rounded-full border border-ops-line-bright bg-ops-panel px-4 py-1.5 text-[12px] font-medium text-ink-dim transition-all hover:border-ink-dim hover:text-ink hover:bg-ops-raised disabled:opacity-50 cursor-pointer"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Active Message Stream */
          messages.map((m) => {
            const isUser = m.role === "USER";
            return (
              <div
                key={m.id}
                className={cn(
                  "flex flex-col gap-1.5 animate-in fade-in duration-150",
                  isUser ? "items-end" : "items-start",
                )}
              >
                {/* Author Subtitle */}
                <div className="flex items-center gap-2 px-1 text-[11px] text-ink-faint">
                  <span className={isUser ? "font-semibold text-ink-dim" : "font-bold text-ink"}>
                    {isUser ? "You" : "IRIS"}
                  </span>
                  <span className="font-[family-name:var(--font-telemetry)] text-[10px] tnum">
                    {fmtTime(m.created_at)}
                  </span>
                </div>

                {/* Message Body */}
                <div
                  className={cn(
                    "text-[14px] leading-relaxed whitespace-pre-wrap",
                    isUser
                      ? "max-w-[88%] sm:max-w-[80%] rounded-2xl border border-ops-line-bright bg-ops-raised px-4 py-2.5 text-ink shadow-xs"
                      : "w-full text-ink pl-1 sm:pl-2",
                  )}
                >
                  {m.content}
                </div>

                {/* Subtle Tool Actions Feedback (Inline & Unobtrusive) */}
                {m.actions_taken && m.actions_taken.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1.5 pl-1 sm:pl-2">
                    {m.actions_taken.map((act, i) => (
                      <div
                        key={i}
                        className="inline-flex items-center gap-1.5 rounded-full border border-ops-line-bright bg-ops-panel px-3 py-1 text-[11px] text-ink-dim"
                      >
                        <CheckCircle2
                          size={12}
                          className={act.success ? "text-go shrink-0" : "text-critical shrink-0"}
                        />
                        <span>{act.summary || act.tool_name}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Inline Recommendation Action CTA */}
                {m.recommended_action && m.recommended_action.duration_minutes && (
                  <div className="mt-2 max-w-full pl-1 sm:pl-2">
                    <Button
                      size="sm"
                      variant="go"
                      onClick={() =>
                        startFocus.mutate({
                          task_id: m.recommended_action?.task_id ?? undefined,
                          planned_duration: m.recommended_action?.duration_minutes ?? 45,
                        })
                      }
                      disabled={startFocus.isPending}
                      className="h-auto max-w-full flex-wrap rounded-full gap-1.5 px-3 py-1.5 text-[12px] shadow-sm whitespace-normal text-left"
                    >
                      <Play size={11} fill="currentColor" className="shrink-0" />
                      <span className="truncate max-w-[240px] sm:max-w-none">
                        Start {m.recommended_action.duration_minutes}m Focus ·{" "}
                        {m.recommended_action.title || "Next task"}
                      </span>
                    </Button>
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* Thinking status */}
        {sendMsg.isPending && (
          <div className="flex items-center gap-2.5 py-2 pl-2 text-[13px] text-ink-dim animate-pulse">
            <RefreshCw size={13} className="animate-spin text-ink-dim" />
            <span>IRIS is reasoning and evaluating context...</span>
          </div>
        )}

        {/* Error / Retry Bar */}
        {sendMsg.isError && (
          <div className="my-2 flex items-center justify-between gap-2 rounded-lg border border-critical/40 bg-critical/10 p-3 text-[12px] text-critical">
            <span>Failed to send message to IRIS.</span>
            {lastSentText && (
              <Button size="sm" variant="outline" onClick={() => handleSend(lastSentText)}>
                Retry
              </Button>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 3. Anchored Chat Composer (Clean Solid Matte Pill) */}
      <div className="fixed inset-x-0 bottom-12 md:bottom-4 z-30 px-3 sm:px-6 pointer-events-none">
        <div className="mx-auto max-w-[760px] pointer-events-auto">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-end gap-2 rounded-2xl border border-ops-line-bright bg-ops-panel p-2 shadow-xl transition-all focus-within:border-ink-dim focus-within:ring-2 focus-within:ring-ink-dim/20"
          >
            <textarea
              ref={textareaRef}
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask IRIS anything or update your state..."
              rows={1}
              disabled={sendMsg.isPending}
              className="max-h-36 min-h-[40px] flex-1 resize-none bg-transparent px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint focus:outline-none leading-relaxed"
            />
            <button
              type="submit"
              disabled={!inputVal.trim() || sendMsg.isPending}
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-all",
                inputVal.trim() && !sendMsg.isPending
                  ? "bg-ink text-ops-ground hover:bg-white cursor-pointer"
                  : "bg-ops-raised text-ink-faint cursor-not-allowed opacity-50",
              )}
              aria-label="Send message"
            >
              {sendMsg.isPending ? (
                <RefreshCw size={14} className="animate-spin" />
              ) : (
                <ArrowUp size={16} strokeWidth={2.5} />
              )}
            </button>
          </form>
          <p className="mt-1 text-center text-[10px] text-ink-faint tracking-wide">
            Enter to send · Shift+Enter for newline · Grounded in your authoritative IRIS decision engine
          </p>
        </div>
      </div>
    </div>
  );
}

// --- Preserved Helpers (Exported for TodayPage & AreaLensPage) ----------------


export function RankedRows({ rows }: { rows: RankedTasksResponse[] }) {
  return (
    <ol className="divide-y divide-ops-line">
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
    <div className="group flex items-center gap-3 py-2.5">
      <button
        aria-label={`Mark "${task.title}" complete`}
        title="Complete"
        onClick={() => complete.mutate({ id: task.id })}
        disabled={complete.isPending}
        className="h-3.5 w-3.5 shrink-0 border border-ops-line-bright hover:border-go focus-visible:border-go"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-ink">{task.title}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-ink-faint">
          <span className="tracking-[0.08em] uppercase">{task.area}</span>
          {urgency && (
            <span
              className={
                urgency.tone === "critical"
                  ? "text-critical tnum"
                  : urgency.tone === "caution"
                    ? "text-caution tnum"
                    : ""
              }
            >
              {urgency.text}
            </span>
          )}
          {task.estimated_duration != null && (
            <span className="tnum">{humanDuration(task.estimated_duration)}</span>
          )}
        </p>
      </div>
      {score !== undefined && (
        <span className="tnum hidden text-[12px] text-ink-faint sm:block" title="Priority score">
          {score.toFixed(0)}
        </span>
      )}
    </div>
  );
}
