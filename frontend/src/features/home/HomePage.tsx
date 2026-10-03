import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowUp, Play } from "lucide-react";
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
  const endRef = useRef<HTMLDivElement>(null);
  // The conversation this component just created from a new chat: switching to
  // it must not reset the in-flight reply.
  const createdRef = useRef<number | null>(null);

  const messages = conv.data?.messages ?? [];

  useEffect(() => {
    if (conversationId !== null && conversationId === createdRef.current) return;
    setInput("");
    setLastSent("");
    sendMsg.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    if (messages.length || sendMsg.isPending) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, sendMsg.isPending]);

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || sendMsg.isPending) return;
    let id = conversationId;
    if (!id) {
      try {
        id = (await createConv.mutateAsync(content.slice(0, 60))).id;
        createdRef.current = id;
        onCreated(id);
      } catch {
        return;
      }
    }
    setLastSent(content);
    setInput("");
    sendMsg.mutate({ conversationId: id, content });
  };

  const busy = sendMsg.isPending || createConv.isPending;
  const isNewChat = !conversationId && !busy;

  if (isNewChat) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center pb-[12vh]">
        <h1 className="neon select-none text-[44px] font-semibold tracking-[0.22em] text-ink sm:text-[56px]">
          IRIS
        </h1>
        <div className="mt-10 w-full">
          <Composer value={input} onChange={setInput} onSend={() => send()} disabled={busy} autoFocus />
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
              <UserNote content={lastSent} />
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

      <div className="sticky bottom-14 md:bottom-0 bg-gradient-to-t from-ops-ground from-75% to-transparent pb-4 pt-6">
        <Composer value={input} onChange={setInput} onSend={() => send()} disabled={busy} />
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const ready = value.trim() && !disabled;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
      className="flex items-end gap-2 rounded-3xl border border-ops-line-bright bg-ops-void px-4 py-2.5 focus-within:border-ink-faint"
    >
      <textarea
        ref={ref}
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        placeholder="Ask IRIS anything"
        rows={1}
        disabled={disabled}
        className="min-h-[28px] max-h-52 flex-1 resize-none bg-transparent py-1 text-[15px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
      />
      <button
        type="submit"
        disabled={!ready}
        aria-label="Send"
        className={cn(
          "mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-opacity",
          ready ? "bg-ink text-ops-ground cursor-pointer hover:opacity-85" : "bg-ops-raised text-ink-faint",
        )}
      >
        <ArrowUp size={16} strokeWidth={2.5} />
      </button>
    </form>
  );
}

function UserNote({ content, time }: { content: string; time?: string }) {
  return (
    <div className="flex flex-col items-end">
      {time && <p className="mb-1 text-[12px] text-ink-faint tnum">{time}</p>}
      <p className="max-w-[85%] whitespace-pre-wrap rounded-3xl bg-ops-raised px-4 py-2.5 text-[15px] leading-relaxed text-ink">
        {content}
      </p>
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
