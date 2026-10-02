import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";
import type { Page } from "./types";

export type ImportBatch = components["schemas"]["ImportBatch"];
export type ImportRowIssue = components["schemas"]["ImportRowIssue"];
export type IssueSeverity = ImportRowIssue["severity"];

export function useImports(page: number) {
  return useQuery({
    queryKey: ["imports", "list", page],
    queryFn: () => api<Page<ImportBatch>>("/api/imports/", { query: { page } }),
    placeholderData: keepPreviousData,
  });
}

export function useImport(id: string) {
  return useQuery({
    queryKey: ["imports", "detail", id],
    queryFn: () => api<ImportBatch>(`/api/imports/${id}/`),
  });
}

export function useImportIssues(id: string, filters: { severity?: IssueSeverity; page: number }) {
  return useQuery({
    queryKey: ["imports", "detail", id, "issues", filters],
    queryFn: () => api<Page<ImportRowIssue>>(`/api/imports/${id}/issues/`, { query: { ...filters, page_size: 50 } }),
    placeholderData: keepPreviousData,
  });
}

export function useUploadImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, key }: { file: File; key: string }) => {
      const form = new FormData();
      form.append("file", file);
      return api<ImportBatch>("/api/imports/", { method: "POST", body: form, headers: { "Idempotency-Key": key } });
    },
    onSuccess: (created) => {
      queryClient.setQueryData(["imports", "detail", String(created.id)], created);
      void queryClient.invalidateQueries({ queryKey: ["imports", "list"] });
      void queryClient.invalidateQueries({ queryKey: ["episodes"] }); // new episodes are available to assign
    },
  });
}
