import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Search } from "lucide-react";
import { MobileBottomNav } from "@/components/layout/TopStrip";
import { MobileTopBar, Sidebar } from "@/components/layout/Sidebar";
import { AskIrisConsole } from "@/features/ai/AskIrisConsole";
import { useFocusSessions } from "@/hooks/queries";
import { useUiStore } from "@/stores";

/**
 * Notes-style shell: a quiet sidebar and one centred reading column.
 * Cmd/Ctrl+K opens Ask IRIS from anywhere.
 */
export function AppShell() {
  const location = useLocation();
  const setAskOpen = useUiStore((s) => s.setAskOpen);

  // Hydrate any running focus session once at boot.
  useFocusSessions();

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
    <div className="flex min-h-dvh bg-ops-ground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopBar
          askTrigger={
            <button
              onClick={() => setAskOpen(true)}
              aria-label="Ask IRIS"
              className="rounded-md p-1.5 text-ink-faint hover:bg-ops-raised hover:text-ink"
            >
              <Search size={16} strokeWidth={1.75} />
            </button>
          }
        />
        <main className="mx-auto flex w-full min-w-0 max-w-[920px] flex-1 flex-col px-5 pb-24 pt-6 md:px-12 md:pb-10 md:pt-12">
          <Outlet key={location.pathname} />
        </main>
      </div>
      <MobileBottomNav />
      <AskIrisConsole />
    </div>
  );
}
