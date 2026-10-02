import { Alert, Anchor, Badge, Button, Group, Pagination, Paper, ScrollArea, SegmentedControl, Stack, Table, Text } from "@mantine/core";
import { IconBellRinging, IconPlus } from "@tabler/icons-react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useRequests } from "../api/requests";
import type { DatasetRequest, RequestStatus } from "../api/types";
import { EmptyState, LoadError, PageHeader, TableSkeleton } from "../components/states";
import { deadlineHint, formatDate, plural } from "../format";
import { usePageTitle } from "../usePageTitle";
import { STATUSES, STATUS_LABELS, StatusBadge } from "./status";

const PAGE_SIZE = 25;

/** The filter lives in the URL: shareable, and the back button restores it. */
export function useListParams() {
  const [params, setParams] = useSearchParams();
  const status = STATUSES.find((value) => value === params.get("status"));
  const page = Math.max(1, Number(params.get("page")) || 1);
  const update = (next: { status?: RequestStatus | null; page?: number }) => {
    const merged = new URLSearchParams(params);
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
  return { status, page, update };
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

export function MyRequestsPage() {
  usePageTitle("My requests");
  const navigate = useNavigate();
  const { status, page, update } = useListParams();
  const list = useRequests({ status, page });
  // The reminder banner counts every delivery waiting for a decision, whatever the filter shows.
  const waiting = useRequests({ status: "delivered" });
  const waitingCount = waiting.data?.count ?? 0;

  const newRequest = (
    <Button component={Link} to="/requests/new" leftSection={<IconPlus size={16} />}>
      New request
    </Button>
  );

  return (
    <>
      <PageHeader title="My requests" action={newRequest}>
        <Text c="dimmed">Track each request from submission to delivery, and review what's delivered.</Text>
      </PageHeader>
      <Stack>
        {waitingCount > 0 && (
          <Alert color="violet" variant="light" icon={<IconBellRinging size={18} />}>
            {plural(waitingCount, "delivery", "deliveries")} {waitingCount === 1 ? "is" : "are"} waiting for your
            review. Accept it, or reject it with a reason so the team can rework it.
          </Alert>
        )}
        <StatusFilter value={status} onChange={(next) => update({ status: next })} />

        {list.isPending ? (
          <TableSkeleton />
        ) : list.isError ? (
          <LoadError what="your requests" onRetry={() => void list.refetch()} />
        ) : list.data.results.length === 0 ? (
          status ? (
            <EmptyState title={`No ${STATUS_LABELS[status].toLowerCase()} requests`}>Try another filter.</EmptyState>
          ) : (
            <EmptyState title="No requests yet" action={newRequest}>
              Ask for the episodes you need: the task, how many and by when.
            </EmptyState>
          )
        ) : (
          <>
            <Stack gap="xs" hiddenFrom="sm">
              {list.data.results.map((request) => (
                <RequestCard key={request.id} request={request} />
              ))}
            </Stack>
            <Paper withBorder radius="md" visibleFrom="sm">
              <Table.ScrollContainer minWidth={640}>
                <Table highlightOnHover verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Task</Table.Th>
                      <Table.Th ta="right">Episodes</Table.Th>
                      <Table.Th>Deadline</Table.Th>
                      <Table.Th>Status</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {list.data.results.map((request) => (
                      <RequestRow key={request.id} request={request} onOpen={() => navigate(`/requests/${request.id}`)} />
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Paper>
            <ListFooter count={list.data.count} page={page} onPage={(next) => update({ page: next })} />
          </>
        )}
      </Stack>
    </>
  );
}

function RequestRow({ request, onOpen }: { request: DatasetRequest; onOpen: () => void }) {
  const actionRequired = request.status === "delivered";
  return (
    <Table.Tr onClick={onOpen} style={{ cursor: "pointer" }} bg={actionRequired ? "var(--mantine-color-violet-light)" : undefined}>
      <Table.Td>
        <Anchor
          component={Link}
          to={`/requests/${request.id}`}
          c="var(--mantine-color-text)"
          fw={500}
          onClick={(event) => event.stopPropagation()}
        >
          {request.task_name}
        </Anchor>
      </Table.Td>
      <Table.Td ta="right">
        {request.assigned_count.toLocaleString("en-GB")} / {request.episodes_requested.toLocaleString("en-GB")}
      </Table.Td>
      <Table.Td>
        <Text size="sm">{formatDate(request.deadline)}</Text>
        {!["accepted", "delivered"].includes(request.status) && (
          <Text size="xs" c="dimmed">
            {deadlineHint(request.deadline)}
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <StatusBadge status={request.status} />
          {actionRequired && (
            <Badge color="violet" variant="filled" radius="sm">
              Action required
            </Badge>
          )}
        </Group>
      </Table.Td>
    </Table.Tr>
  );
}

/** Small screens: one card per request, status first. */
function RequestCard({ request }: { request: DatasetRequest }) {
  const actionRequired = request.status === "delivered";
  return (
    <Paper
      component={Link}
      to={`/requests/${request.id}`}
      withBorder
      radius="md"
      p="sm"
      bg={actionRequired ? "var(--mantine-color-violet-light)" : undefined}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      <Group justify="space-between" wrap="nowrap" mb={6}>
        <Text fw={600}>{request.task_name}</Text>
        <StatusBadge status={request.status} />
      </Group>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {request.assigned_count.toLocaleString("en-GB")} / {request.episodes_requested.toLocaleString("en-GB")} episodes ·
          due {formatDate(request.deadline)}
        </Text>
        {actionRequired && (
          <Badge color="violet" variant="filled" radius="sm">
            Action required
          </Badge>
        )}
      </Group>
    </Paper>
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
