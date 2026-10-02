import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type Analytics = components["schemas"]["Analytics"];

/** Analytics for an inclusive range of business days. The API caches the result and shares it between staff. */
export function useAnalytics(from: string, to: string) {
  return useQuery({
    queryKey: ["analytics", from, to],
    queryFn: () => api<Analytics>("/api/analytics/", { query: { from, to } }),
    placeholderData: keepPreviousData,
  });
}
