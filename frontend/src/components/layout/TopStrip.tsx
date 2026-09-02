import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Command, Square } from "lucide-react";
import { useCompleteFocus } from "@/hooks/queries";
import { useFocusStore, useUiStore } from "@/stores";
import { parseUtc } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Lamp } from "@/components/ui/Panel";

/** Ticking local time + free-time + focus chip + ASK trigger. */
export function TopStrip({ askTrigger }: { askTrigger?: React.ReactNode }) {
  const running = useFocusStore((s) => s.running);
  const setAskOpen = useUiStore((s) => s.setAskOpen);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="hidden h-14 items-center gap-5 border-b border-ops-line bg-ops-ground px-6 md:flex">
      <div className="flex items-baseline gap-2.5">
        <span className="font-[family-name:var(--font-telemetry)] text-[16px] font-semibold text-ink tnum">
          {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </span>
        <span className="font-[family-name:var(--font-display)] text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-faint">
          {now.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-3">
        {running && <FocusChip sessionId={running.id} startedAt={running.started_at} />}

        {askTrigger ?? (
          <Button size="sm" variant="outline" onClick={() => setAskOpen(true)} className="gap-2">
            <Command size={12} strokeWidth={2} className="text-ink-dim" />
            <span>Ask IRIS</span>
            <kbd className="ml-1 rounded border border-ops-line-bright bg-ops-raised px-1.5 py-0.5 font-[family-name:var(--font-telemetry)] text-[10px] text-ink-dim">
              ⌘K
            </kbd>
          </Button>
        )}
      </div>
    </div>
  );
}

function FocusChip({ sessionId, startedAt }: { sessionId: number; startedAt: string }) {
  const complete = useCompleteFocus();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = parseUtc(startedAt).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [startedAt]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="flex items-center gap-2 rounded-full border border-go-dim bg-go-dim/30 px-3 py-1 text-go">
      <Lamp tone="go" pulse />
      <button
        onClick={() => navigate("/focus")}
        className="font-[family-name:var(--font-telemetry)] text-[12px] font-semibold tracking-wide text-go hover:text-ink cursor-pointer"
        title="Open focus console"
      >
        FOCUS {mm}:{ss}
      </button>
      <button
        aria-label="Complete focus session"
        title="Complete session"
        className="text-ink-faint hover:text-critical cursor-pointer ml-0.5"
        onClick={() =>
          complete.mutate(
            { id: sessionId },
            { onSuccess: () => qc.invalidateQueries() },
          )
        }
      >
        <Square size={11} strokeWidth={2} />
      </button>
    </div>
  );
}

/**
 * Mobile bottom navigation — solid clean 4 primary destinations:
 * Home (⌾), Schedule (▦), Tasks (☷), Projects (⌁).
 */
export function MobileBottomNav() {
  const items = [
    { id: "home", name: "Home", route: "/", glyph: "⌾" },
    { id: "schedule", name: "Schedule", route: "/schedule", glyph: "▦" },
    { id: "tasks", name: "Tasks", route: "/tasks", glyph: "☷" },
    { id: "projects", name: "Projects", route: "/projects", glyph: "⌁" },
  ];

  return (
    <nav
      aria-label="Primary Mobile Navigation"
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-ops-line bg-ops-ground md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {items.map((item) => (
        <NavLink
          key={item.id}
          to={item.route}
          end={item.route === "/"}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 py-2 text-[11px] font-medium tracking-wide transition-colors ${
              isActive ? "text-ink font-semibold" : "text-ink-faint hover:text-ink"
            }`
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={`h-[2px] w-8 rounded-full transition-all ${isActive ? "bg-ink" : "bg-transparent"}`}
                aria-hidden
              />
              <span className="font-[family-name:var(--font-telemetry)] text-[14px] leading-none" aria-hidden>
                {item.glyph}
              </span>
              <span className="font-[family-name:var(--font-body)] text-[11px] leading-none">
                {item.name}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}


