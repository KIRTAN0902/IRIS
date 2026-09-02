/**
 * Endpoint functions grouped by backend module. One function per API call;
 * components and hooks import from here only.
 */

import { api } from "@/api/client";
import type {
  AskIRISResponse,
  AttentionItemOut,
  AvailabilityOut,
  CalendarEventOut,
  ConversationRow,
  DailyReviewAIOut,
  DailyReviewOut,
  DecisionFeedbackIn,
  DecisionFeedbackOut,
  DecisionHistoryOut,
  DecisionRecommendationOut,
  ExperimentOut,
  FocusSessionOut,
  GoalCreate,
  GoalOut,
  GoalTreeNode,
  GoalUpdate,
  LeadOut,
  MessageRow,
  OutreachActivityOut,
  PlanDayOut,
  ProductivityAnalytics,
  ProjectOut,
  RecommendationOut,
  RecurringScheduleIn,
  RecurringScheduleOut,
  RecurringScheduleUpdate,
  SignalOut,
  StartupAnalysisOut,
  StartupAnalytics,
  StartupOut,
  StartupTrends,
  ChatMessageIn,
  ChatMessageOut,
  ConversationDetailOut,
  ConversationOut,
  TaskCreate,
  TaskOut,
  TaskUpdate,
  TimeAnalytics,
  TimeBlockCreate,
  TimeBlockOut,
  TodayStateOut,
  UserOut,
} from "@/types/api";

// --- Users ---------------------------------------------------------------------

export const usersApi = {
  me: () => api.get<UserOut>("/users/me"),
  updateMe: (patch: Partial<Pick<UserOut, "name" | "timezone">>) =>
    api.patch<UserOut>("/users/me", patch),
};

// --- Tasks ---------------------------------------------------------------------

export interface TaskFilters {
  area?: string;
  status?: string;
  priority?: string;
  goal_id?: number;
  project_id?: number;
  deadline_before?: string;
  deadline_after?: string;
  overdue_only?: boolean;
  open_only?: boolean;
  limit?: number;
  offset?: number;
}

export const tasksApi = {
  list: (filters: TaskFilters = {}) => api.get<TaskOut[]>("/tasks", { ...filters }),
  create: (data: TaskCreate) => api.post<TaskOut>("/tasks", data),
  get: (id: number) => api.get<TaskOut>(`/tasks/${id}`),
  update: (id: number, patch: TaskUpdate) => api.patch<TaskOut>(`/tasks/${id}`, patch),
  complete: (id: number, actualDuration?: number) =>
    api.post<TaskOut>(`/tasks/${id}/complete`, actualDuration != null ? { actual_duration: actualDuration } : undefined),
  remove: (id: number) => api.delete<void>(`/tasks/${id}`),
};

// --- Projects --------------------------------------------------------------------

export const projectsApi = {
  list: (area?: string) => api.get<ProjectOut[]>("/projects", area ? { area } : undefined),
  create: (data: { name: string; description?: string | null; area?: string; deadline?: string | null }) =>
    api.post<ProjectOut>("/projects", data),
};

// --- Goals -----------------------------------------------------------------------

export const goalsApi = {
  list: (params: { area?: string; tree?: boolean } = {}) =>
    api.get<(GoalOut | GoalTreeNode)[]>("/goals", params as Record<string, string | number | boolean>),
  create: (data: GoalCreate) => api.post<GoalTreeNode>("/goals", data),
  update: (id: number, patch: GoalUpdate) => api.patch<GoalOut>(`/goals/${id}`, patch),
  remove: (id: number) => api.delete<void>(`/goals/${id}`),
};

// --- Schedule ----------------------------------------------------------------------

export const scheduleApi = {
  timeBlocks: (params: { start?: string; end?: string; task_id?: number } = {}) =>
    api.get<TimeBlockOut[]>("/time-blocks", params),
  createTimeBlock: (data: TimeBlockCreate) => api.post<TimeBlockOut>("/time-blocks", data),
  deleteTimeBlock: (id: number) => api.delete<void>(`/time-blocks/${id}`),
  calendarEvents: (params: { start?: string; end?: string } = {}) =>
    api.get<CalendarEventOut[]>("/calendar-events", params),
  availability: (params: { window_start?: string; window_end?: string; hours_ahead?: number } = {}) =>
    api.get<AvailabilityOut>("/availability", params),
};

// --- Focus -------------------------------------------------------------------------

export const focusApi = {
  start: (data: { task_id?: number | null; planned_duration?: number | null; notes?: string | null } = {}) =>
    api.post<FocusSessionOut>("/focus/start", data),
  /** Complete a session; status PARTIAL ends it early without full credit. */
  complete: (id: number, status: "COMPLETED" | "PARTIAL" | "ABANDONED" = "COMPLETED", notes?: string) =>
    api.post<FocusSessionOut>(`/focus/${id}/complete`, { status, ...(notes ? { notes } : {}) }),
  list: () => api.get<FocusSessionOut[]>("/focus"),
};

// --- Reviews -------------------------------------------------------------------------

export const reviewsApi = {
  list: () => api.get<DailyReviewOut[]>("/reviews"),
  submit: (data: { date: string; productivity_rating?: number; notes?: string; blockers?: string }) =>
    api.post<DailyReviewOut>("/reviews", data),
};

// --- Startup ---------------------------------------------------------------------------

export const startupApi = {
  list: () => api.get<StartupOut[]>("/startup"),
  leads: (params: { startup_id?: number; status?: string } = {}) => api.get<LeadOut[]>("/leads", params),
  createLead: (data: Partial<LeadOut> & { startup_id: number; name: string }) =>
    api.post<LeadOut>("/leads", data),
  updateLead: (id: number, patch: Partial<LeadOut>) => api.patch<LeadOut>(`/leads/${id}`, patch),
  logOutreach: (data: {
    lead_id: number;
    startup_id: number;
    type?: string;
    result?: string;
    message?: string | null;
    notes?: string | null;
  }) => api.post<OutreachActivityOut>("/outreach", data),
  outreach: (params: { lead_id?: number; startup_id?: number } = {}) =>
    api.get<OutreachActivityOut[]>("/outreach", params),
  experiments: (params: { startup_id?: number; status?: string } = {}) =>
    api.get<ExperimentOut[]>("/experiments", params),
  createExperiment: (data: Record<string, unknown>) => api.post<ExperimentOut>("/experiments", data),
  updateExperiment: (id: number, patch: Partial<ExperimentOut>) =>
    api.patch<ExperimentOut>(`/experiments/${id}`, patch),
};

// --- Analytics --------------------------------------------------------------------------

export interface CustomRange {
  start?: string;
  end?: string;
}

export const analyticsApi = {
  time: (period: "today" | "week" | "month" | "custom" = "today", range?: CustomRange) =>
    api.get<TimeAnalytics>("/analytics/time", { period, ...range }),
  productivity: (period: "today" | "week" | "month" | "custom" = "week", range?: CustomRange) =>
    api.get<ProductivityAnalytics>("/analytics/productivity", { period, ...range }),
  startup: () => api.get<StartupAnalytics>("/analytics/startup"),
  startupTrends: (weeks = 8) => api.get<StartupTrends>("/analytics/startup/trends", { weeks }),
  priorities: (availableMinutes?: number) =>
    api.get<RankedTasksResponse[]>(
      "/analytics/priorities",
      availableMinutes ? { available_minutes: availableMinutes } : undefined,
    ),
};

export interface RankedTasksResponse {
  task: TaskOut;
  score: number;
  breakdown: {
    deadline_score: number;
    priority_score: number;
    strategic_score: number;
    goal_alignment_score: number;
    overdue_penalty: number;
    effort_fit_score: number;
    total: number;
  };
}

// --- AI -----------------------------------------------------------------------------------

export const aiApi = {
  recommend: (availableMinutes?: number) =>
    api.post<RecommendationOut>(
      "/ai/recommend",
      undefined,
      availableMinutes ? { available_minutes: availableMinutes } : undefined,
    ),
  planDay: (planDate?: string) =>
    api.post<PlanDayOut>("/ai/plan-day", undefined, planDate ? { plan_date: planDate } : undefined),
  dailyReview: (reviewDate?: string) =>
    api.post<DailyReviewAIOut>(
      "/ai/daily-review",
      undefined,
      reviewDate ? { review_date: reviewDate } : undefined,
    ),
  startupAnalysis: () => api.post<StartupAnalysisOut>("/ai/startup-analysis"),
  ask: (question: string, conversationId?: number) =>
    api.post<AskIRISResponse>("/ai/ask", { question, conversation_id: conversationId ?? null }),
  conversations: () => api.get<ConversationRow[]>("/ai/conversations"),
  messages: (conversationId: number) =>
    api.get<MessageRow[]>(`/ai/conversations/${conversationId}/messages`),
};

// --- Intelligence (Phase 3) ---------------------------------------------------------------

export const intelligenceApi = {
  today: () => api.get<TodayStateOut>("/intelligence/today"),
  signals: (params: { domain?: string; min_importance?: number; active_only?: boolean; limit?: number } = {}) =>
    api.get<SignalOut[]>("/intelligence/signals", params),
  attention: () => api.get<AttentionItemOut[]>("/intelligence/attention"),
  decisions: (params: { decision_type?: string; feedback?: string; limit?: number } = {}) =>
    api.get<DecisionHistoryOut[]>("/intelligence/decisions", params),
  feedback: (payload: DecisionFeedbackIn) =>
    api.post<DecisionFeedbackOut>("/intelligence/feedback", payload),
  recommend: (params: { available_minutes?: number; current_energy?: string; use_ai?: boolean } = {}) =>
    api.post<DecisionRecommendationOut>("/intelligence/recommend", undefined, params),
  recurringSchedules: () =>
    api.get<RecurringScheduleOut[]>("/intelligence/recurring-schedules"),
  createRecurringSchedule: (payload: RecurringScheduleIn) =>
    api.post<RecurringScheduleOut>("/intelligence/recurring-schedules", payload),
  updateRecurringSchedule: (id: number, payload: RecurringScheduleUpdate) =>
    api.patch<RecurringScheduleOut>(`/intelligence/recurring-schedules/${id}`, payload),
  deleteRecurringSchedule: (id: number) =>
    api.delete<void>(`/intelligence/recurring-schedules/${id}`),
};

// --- Chat & Action Layer (Phase 4) --------------------------------------------

export const chatApi = {
  conversations: (limit: number = 50) =>
    api.get<ConversationOut[]>("/chat/conversations", { limit }),
  createConversation: (title?: string) =>
    api.post<ConversationOut>("/chat/conversations", undefined, { title }),
  getConversation: (conversationId: number) =>
    api.get<ConversationDetailOut>(`/chat/conversations/${conversationId}`),
  sendMessage: (conversationId: number, payload: ChatMessageIn) =>
    api.post<ChatMessageOut>(`/chat/conversations/${conversationId}/messages`, payload),
  deleteConversation: (conversationId: number) =>
    api.delete<void>(`/chat/conversations/${conversationId}`),
};

