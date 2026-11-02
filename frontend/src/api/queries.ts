import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { importFiles } from "../playlists/importFiles";
import { api } from "./client";
import type {
  BackupOut,
  CancelOut,
  JobOut,
  PickPathIn,
  PickPathOut,
  PlanOut,
  PlaylistDetailOut,
  PlaylistOut,
  RunOut,
  SettingsOut,
  StatusOut,
  StickOut,
  StickScanOut,
  SyncIn,
  TagMapping,
  TidalLoginOut,
} from "./types";

export const queryKeys = {
  status: ["status"] as const,
  playlists: ["playlists"] as const,
  playlist: (id: number) => ["playlists", id] as const,
  runs: ["runs"] as const,
  run: (id: number) => ["runs", id] as const,
  plans: ["plans"] as const,
  plan: (runId: number) => ["plans", runId] as const,
  settings: ["settings"] as const,
  tagMapping: ["tag-mapping"] as const,
  tidalLogin: ["auth", "tidal"] as const,
  backups: ["backups"] as const,
  sticks: ["sticks"] as const,
  currentJob: ["jobs", "current"] as const,
  job: (id: string) => ["jobs", id] as const,
};

const enc = encodeURIComponent;

export function isRunning(job: JobOut | null | undefined): job is JobOut {
  return job?.status === "running";
}

export function useStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: ({ signal }) => api.get<StatusOut>("/api/status", signal),
    refetchInterval: (query) => (isRunning(query.state.data?.current_job) ? 3000 : false),
  });
}

/** The running job, if any (the server also returns the last finished job). */
export function useCurrentJob() {
  return useQuery({
    queryKey: queryKeys.currentJob,
    queryFn: ({ signal }) => api.get<JobOut | null>("/api/jobs/current", signal),
    refetchInterval: (query) => (isRunning(query.state.data) ? 3000 : 15000),
  });
}

export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    queryFn: ({ signal }) => api.get<JobOut>(`/api/jobs/${enc(jobId ?? "")}`, signal),
    enabled: jobId !== null,
  });
}

export function usePlaylists() {
  return useQuery({
    queryKey: queryKeys.playlists,
    queryFn: ({ signal }) => api.get<PlaylistOut[]>("/api/playlists", signal),
  });
}

export function usePlaylist(id: number) {
  return useQuery({
    queryKey: queryKeys.playlist(id),
    queryFn: ({ signal }) => api.get<PlaylistDetailOut>(`/api/playlists/${id}`, signal),
  });
}

export function useRuns() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: ({ signal }) => api.get<RunOut[]>("/api/runs?limit=200", signal),
  });
}

export function useRun(id: number | null) {
  return useQuery({
    queryKey: queryKeys.run(id ?? -1),
    queryFn: ({ signal }) => api.get<RunOut>(`/api/runs/${id}`, signal),
    enabled: id !== null,
  });
}

export function usePlan(runId: number) {
  return useQuery({
    queryKey: queryKeys.plan(runId),
    queryFn: ({ signal }) => api.get<PlanOut>(`/api/plans/${runId}`, signal),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: ({ signal }) => api.get<SettingsOut>("/api/settings", signal),
  });
}

export function useTagMapping() {
  return useQuery({
    queryKey: queryKeys.tagMapping,
    queryFn: ({ signal }) => api.get<TagMapping>("/api/settings/tag-mapping", signal),
    // Do not overwrite edits in progress when the window gets focus again.
    refetchOnWindowFocus: false,
  });
}

export function useTidalLogin() {
  return useQuery({
    queryKey: queryKeys.tidalLogin,
    queryFn: ({ signal }) => api.get<TidalLoginOut>("/api/auth/tidal", signal),
    refetchInterval: (query) => (query.state.data?.state === "pending" ? 2000 : false),
  });
}

export function useBackups() {
  return useQuery({
    queryKey: queryKeys.backups,
    queryFn: ({ signal }) => api.get<BackupOut[]>("/api/backups", signal),
  });
}

export function useSticks() {
  return useQuery({
    queryKey: queryKeys.sticks,
    queryFn: ({ signal }) => api.get<StickOut[]>("/api/sticks", signal),
  });
}

/** Read the plugged-in USB sticks (never writes to them). */
export function useScanSticks() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<StickScanOut>("/api/sticks/scan"),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.sticks, data.sticks);
      void queryClient.invalidateQueries({ queryKey: queryKeys.playlists });
    },
  });
}

/** Refresh everything a finished job can change. */
export function invalidateAfterJob(queryClient: QueryClient): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.status }),
    queryClient.invalidateQueries({ queryKey: queryKeys.runs }),
    queryClient.invalidateQueries({ queryKey: queryKeys.playlists }),
    queryClient.invalidateQueries({ queryKey: queryKeys.plans }),
    queryClient.invalidateQueries({ queryKey: queryKeys.backups }),
    queryClient.invalidateQueries({ queryKey: queryKeys.currentJob }),
  ]).then(() => undefined);
}

function useJobStarter<TVars>(start: (vars: TVars) => Promise<JobOut>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: start,
    onSuccess: (job) => {
      queryClient.setQueryData(queryKeys.currentJob, job);
      queryClient.setQueryData(queryKeys.job(job.id), job);
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}

export function useStartSync() {
  return useJobStarter((body: SyncIn) => api.post<JobOut>("/api/sync", body));
}

export function useApplyPlan(runId: number) {
  return useJobStarter((groups: string[]) =>
    api.post<JobOut>(`/api/plans/${runId}/apply`, { groups }),
  );
}

export function useRestoreBackup() {
  return useJobStarter((backupId: string) =>
    api.post<JobOut>(`/api/backups/${enc(backupId)}/restore`),
  );
}

export function useCancelJob() {
  return useMutation({
    mutationFn: (jobId: string) => api.post<CancelOut>(`/api/jobs/${enc(jobId)}/cancel`),
  });
}

export function useSaveSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      api.put<SettingsOut>("/api/settings", values),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.settings, data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
      void queryClient.invalidateQueries({ queryKey: queryKeys.tagMapping });
      void queryClient.invalidateQueries({ queryKey: queryKeys.playlists });
    },
  });
}

/** Open the Finder dialog on the server's Mac; resolves to null when cancelled. */
export function usePickPath() {
  return useMutation({
    mutationFn: async (body: PickPathIn) =>
      (await api.post<PickPathOut>("/api/settings/pick-path", body)).path ?? null,
  });
}

export function useSaveTagMapping() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mapping: TagMapping) =>
      api.put<TagMapping>("/api/settings/tag-mapping", mapping),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.tagMapping, data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.playlists });
    },
  });
}

export function useImportFiles(playlistId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: readonly File[]) => importFiles(playlistId, files),
    onSettled: () =>
      Promise.all([
        // Also matches queryKeys.playlist(playlistId).
        queryClient.invalidateQueries({ queryKey: queryKeys.playlists }),
        queryClient.invalidateQueries({ queryKey: queryKeys.status }),
      ]),
  });
}

export function useStartTidalLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<TidalLoginOut>("/api/auth/tidal"),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.tidalLogin, data);
    },
  });
}
