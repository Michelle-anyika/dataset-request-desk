import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { isConflict, requestKeys } from "./requests";
import type { Episode, Page, Quality } from "./types";

export interface EpisodeFilters {
  task_name?: string;
  quality?: Quality[];
  robot_id?: string;
  available?: "true" | "false";
  ordering?: string;
  page?: number;
  page_size?: number;
}

export function useEpisodes(filters: EpisodeFilters, { enabled = true } = {}) {
  return useQuery({
    queryKey: ["episodes", filters],
    queryFn: () => api<Page<Episode>>("/api/episodes/", { query: { ...filters } }),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** After any change to a request's episodes: its progress, its list and the episode catalogue are stale. */
function useInvalidateAssignments(requestId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: requestKeys.detail(requestId) }),
      queryClient.invalidateQueries({ queryKey: ["episodes"] }),
      queryClient.invalidateQueries({ queryKey: requestKeys.all, refetchType: "none" }),
    ]);
}

export function useAssignEpisodes(requestId: string) {
  const invalidate = useInvalidateAssignments(requestId);
  return useMutation({
    mutationFn: ({ episodeIds, key }: { episodeIds: string[]; key: string }) =>
      api<{ assigned: string[]; assigned_count: number; episodes_requested: number }>(
        `/api/requests/${requestId}/assignments/`,
        { method: "POST", body: { episode_ids: episodeIds }, headers: { "Idempotency-Key": key } },
      ),
    onSuccess: invalidate,
    onError: (error) => isConflict(error) && invalidate(), // the catalogue or the request changed meanwhile
  });
}

export function useUnassignEpisode(requestId: string) {
  const invalidate = useInvalidateAssignments(requestId);
  return useMutation({
    mutationFn: (episodeId: string) =>
      api<undefined>(`/api/requests/${requestId}/assignments/${encodeURIComponent(episodeId)}/`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (error) => isConflict(error) && invalidate(),
  });
}
