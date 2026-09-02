import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Command } from "lucide-react";
import { MobileBottomNav, TopStrip } from "@/components/layout/TopStrip";
import { MobileTopBar, Sidebar } from "@/components/layout/Sidebar";
import { AskIrisConsole } from "@/features/ai/AskIrisConsole";
import { useFocusSessions } from "@/hooks/queries";
import { useUiStore } from "@/stores";
import { cn } from "@/lib/format";

/**
 * The operating shell: module rail + status strip + workspace.
 * Every screen mounts inside this frame; the AI console overlays all of it.
 */
export function AppShell() {
  const location = useLocation();
  const setAskOpen = useUiStore((s) => s.setAskOpen);

  // Hydrate any running focus session once at boot.
  useFocusSessions();

  // Global keyboard chord: Cmd/Ctrl+K asks IRIS from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAskOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setAskOpen]);

  return (
    <div className="flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopStrip />
        <MobileTopBar
          askTrigger={
            <button
              onClick={() => setAskOpen(true)}
              aria-label="Ask IRIS"
              className="flex h-8 w-8 items-center justify-center border border-ops-line-bright text-ink-dim"
            >
              <Command size={14} strokeWidth={1.75} />
            </button>
          }
        />
        <main className={cn("min-w-0 flex-1 px-4 pb-24 pt-5 md:px-8 md:pb-10", "mx-auto w-full max-w-[1400px]")}>
          <Outlet key={location.pathname} />
        </main>
      </div>
      <MobileBottomNav />
      <AskIrisConsole />
    </div>
  );
}
