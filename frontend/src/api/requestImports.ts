import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { requestKeys } from "./requests";
import type { components } from "./schema";

export type RequestImportReport = components["schemas"]["RequestImportReport"];
export type RequestImportRow = RequestImportReport["rows"][number];

function form(file: File) {
  const body = new FormData();
  body.append("file", file);
  return body;
}

/** What importing the spreadsheet would do, row by row. Saves nothing. */
export function usePreviewRequestImport() {
  return useMutation({
    mutationFn: (file: File) =>
      api<RequestImportReport>("/api/request-imports/preview/", { method: "POST", body: form(file) }),
  });
}

/** Import it: rows that pass are created, the rest reported. Re-running creates nothing. */
export function useCommitRequestImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, key }: { file: File; key: string }) =>
      api<RequestImportReport>("/api/request-imports/", {
        method: "POST",
        body: form(file),
        headers: { "Idempotency-Key": key },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: requestKeys.all }),
  });
}
