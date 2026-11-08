import { Calendar, Command, Compass, Database, Users } from "lucide-react";
import { useLensStore, type IrisLens } from "@/stores/lensStore";
import { cn } from "@/lib/format";

export function IrisBottomHUD() {
  const { activeLens, setActiveLens } = useLensStore();

  return (
    <nav
      aria-label="Mobile Operating Navigation"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-ops-line bg-ops-panel/95 backdrop-blur-md pb-[max(env(safe-area-inset-bottom,0px),8px)] pt-1 md:hidden"
    >
      <div className="flex items-center justify-around px-2">
        <MobileTab
          id="home"
          label="Home"
          icon={Compass}
          active={activeLens === "home"}
          onClick={() => setActiveLens("home")}
        />
        <MobileTab
          id="studio"
          label="Chat"
          icon={Command}
          active={activeLens === "studio"}
          onClick={() => setActiveLens("studio")}
        />
        <MobileTab
          id="horizon"
          label="Horizon"
          icon={Calendar}
          active={activeLens === "horizon"}
          onClick={() => setActiveLens("horizon")}
        />
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
