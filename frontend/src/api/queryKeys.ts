/** Centralized TanStack Query keys — one factory, no ad-hoc key strings. */

import type { TaskFilters } from "@/api/endpoints";

export const qk = {
  me: ["me"] as const,

  tasks: (filters: TaskFilters = {}) => ["tasks", filters] as const,
  projects: () => ["projects"] as const,
  goals: (area?: string) => ["goals", area ?? "all"] as const,

  timeBlocks: (range?: Record<string, unknown>) => ["time-blocks", range] as const,
  calendarEvents: (range?: Record<string, unknown>) => ["calendar-events", range] as const,
  availability: (params?: Record<string, unknown>) => ["availability", params] as const,

  focus: () => ["focus"] as const,
  reviews: () => ["reviews"] as const,

  startup: () => ["startup"] as const,
  leads: (filters: { startup_id?: number; status?: string } = {}) => ["leads", filters] as const,
  outreach: (filters: { lead_id?: number } = {}) => ["outreach", filters] as const,
  experiments: (filters: { status?: string } = {}) => ["experiments", filters] as const,

  analyticsTime: (period: string) => ["analytics-time", period] as const,
  analyticsProductivity: (period: string) => ["analytics-productivity", period] as const,
  analyticsStartup: () => ["analytics-startup"] as const,
  startupTrends: (weeks: number) => ["startup-trends", weeks] as const,
  priorities: () => ["priorities"] as const,

  recommendation: (params?: Record<string, unknown>) => ["ai-recommendation", params] as const,
  planDay: () => ["ai-plan-day", "draft"] as const,

  // --- Intelligence (Phase 3) ---
  todayState: () => ["intelligence-today"] as const,
  signals: (params?: Record<string, unknown>) => ["intelligence-signals", params] as const,
  attention: () => ["intelligence-attention"] as const,
  decisions: (params?: Record<string, unknown>) => ["intelligence-decisions", params] as const,
  recurringSchedules: () => ["intelligence-recurring-schedules"] as const,

  // --- Chat & Assistant (Phase 4) ---
  chatConversations: () => ["chat-conversations"] as const,
  chatConversation: (id: number) => ["chat-conversation", id] as const,
};
