import { api } from "@/api/client";

export type AgyState = "STARTING" | "IDLE" | "BUSY";

export interface AgySession {
  key: string;
  alias: string;
  directory: string;
  state: AgyState;
  alive: boolean;
  created_at: string;
  last_output_at: number;
  last_prompt: string;
  last_slash_command: string;
  last_diff_stat: string;
  last_summary: string;
  pending_prompt: string;
  buffer_lines: number;
}

export interface AgyWorkspace {
  alias: string;
  path: string;
  exists: boolean;
  is_git: boolean;
  source: string;
}

export interface AgyListResponse {
  current_session_key: string | null;
  sessions: AgySession[];
  workspaces: AgyWorkspace[];
}

export interface AgyAttachResponse {
  session: AgySession;
  recent_output: string;
}

export interface AgyStatusResponse {
  session: AgySession;
  recent_output: string;
  last_diff: string;
  last_diff_stat: string;
}

export const agyApi = {
  list: () => api.get<AgyListResponse>("/agy/sessions"),
  workspaces: () => api.get<{ workspaces: AgyWorkspace[] }>("/agy/workspaces"),
  attach: (directory: string, alias?: string) =>
    api.post<AgyAttachResponse>("/agy/attach", { directory, alias }),
  input: (input: string, sessionKey?: string | null) =>
    api.post<{ session: AgySession; recent_output: string }>("/agy/input", {
      input,
      session_key: sessionKey,
    }),
  slash: (command: string, sessionKey?: string | null) =>
    api.post<{ session: AgySession; recent_output: string }>("/agy/slash", {
      command,
      session_key: sessionKey,
    }),
  status: (sessionKey: string) =>
    api.get<AgyStatusResponse>(`/agy/session/${encodeURIComponent(sessionKey)}`),
  close: (sessionKey: string) =>
    api.delete<{ closed: string }>(`/agy/session/${encodeURIComponent(sessionKey)}`),
};

export function agyStreamUrl(sessionKey: string): string {
  const isDesktop = window.location.protocol === "iris:";
  if (isDesktop) {
    return `ws://127.0.0.1:8000/api/agy/stream/${encodeURIComponent(sessionKey)}`;
  }
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/agy/stream/${encodeURIComponent(sessionKey)}`;
}
