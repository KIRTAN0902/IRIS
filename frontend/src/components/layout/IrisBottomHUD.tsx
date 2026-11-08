import { Command, Compass, Database, Mic, Users } from "lucide-react";
import { useLensStore, type IrisLens } from "@/stores/lensStore";
import { useVoiceSession } from "@/features/home/VoiceSession";
import { cn } from "@/lib/format";

export function IrisBottomHUD() {
  const { activeLens, setActiveLens } = useLensStore();
  const voice = useVoiceSession();
  const isListening = voice.phase === "listening" || voice.phase === "speaking";

  return (
    <nav
      aria-label="Mobile Operating Navigation"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-ops-line bg-ops-panel/95 backdrop-blur-md pb-[max(env(safe-area-inset-bottom,0px),8px)] pt-1 md:hidden"
    >
      <div className="flex items-center justify-around px-2">
        <MobileTab
          id="studio"
          label="Studio"
          icon={Command}
          active={activeLens === "studio"}
          onClick={() => setActiveLens("studio")}
        />
        <MobileTab
          id="horizon"
          label="Horizon"
          icon={Compass}
          active={activeLens === "horizon"}
          onClick={() => setActiveLens("horizon")}
        />

        {/* Center Floating Voice Action Button */}
        <button
          type="button"
          onClick={() => (isListening ? voice.end() : voice.start())}
          aria-label={isListening ? "Stop voice" : "Talk to IRIS"}
          className={cn(
            "relative -top-2 flex h-11 w-11 items-center justify-center rounded-full border shadow-md transition-all cursor-pointer",
            isListening
              ? "bg-critical border-critical text-white animate-pulse"
              : "bg-ai border-ai/50 text-white hover:scale-105 active:scale-95",
          )}
        >
          <Mic size={18} />
          {isListening && (
            <span className="absolute -inset-1 rounded-full border-2 border-critical/50 animate-ping pointer-events-none" />
          )}
        </button>

        <MobileTab
          id="fleet"
          label="Fleet"
          icon={Users}
          active={activeLens === "fleet"}
          onClick={() => setActiveLens("fleet")}
        />
        <MobileTab
          id="vault"
          label="Vault"
          icon={Database}
          active={activeLens === "vault"}
          onClick={() => setActiveLens("vault")}
        />
      </div>
    </nav>
  );
}

function MobileTab({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  id: IrisLens;
  label: string;
  icon: typeof Command;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center gap-0.5 py-1 px-3 text-[10px] font-medium transition-colors cursor-pointer",
        active ? "text-ai font-semibold" : "text-ink-faint hover:text-ink",
      )}
    >
      <Icon size={18} className={cn(active ? "text-ai" : "opacity-75")} />
      <span>{label}</span>
    </button>
  );
}
