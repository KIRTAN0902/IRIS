import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useLensStore, type IrisLens } from "@/stores/lensStore";
import { ProductivityHomePage } from "@/features/home/ProductivityHomePage";
import { StudioLens } from "@/features/studio/StudioLens";
import { HorizonLens } from "@/features/horizon/HorizonLens";
import { FleetLens } from "@/features/fleet/FleetLens";
import { VaultLens } from "@/features/vault/VaultLens";

export function IrisOSStage() {
  const [params] = useSearchParams();
  const { activeLens, setActiveLens, setHorizonTab, setVaultTab } = useLensStore();

  const queryLens = params.get("lens") as IrisLens | null;
  const queryTab = params.get("tab");

  // Sync URL query params with lens store
  useEffect(() => {
    if (queryLens && ["home", "studio", "horizon", "fleet", "vault"].includes(queryLens)) {
      setActiveLens(queryLens);
    }
    if (queryTab) {
      if (
        [
          "overview",
          "priorities",
          "schedule",
          "routines",
          "projects",
          "finance",
          "fitness",
          "diary",
        ].includes(queryTab)
      ) {
        setHorizonTab(queryTab as any);
      }
      if (["graph", "vault", "memories", "mesh"].includes(queryTab)) {
        setVaultTab(queryTab as any);
      }
    }
  }, [queryLens, queryTab, setActiveLens, setHorizonTab, setVaultTab]);

  return (
    <div className="flex-1 min-w-0 bg-ops-ground">
      {(activeLens === "home" || !activeLens) && <ProductivityHomePage />}
      {activeLens === "studio" && <StudioLens />}
      {activeLens === "horizon" && <HorizonLens />}
      {activeLens === "fleet" && <FleetLens />}
      {activeLens === "vault" && <VaultLens />}
    </div>
  );
}
