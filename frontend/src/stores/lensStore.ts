import { create } from "zustand";

export type IrisLens = "studio" | "horizon" | "fleet" | "vault";

interface LensStoreState {
  activeLens: IrisLens;
  setActiveLens: (lens: IrisLens) => void;
  // Subview within Horizon
  horizonTab: "overview" | "priorities" | "schedule" | "routines" | "projects" | "finance" | "fitness" | "diary";
  setHorizonTab: (tab: LensStoreState["horizonTab"]) => void;
  // Subview within Vault
  vaultTab: "graph" | "vault" | "memories" | "mesh";
  setVaultTab: (tab: LensStoreState["vaultTab"]) => void;
  // Active coworker selected for direct session in Fleet
  selectedCoworkerId: string | null;
  setSelectedCoworkerId: (id: string | null) => void;
  // Context inspector pane in Studio (collapsible)
  studioInspectorOpen: boolean;
  toggleStudioInspector: () => void;
  setStudioInspectorOpen: (open: boolean) => void;
  // Quick conversation history drawer
  historyDrawerOpen: boolean;
  setHistoryDrawerOpen: (open: boolean) => void;
  // Settings overlay
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
}

export const useLensStore = create<LensStoreState>((set) => ({
  activeLens: "studio",
  setActiveLens: (lens) => set({ activeLens: lens }),
  horizonTab: "overview",
  setHorizonTab: (tab) => set({ horizonTab: tab }),
  vaultTab: "graph",
  setVaultTab: (tab) => set({ vaultTab: tab }),
  selectedCoworkerId: null,
  setSelectedCoworkerId: (id) => set({ selectedCoworkerId: id }),
  studioInspectorOpen: true,
  toggleStudioInspector: () => set((s) => ({ studioInspectorOpen: !s.studioInspectorOpen })),
  setStudioInspectorOpen: (open) => set({ studioInspectorOpen: open }),
  historyDrawerOpen: false,
  setHistoryDrawerOpen: (open) => set({ historyDrawerOpen: open }),
  settingsOpen: false,
  setSettingsOpen: (open) => set({ settingsOpen: open }),
}));
