import { Group, Pagination, ScrollArea, SegmentedControl, Text } from "@mantine/core";
import { useSearchParams } from "react-router";

import type { RequestStatus } from "../api/types";
import { plural } from "../format";
import { STATUSES, STATUS_LABELS } from "./status";

const PAGE_SIZE = 25;

/** The filter lives in the URL: shareable, and the back button restores it. */
export function useListParams() {
  const [params, setParams] = useSearchParams();
  const status = STATUSES.find((value) => value === params.get("status"));
  const page = Math.max(1, Number(params.get("page")) || 1);
  const sort = params.get("sort") ?? undefined;
  const update = (next: { status?: RequestStatus | null; page?: number; sort?: string }) => {
    const merged = new URLSearchParams(params);
    if (next.sort !== undefined) {
      merged.set("sort", next.sort);
      merged.delete("page");
    }
    if (next.status !== undefined) {
      if (next.status) merged.set("status", next.status);
      else merged.delete("status");
      merged.delete("page");
    }
    if (next.page !== undefined) {
      if (next.page > 1) merged.set("page", String(next.page));
      else merged.delete("page");
    }
    setParams(merged);
  };
  return { status, page, sort, update };
}

export function StatusFilter({ value, onChange }: { value?: RequestStatus; onChange: (status: RequestStatus | null) => void }) {
  return (
    <ScrollArea type="never">
      <SegmentedControl
        aria-label="Filter by status"
        value={value ?? "all"}
        onChange={(next) => onChange(next === "all" ? null : (next as RequestStatus))}
        data={[{ value: "all", label: "All" }, ...STATUSES.map((status) => ({ value: status, label: STATUS_LABELS[status] }))]}
      />
    </ScrollArea>
  );
}

export function ListFooter({ count, page, onPage }: { count: number; page: number; onPage: (page: number) => void }) {
  const pages = Math.ceil(count / PAGE_SIZE);
  return (
    <Group justify="space-between">
      <Text size="sm" c="dimmed">
        {plural(count, "request")}
      </Text>
      {pages > 1 && <Pagination value={page} onChange={onPage} total={pages} size="sm" aria-label="Pages" />}
    </Group>
  );
}
