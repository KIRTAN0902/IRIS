import { create } from "zustand";
import type { FocusSessionOut } from "@/types/api";

/** Global UI state: navigation fold + the Ask IRIS console. */
interface UiState {
  navFold: boolean;
  toggleNavFold: () => void;
  askOpen: boolean;
  setAskOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  navFold: false,
  toggleNavFold: () => set((s) => ({ navFold: !s.navFold })),
  askOpen: false,
  setAskOpen: (open) => set({ askOpen: open }),
}));

/**
 * Focus session console state. The session lives server-side; this store only
 * mirrors the RUNNING session so any screen can render the timer chip.
 */
interface FocusState {
  running: FocusSessionOut | null;
  setRunning: (session: FocusSessionOut | null) => void;
}

export const useFocusStore = create<FocusState>((set) => ({
  running: null,
  setRunning: (running) => set({ running }),
}));
