/**
 * Query + mutation hooks. All server access flows through here so caching,
 * invalidation, and error handling stay in one place.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  aiApi,
  analyticsApi,
  assistantApi,
  chatApi,
  financeApi,
  habitsApi,
  workoutsApi,
  focusApi,
  goalsApi,
  intelligenceApi,
  memoriesApi,
  projectsApi,
  reviewsApi,
  scheduleApi,
  startupApi,
  tasksApi,
  usersApi,
  type TaskFilters,
} from "@/api/endpoints";
import type {
  AIMemoryIn,
  AIMemoryUpdate,
  BillIn,
  HabitIn,
  HabitOut,
  ExerciseIn,
  WorkoutIn,
  WorkoutOut,
  SavingsGoalIn,
  TransactionIn,
  TransactionKind,
} from "@/types/api";

import { qk } from "@/api/queryKeys";
import { useFocusStore } from "@/stores";

// --- Users ---------------------------------------------------------------------

export const useMe = () => useQuery({ queryKey: qk.me, queryFn: usersApi.me, staleTime: 5 * 60_000 });

// --- Tasks ---------------------------------------------------------------------

export const useTasks = (filters: TaskFilters = {}) =>
  useQuery({ queryKey: qk.tasks(filters), queryFn: () => tasksApi.list(filters) });

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

export const useCreateTask = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: tasksApi.create, onSuccess: invalidate });
};

export const useUpdateTask = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Parameters<typeof tasksApi.update>[1] }) =>
      tasksApi.update(id, patch),
    onSuccess: invalidate,
  });
};

export const useCompleteTask = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, actualDuration }: { id: number; actualDuration?: number }) =>
      tasksApi.complete(id, actualDuration),
    onSuccess: invalidate,
  });
};

export const useDeleteTask = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (id: number) => tasksApi.remove(id), onSuccess: invalidate });
};

// --- Projects / Goals -------------------------------------------------------------

export const useProjects = () => useQuery({ queryKey: qk.projects(), queryFn: () => projectsApi.list() });

export interface GoalNode {
  id: number;
  name: string;
  description?: string | null;
  area: string;
  status: string;
  parent_goal_id: number | null;
  target_value: number | null;
  current_value: number;
  unit: string | null;
  deadline: string | null;
  progress_fraction: number | null;
  children: GoalNode[];
}

export const useGoals = (area?: string) =>
  useQuery({
    queryKey: qk.goals(area),
    queryFn: async () => {
      const rows = await goalsApi.list({ area, tree: true });
      return rows as unknown as GoalNode[];
    },
  });

export const useCreateGoal = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: goalsApi.create, onSuccess: invalidate });
};

export const useUpdateGoal = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      goalsApi.update(id, patch),
    onSuccess: invalidate,
  });
};

// --- Schedule -----------------------------------------------------------------------

export const useTimeBlocks = (range?: { start?: string; end?: string }) =>
  useQuery({ queryKey: qk.timeBlocks(range), queryFn: () => scheduleApi.timeBlocks(range) });

export const useCalendarEvents = (range?: { start?: string; end?: string }) =>
  useQuery({ queryKey: qk.calendarEvents(range), queryFn: () => scheduleApi.calendarEvents(range) });

export const useAvailability = (params?: { window_start?: string; window_end?: string; hours_ahead?: number }) =>
  useQuery({
    queryKey: qk.availability(params),
    queryFn: () => scheduleApi.availability(params ?? {}),
  });

export const useCreateTimeBlock = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: scheduleApi.createTimeBlock, onSuccess: invalidate });
};

// --- Focus ----------------------------------------------------------------------------

export function useFocusSessions() {
  const setRunning = useFocusStore((s) => s.setRunning);
  return useQuery({
    queryKey: qk.focus(),
    queryFn: async () => {
      const sessions = await focusApi.list();
      setRunning(sessions.find((s) => s.status === "RUNNING") ?? null);
      return sessions;
    },
  });
}

export const useStartFocus = () => {
  const setRunning = useFocusStore((s) => s.setRunning);
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: focusApi.start,
    onSuccess: (session) => {
      setRunning(session.status === "RUNNING" ? session : null);
      invalidate();
    },
  });
};

export const useCompleteFocus = () => {
  const setRunning = useFocusStore((s) => s.setRunning);
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status?: "COMPLETED" | "PARTIAL" | "ABANDONED" }) =>
      focusApi.complete(id, status ?? "COMPLETED"),
    onSuccess: () => {
      setRunning(null);
      invalidate();
    },
  });
};

// --- Reviews ---------------------------------------------------------------------------

export const useSubmitReview = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: reviewsApi.submit, onSuccess: invalidate });
};

// --- Startup ------------------------------------------------------------------------------

export const useStartup = () =>
  useQuery({ queryKey: qk.startup(), queryFn: startupApi.list, select: (rows) => rows[0] ?? null });

export const useLeads = (filters: { startup_id?: number; status?: string } = {}) =>
  useQuery({ queryKey: qk.leads(filters), queryFn: () => startupApi.leads(filters) });

export const useOutreach = (filters: { lead_id?: number; startup_id?: number } = {}) =>
  useQuery({ queryKey: ["outreach", filters] as const, queryFn: () => startupApi.outreach(filters) });

export const useExperiments = (filters: { status?: string } = {}) =>
  useQuery({ queryKey: qk.experiments(filters), queryFn: () => startupApi.experiments(filters) });

export const useUpdateExperiment = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      startupApi.updateExperiment(id, patch),
    onSuccess: invalidate,
  });
};

export const useLogOutreach = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: startupApi.logOutreach, onSuccess: invalidate });
};

export const useCreateLead = () => {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: startupApi.createLead, onSuccess: invalidate });
};

export const useUpdateLead = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) =>
      startupApi.updateLead(id, patch),
    onSuccess: invalidate,
  });
};

// --- Analytics -------------------------------------------------------------------------------

export const useTimeAnalytics = (period: "today" | "week" | "month" = "today") =>
  useQuery({ queryKey: qk.analyticsTime(period), queryFn: () => analyticsApi.time(period) });

export const useProductivity = (period: "today" | "week" | "month" = "week") =>
  useQuery({ queryKey: qk.analyticsProductivity(period), queryFn: () => analyticsApi.productivity(period) });

export const useStartupAnalytics = () =>
  useQuery({ queryKey: qk.analyticsStartup(), queryFn: analyticsApi.startup });

export const useStartupTrends = (weeks = 8) =>
  useQuery({ queryKey: qk.startupTrends(weeks), queryFn: () => analyticsApi.startupTrends(weeks) });

export const usePriorities = () =>
  useQuery({ queryKey: qk.priorities(), queryFn: () => analyticsApi.priorities() });

// --- AI & Intelligence (Phase 3) ------------------------------------------------

export const useRecommendation = (params?: { available_minutes?: number; current_energy?: string; use_ai?: boolean }) =>
  useQuery({
    queryKey: qk.recommendation(params),
    queryFn: () => intelligenceApi.recommend(params),
    staleTime: 60_000,
    refetchInterval: 10 * 60_000,
  });

/** Imperative AI actions (plan-day draft, ask) are mutations, not queries. */
export const usePlanDay = () =>
  useMutation({ mutationFn: (planDate?: string) => aiApi.planDay(planDate) });

export const useAskIRIS = () =>
  useMutation({
    mutationFn: (vars: { question: string; conversation_id?: number | null }) =>
      aiApi.ask(vars.question, vars.conversation_id ?? undefined),
  });

export const useAIStatus = () =>
  useQuery({
    queryKey: qk.aiStatus(),
    queryFn: aiApi.status,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

// --- Intelligence Today & Attention ---

export const useTodayState = () =>
  useQuery({
    queryKey: qk.todayState(),
    queryFn: intelligenceApi.today,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

export const useSignals = (params: { domain?: string; min_importance?: number; active_only?: boolean; limit?: number } = {}) =>
  useQuery({
    queryKey: qk.signals(params),
    queryFn: () => intelligenceApi.signals(params),
    staleTime: 30_000,
  });

export const useAttentionItems = () =>
  useQuery({
    queryKey: qk.attention(),
    queryFn: intelligenceApi.attention,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

export const useDecisionHistory = (params: { decision_type?: string; feedback?: string; limit?: number } = {}) =>
  useQuery({
    queryKey: qk.decisions(params),
    queryFn: () => intelligenceApi.decisions(params),
    staleTime: 30_000,
  });

export const useDecisionFeedback = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: intelligenceApi.feedback,
    onSuccess: invalidate,
  });
};

export const useRecurringSchedules = () =>
  useQuery({
    queryKey: qk.recurringSchedules(),
    queryFn: intelligenceApi.recurringSchedules,
    staleTime: 60_000,
  });

export const useCreateRecurringSchedule = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: intelligenceApi.createRecurringSchedule,
    onSuccess: invalidate,
  });
};

export const useUpdateRecurringSchedule = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Parameters<typeof intelligenceApi.updateRecurringSchedule>[1] }) =>
      intelligenceApi.updateRecurringSchedule(id, payload),
    onSuccess: invalidate,
  });
};

export const useDeleteRecurringSchedule = () => {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (id: number) => intelligenceApi.deleteRecurringSchedule(id),
    onSuccess: invalidate,
  });
};

// --- Chat & Assistant (Phase 4) -----------------------------------------------

export const useConversations = (limit: number = 50) =>
  useQuery({
    queryKey: qk.chatConversations(),
    queryFn: () => chatApi.conversations(limit),
  });

export const useConversation = (id: number | null) =>
  useQuery({
    queryKey: id ? qk.chatConversation(id) : ["chat-conversation", "none"],
    queryFn: () => (id ? chatApi.getConversation(id) : null),
    enabled: Boolean(id),
  });

export const useCreateConversation = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => chatApi.createConversation(title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.chatConversations() });
    },
  });
};

export const useSendMessage = () => {
  const qc = useQueryClient();
  return useMutation({
    // Reply first; memory is updated by a follow-up call so it never delays the answer.
    mutationFn: ({ conversationId, content, voice }: { conversationId: number; content: string; voice?: boolean }) =>
      chatApi.sendMessage(conversationId, { content, voice, defer_memory: true }),
    onSuccess: (data, variables) => {
      chatApi
        .remember(data.id)
        .then(() => {
          qc.invalidateQueries({ queryKey: qk.chatConversation(variables.conversationId) });
          qc.invalidateQueries({ queryKey: qk.chatConversations() });
          qc.invalidateQueries({ queryKey: ["memories"] });
        })
        .catch(() => {});
      qc.invalidateQueries({ queryKey: qk.chatConversation(variables.conversationId) });
      qc.invalidateQueries({ queryKey: qk.chatConversations() });
      // Invalidate live IRIS state as actions may have mutated tasks/schedule/goals
      qc.invalidateQueries({ queryKey: qk.todayState() });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: qk.attention() });
      qc.invalidateQueries({ queryKey: qk.decisions() });
      qc.invalidateQueries({ queryKey: ["time-blocks"] });
      qc.invalidateQueries({ queryKey: ["goals"] });
      qc.invalidateQueries({ queryKey: ["ai-recommendation"] });
      qc.invalidateQueries({ queryKey: qk.priorities() });
      qc.invalidateQueries({ queryKey: ["availability"] });
      qc.invalidateQueries({ queryKey: ["intelligence-signals"] });
      qc.invalidateQueries({ queryKey: qk.startup() });
      qc.invalidateQueries({ queryKey: qk.recurringSchedules() });
      qc.invalidateQueries({ queryKey: ["memories"] });
      qc.invalidateQueries({ queryKey: ["finance"] });
      qc.invalidateQueries({ queryKey: ["habits"] });
      qc.invalidateQueries({ queryKey: ["workouts"] });
      qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
};

export const useDeleteConversation = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => chatApi.deleteConversation(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.chatConversations() });
    },
  });
};

// --- Assistant awareness -----------------------------------------------------

export const useBriefing = () =>
  useQuery({
    queryKey: qk.briefing(),
    queryFn: () => assistantApi.briefing(false),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });

// --- Memories & Context Layer ------------------------------------------------

export const useMemories = (params?: { category?: string; search?: string; limit?: number }) =>
  useQuery({
    queryKey: qk.memories(params),
    queryFn: () => memoriesApi.list(params),
  });

export const useCreateMemory = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AIMemoryIn) => memoriesApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
    },
  });
};

export const useUpdateMemory = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: AIMemoryUpdate }) =>
      memoriesApi.update(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
    },
  });
};

export const useDeleteMemory = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => memoriesApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
    },
  });
};

// --- Personal finance ------------------------------------------------------------

const financeKey = ["finance"] as const;

export const useFinanceSummary = (month?: string) =>
  useQuery({ queryKey: [...financeKey, "summary", month ?? "current"], queryFn: () => financeApi.summary(month) });

export const useFinanceCategories = () =>
  useQuery({ queryKey: [...financeKey, "categories"], queryFn: financeApi.categories, staleTime: 5 * 60_000 });

export const useTransactions = (filters: { month?: string; kind?: TransactionKind; q?: string }) =>
  useQuery({ queryKey: [...financeKey, "transactions", filters], queryFn: () => financeApi.transactions(filters) });

export const useBills = () => useQuery({ queryKey: [...financeKey, "bills"], queryFn: financeApi.bills });

export const useSavingsGoals = () => useQuery({ queryKey: [...financeKey, "savings"], queryFn: financeApi.savings });

/** Any money change refreshes every finance view. */
function useFinanceMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: financeKey }) });
}

export const useSaveTransaction = () =>
  useFinanceMutation(({ id, body }: { id?: number; body: TransactionIn }) =>
    id ? financeApi.updateTransaction(id, body) : financeApi.createTransaction(body),
  );
export const useDeleteTransaction = () => useFinanceMutation((id: number) => financeApi.deleteTransaction(id));
export const useSetBudget = () =>
  useFinanceMutation(({ category, limit }: { category: string; limit: number }) => financeApi.setBudget(category, limit));
export const useDeleteBudget = () => useFinanceMutation((id: number) => financeApi.deleteBudget(id));
export const useSaveBill = () =>
  useFinanceMutation(({ id, body }: { id?: number; body: BillIn }) =>
    id ? financeApi.updateBill(id, body) : financeApi.createBill(body),
  );
export const usePayBill = () =>
  useFinanceMutation(({ id, amount }: { id: number; amount?: number }) =>
    financeApi.payBill(id, amount ? { amount } : {}),
  );
export const useDeleteBill = () => useFinanceMutation((id: number) => financeApi.deleteBill(id));
export const useSaveSavingsGoal = () =>
  useFinanceMutation(({ id, body }: { id?: number; body: SavingsGoalIn }) =>
    id ? financeApi.updateSavings(id, body) : financeApi.createSavings(body),
  );
export const useAddToSavings = () =>
  useFinanceMutation(({ id, amount }: { id: number; amount: number }) => financeApi.addToSavings(id, amount));
export const useDeleteSavingsGoal = () => useFinanceMutation((id: number) => financeApi.deleteSavings(id));

// --- Today & routines ------------------------------------------------------------

/** The live situation (now/next, today's schedule, tasks); refreshed every minute. */
export const useSituation = () =>
  useQuery({ queryKey: ["assistant", "situation"], queryFn: assistantApi.situation, refetchInterval: 60_000 });

export const useHabits = () => useQuery({ queryKey: ["habits"], queryFn: habitsApi.list });

function useHabitMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["habits"] });
      qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
}

export const useSaveHabit = () =>
  useHabitMutation(({ id, body }: { id?: number; body: HabitIn }) => (id ? habitsApi.update(id, body) : habitsApi.create(body)));
export const useDeleteHabit = () => useHabitMutation((id: number) => habitsApi.remove(id));

/** Tick a routine; the list updates instantly and rolls back if the request fails. */
export const useCheckHabit = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => habitsApi.check(id, done),
    onMutate: async ({ id, done }) => {
      await qc.cancelQueries({ queryKey: ["habits"] });
      const before = qc.getQueryData<HabitOut[]>(["habits"]);
      qc.setQueryData<HabitOut[]>(["habits"], (list) =>
        list?.map((h) =>
          h.id === id
            ? {
                ...h,
                done_today: done,
                streak: Math.max(0, h.streak + (done && !h.done_today ? 1 : !done && h.done_today ? -1 : 0)),
                last_7: h.last_7.map((d, i) => (i === h.last_7.length - 1 ? { ...d, done } : d)),
              }
            : h,
        ),
      );
      return { before };
    },
    onError: (_err, _vars, ctx) => ctx?.before && qc.setQueryData(["habits"], ctx.before),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["habits"] });
      qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
};

// --- Workouts ----------------------------------------------------------------------

export const useWorkouts = () => useQuery({ queryKey: ["workouts"], queryFn: workoutsApi.list });

function useWorkoutMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workouts"] });
      qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
}

export const useSaveWorkout = () =>
  useWorkoutMutation(({ id, body }: { id?: number; body: WorkoutIn }) =>
    id ? workoutsApi.update(id, body) : workoutsApi.create(body),
  );
export const useDeleteWorkout = () => useWorkoutMutation((id: number) => workoutsApi.remove(id));
export const useUpdateExercise = () =>
  useWorkoutMutation(({ id, exerciseId, body }: { id: number; exerciseId: number; body: Partial<ExerciseIn> }) =>
    workoutsApi.updateExercise(id, exerciseId, body),
  );

/** Tick an exercise mid-workout: instant, rolled back if the request fails. */
export const useCheckExercise = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exerciseId, done }: { id: number; exerciseId: number; done: boolean }) =>
      workoutsApi.check(id, exerciseId, done),
    onMutate: async ({ id, exerciseId, done }) => {
      await qc.cancelQueries({ queryKey: ["workouts"] });
      const before = qc.getQueryData<WorkoutOut[]>(["workouts"]);
      qc.setQueryData<WorkoutOut[]>(["workouts"], (list) =>
        list?.map((w) => {
          if (w.id !== id) return w;
          const exercises = w.exercises.map((e) => (e.id === exerciseId ? { ...e, done_today: done } : e));
          return { ...w, exercises, done_count: exercises.filter((e) => e.done_today).length };
        }),
      );
      return { before };
    },
    onError: (_e, _v, ctx) => ctx?.before && qc.setQueryData(["workouts"], ctx.before),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["workouts"] });
      qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
};
