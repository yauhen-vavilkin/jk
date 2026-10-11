// One place the panel asks the server for something, and one place it tells the
// server what the user did.
import {
  keepPreviousData,
  useMutation,
  useMutationState,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { api } from "./client";
import type {
  Attention,
  Flow,
  JenkinsJob,
  JenkinsStatus,
  ParamDefinition,
  Preset,
  PresetUsage,
  RepairRequest,
  Review,
  ReviewScope,
  SavedFlow,
  StepCreate,
} from "./types";

export type RunValues = Record<string, Record<string, string>>;

export const keys = {
  presets: ["presets"] as const,
  savedFlows: ["saved-flows"] as const,
  flows: ["flows"] as const,
  jenkinsJobs: (q: string) => ["jenkins-jobs", q] as const,
  jenkinsStatus: ["jenkins-status"] as const,
  definitions: (jobPath: string) => ["definitions", jobPath] as const,
  presetUsage: (presetId: string) => ["preset-usage", presetId] as const,
  saveFlow: ["save-flow"] as const,
};

export function usePresets() {
  return useQuery({ queryKey: keys.presets, queryFn: () => api.get<Preset[]>("/presets") });
}

export function useSavedFlows() {
  return useQuery({
    queryKey: keys.savedFlows,
    queryFn: () => api.get<SavedFlow[]>("/saved-flows"),
    // A saved flow deleted in another tab sends no event, and Save compares with
    // this list: coming back to the tab reads it again, however fresh it looks.
    refetchOnWindowFocus: "always",
  });
}

export function useFlows() {
  return useQuery({ queryKey: keys.flows, queryFn: () => api.get<Flow[]>("/flows") });
}

export function useJenkinsJobs(query: string) {
  return useQuery({
    queryKey: keys.jenkinsJobs(query),
    queryFn: () => api.get<JenkinsJob[]>(`/jenkins/jobs?q=${encodeURIComponent(query)}`),
    placeholderData: keepPreviousData,
  });
}

export function useJenkinsStatus() {
  return useQuery({
    queryKey: keys.jenkinsStatus,
    queryFn: () => api.get<JenkinsStatus>("/jenkins/status"),
    refetchInterval: 60_000,
  });
}

/** Ask Jenkins again whether it accepts the token; the answer replaces the status. */
export function useCheckToken() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<JenkinsStatus>("/jenkins/check"),
    onSuccess: (status) => client.setQueryData(keys.jenkinsStatus, status),
  });
}

export function useDefinitions(jobPath: string | null) {
  return useQuery({
    queryKey: keys.definitions(jobPath ?? ""),
    enabled: Boolean(jobPath),
    queryFn: () =>
      api.get<ParamDefinition[]>(`/jenkins/jobs/${jobPath}/definitions`),
  });
}

/** Where a saved job is still used: read again each time the editor opens it. */
export function usePresetUsage(presetId: string | null) {
  return useQuery({
    queryKey: keys.presetUsage(presetId ?? ""),
    enabled: Boolean(presetId),
    staleTime: 0,
    queryFn: () => api.get<PresetUsage>(`/presets/${presetId}/usage`),
  });
}

/** Replace one entity in a cached list by id, leaving the rest alone. */
function replaceById<T extends { id: string }>(list: T[] | undefined, item: T): T[] {
  if (!list) return [item];
  const index = list.findIndex((existing) => existing.id === item.id);
  if (index === -1) return [...list, item];
  const next = list.slice();
  next[index] = item;
  return next;
}

export function putFlow(client: QueryClient, flow: Flow): void {
  client.setQueryData<Flow[]>(keys.flows, (current) => replaceById(current, flow));
}

export function putPreset(client: QueryClient, preset: Preset): void {
  client.setQueryData<Preset[]>(keys.presets, (current) => replaceById(current, preset));
}

export function putSavedFlow(client: QueryClient, savedFlow: SavedFlow): void {
  client.setQueryData<SavedFlow[]>(keys.savedFlows, (current) => replaceById(current, savedFlow));
}

/** Puts the returned flow in the cache; `refetch` also reloads the list, for a call that changes a second flow. */
function useFlowMutation<TVariables>(
  send: (variables: TVariables) => Promise<Flow>,
  { refetch = false } = {},
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: (flow) => {
      putFlow(client, flow);
      return refetch ? client.invalidateQueries({ queryKey: keys.flows }) : undefined;
    },
  });
}

export function useCreateFlow() {
  return useFlowMutation((body: { name?: string; steps: StepCreate[] }) =>
    api.post<Flow>("/flows", body),
  );
}

export function useAddStep() {
  return useFlowMutation(
    // `position` is the step number the card was dropped on: only a draft takes
    // one, and without it the step goes at the end.
    ({ flowId, step, position }: { flowId: string; step: StepCreate; position?: number }) =>
      api.post<Flow>(`/flows/${flowId}/steps`, { ...step, position }),
  );
}

export function usePatchStep() {
  return useFlowMutation(
    ({
      flowId,
      stepId,
      patch,
    }: {
      flowId: string;
      stepId: string;
      patch: { condition?: string; run_values?: Record<string, string>; position?: number };
    }) => api.patch<Flow>(`/flows/${flowId}/steps/${stepId}`, patch),
  );
}

export function useRemoveStep() {
  return useFlowMutation(({ flowId, stepId }: { flowId: string; stepId: string }) =>
    api.delete<Flow>(`/flows/${flowId}/steps/${stepId}`),
  );
}

export function useStartFlow() {
  return useFlowMutation(
    ({ flowId, runValues, token }: { flowId: string; runValues: RunValues; token: string }) =>
      api.post<Flow>(`/flows/${flowId}/start`, { run_values: runValues, review_token: token }),
  );
}

export function useConfirmHeld() {
  return useFlowMutation(
    ({ flowId, runValues, token }: { flowId: string; runValues: RunValues; token: string }) =>
      api.post<Flow>(`/flows/${flowId}/confirm`, { run_values: runValues, review_token: token }),
  );
}

export function useStopFlow() {
  return useFlowMutation(({ flowId, abort }: { flowId: string; abort: boolean }) =>
    api.post<Flow>(`/flows/${flowId}/stop`, { abort_current: abort }),
  );
}

export function useResumeFlow() {
  return useFlowMutation(
    ({
      flowId,
      fromPosition,
      runValues,
      token,
    }: {
      flowId: string;
      fromPosition?: number;
      runValues: RunValues;
      token: string;
    }) =>
      api.post<Flow>(`/flows/${flowId}/resume`, {
        from_position: fromPosition ?? null,
        run_values: runValues,
        review_token: token,
      }),
  );
}

export function useRenameFlow() {
  return useFlowMutation(({ flowId, name }: { flowId: string; name: string }) =>
    api.patch<Flow>(`/flows/${flowId}`, { name }),
  );
}

/** Takes a flow off the board, or with `cleared: false` puts it back (Undo). */
export function useClearFlow() {
  return useFlowMutation(({ flowId, cleared = true }: { flowId: string; cleared?: boolean }) =>
    api.patch<Flow>(`/flows/${flowId}`, { cleared }),
  );
}

export function useDeleteFlow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ flowId }: { flowId: string }) => api.delete<void>(`/flows/${flowId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.flows }),
  });
}

/** Run again keeps the original until reviewed start; edit replaces it immediately. */
export function useRerunFlow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ flowId, editing = false }: { flowId: string; editing?: boolean }) =>
      api.post<Flow>(`/flows/${flowId}/rerun`, { editing, keep_source: !editing }),
    onSuccess: (flow, { editing }) => {
      putFlow(client, flow);
      // Run again needs only the returned copy. A stalled refetch must not delay review.
      if (editing) return client.invalidateQueries({ queryKey: keys.flows });
    },
  });
}

/** A second flow with the same steps, under a free name, open to change. */
export function useDuplicateFlow() {
  return useFlowMutation(({ flowId }: { flowId: string }) =>
    api.post<Flow>(`/flows/${flowId}/duplicate`),
  );
}

/** Turns editing on or off. Only a draft takes it. */
export function useSetEditing() {
  return useFlowMutation(({ flowId, editing }: { flowId: string; editing: boolean }) =>
    api.patch<Flow>(`/flows/${flowId}`, { editing }),
  );
}

export function usePinFlow() {
  return useFlowMutation(({ flowId, pinned }: { flowId: string; pinned: boolean }) =>
    api.patch<Flow>(`/flows/${flowId}`, { pinned }),
  );
}

export function useLinkBuild() {
  return useFlowMutation(
    ({ flowId, stepId, buildNumber }: { flowId: string; stepId: string; buildNumber: number }) =>
      api.post<Flow>(`/flows/${flowId}/steps/${stepId}/link`, { build_number: buildNumber }),
  );
}

/**
 * "End flow": ends a flow whose step needs attention, stopped or not. Nothing is
 * sent. `buildNumbers` are the matching builds the window listed; the step's note
 * keeps them.
 */
export function useCloseFlow() {
  return useFlowMutation(
    ({ flowId, buildNumbers = [] }: { flowId: string; buildNumbers?: number[] }) =>
      api.post<Flow>(`/flows/${flowId}/close`, { build_numbers: buildNumbers }),
  );
}

export function useReview(flowId: string | null, scope: ReviewScope) {
  const body = {
    scope: scope.kind === "start" ? "all" : scope.kind,
    from_position: scope.kind === "resume" ? (scope.fromPosition ?? null) : null,
  };
  return useQuery({
    queryKey: ["review", flowId, body.scope, body.from_position],
    enabled: Boolean(flowId),
    gcTime: 0,
    staleTime: 0,
    retry: false,
    queryFn: () => api.post<Review>(`/flows/${flowId}/review`, body),
  });
}

export function useAttention(flowId: string | null, stepId: string | null) {
  return useQuery({
    queryKey: ["attention", flowId, stepId],
    enabled: Boolean(flowId && stepId),
    gcTime: 0,
    queryFn: () => api.get<Attention>(`/flows/${flowId}/steps/${stepId}/attention`),
  });
}

export function useSavePreset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string | null; body: unknown }) =>
      id ? api.put<Preset>(`/presets/${id}`, body) : api.post<Preset>("/presets", body),
    onSuccess: (preset) => {
      putPreset(client, preset);
      void client.invalidateQueries({ queryKey: keys.presets });
    },
  });
}

export function useRepairPreset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RepairRequest }) =>
      api.post<Preset>(`/presets/${id}/repair`, body),
    onSuccess: (preset) => putPreset(client, preset),
  });
}

export function useDuplicatePreset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => api.post<Preset>(`/presets/${id}/duplicate`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.presets }),
  });
}

export function useDeletePreset() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => api.delete<void>(`/presets/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.presets }),
  });
}

export function useRefreshIndex() {
  return useMutation({
    mutationFn: () => api.post<void>("/jenkins/jobs/refresh"),
  });
}

/** Keeps a flow as a saved flow: the one it already is, or a new one. */
export function useSaveAsFlow() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: keys.saveFlow,
    mutationFn: (flowId: string) => api.post<Flow>(`/flows/${flowId}/save`),
    onSuccess: (flow) => {
      putFlow(client, flow);
      // Returned, so the save is still pending until the saved flows are read
      // again: `Saved` is never shown against the list from before it.
      return client.invalidateQueries({ queryKey: keys.savedFlows });
    },
  });
}

/** The flows whose Save is on its way, by id, however many are saving at once. */
export function useSavingFlows(): string[] {
  return useMutationState({
    filters: { mutationKey: keys.saveFlow, status: "pending" },
    select: (mutation) => mutation.state.variables as string,
  });
}

/** Only the name is sent: the steps stay what the server holds, not what this tab last saw. */
export function useRenameSavedFlow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch<SavedFlow>(`/saved-flows/${id}`, { name }),
    onSuccess: (savedFlow) => putSavedFlow(client, savedFlow),
  });
}

export function useDuplicateSavedFlow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => api.post<SavedFlow>(`/saved-flows/${id}/duplicate`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.savedFlows }),
  });
}

export function useDeleteSavedFlow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => api.delete<void>(`/saved-flows/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.savedFlows }),
  });
}

export function useInstantiateSavedFlow() {
  return useFlowMutation(({ id, flowId }: { id: string; flowId?: string }) =>
    api.post<Flow>(`/saved-flows/${id}/instantiate`, { flow_id: flowId ?? null }),
  );
}
