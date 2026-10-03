import { Anchor, Group, NativeSelect, Paper, Progress, Stack, Table, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Link, useNavigate } from "react-router";

import { useRequests } from "../api/requests";
import type { DatasetRequest } from "../api/types";
import { EmptyState, LoadError, PageHeader, TableSkeleton } from "../components/states";
import { daysUntil, deadlineHint, formatDate, progressColor, waitedFor } from "../format";
import { usePageTitle } from "../usePageTitle";
import { ListFooter, StatusFilter, useListParams } from "./list";
import { STATUS_LABELS, StatusBadge } from "./status";

const SORTS = [
  { value: "-created_at", label: "Newest first" },
  { value: "deadline", label: "Deadline, soonest first" },
  { value: "status_changed_at", label: "Waiting longest" },
];

/** The operators' view of every request. */
export function RequestQueuePage() {
  usePageTitle("Request queue");
  const navigate = useNavigate();
  const { status, page, sort, update } = useListParams();
  // A delivery waiting longest for its client is the one to chase, so delivered requests start oldest first.
  const ordering = sort ?? (status === "delivered" ? "status_changed_at" : "-created_at");
  const list = useRequests({ status, page, ordering });

  return (
    <>
      <PageHeader title="Request queue">
        <Text c="dimmed">Every client's requests. Open one to start it, assign episodes and deliver.</Text>
      </PageHeader>
      <Stack>
        <Group justify="space-between" align="flex-end" gap="sm">
          <StatusFilter value={status} onChange={(next) => update({ status: next })} />
          <NativeSelect
            label="Sort by"
            size="xs"
            w={200}
            value={ordering}
            data={SORTS}
            onChange={(event) => update({ sort: event.currentTarget.value })}
          />
        </Group>

        {list.isPending ? (
          <TableSkeleton />
        ) : list.isError ? (
          <LoadError what="the requests" error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data.results.length === 0 ? (
          <EmptyState title={status ? `No ${STATUS_LABELS[status].toLowerCase()} requests` : "No requests yet"}>
            {status ? "Try another filter." : "Requests appear here as soon as clients submit them."}
          </EmptyState>
        ) : (
          <>
            <Paper withBorder radius="md">
              <Table.ScrollContainer minWidth={760}>
                <Table highlightOnHover verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Task</Table.Th>
                      <Table.Th>Client</Table.Th>
                      <Table.Th>Episodes</Table.Th>
                      <Table.Th>Deadline</Table.Th>
                      <Table.Th>Status</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {list.data.results.map((request) => (
                      <QueueRow key={request.id} request={request} onOpen={() => navigate(`/requests/${request.id}`)} />
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

function QueueRow({ request, onOpen }: { request: DatasetRequest; onOpen: () => void }) {
  const open = !["accepted", "delivered"].includes(request.status);
  const overdue = open && daysUntil(request.deadline) < 0;
  const share = Math.min(100, (request.assigned_count / request.episodes_requested) * 100);
  return (
    <Table.Tr onClick={onOpen} style={{ cursor: "pointer" }}>
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
      <Table.Td>
        <Text size="sm">{request.client.full_name}</Text>
        {request.client.organisation && request.client.organisation !== request.client.full_name && (
          <Text size="xs" c="dimmed">
            {request.client.organisation}
          </Text>
        )}
      </Table.Td>
      <Table.Td miw={140}>
        <Text size="sm">
          {request.assigned_count.toLocaleString("en-GB")} / {request.episodes_requested.toLocaleString("en-GB")}
        </Text>
        <Progress
          value={share}
          size="xs"
          mt={4}
          color={progressColor(request.assigned_count, request.episodes_requested)}
          aria-hidden
        />
      </Table.Td>
      <Table.Td>
        <Text size="sm">{formatDate(request.deadline)}</Text>
        {open && (
          <Group gap={4} wrap="nowrap">
            {overdue && <IconAlertTriangle size={12} color="var(--mantine-color-orange-6)" aria-hidden />}
            <Text size="xs" c={overdue ? "var(--mantine-color-orange-light-color)" : "dimmed"} fw={overdue ? 600 : undefined}>
              {deadlineHint(request.deadline)}
            </Text>
          </Group>
        )}
      </Table.Td>
      <Table.Td>
        <StatusBadge status={request.status} />
        {request.status === "delivered" && (
          <Text size="xs" c="dimmed" mt={4}>
            Awaiting client {waitedFor(request.status_changed_at)}
          </Text>
        )}
      </Table.Td>
    </Table.Tr>
  );
}
