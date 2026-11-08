import { lazy, Suspense } from "react";
import { X } from "lucide-react";
import { useLensStore } from "@/stores/lensStore";

const SettingsPage = lazy(() =>
  import("@/features/settings/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);

export function SettingsOverlay() {
  const { settingsOpen, setSettingsOpen } = useLensStore();

  if (!settingsOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity animate-in fade-in"
        onClick={() => setSettingsOpen(false)}
      />

      {/* Slide-over panel */}
      <div className="relative z-10 h-full w-full max-w-4xl border-l border-ops-line-bright bg-ops-panel p-6 shadow-2xl overflow-y-auto animate-in slide-in-from-right duration-200">
        <div className="flex items-center justify-between pb-4 border-b border-ops-line mb-6">
          <h2 className="text-base font-bold text-ink">IRIS System Hub</h2>
          <button
            type="button"
            onClick={() => setSettingsOpen(false)}
            aria-label="Close settings"
            className="rounded-lg p-1.5 text-ink-faint hover:text-ink hover:bg-ops-raised transition cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        <Suspense fallback={<div className="text-xs text-ink-faint animate-pulse">Loading Settings Hub…</div>}>
          <SettingsPage />
        </Suspense>
      </div>
    </div>
  );
}
