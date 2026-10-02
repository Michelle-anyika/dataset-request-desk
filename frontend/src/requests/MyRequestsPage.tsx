import { Alert, Anchor, Badge, Button, Group, Paper, Stack, Table, Text } from "@mantine/core";
import { IconBellRinging, IconPlus } from "@tabler/icons-react";
import { Link, useNavigate } from "react-router";

import { useRequests } from "../api/requests";
import type { DatasetRequest } from "../api/types";
import { EmptyState, LoadError, PageHeader, TableSkeleton } from "../components/states";
import { deadlineHint, formatDate, plural } from "../format";
import { usePageTitle } from "../usePageTitle";
import { ListFooter, StatusFilter, useListParams } from "./list";
import { STATUS_LABELS, StatusBadge } from "./status";

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
