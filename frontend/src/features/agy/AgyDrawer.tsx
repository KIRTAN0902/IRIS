import { lazy, Suspense, useEffect, useState } from "react";

const AgyTerminalDeck = lazy(() => import("@/features/agy/AgyTerminalDeck").then((m) => ({ default: m.AgyTerminalDeck })));

export function AgyDrawer() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const desktop = window.irisDesktop;
    const offDesktop = desktop?.onOpenAgyDrawer?.(() => setOpen(true));
    const onOpen = () => setOpen(true);
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey && event.key.toLowerCase() === "g") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("iris:open-agy", onOpen);
    window.addEventListener("keydown", onKey);
    return () => {
      offDesktop?.();
      window.removeEventListener("iris:open-agy", onOpen);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex justify-end bg-black/60 backdrop-blur-[2px]"
      onClick={() => setOpen(false)}
    >
      <div
        className="h-full w-full max-w-[760px] border-l border-ops-line-bright bg-[#080A0F] p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <Suspense fallback={<div className="p-6 text-sm text-ink-faint">Opening Antigravity…</div>}><AgyTerminalDeck variant="drawer" onClose={() => setOpen(false)} /></Suspense>
      </div>
    </div>
  );
}
