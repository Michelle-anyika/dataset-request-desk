import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";
import type { Page } from "./types";

export type Notification = components["schemas"]["Notification"];

const keys = {
  all: ["notifications"] as const,
  summary: ["notifications", "summary"] as const,
  list: (filters: { unread?: boolean; page?: number; page_size?: number }) => ["notifications", "list", filters] as const,
};

/** The unread count for the bell: polled every 30 seconds while the tab is visible. */
export function useUnreadCount() {
  return useQuery({
    queryKey: keys.summary,
    queryFn: () => api<{ unread: number }>("/api/notifications/summary/"),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}

export function useNotifications(filters: { unread?: boolean; page?: number; page_size?: number }, { enabled = true } = {}) {
  return useQuery({
    queryKey: keys.list(filters),
    queryFn: () =>
      api<Page<Notification>>("/api/notifications/", {
        query: { unread: filters.unread ? "true" : undefined, page: filters.page, page_size: filters.page_size },
      }),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<undefined>(`/api/notifications/${id}/read/`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api<undefined>("/api/notifications/read-all/", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  });
}
