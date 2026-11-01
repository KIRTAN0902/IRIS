import { api } from "@/api/client";

export type Platform = "desktop" | "android";
export interface WidgetLayoutItem { id: string; visible: boolean; size: string; locked: boolean; config: Record<string, unknown>; lifecycle: "persistent" | "temporary"; expires_at: string | null }
export interface UIProposal { id: string; title: string; reason: string; status: string; layout: { platform: Platform; widgets: WidgetLayoutItem[] } }
export interface UIState {
  version: number;
  preferences: { density: "compact" | "comfortable" | "spacious"; interaction_learning: boolean; week_start: string; theme?: "light" | "dark" | "system" };
  layouts: Record<Platform, WidgetLayoutItem[]>;
  history: { version: number; kind: string; created_at: string }[];
  proposals: UIProposal[];
}
export interface UIContext { page: string; local_time?: string; attention_count: number; has_schedule: boolean; active_coworker_tasks: number; available_widgets: string[] }

export const uiOrchestratorApi = {
  state: () => api.get<UIState>("/ui-orchestrator/state"),
  context: () => api.get<UIContext>("/ui-orchestrator/context"),
  saveLayout: (platform: Platform, version: number, widgets: WidgetLayoutItem[]) => api.put<{ version: number; platform: Platform; widgets: WidgetLayoutItem[] }>(`/ui-orchestrator/layouts/${platform}`, { expected_version: version, widgets }),
  savePreferences: (version: number, preferences: Partial<UIState["preferences"]>) => api.put<{ version: number; preferences: UIState["preferences"] }>("/ui-orchestrator/preferences", { expected_version: version, ...preferences }),
  propose: (platform: Platform, title: string, reason: string, widgets: WidgetLayoutItem[]) => api.post<UIProposal>("/ui-orchestrator/proposals", { platform, title, reason, widgets }),
  decide: (id: string, decision: "approve" | "reject") => api.post<{ proposal: UIProposal; version: number }>(`/ui-orchestrator/proposals/${id}/decision`, { decision }),
  rollback: () => api.post<Pick<UIState, "version" | "preferences" | "layouts">>("/ui-orchestrator/rollback"),
};
