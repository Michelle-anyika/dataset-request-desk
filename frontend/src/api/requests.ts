import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { Assignment, DatasetRequest, NewDatasetRequest, Page, RequestEvent, RequestStatus } from "./types";

export interface RequestFilters {
  status?: RequestStatus;
  ordering?: string;
  page?: number;
}

export const requestKeys = {
  all: ["requests"] as const,
  list: (filters: RequestFilters) => ["requests", "list", filters] as const,
  detail: (id: string) => ["requests", "detail", id] as const,
  events: (id: string) => ["requests", "detail", id, "events"] as const,
  assignments: (id: string) => ["requests", "detail", id, "assignments"] as const,
};

export function useRequests(filters: RequestFilters) {
  return useQuery({
    queryKey: requestKeys.list(filters),
    queryFn: () => api<Page<DatasetRequest>>("/api/requests/", { query: { ...filters } }),
    placeholderData: keepPreviousData, // keep the table on screen while the next page loads
  });
}

export function useRequest(id: string) {
  return useQuery({
    queryKey: requestKeys.detail(id),
    queryFn: () => api<DatasetRequest>(`/api/requests/${id}/`),
  });
}

export function useRequestEvents(id: string) {
  return useQuery({
    queryKey: requestKeys.events(id),
    queryFn: () => api<Page<RequestEvent>>(`/api/requests/${id}/events/`, { query: { page_size: 100 } }),
  });
}

export function useAssignments(id: string, { history = false } = {}) {
  return useQuery({
    queryKey: [...requestKeys.assignments(id), { history }],
    queryFn: () =>
      api<Page<Assignment>>(`/api/requests/${id}/assignments/`, {
        query: { page_size: 100, history: history ? "true" : undefined },
      }),
  });
}

export function useSubmitRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ request, key }: { request: NewDatasetRequest; key: string }) =>
      api<DatasetRequest>("/api/requests/", { method: "POST", body: request, headers: { "Idempotency-Key": key } }),
    onSuccess: (created) => {
      queryClient.setQueryData(requestKeys.detail(created.id), created);
      void queryClient.invalidateQueries({ queryKey: requestKeys.all });
    },
  });
}

export function useTransition(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ to, comment = "", key }: { to: RequestStatus; comment?: string; key: string }) =>
      api<DatasetRequest>(`/api/requests/${id}/transitions/`, {
        method: "POST",
        body: { to_status: to, comment },
        headers: { "Idempotency-Key": key },
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(requestKeys.detail(id), updated);
      void queryClient.invalidateQueries({ queryKey: requestKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
