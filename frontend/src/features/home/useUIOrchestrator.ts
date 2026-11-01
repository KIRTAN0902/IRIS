import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { uiOrchestratorApi } from "@/features/home/uiOrchestratorApi";

export const uiStateKey = ["ui-orchestrator", "state"] as const;
// The service currently exposes versioned REST state without a UI event stream.
// Refetch in the foreground so changes from another device arrive promptly.
export const useUIState = () => useQuery({ queryKey: uiStateKey, queryFn: uiOrchestratorApi.state, staleTime: 10_000, refetchInterval: 20_000 });
export const useUIContext = () => useQuery({ queryKey: ["ui-orchestrator", "context"], queryFn: uiOrchestratorApi.context, staleTime: 30_000, refetchInterval: 30_000 });

function useRefresh() {
  const qc = useQueryClient();
  return () => { void qc.invalidateQueries({ queryKey: uiStateKey }); void qc.invalidateQueries({ queryKey: ["ui-orchestrator", "context"] }); };
}
export const useSaveUILayout = () => { const refresh = useRefresh(); return useMutation({ mutationFn: ({ platform, version, widgets }: { platform: "desktop" | "android"; version: number; widgets: import("@/features/home/uiOrchestratorApi").WidgetLayoutItem[] }) => uiOrchestratorApi.saveLayout(platform, version, widgets), onSuccess: refresh, onError: refresh }); };
export const useSaveUIPreferences = () => { const refresh = useRefresh(); return useMutation({ mutationFn: ({ version, preferences }: { version: number; preferences: Partial<import("@/features/home/uiOrchestratorApi").UIState["preferences"]> }) => uiOrchestratorApi.savePreferences(version, preferences), onSuccess: refresh, onError: refresh }); };
export const useCreateUIProposal = () => { const refresh = useRefresh(); return useMutation({ mutationFn: ({ platform, title, reason, widgets }: { platform: "desktop" | "android"; title: string; reason: string; widgets: import("@/features/home/uiOrchestratorApi").WidgetLayoutItem[] }) => uiOrchestratorApi.propose(platform, title, reason, widgets), onSuccess: refresh, onError: refresh }); };
export const useDecideUIProposal = () => { const refresh = useRefresh(); return useMutation({ mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) => uiOrchestratorApi.decide(id, decision), onSuccess: refresh, onError: refresh }); };
export const useRollbackUI = () => { const refresh = useRefresh(); return useMutation({ mutationFn: uiOrchestratorApi.rollback, onSuccess: refresh, onError: refresh }); };
