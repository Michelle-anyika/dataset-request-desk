import {
  Anchor,
  Badge,
  Box,
  Grid,
  Group,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconCircleCheck, IconCircleDot } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { ASSIGNMENTS_PAGE_SIZE, useAssignments, useRequest, useRequestEvents } from "../api/requests";
import type { Assignment, DatasetRequest, RequestEvent } from "../api/types";
import { useUser } from "../auth/AuthProvider";
import { Pager } from "../components/Pager";
import { EmptyState, LoadError, TableSkeleton } from "../components/states";
import { clientLabel, daysSince, deadlineHint, formatDate, formatDateTime, formatDuration, plural, progressColor } from "../format";
import { usePageTitle } from "../usePageTitle";
import { ClientDecision } from "./ClientDecision";
import { StaffActions } from "./StaffActions";
import { STATUS_LABELS, StatusBadge } from "./status";

export function RequestDetailPage() {
  const { id = "" } = useParams();
  const user = useUser();
  const request = useRequest(id);
  const isClient = user.role === "client";
  const back = (
    <Anchor component={Link} to="/requests" size="sm" c="dimmed">
      <Group gap={4}>
        <IconArrowLeft size={14} /> {isClient ? "My requests" : "Request queue"}
      </Group>
    </Anchor>
  );
  usePageTitle(request.data?.task_name ?? "Request");

  if (request.isPending) return <TableSkeleton rows={6} />;
  if (request.isError) {
    if (request.error instanceof ApiError && request.error.status === 404) {
      return (
        <>
          {back}
          <EmptyState title="Request not found">It may have been mistyped, or it isn't visible to your account.</EmptyState>
        </>
      );
    }
    return <LoadError what="this request" error={request.error} onRetry={() => void request.refetch()} />;
  }

  const data = request.data;
  return (
    <Stack gap="lg">
      <Stack gap={6}>
        {back}
        <Group gap="sm" align="center">
          <Title order={1} fz="h2">
            {data.task_name}
          </Title>
          <StatusBadge status={data.status} />
        </Group>
        <Text c="dimmed" size="sm">
          Submitted {formatDateTime(data.created_at)}
          {!isClient && ` by ${clientLabel(data.client)}`}
        </Text>
      </Stack>

      <Summary request={data} />
      {data.notes && (
        <Paper withBorder radius="md" p="md">
          <Text size="sm" fw={600} mb={4}>
            Notes
          </Text>
          <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
            {data.notes}
          </Text>
        </Paper>
      )}

      {isClient && data.status === "delivered" && <ClientDecision request={data} />}
      {!isClient && <StaffActions request={data} />}

      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <History requestId={data.id} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Episodes requestId={data.id} title={isClient ? "Delivered episodes" : "Assigned episodes"} />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function Stat({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fw={600} size="lg" mt={2}>
        {children}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed" mt={2}>
          {hint}
        </Text>
      )}
    </Paper>
  );
}

function Summary({ request }: { request: DatasetRequest }) {
  const share = Math.min(100, (request.assigned_count / request.episodes_requested) * 100);
  const waitingDays = daysSince(request.status_changed_at);
  return (
    <SimpleGrid cols={{ base: 1, xs: 3 }}>
      <Stat
        label="Episodes"
        hint={
          <Progress
            value={share}
            size="sm"
            mt={6}
            color={progressColor(request.assigned_count, request.episodes_requested)}
            aria-label={`${Math.round(share)}% of the episodes assigned`}
          />
        }
      >
        {request.assigned_count.toLocaleString("en-GB")} / {request.episodes_requested.toLocaleString("en-GB")}
      </Stat>
      <Stat label="Deadline" hint={request.status === "accepted" ? undefined : deadlineHint(request.deadline)}>
        {formatDate(request.deadline)}
      </Stat>
      <Stat label={STATUS_LABELS[request.status]} hint={`since ${formatDate(request.status_changed_at.slice(0, 10))}`}>
        {waitingDays === 0 ? "today" : plural(waitingDays, "day")}
      </Stat>
    </SimpleGrid>
  );
}

function History({ requestId }: { requestId: string }) {
  const events = useRequestEvents(requestId);
  return (
    <Paper withBorder radius="md" p="md">
      <Title order={2} fz="h4" mb="md" id="history-title">
        History
      </Title>
      {events.isPending ? (
        <TableSkeleton rows={3} />
      ) : events.isError ? (
        <LoadError what="the history" error={events.error} onRetry={() => void events.refetch()} />
      ) : (
        <Box component="ol" aria-label="History" m={0} p={0} style={{ listStyle: "none" }}>
          {events.data.results.map((event, index) => (
            <HistoryItem key={`${event.changed_at}-${index}`} event={event} last={index === events.data.results.length - 1} />
          ))}
        </Box>
      )}
    </Paper>
  );
}

function HistoryItem({ event, last }: { event: RequestEvent; last: boolean }) {
  const Icon = last ? IconCircleDot : IconCircleCheck;
  return (
    <Box component="li" pb={last ? 0 : "md"} style={{ display: "flex", gap: 12 }}>
      <ThemeIcon size={22} radius="xl" variant={last ? "filled" : "light"} aria-hidden>
        <Icon size={14} />
      </ThemeIcon>
      <Stack gap={2}>
        <Text size="sm" fw={600}>
          {STATUS_LABELS[event.to_status]}
        </Text>
        <Text size="xs" c="dimmed">
          {event.changed_by.full_name} · {formatDateTime(event.changed_at)}
        </Text>
        {event.comment && (
          <Text size="sm" mt={4} style={{ whiteSpace: "pre-wrap" }}>
            “{event.comment}”
          </Text>
        )}
      </Stack>
    </Box>
  );
}

const QUALITY_COLORS = { good: "teal", usable: "yellow", bad: "gray" } as const;

function Episodes({ requestId, title }: { requestId: string; title: string }) {
  const [page, setPage] = useState(1);
  const assignments = useAssignments(requestId, { page });
  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="md">
        <Title order={2} fz="h4">
          {title}
        </Title>
        {assignments.data && <Text size="sm" c="dimmed">{plural(assignments.data.count, "episode")}</Text>}
      </Group>
      {assignments.isPending ? (
        <TableSkeleton rows={3} />
      ) : assignments.isError ? (
        <LoadError what="the episodes" error={assignments.error} onRetry={() => void assignments.refetch()} />
      ) : assignments.data.results.length === 0 ? (
        <Text c="dimmed" size="sm">
          No episodes assigned yet.
        </Text>
      ) : (
        <Stack gap="sm">
          <EpisodeTable rows={assignments.data.results} />
          <Pager label="Episode pages" page={page} pages={Math.ceil(assignments.data.count / ASSIGNMENTS_PAGE_SIZE)} onChange={setPage} />
        </Stack>
      )}
    </Paper>
  );
}

export function EpisodeTable({ rows, actions }: { rows: Assignment[]; actions?: (row: Assignment) => ReactNode }) {
  return (
    <Table.ScrollContainer minWidth={520}>
      <Table verticalSpacing={6} fz="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Episode</Table.Th>
            <Table.Th>Robot</Table.Th>
            <Table.Th>Recorded</Table.Th>
            <Table.Th ta="right">Duration</Table.Th>
            <Table.Th>Quality</Table.Th>
            {actions && <Table.Th aria-label="Actions" />}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.episode.episode_id}>
              <Table.Td ff="monospace">{row.episode.episode_id}</Table.Td>
              <Table.Td>{row.episode.robot_id}</Table.Td>
              <Table.Td>{formatDate(row.episode.recorded_at.slice(0, 10))}</Table.Td>
              <Table.Td ta="right">{formatDuration(row.episode.duration_seconds)}</Table.Td>
              <Table.Td>
                <Badge variant="light" color={QUALITY_COLORS[row.episode.quality]} radius="sm">
                  {row.episode.quality}
                </Badge>
              </Table.Td>
              {actions && <Table.Td ta="right">{actions(row)}</Table.Td>}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
