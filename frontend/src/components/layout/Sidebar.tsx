import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Brain, Menu, PanelLeftClose, PanelLeftOpen, SquarePen, Square, X } from "lucide-react";
import { PRIMARY_NAV_ITEMS } from "@/modules/registry";
import { cn, parseUtc } from "@/lib/format";
import { useFocusStore, useUiStore } from "@/stores";
import {
  useAIStatus,
  useCompleteFocus,
  useConversations,
  useTodayState,
} from "@/hooks/queries";
import { MemoryModal } from "@/features/home/MemoryModal";

/**
 * Notes-style sidebar: sections at the top, conversations listed like notes
 * below, and a quiet footer (AI status, memory, running focus timer).
 */
export function Sidebar() {
  const fold = useUiStore((s) => s.navFold);
  const toggle = useUiStore((s) => s.toggleNavFold);
  const [memoryOpen, setMemoryOpen] = useState(false);

  if (fold) {
    return (
      <nav aria-label="Primary Navigation" className="hidden md:flex w-12 flex-col items-center gap-1 bg-ops-panel py-3">
        <button
          onClick={toggle}
          aria-label="Show sidebar"
          className="rounded-md p-2 text-ink-faint hover:bg-ops-raised hover:text-ink cursor-pointer"
        >
          <PanelLeftOpen size={16} />
        </button>
        {PRIMARY_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            to={item.route}
            end={item.route === "/"}
            title={item.name}
            className={({ isActive }) =>
              cn(
                "rounded-md p-2 transition-colors",
                isActive ? "bg-ops-raised text-ink" : "text-ink-faint hover:bg-ops-raised hover:text-ink",
              )
            }
          >
            <item.icon size={16} strokeWidth={1.75} />
          </NavLink>
        ))}
      </nav>
    );
  }

  return (
    <nav
      aria-label="Primary Navigation"
      className="hidden md:flex sticky top-0 h-dvh w-60 shrink-0 flex-col bg-ops-panel select-none"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <NavLink to="/" className="flex items-center gap-2 text-ink">
          <IrisMark size={18} />
          <span className="text-[15px] font-semibold">IRIS</span>
        </NavLink>
        <div className="ml-auto flex items-center">
          <NewNoteButton />
          <button
            onClick={toggle}
            aria-label="Hide sidebar"
            title="Hide sidebar"
            className="rounded-md p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink cursor-pointer"
          >
            <PanelLeftClose size={15} />
          </button>
        </div>
      </div>

      {/* Sections */}
      <div className="px-2 space-y-px">
        {PRIMARY_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            to={item.route}
            end={item.route === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[14px] transition-colors",
                isActive ? "bg-ops-raised text-ink font-medium" : "text-ink-dim hover:bg-ops-raised/60 hover:text-ink",
              )
            }
          >
            <item.icon size={15} strokeWidth={1.75} className="shrink-0 opacity-80" />
            <span>{item.name}</span>
          </NavLink>
        ))}
      </div>

      {/* Conversations, listed like notes */}
      <ConversationList />

      {/* Footer */}
      <div className="space-y-1 px-2 pb-3 pt-2">
        <FocusTimer />
        <button
          onClick={() => setMemoryOpen(true)}
          className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-ink-dim hover:bg-ops-raised/60 hover:text-ink cursor-pointer"
        >
          <Brain size={15} strokeWidth={1.75} className="shrink-0 opacity-80" />
          <span>What IRIS remembers</span>
        </button>
        <AIStatusLine />
      </div>

      <MemoryModal open={memoryOpen} onClose={() => setMemoryOpen(false)} />
    </nav>
  );
}

/** Opens a new chat; the conversation is created on the first message. */
function NewNoteButton({ onClick }: { onClick?: () => void }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => {
        navigate("/");
        onClick?.();
      }}
      aria-label="New chat"
      title="New chat"
      className="rounded-md p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink cursor-pointer disabled:opacity-40"
    >
      <SquarePen size={15} />
    </button>
  );
}

function relativeDay(iso: string): string {
  const d = parseUtc(iso);
  const today = new Date();
  const days = Math.floor(
    (new Date(today.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86_400_000,
  );
  if (days <= 0) return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (days === 1) return "Yesterday";
  if (days < 7) return d.toLocaleDateString([], { weekday: "long" });
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

/** First line of a conversation's summary, like a notes app's preview text. */
function preview(summary?: string | null): string {
  const line = (summary ?? "").split("\n").find((l) => l.trim());
  return line ? line.replace(/^\s*[-•]\s*/, "").trim() : "";
}

function ConversationList() {
  const convs = useConversations(30);
  const location = useLocation();
  const [params] = useSearchParams();
  const activeId = Number(params.get("c")) || null;
  const onHome = location.pathname === "/";
  const list = convs.data ?? [];

  return (
    <div className="mt-5 flex min-h-0 flex-1 flex-col">
      <p className="label-caps px-4 pb-1">Conversations</p>
      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        {list.length === 0 && !convs.isLoading && (
          <p className="px-2.5 py-1 text-[13px] text-ink-faint">No conversations yet.</p>
        )}
        {list.map((c) => {
          const active = onHome && activeId === c.id;
          return (
            <NavLink
              key={c.id}
              to={`/?c=${c.id}`}
              className={cn(
                "block rounded-md px-2.5 py-1.5 transition-colors",
                active ? "bg-ai-dim" : "hover:bg-ops-raised/60",
              )}
            >
              <p className={cn("truncate text-[13px]", active ? "text-ink font-medium" : "text-ink")}>
                {c.title || "Untitled"}
              </p>
              <p className="truncate text-[11px] text-ink-faint">
                <span className="tnum">{relativeDay(c.updated_at)}</span>
                {preview(c.summary) && <span className="ml-1.5">{preview(c.summary)}</span>}
              </p>
            </NavLink>
          );
        })}
      </div>
    </div>
  );
}

function AIStatusLine() {
  const aiStatusQuery = useAIStatus();
  const todayState = useTodayState();
  const s = aiStatusQuery.data ?? todayState.data?.ai_status;
  if (!s) return null;

  const offline = !s.responding || s.status === "NOT_RESPONDING";
  const unconfigured = s.status === "NOT_CONFIGURED";
  const label = unconfigured ? "AI not set up" : offline ? "AI offline · using offline engine" : s.model.split("/").pop();

  return (
    <div className="flex items-center gap-2 px-2.5 pt-1 text-[11px] text-ink-faint" title={s.message ?? undefined}>
      <span
        className={cn("h-1.5 w-1.5 shrink-0 rounded-full", offline || unconfigured ? "bg-caution" : "bg-go")}
        aria-hidden
      />
      <span className="truncate">{label}</span>
    </div>
  );
}

/** Running focus session timer (shown only while a session is active). */
export function FocusTimer() {
  const running = useFocusStore((s) => s.running);
  const complete = useCompleteFocus();
  const navigate = useNavigate();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!running) return;
    const start = parseUtc(running.started_at).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [running]);

  if (!running) return null;
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="flex items-center gap-2 rounded-md bg-go-dim px-2.5 py-1.5 text-[13px] text-go">
      <span className="h-1.5 w-1.5 rounded-full bg-go lamp-pulse" aria-hidden />
      <button onClick={() => navigate("/focus")} className="tnum font-medium cursor-pointer">
        Focusing {mm}:{ss}
      </button>
      <button
        aria-label="Finish focus session"
        title="Finish session"
        onClick={() => complete.mutate({ id: running.id })}
        className="ml-auto opacity-70 hover:opacity-100 cursor-pointer"
      >
        <Square size={11} strokeWidth={2.25} />
      </button>
    </div>
  );
}

/** The IRIS mark: a simple ring, drawn in the current text colour. */
export function IrisMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden className="shrink-0">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="3" fill="var(--color-ai)" />
    </svg>
  );
}

/** Mobile top bar, with a slide-in drawer holding the conversation history. */
export function MobileTopBar({ askTrigger }: { askTrigger: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close the drawer whenever navigation happens (opening a chat, new chat…).
  useEffect(() => setOpen(false), [location.pathname, location.search]);

  return (
    <>
      <header className="sticky top-0 z-40 flex h-12 items-center gap-2 bg-ops-ground/90 px-4 backdrop-blur md:hidden">
        <button
          onClick={() => setOpen(true)}
          aria-label="Open conversations"
          className="-ml-1.5 rounded-md p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink"
        >
          <Menu size={18} strokeWidth={1.75} />
        </button>
        <NavLink to="/" className="flex items-center gap-2 text-ink">
          <IrisMark size={18} />
          <span className="text-[15px] font-semibold">IRIS</span>
        </NavLink>
        <div className="ml-auto flex items-center gap-1">
          <NewNoteButton />
          {askTrigger}
        </div>
      </header>
      <MobileDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function MobileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [memoryOpen, setMemoryOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  return (
    <div
      className={cn("fixed inset-0 z-50 md:hidden", open ? "" : "pointer-events-none")}
      aria-hidden={!open}
    >
      <div
        onClick={onClose}
        className={cn("absolute inset-0 bg-black/60 transition-opacity", open ? "opacity-100" : "opacity-0")}
      />
      <nav
        aria-label="Conversations"
        // Tapping a link inside (even the chat already open) closes the drawer.
        onClick={(e) => (e.target as HTMLElement).closest("a") && onClose()}
        className={cn(
          "absolute inset-y-0 left-0 flex w-[82%] max-w-[300px] flex-col bg-ops-panel transition-transform duration-200",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex items-center gap-2 px-4 pt-4 pb-1">
          <NavLink to="/" className="flex items-center gap-2 text-ink">
            <IrisMark size={18} />
            <span className="text-[15px] font-semibold">IRIS</span>
          </NavLink>
          <div className="ml-auto flex items-center">
            <NewNoteButton onClick={onClose} />
            <button
              onClick={onClose}
              aria-label="Close conversations"
              className="rounded-md p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <ConversationList />

        <div className="space-y-1 px-2 pb-3 pt-2">
          <FocusTimer />
          <button
            onClick={() => setMemoryOpen(true)}
            className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-ink-dim hover:bg-ops-raised/60 hover:text-ink cursor-pointer"
          >
            <Brain size={15} strokeWidth={1.75} className="shrink-0 opacity-80" />
            <span>What IRIS remembers</span>
          </button>
          <AIStatusLine />
        </div>
      </nav>
      <MemoryModal open={memoryOpen} onClose={() => setMemoryOpen(false)} />
    </div>
  );
}
