import { useState, useRef, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUp,
  Bot,
  Brain,
  Calendar,
  CheckCircle2,
  Clock,
  Flame,
  ListTodo,
  Monitor,
  Play,
  Repeat,
  ShieldAlert,
  Sparkles,
  StopCircle,
  UploadCloud,
  X,
  Zap,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import {
  useCheckHabit,
  useCompleteFocus,
  useCompleteTask,
  useCreateConversation,
  useHabits,
  useMe,
  useSendMessage,
  useSituation,
  useStartFocus,
} from "@/hooks/queries";
import { useFocusStore } from "@/stores";
import { useLensStore } from "@/stores/lensStore";
import { useVoiceSession } from "@/features/home/VoiceSession";
import { captureCurrentScreen } from "@/lib/screenCapture";
import { cn } from "@/lib/format";

interface AttachedImage {
  id: string;
  file: File;
  preview: string;
}

export function ProductivityHomePage() {
  const { setActiveLens, setHorizonTab, setVaultTab } = useLensStore();
  const situation = useSituation();
  const habits = useHabits();
  const me = useMe();
  const checkHabit = useCheckHabit();
  const completeTask = useCompleteTask();
  const runningFocus = useFocusStore((s) => s.running);
  const startFocus = useStartFocus();
  const completeFocus = useCompleteFocus();
  const createConversation = useCreateConversation();
  const sendMessage = useSendMessage();
  const voice = useVoiceSession();

  // Desktop companion & autonomy state
  const computer = useQuery({
    queryKey: ["computer-status"],
    queryFn: () => api.get<any>("/computer/status"),
    refetchInterval: 15_000,
  });

  // Pending coworker approvals
  const approvalsQuery = useQuery({
    queryKey: ["coworkers-approvals-home"],
    queryFn: () => api.get<any[]>("/coworkers/approvals"),
    refetchInterval: 15_000,
  });

  // Coworkers swarm state
  const coworkersQuery = useQuery({
    queryKey: ["coworkers-list-home"],
    queryFn: () => api.get<any[]>("/coworkers"),
    refetchInterval: 30_000,
  });

  // Chat composer state
  const [prompt, setPrompt] = useState("");
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [capturingScreen, setCapturingScreen] = useState(false);
  const [sending, setSending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const s = situation.data;
  const nowBlock = s?.now?.current_block;
  const nextCommitment = s?.now?.next_commitment;
  const minutesLeft = s?.now?.minutes_left_in_block;
  const localTime = s?.now?.local_time;

  const urgentTasks = [
    ...(s?.tasks?.overdue ?? []),
    ...(s?.tasks?.in_progress ?? []),
    ...(s?.tasks?.due_today ?? []),
  ].slice(0, 5);

  const habitsToday = (habits.data ?? []).filter((h) => h.active && h.scheduled_today);
  const habitsDone = habitsToday.filter((h) => h.done_today).length;
  const habitsTotal = habitsToday.length;
  const routinePct = habitsTotal > 0 ? Math.round((habitsDone / habitsTotal) * 100) : 100;

  const pendingApprovals = approvalsQuery.data ?? [];
  const coworkerList = coworkersQuery.data ?? [];
  const activeCoworkersCount = coworkerList.filter((c) => c.availability !== false).length;

  const greeting = () => {
    const h = new Date().getHours();
    const name = me.data?.name?.split(" ")[0] || "Kirtan";
    if (h >= 4 && h < 12) return `Good morning, ${name}`;
    if (h >= 12 && h < 17) return `Good afternoon, ${name}`;
    return `Good evening, ${name}`;
  };

  const currentDateFormatted = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date());

  // Handle composer submission
  const handleComposerSubmit = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed && attachedImages.length === 0) return;

    setSending(true);
    try {
      // 1. Create a fresh conversation
      const title = trimmed ? trimmed.slice(0, 48) : "Visual Inquiry";
      const conv = await createConversation.mutateAsync(title);

      // 2. Prepare images if any
      const imagesPayload = await Promise.all(
        attachedImages.map(async (img) => {
          return new Promise<{ image_base64: string; mime_type: string }>((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => {
              const res = (reader.result as string) || "";
              const base64 = res.includes(",") ? res.split(",")[1] : res;
              resolve({ image_base64: base64, mime_type: img.file.type });
            };
            reader.readAsDataURL(img.file);
          });
        }),
      );

      // 3. Send message
      await sendMessage.mutateAsync({
        conversationId: conv.id,
        content: trimmed || "Please inspect this attached screen/image.",
        images: imagesPayload.length > 0 ? imagesPayload : undefined,
      });

      // 4. Smoothly switch to Studio lens to view the live conversation
      setActiveLens("studio");
      window.history.pushState({}, "", `/?lens=studio&c=${conv.id}`);
    } catch (err) {
      console.error("Failed to send message from home composer:", err);
    } finally {
      setSending(false);
      setPrompt("");
      setAttachedImages([]);
    }
  };

  const handleCaptureScreen = async () => {
    try {
      setCapturingScreen(true);
      const b64 = await captureCurrentScreen();
      if (!b64) return;
      const res = await fetch(`data:image/png;base64,${b64}`);
      const blob = await res.blob();
      const file = new File([blob], `screen-${Date.now()}.png`, { type: "image/png" });
      setAttachedImages((prev) => [
        ...prev,
        { id: `screen-${Date.now()}`, file, preview: `data:image/png;base64,${b64}` },
      ]);
    } catch (err) {
      console.error("Screen capture error:", err);
    } finally {
      setCapturingScreen(false);
    }
  };

  const handleQuickPrompt = (text: string) => {
    if (text.includes("Start 25m focus")) {
      startFocus.mutate({ planned_duration: 25, notes: "Sprint started from Home command bar" });
      return;
    }
    setPrompt(text);
  };

  return (
    <div className="relative min-h-[calc(100vh-3.5rem)] w-full overflow-y-auto bg-ops-ground">
      {/* 1. Main Structured Productivity Canvas */}
      <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 space-y-6 pb-64">
        {/* Header: Date, Greeting & System Presence */}
        <header className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-ops-line/80 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-ai/10 px-2.5 py-0.5 text-[11px] font-semibold text-ai border border-ai/20">
                <span className="h-1.5 w-1.5 rounded-full bg-ai animate-pulse" />
                IRIS Sovereign OS
              </span>
              <span className="text-xs text-ink-faint">·</span>
              <span className="text-xs text-ink-dim font-medium">{currentDateFormatted}</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-ink mt-1.5 font-display">
              {greeting()}
            </h1>
          </div>

          {/* Real-time Ambient Telemetry Badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {localTime && (
              <div className="flex items-center gap-1.5 rounded-xl border border-ops-line bg-ops-panel px-3 py-1.5 text-ink-dim shadow-2xs">
                <Clock size={13} className="text-ai" />
                <span className="font-mono font-medium text-ink">{localTime}</span>
              </div>
            )}
            <div className="flex items-center gap-1.5 rounded-xl border border-ops-line bg-ops-panel px-3 py-1.5 text-ink-dim shadow-2xs">
              <Monitor
                size={13}
                className={computer.data?.companion_online ? "text-emerald-500" : "text-amber-500"}
              />
              <span>{computer.data?.companion_online ? "Windows Companion Online" : "Companion Idle"}</span>
            </div>
            <div className="flex items-center gap-1.5 rounded-xl border border-ops-line bg-ops-panel px-3 py-1.5 text-ink-dim shadow-2xs">
              <Bot size={13} className="text-ai" />
              <span>{activeCoworkersCount} Specialists Ready</span>
            </div>
          </div>
        </header>

        {/* 2. SECTION: WHAT IS HAPPENING TODAY & FOCUS ENGINE */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Active Horizon Card */}
          <div className="md:col-span-2 rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs flex flex-col justify-between space-y-4">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ai flex items-center gap-1">
                  <Calendar size={12} />
                  Active Temporal Block
                </span>
                {minutesLeft !== null && minutesLeft !== undefined && (
                  <span className="rounded-full bg-ops-raised px-2 py-0.5 text-[11px] font-mono text-ink-dim border border-ops-line">
                    {minutesLeft}m remaining
                  </span>
                )}
              </div>
              <h2 className="text-xl font-bold text-ink mt-2">
                {nowBlock || "Free Flow & Strategic Focus"}
              </h2>
              {nextCommitment ? (
                <p className="text-xs text-ink-dim mt-1.5">
                  Next commitment: <span className="font-semibold text-ink">{nextCommitment}</span>
                </p>
              ) : (
                <p className="text-xs text-ink-faint mt-1.5">
                  No upcoming calendar constraints for the next few hours.
                </p>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-ops-line/60 pt-3 text-xs">
              <span className="text-ink-faint">
                {s?.today_schedule?.length ?? 0} scheduled block(s) today
              </span>
              <button
                type="button"
                onClick={() => {
                  setActiveLens("horizon");
                  setHorizonTab("schedule");
                }}
                className="font-semibold text-ai hover:underline cursor-pointer flex items-center gap-1"
              >
                <span>Full Schedule</span>
                <ArrowRight size={12} />
              </button>
            </div>
          </div>

          {/* 1-Click Focus Session Sprint Engine */}
          <div className="rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs flex flex-col justify-between space-y-4">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ink-faint flex items-center gap-1">
                  <Zap size={12} className="text-amber-500" />
                  Deep Work Engine
                </span>
                {runningFocus && (
                  <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-600 animate-pulse">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    Sprint Active
                  </span>
                )}
              </div>
              <h3 className="text-lg font-bold text-ink mt-2">
                {runningFocus ? "Sprint in Progress" : "25m Deep Work"}
              </h3>
              <p className="text-xs text-ink-dim mt-1">
                {runningFocus
                  ? runningFocus.notes || "High-intensity autonomous focus block."
                  : "Shield notifications, calibrate audio, and enter deep state."}
              </p>
            </div>

            <div className="space-y-2 pt-2">
              {runningFocus ? (
                <button
                  type="button"
                  onClick={() => completeFocus.mutate({ id: runningFocus.id })}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-critical text-white py-2 px-3 text-xs font-semibold hover:bg-critical/90 shadow-xs cursor-pointer transition"
                >
                  <StopCircle size={14} />
                  <span>End Focus Session</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    startFocus.mutate({
                      planned_duration: 25,
                      notes: "Sprint launched from Home command center",
                    })
                  }
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-ai text-white py-2 px-3 text-xs font-semibold hover:bg-ai/90 shadow-xs cursor-pointer transition"
                >
                  <Play size={13} className="fill-current" />
                  <span>Start 25m Focus Sprint</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* 3. SECTION: DUAL STAGE: URGENT PRIORITIES & DAILY ROUTINES */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Urgent Priorities (What should I focus on) */}
          <section className="rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-lg bg-ai/10 flex items-center justify-center text-ai">
                  <ListTodo size={16} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-ink">Urgent Priorities</h3>
                  <p className="text-[11px] text-ink-faint">
                    {urgentTasks.length} task(s) requiring immediate execution
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setActiveLens("horizon");
                  setHorizonTab("priorities");
                }}
                className="text-xs font-semibold text-ai hover:underline cursor-pointer flex items-center gap-1"
              >
                <span>All Tasks</span>
                <ArrowRight size={11} />
              </button>
            </div>

            {urgentTasks.length === 0 ? (
              <div className="py-10 text-center rounded-xl bg-ops-void border border-dashed border-ops-line/80">
                <CheckCircle2 size={24} className="mx-auto text-emerald-500 mb-1.5 opacity-80" />
                <p className="text-xs font-medium text-ink">All urgent priorities cleared</p>
                <p className="text-[11px] text-ink-faint mt-0.5">
                  You are ahead of schedule. Tap below to delegate tasks to IRIS.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {urgentTasks.map((t) => (
                  <div
                    key={t.id}
                    className="group flex items-center justify-between rounded-xl bg-ops-void p-3 border border-ops-line/80 hover:border-ai/40 transition shadow-2xs"
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <button
                        type="button"
                        onClick={() => completeTask.mutate({ id: t.id })}
                        title="Mark task completed"
                        className="h-5 w-5 rounded-md border border-ops-line-bright flex items-center justify-center text-transparent hover:text-emerald-500 hover:border-emerald-500 transition cursor-pointer shrink-0"
                      >
                        <CheckCircle2 size={14} />
                      </button>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink truncate">{t.title}</p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className="text-[10px] text-ink-faint font-medium uppercase tracking-wider">
                            {t.area || "General"}
                          </span>
                          {t.due && (
                            <span className="text-[10px] text-critical font-medium">
                              · Due {t.due}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    {t.priority && (
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase shrink-0",
                          t.priority.toLowerCase() === "urgent"
                            ? "bg-critical/10 text-critical"
                            : t.priority.toLowerCase() === "high"
                            ? "bg-amber-500/10 text-amber-600"
                            : "bg-ai/10 text-ai",
                        )}
                      >
                        {t.priority}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Daily Routines & Cadence (What routines to complete) */}
          <section className="rounded-2xl border border-ops-line bg-ops-panel p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-600">
                  <Repeat size={16} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-ink">Daily Routines</h3>
                  <p className="text-[11px] text-ink-faint">
                    {habitsDone} of {habitsTotal} completed ({routinePct}%)
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setActiveLens("horizon");
                  setHorizonTab("routines");
                }}
                className="text-xs font-semibold text-ai hover:underline cursor-pointer flex items-center gap-1"
              >
                <span>Manage</span>
                <ArrowRight size={11} />
              </button>
            </div>

            {/* Cadence Progress Bar */}
            <div className="space-y-1.5">
              <div className="h-2 w-full rounded-full bg-ops-raised overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all duration-500 ease-out"
                  style={{ width: `${routinePct}%` }}
                />
              </div>
            </div>

            {habitsToday.length === 0 ? (
              <div className="py-10 text-center rounded-xl bg-ops-void border border-dashed border-ops-line/80">
                <Repeat size={24} className="mx-auto text-ink-faint mb-1.5 opacity-60" />
                <p className="text-xs font-medium text-ink">No routines scheduled today</p>
                <p className="text-[11px] text-ink-faint mt-0.5">
                  Add morning, fitness, or evening routines in Routines tab.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {habitsToday.map((h) => (
                  <div
                    key={h.id}
                    className="flex items-center justify-between rounded-xl bg-ops-void p-3 border border-ops-line/80 shadow-2xs"
                  >
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <button
                        type="button"
                        onClick={() => checkHabit.mutate({ id: h.id, done: !h.done_today })}
                        title={h.done_today ? "Uncheck habit" : "Complete habit"}
                        className={cn(
                          "h-5 w-5 rounded-full border flex items-center justify-center transition cursor-pointer shrink-0",
                          h.done_today
                            ? "bg-emerald-500 border-emerald-500 text-white"
                            : "border-ops-line-bright text-transparent hover:border-ai",
                        )}
                      >
                        <CheckCircle2 size={13} />
                      </button>
                      <span
                        className={cn(
                          "text-sm font-medium truncate",
                          h.done_today ? "line-through text-ink-faint" : "text-ink",
                        )}
                      >
                        {h.name}
                      </span>
                    </div>
                    {h.streak > 0 && (
                      <span className="flex items-center gap-1 rounded-full bg-amber-500/10 text-amber-600 px-2 py-0.5 text-[10px] font-bold">
                        <Flame size={11} className="fill-current text-amber-500" />
                        <span>{h.streak}d streak</span>
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* 4. SECTION: WHAT IS IRIS HANDLING FOR ME (AUTONOMOUS SWARM & DESKTOP) */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-ai flex items-center gap-1">
              <Sparkles size={12} />
              IRIS Autonomous Operations & Infrastructure
            </span>
            <span className="text-xs text-ink-faint">Live Runtime Snapshot</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Windows 11 Desktop Companion */}
            <div className="rounded-2xl border border-ops-line bg-ops-panel p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-7 w-7 rounded-lg bg-ops-raised flex items-center justify-center text-ink">
                    <Monitor size={15} />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-ink">Desktop Companion</h4>
                    <p className="text-[10px] text-ink-faint">Windows 11 Laptop Control</p>
                  </div>
                </div>
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    computer.data?.companion_online ? "bg-emerald-500" : "bg-gray-400",
                  )}
                />
              </div>

              <div className="rounded-xl bg-ops-void p-2.5 border border-ops-line/80 text-xs space-y-1">
                <div className="flex justify-between text-ink-dim">
                  <span>Companion Status:</span>
                  <span className="font-semibold text-ink">
                    {computer.data?.session?.kill_switch_engaged
                      ? "🚨 Kill Switch Active"
                      : computer.data?.session?.state === "active"
                      ? "🟢 Desktop Session Active"
                      : computer.data?.companion_online
                      ? "Idle · Ready for actions"
                      : "Companion Offline"}
                  </span>
                </div>
                <div className="flex justify-between text-ink-dim">
                  <span>Target Machine:</span>
                  <span className="font-semibold text-ink">
                    {computer.data?.is_windows ? "Local Windows Laptop" : "Local Host"}
                  </span>
                </div>
              </div>
            </div>

            {/* Specialist Coworkers Swarm */}
            <div className="rounded-2xl border border-ops-line bg-ops-panel p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-7 w-7 rounded-lg bg-ai/10 flex items-center justify-center text-ai">
                    <Bot size={15} />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-ink">Coworker Fleet</h4>
                    <p className="text-[10px] text-ink-faint">
                      {coworkerList.length} Specialist Agents
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setActiveLens("fleet")}
                  className="text-[11px] font-semibold text-ai hover:underline cursor-pointer"
                >
                  Fleet →
                </button>
              </div>

              <div className="rounded-xl bg-ops-void p-2.5 border border-ops-line/80 text-xs space-y-1">
                {pendingApprovals.length > 0 ? (
                  <div className="flex items-center gap-2 text-critical font-medium">
                    <ShieldAlert size={14} />
                    <span>{pendingApprovals.length} capability approval(s) waiting</span>
                  </div>
                ) : (
                  <div className="flex justify-between text-ink-dim">
                    <span>Swarm Availability:</span>
                    <span className="font-semibold text-emerald-600">All Agents Idle & Ready</span>
                  </div>
                )}
                <div className="flex justify-between text-ink-dim">
                  <span>Task Delegation:</span>
                  <span className="font-semibold text-ink">Auto-routed via Supervisor</span>
                </div>
              </div>
            </div>

            {/* Knowledge Vault & Neural Graph */}
            <div className="rounded-2xl border border-ops-line bg-ops-panel p-4 shadow-xs space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-7 w-7 rounded-lg bg-ops-raised flex items-center justify-center text-ai">
                    <Brain size={15} />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-ink">Knowledge Vault</h4>
                    <p className="text-[10px] text-ink-faint">Supabase PostgreSQL + pgvector</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setActiveLens("vault");
                    setVaultTab("graph");
                  }}
                  className="text-[11px] font-semibold text-ai hover:underline cursor-pointer"
                >
                  Vault →
                </button>
              </div>

              <div className="rounded-xl bg-ops-void p-2.5 border border-ops-line/80 text-xs space-y-1">
                <div className="flex justify-between text-ink-dim">
                  <span>Encrypted Storage:</span>
                  <span className="font-semibold text-ink">iris-knowledge-vault</span>
                </div>
                <div className="flex justify-between text-ink-dim">
                  <span>Hybrid Retrieval:</span>
                  <span className="font-semibold text-emerald-600">Semantic & Lexical Sync</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* 5. BOTTOM COMMAND CENTER COMPOSER (DOCKED AT BOTTOM CENTER) */}
      <div className="fixed bottom-3 sm:bottom-4 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 z-20 pointer-events-none">
        <div className="pointer-events-auto space-y-2">
          {/* Quick Action Suggestion Pills */}
          <div className="flex items-center justify-center gap-1.5 overflow-x-auto scrollbar-none py-1">
            <button
              type="button"
              onClick={() => handleQuickPrompt("What is my next commitment today?")}
              className="rounded-full border border-ops-line bg-ops-panel/95 backdrop-blur-md px-3 py-1 text-[11px] font-medium text-ink-dim hover:text-ink hover:border-ai/50 shadow-2xs transition cursor-pointer whitespace-nowrap"
            >
              📅 Next commitment
            </button>
            <button
              type="button"
              onClick={() => handleQuickPrompt("Start 25m focus sprint")}
              className="rounded-full border border-ops-line bg-ops-panel/95 backdrop-blur-md px-3 py-1 text-[11px] font-medium text-ink-dim hover:text-ink hover:border-ai/50 shadow-2xs transition cursor-pointer whitespace-nowrap"
            >
              ⚡ 25m focus sprint
            </button>
            <button
              type="button"
              onClick={() => handleQuickPrompt("Review my urgent priorities for today.")}
              className="rounded-full border border-ops-line bg-ops-panel/95 backdrop-blur-md px-3 py-1 text-[11px] font-medium text-ink-dim hover:text-ink hover:border-ai/50 shadow-2xs transition cursor-pointer whitespace-nowrap"
            >
              🎯 Review priorities
            </button>
            <button
              type="button"
              onClick={() => handleQuickPrompt("Check Windows companion and desktop status.")}
              className="rounded-full border border-ops-line bg-ops-panel/95 backdrop-blur-md px-3 py-1 text-[11px] font-medium text-ink-dim hover:text-ink hover:border-ai/50 shadow-2xs transition cursor-pointer whitespace-nowrap"
            >
              💻 Companion status
            </button>
          </div>

          {/* Attached Image Previews */}
          {attachedImages.length > 0 && (
            <div className="flex items-center gap-2 rounded-xl border border-ops-line bg-ops-panel/95 backdrop-blur-md p-2 shadow-xs">
              {attachedImages.map((img) => (
                <div key={img.id} className="relative group">
                  <img
                    src={img.preview}
                    alt="attachment"
                    className="h-12 w-12 rounded-lg object-cover border border-ops-line"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setAttachedImages((prev) => prev.filter((i) => i.id !== img.id))
                    }
                    className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-critical text-white flex items-center justify-center text-[10px]"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Docked Command Bar Box */}
          <form
            onSubmit={handleComposerSubmit}
            className="flex items-center gap-2 rounded-2xl border border-ai/30 bg-ops-panel/95 backdrop-blur-md px-3 py-2 shadow-lg focus-within:border-ai focus-within:ring-2 focus-within:ring-ai/20 transition"
          >
            {/* Visual Screen Perception Button */}
            <button
              type="button"
              onClick={handleCaptureScreen}
              disabled={capturingScreen}
              title="Capture active screen & attach to prompt"
              className="rounded-xl p-2 text-ink-dim hover:text-ink hover:bg-ops-raised transition cursor-pointer shrink-0 disabled:opacity-50"
            >
              <Monitor size={17} className={capturingScreen ? "text-ai animate-spin" : ""} />
            </button>

            {/* File upload hidden input & trigger */}
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const files = e.target.files;
                if (!files || files.length === 0) return;
                const file = files[0];
                const preview = URL.createObjectURL(file);
                setAttachedImages((prev) => [
                  ...prev,
                  { id: `file-${Date.now()}`, file, preview },
                ]);
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              title="Attach image or screenshot"
              className="rounded-xl p-2 text-ink-dim hover:text-ink hover:bg-ops-raised transition cursor-pointer shrink-0"
            >
              <UploadCloud size={17} />
            </button>

            {/* Main Input Textarea/Input */}
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask IRIS anything or enter an autonomous command…"
              className="flex-1 bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-hidden px-1"
            />

            {/* Voice session button */}
            <button
              type="button"
              onClick={() => {
                if (voice.phase === "off") {
                  void voice.start();
                } else {
                  voice.tap();
                }
              }}
              title={voice.phase === "off" ? "Start voice interaction" : "Voice Active"}
              className={cn(
                "rounded-xl p-2 transition cursor-pointer shrink-0",
                voice.phase !== "off"
                  ? "bg-emerald-500 text-white animate-pulse"
                  : "text-ink-dim hover:text-ink hover:bg-ops-raised",
              )}
            >
              <Sparkles size={17} />
            </button>

            {/* Submit Arrow Button */}
            <button
              type="submit"
              disabled={sending || (!prompt.trim() && attachedImages.length === 0)}
              title="Send to IRIS"
              className={cn(
                "rounded-xl p-2 transition cursor-pointer shrink-0",
                prompt.trim() || attachedImages.length > 0
                  ? "bg-ai text-white hover:bg-ai/90 shadow-2xs"
                  : "text-ink-faint opacity-40 cursor-not-allowed",
              )}
            >
              <ArrowUp size={17} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
