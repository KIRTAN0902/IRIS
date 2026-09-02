/**
 * Types mirroring the IRIS FastAPI Pydantic schemas (backend/app/schemas).
 * Kept in sync manually; the backend is the source of truth.
 */

// --- Enums (string unions) -----------------------------------------------------

export type LifeArea = "COLLEGE" | "INTERNSHIP" | "STARTUP" | "PERSONAL";
export type TaskPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type TaskStatus = "TODO" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED" | "BLOCKED";
export type EnergyLevel = "DEEP_WORK" | "NORMAL" | "LOW_ENERGY";
export type ProjectStatus = "PLANNED" | "ACTIVE" | "ON_HOLD" | "COMPLETED" | "CANCELLED";
export type GoalStatus = "ACTIVE" | "ACHIEVED" | "BEHIND" | "PAUSED" | "ABANDONED";
export type TimeBlockType = "FOCUS" | "BREAK" | "MEETING" | "PERSONAL" | "OTHER";
export type TimeBlockStatus = "SCHEDULED" | "IN_PROGRESS" | "DONE" | "CANCELLED";
export type EventSource = "INTERNAL" | "GOOGLE_CALENDAR" | "OTHER";
export type FocusStatus = "RUNNING" | "COMPLETED" | "PARTIAL" | "ABANDONED";
export type LeadStatus =
  | "LEAD"
  | "CONTACTED"
  | "REPLIED"
  | "INTERESTED"
  | "MEETING"
  | "CUSTOMER"
  | "NOT_INTERESTED"
  | "LOST";
export type OutreachType = "EMAIL" | "LINKEDIN" | "CALL" | "WHATSAPP" | "OTHER";
export type OutreachResult =
  | "SENT"
  | "NO_REPLY"
  | "REPLIED"
  | "MEETING_BOOKED"
  | "NOT_INTERESTED"
  | "CONVERTED";
export type ExperimentStatus = "PLANNED" | "RUNNING" | "COMPLETED" | "CANCELLED";
export type StartupStatus = "IDEA" | "BUILDING" | "LAUNCHED" | "GROWING" | "PAUSED" | "ARCHIVED";

export const LIFE_AREAS: LifeArea[] = ["COLLEGE", "INTERNSHIP", "STARTUP", "PERSONAL"];
export const TASK_PRIORITIES: TaskPriority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const TASK_STATUSES: TaskStatus[] = [
  "TODO",
  "IN_PROGRESS",
  "COMPLETED",
  "CANCELLED",
  "BLOCKED",
];
export const LEAD_STATUSES: LeadStatus[] = [
  "LEAD",
  "CONTACTED",
  "REPLIED",
  "INTERESTED",
  "MEETING",
  "CUSTOMER",
  "NOT_INTERESTED",
  "LOST",
];
export const OUTREACH_RESULTS: OutreachResult[] = [
  "SENT",
  "NO_REPLY",
  "REPLIED",
  "MEETING_BOOKED",
  "NOT_INTERESTED",
  "CONVERTED",
];

// --- Shared --------------------------------------------------------------------

/** ISO datetime strings as returned by the API. */
export type Iso = string;

export interface ErrorEnvelope {
  error: { code: string; message: string };
}

// --- Users ---------------------------------------------------------------------

export interface UserOut {
  id: number;
  name: string;
  email: string;
  timezone: string;
  created_at: Iso;
  updated_at: Iso;
}

// --- Tasks ---------------------------------------------------------------------

export interface TaskOut {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  area: LifeArea;
  priority: TaskPriority;
  status: TaskStatus;
  deadline: Iso | null;
  estimated_duration: number | null;
  actual_duration: number | null;
  energy_level: EnergyLevel | null;
  goal_id: number | null;
  project_id: number | null;
  created_at: Iso;
  updated_at: Iso;
  completed_at: Iso | null;
  is_overdue: boolean;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  area?: LifeArea;
  priority?: TaskPriority;
  status?: TaskStatus;
  deadline?: Iso | null;
  estimated_duration?: number | null;
  actual_duration?: number | null;
  energy_level?: EnergyLevel | null;
  goal_id?: number | null;
  project_id?: number | null;
}

export type TaskUpdate = Partial<Omit<TaskCreate, "title">> & { title?: string };

export interface TaskPriorityBreakdown {
  deadline_score: number;
  priority_score: number;
  strategic_score: number;
  goal_alignment_score: number;
  overdue_penalty: number;
  effort_fit_score: number;
  total: number;
}

export interface RankedTask {
  task: TaskOut;
  score: number;
  breakdown: TaskPriorityBreakdown;
}

// --- Projects ------------------------------------------------------------------

export interface ProjectOut {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  area: LifeArea;
  status: ProjectStatus;
  deadline: Iso | null;
  task_count?: number;
  created_at: Iso;
  updated_at: Iso;
}

// --- Goals ---------------------------------------------------------------------

export interface GoalOut {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  parent_goal_id: number | null;
  area: LifeArea;
  deadline: Iso | null;
  target_value: number | null;
  current_value: number;
  unit: string | null;
  status: GoalStatus;
  progress_fraction: number | null;
  created_at: Iso;
  updated_at: Iso;
}

export interface GoalTreeNode extends GoalOut {
  children: GoalTreeNode[];
}

export interface GoalCreate {
  name: string;
  description?: string | null;
  parent_goal_id?: number | null;
  area?: LifeArea;
  deadline?: Iso | null;
  target_value?: number | null;
  current_value?: number;
  unit?: string | null;
  status?: GoalStatus;
}

export type GoalUpdate = Partial<GoalCreate>;

// --- Schedule ------------------------------------------------------------------

export interface TimeBlockOut {
  id: number;
  user_id: number;
  task_id: number | null;
  start_time: Iso;
  end_time: Iso;
  type: TimeBlockType;
  status: TimeBlockStatus;
  notes: string | null;
  duration_minutes: number;
  created_at: Iso;
}

export interface TimeBlockCreate {
  task_id?: number | null;
  start_time: Iso;
  end_time: Iso;
  type?: TimeBlockType;
  notes?: string | null;
  allow_overlap?: boolean;
}

export interface CalendarEventOut {
  id: number;
  user_id: number;
  title: string;
  description: string | null;
  start_time: Iso;
  end_time: Iso;
  location: string | null;
  source: EventSource;
  external_id: string | null;
  duration_minutes: number;
  created_at: Iso;
}

export interface AvailabilityInterval {
  start: Iso;
  end: Iso;
  minutes: number;
}

export interface AvailabilityOut {
  window_start: Iso;
  window_end: Iso;
  total_free_minutes: number;
  free_intervals: AvailabilityInterval[];
  busy_intervals: AvailabilityInterval[];
}

// --- Focus ---------------------------------------------------------------------

export interface FocusSessionOut {
  id: number;
  user_id: number;
  task_id: number | null;
  started_at: Iso;
  ended_at: Iso | null;
  planned_duration: number | null;
  actual_duration: number | null;
  status: FocusStatus;
  notes: string | null;
}

// --- Reviews -------------------------------------------------------------------

export interface DailyReviewOut {
  id: number;
  user_id: number;
  date: string; // YYYY-MM-DD
  completed_tasks: number | null;
  incomplete_tasks: number | null;
  blockers: string | null;
  productivity_rating: number | null;
  notes: string | null;
  ai_summary: string | null;
  created_at: Iso;
  updated_at: Iso;
}

// --- Startup -------------------------------------------------------------------

export interface StartupOut {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  current_objective: string | null;
  status: StartupStatus;
  created_at: Iso;
  updated_at: Iso;
}

export interface LeadOut {
  id: number;
  startup_id: number;
  name: string;
  company: string | null;
  role: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  source: string | null;
  status: LeadStatus;
  notes: string | null;
  last_contacted: Iso | null;
  next_follow_up: Iso | null;
  created_at: Iso;
  updated_at: Iso;
}

export interface OutreachActivityOut {
  id: number;
  lead_id: number;
  startup_id: number;
  type: OutreachType;
  timestamp: Iso;
  message: string | null;
  result: OutreachResult | null;
  notes: string | null;
}

export interface ExperimentOut {
  id: number;
  startup_id: number;
  name: string;
  hypothesis: string | null;
  action: string | null;
  metric: string | null;
  target: string | null;
  result: string | null;
  conclusion: string | null;
  next_action: string | null;
  status: ExperimentStatus;
  started_at: Iso | null;
  ended_at: Iso | null;
}

// --- Analytics -----------------------------------------------------------------

export interface AreaMinutes {
  COLLEGE: number;
  INTERNSHIP: number;
  STARTUP: number;
  PERSONAL: number;
}

export interface TimeAnalytics {
  period: string;
  start: Iso;
  end: Iso;
  focused_minutes: AreaMinutes;
  scheduled_minutes: AreaMinutes;
  total_focused_minutes: number;
}

export interface ProductivityAnalytics {
  period: string;
  start: Iso;
  end: Iso;
  tasks_completed: number;
  tasks_created: number;
  tasks_overdue_open: number;
  completion_rate: number;
  planned_minutes: number;
  actual_minutes: number;
  average_task_duration_minutes: number;
  focus_sessions_count: number;
  focus_minutes: number;
}

export interface StartupPipelineCounts {
  leads_total: number;
  by_status: Partial<Record<LeadStatus, number>>;
}

export interface OutreachTotals {
  total: number;
  sent: number;
  replies: number;
  meetings_booked: number;
  conversions: number;
  reply_rate: number;
  meeting_rate: number;
  conversion_rate: number;
}

export interface StartupAnalytics {
  startup_id: number;
  startup_name: string;
  pipeline: StartupPipelineCounts;
  outreach: OutreachTotals;
  active_goals: number;
  goals_behind: string[];
  running_experiments: number;
  customers: number;
}

export interface WeeklyTrendPoint {
  week_start: string;
  new_leads: number;
  outreach_sent: number;
  replies: number;
  meetings: number;
  conversions: number;
}

export interface StartupTrends {
  startup_id: number;
  weeks: WeeklyTrendPoint[];
}

// --- AI ------------------------------------------------------------------------

export type AISource = "AI" | "DETERMINISTIC";

export interface AIMeta {
  source: AISource;
  ai_available: boolean;
}

export interface RecommendationOut extends AIMeta {
  recommendation_type: "TASK" | "BREAK" | "REST" | "STRATEGIC_NOTE";
  task_id: number | null;
  title: string;
  reason: string;
  duration_minutes: number | null;
  expected_outcome: string | null;
  confidence: number;
}

export interface PlanDayBlock {
  task_id: number | null;
  start: Iso;
  end: Iso;
  reason: string;
}

export interface PlanDayOut extends AIMeta {
  date: string;
  blocks: PlanDayBlock[];
  unscheduled_task_ids: number[];
  summary: string | null;
}

export interface DailyReviewAIOut extends AIMeta {
  summary: string;
  college_status: string | null;
  internship_status: string | null;
  startup_status: string | null;
  main_problem: string | null;
  recommendation_for_tomorrow: string | null;
}

export interface StartupAnalysisOut extends AIMeta {
  observation: string;
  possible_cause: string | null;
  recommendation: string | null;
  priority: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  data_evidence: Record<string, number> | null;
}

export interface AskIRISResponse extends AIMeta {
  answer: string;
  follow_ups: string[];
  conversation_id: number;
}

export interface ConversationRow {
  id: number;
  title: string;
  updated_at: Iso;
}

export interface MessageRow {
  id: number;
  role: "USER" | "ASSISTANT" | "SYSTEM" | "TOOL";
  content: string;
  created_at: Iso;
}

// --- Intelligence (Phase 3) ---------------------------------------------------

export type DecisionType = "MUST_DO" | "SHOULD_DO" | "COULD_DO" | "WAIT" | "ASK_USER";
export type DecisionFeedbackStatus =
  | "ACCEPTED"
  | "REJECTED"
  | "DEFERRED"
  | "COMPLETED"
  | "PARTIALLY_COMPLETED";

export interface AlternativeOption {
  title: string;
  area: string | null;
  trade_off_reason: string;
}

export interface DecisionStep {
  step_number: number;
  title: string;
  task_id: number | null;
  area: string | null;
  duration_minutes: number;
  reason: string;
  expected_outcome: string | null;
}

export interface DecisionRecommendationOut extends AIMeta {
  recommendation_type: "TASK" | "BREAK" | "REST" | "STRATEGIC_NOTE" | "SEQUENCE" | "ASK_USER";
  decision_type: DecisionType;
  decision: string | null;
  task_id: number | null;
  title: string;
  reason: string;
  duration_minutes: number | null;
  expected_outcome: string | null;
  confidence: number;
  opportunity_cost: string | null;
  evidence: string[];
  observed_facts?: string[];
  derived_insights?: string[];
  alternatives_considered?: AlternativeOption[];
  sequence?: DecisionStep[];
  missing_information?: string | null;
}

export interface CurrentWindowInfo {
  is_in_flexible_window: boolean;
  is_in_hard_constraint: boolean;
  active_block_name: string | null;
  active_block_type: string | null;
  minutes_remaining_in_block: number | null;
  minutes_until_next_hard_constraint: number | null;
  next_hard_constraint_name: string | null;
}

export interface SignalOut {
  id?: number | null;
  domain: string;
  signal_type: string;
  source: string;
  provenance: string;
  importance: number;
  urgency: number;
  title: string;
  summary: string | null;
  payload?: Record<string, unknown> | null;
  timestamp: Iso;
  expires_at?: Iso | null;
  is_active: boolean;
}

export interface AttentionItemOut {
  id: string;
  type: string;
  domain: string;
  title: string;
  description: string;
  score: number;
  urgency: number;
  impact: number;
  provenance: string;
  deadline: Iso | null;
  suggested_action: string | null;
  source_id: number | string | null;
}

export interface DecisionHistoryOut {
  id: number;
  user_id: number;
  task_id: number | null;
  recommendation_type: string;
  decision_type: string;
  title: string;
  reason: string | null;
  expected_outcome: string | null;
  duration_minutes: number | null;
  confidence: number | null;
  source: string;
  opportunity_cost: string | null;
  evidence: string[] | null;
  feedback: string | null;
  feedback_notes: string | null;
  feedback_at: Iso | null;
  created_at: Iso;
}

export interface DecisionFeedbackIn {
  recommendation_id: number;
  feedback: DecisionFeedbackStatus | string;
  notes?: string | null;
}

export interface DecisionFeedbackOut {
  id: number;
  recommendation_id: number;
  feedback: string;
  feedback_notes: string | null;
  feedback_at: Iso;
  message: string;
}

export interface RecurringScheduleIn {
  name: string;
  type?: string;
  days_of_week?: string;
  start_time: string;
  end_time: string;
  is_hard_constraint?: boolean;
  status?: string;
  extra_data?: Record<string, unknown> | null;
}

export interface RecurringScheduleUpdate {
  name?: string | null;
  type?: string | null;
  days_of_week?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  is_hard_constraint?: boolean | null;
  status?: string | null;
  extra_data?: Record<string, unknown> | null;
}

export interface RecurringScheduleOut {
  id: number;
  user_id: number;
  name: string;
  type: string;
  days_of_week: string;
  start_time: string;
  end_time: string;
  is_hard_constraint: boolean;
  status: string;
  extra_data?: Record<string, unknown> | null;
  created_at: Iso;
  updated_at: Iso;
}

export interface TodayStateOut {
  date: string;
  current_time: string;
  user_timezone: string;
  available_minutes_today: number;
  current_window: CurrentWindowInfo;
  fixed_commitments: Array<{
    name: string;
    start: string;
    end: string;
    type?: string;
    is_hard_constraint?: boolean;
  }>;
  flexible_windows: Array<{
    start: string;
    end: string;
    minutes?: number;
  }>;
  urgent_obligations: Array<{
    title: string;
    deadline?: string;
    urgency?: string | number;
    area?: string;
    type?: string;
  }>;
  tasks: Array<Record<string, unknown>>;
  goals: Array<Record<string, unknown>>;
  startup?: Record<string, unknown> | null;
  current_recommendation?: Record<string, unknown> | null;
  attention_items: AttentionItemOut[];
  domain_signals: Record<string, SignalOut[]>;
  recent_decisions: Array<{
    id: number;
    title: string;
    decision_type: string;
    feedback: string | null;
    created_at: Iso;
  }>;
}

// --- Chat & Assistant (Phase 4) -----------------------------------------------

export interface ActionExecuted {
  tool_name: string;
  success: boolean;
  summary: string | null;
  error?: string | null;
  data?: unknown;
}

export interface ChatMessageIn {
  content: string;
}

export interface ChatMessageOut {
  id: number;
  conversation_id: number;
  role: "USER" | "ASSISTANT" | "SYSTEM" | "TOOL";
  content: string;
  actions_taken: ActionExecuted[];
  evidence: string[];
  recommended_action: {
    task_id?: number | null;
    title?: string;
    duration_minutes?: number | null;
    decision_type?: string;
    reason?: string;
  } | null;
  source: AISource | string;
  created_at: Iso;
}

export interface ConversationOut {
  id: number;
  title: string;
  created_at: Iso;
  updated_at: Iso;
}

export interface ConversationDetailOut {
  id: number;
  title: string;
  created_at: Iso;
  updated_at: Iso;
  messages: ChatMessageOut[];
}
