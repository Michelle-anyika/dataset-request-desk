import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Checkbox,
  Chip,
  Grid,
  Group,
  List,
  NativeSelect,
  Pagination,
  Paper,
  Progress,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconArrowLeft, IconTrash } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { describeError } from "../api/errors";
import { useAssignEpisodes, useEpisodes, useUnassignEpisode } from "../api/episodes";
import { newIdempotencyKey } from "../api/idempotency";
import { ASSIGNMENTS_PAGE_SIZE, useAssignments, useRequest } from "../api/requests";
import type { DatasetRequest, Episode, Quality } from "../api/types";
import { Pager } from "../components/Pager";
import { EmptyState, LoadError, TableSkeleton } from "../components/states";
import { formatDate, formatDuration, plural, progressColor } from "../format";
import { EpisodeTable } from "../requests/RequestDetailPage";
import { usePageTitle } from "../usePageTitle";
import { KNOWN_ROBOTS } from "./robots";

const PAGE_SIZE = 20;
const QUALITY_COLORS = { good: "teal", usable: "yellow", bad: "gray" } as const;

export function AssignEpisodesPage() {
  const { id = "" } = useParams();
  const request = useRequest(id);
  usePageTitle("Assign episodes");

  const back = (
    <Anchor component={Link} to={`/requests/${id}`} size="sm" c="dimmed">
      <Group gap={4}>
        <IconArrowLeft size={14} /> {request.data?.task_name ?? "Request"}
      </Group>
    </Anchor>
  );

  if (request.isPending) return <TableSkeleton rows={8} />;
  if (request.isError) {
    if (request.error instanceof ApiError && request.error.status === 404) {
      return <EmptyState title="Request not found" />;
    }
    return <LoadError what="this request" error={request.error} onRetry={() => void request.refetch()} />;
  }

  const data = request.data;
  const missing = Math.max(0, data.episodes_requested - data.assigned_count);
  return (
    <Stack gap="lg">
      <Stack gap={6}>
        {back}
        <Title order={1} fz="h2">
          Assign episodes
        </Title>
        <Group gap="sm">
          <Text c="dimmed">
            “{data.task_name}” for {data.client.full_name}
          </Text>
        </Group>
        <Group gap="sm" maw={420}>
          <Text fw={600} size="sm">
            {data.assigned_count.toLocaleString("en-GB")} of {data.episodes_requested.toLocaleString("en-GB")} assigned
          </Text>
          <Progress
            flex={1}
            value={Math.min(100, (data.assigned_count / data.episodes_requested) * 100)}
            color={progressColor(data.assigned_count, data.episodes_requested)}
            aria-hidden
          />
        </Group>
      </Stack>

      {data.status !== "in_progress" ? (
        <Alert color="blue" variant="light" icon={<IconAlertCircle size={18} />}>
          Episodes can only be changed while the request is in progress. Start the work (or the rework) on the{" "}
          <Anchor component={Link} to={`/requests/${id}`}>
            request page
          </Anchor>{" "}
          first.
        </Alert>
      ) : (
        <Grid gap="lg">
          <Grid.Col span={{ base: 12, xl: 7 }}>
            <AvailableEpisodes request={data} missing={missing} />
          </Grid.Col>
          <Grid.Col span={{ base: 12, xl: 5 }}>
            <CurrentAssignments requestId={id} />
          </Grid.Col>
        </Grid>
      )}
    </Stack>
  );
}

function AvailableEpisodes({ request, missing }: { request: DatasetRequest; missing: number }) {
  const [qualities, setQualities] = useState<Quality[]>(["good", "usable"]);
  const [robot, setRobot] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [problem, setProblem] = useState<ReactNode>(null);
  const assign = useAssignEpisodes(request.id);

  // Only what the API would accept: this task, assignable quality, not held by another request.
  const episodes = useEpisodes({
    task_name: request.task_name,
    quality: qualities,
    robot_id: robot || undefined,
    available: "true",
    ordering: "-recorded_at",
    page,
    page_size: PAGE_SIZE,
  });
  const rows = episodes.data?.results ?? [];
  const toggle = (episodeId: string) =>
    setSelected((current) => (current.includes(episodeId) ? current.filter((value) => value !== episodeId) : [...current, episodeId]));
  const allOnPage = rows.length > 0 && rows.every((row) => selected.includes(row.episode_id));

  const submit = async () => {
    setProblem(null);
    try {
      await assign.mutateAsync({ episodeIds: selected, key: newIdempotencyKey() });
      notifications.show({ color: "teal", title: `Assigned ${plural(selected.length, "episode")}`, message: request.task_name });
      setSelected([]);
    } catch (error) {
      setProblem(describeFailure(error));
    }
  };

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={2} fz="h4">
            Available episodes
          </Title>
          {episodes.data && (
            <Text size="sm" c="dimmed">
              {plural(episodes.data.count, "episode")}
            </Text>
          )}
        </Group>
        <Group gap="md" align="flex-end">
          <Chip.Group
            multiple
            value={qualities}
            onChange={(next) => {
              setQualities(next.length ? (next as Quality[]) : qualities); // at least one quality
              setPage(1);
            }}
          >
            <Group gap={6} role="group" aria-label="Quality">
              <Chip value="good" size="xs">
                Good
              </Chip>
              <Chip value="usable" size="xs">
                Usable
              </Chip>
            </Group>
          </Chip.Group>
          <NativeSelect
            label="Robot"
            size="xs"
            value={robot}
            onChange={(event) => {
              setRobot(event.currentTarget.value);
              setPage(1);
            }}
            data={[{ value: "", label: "All robots" }, ...KNOWN_ROBOTS.map((value) => ({ value, label: value }))]}
          />
        </Group>

        {problem && (
          <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />} withCloseButton onClose={() => setProblem(null)}>
            {problem}
          </Alert>
        )}

        <Group justify="space-between" gap="xs">
          <Text size="sm">{selected.length ? `${plural(selected.length, "episode")} selected` : "Select episodes to assign."}</Text>
          <Group gap="xs">
            {missing > 0 && rows.length > 0 && (
              <Button
                variant="subtle"
                size="xs"
                onClick={() => setSelected(rows.slice(0, missing).map((row) => row.episode_id))}
              >
                {/* Only this page's rows can be selected, so say so when they're fewer than what's missing. */}
                {Math.min(missing, rows.length) === missing
                  ? `Select the ${missing.toLocaleString("en-GB")} still needed`
                  : `Select ${rows.length} of the ${missing.toLocaleString("en-GB")} still needed`}
              </Button>
            )}
            <Button size="xs" disabled={!selected.length} loading={assign.isPending} onClick={() => void submit()}>
              {selected.length ? `Assign ${plural(selected.length, "episode")}` : "Assign"}
            </Button>
          </Group>
        </Group>

        {episodes.isPending ? (
          <TableSkeleton />
        ) : episodes.isError ? (
          <LoadError what="the episodes" error={episodes.error} onRetry={() => void episodes.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState title="No episodes available">
            None of this task's {qualities.join(" or ")} episodes are free. Import more, or widen the filters.
          </EmptyState>
        ) : (
          <>
            <Table.ScrollContainer minWidth={560}>
              <Table verticalSpacing={6} fz="sm" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={36}>
                      <Checkbox
                        aria-label="Select every episode on this page"
                        checked={allOnPage}
                        indeterminate={!allOnPage && rows.some((row) => selected.includes(row.episode_id))}
                        onChange={() =>
                          setSelected(allOnPage ? selected.filter((value) => !rows.some((row) => row.episode_id === value)) : [...new Set([...selected, ...rows.map((row) => row.episode_id)])])
                        }
                      />
                    </Table.Th>
                    <Table.Th>Episode</Table.Th>
                    <Table.Th>Robot</Table.Th>
                    <Table.Th>Recorded</Table.Th>
                    <Table.Th ta="right">Duration</Table.Th>
                    <Table.Th>Quality</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((row) => (
                    <EpisodeRow key={row.episode_id} episode={row} selected={selected.includes(row.episode_id)} onToggle={() => toggle(row.episode_id)} />
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {episodes.data.count > PAGE_SIZE && (
              <Pagination size="sm" value={page} onChange={setPage} total={Math.ceil(episodes.data.count / PAGE_SIZE)} aria-label="Episode pages" />
            )}
          </>
        )}
      </Stack>
    </Paper>
  );
}

function EpisodeRow({ episode, selected, onToggle }: { episode: Episode; selected: boolean; onToggle: () => void }) {
  return (
    <Table.Tr bg={selected ? "var(--mantine-primary-color-light)" : undefined} onClick={onToggle} style={{ cursor: "pointer" }}>
      <Table.Td>
        <Checkbox aria-label={`Select ${episode.episode_id}`} checked={selected} onChange={onToggle} onClick={(event) => event.stopPropagation()} />
      </Table.Td>
      <Table.Td ff="monospace">{episode.episode_id}</Table.Td>
      <Table.Td>{episode.robot_id}</Table.Td>
      <Table.Td>{formatDate(episode.recorded_at.slice(0, 10))}</Table.Td>
      <Table.Td ta="right">{formatDuration(episode.duration_seconds)}</Table.Td>
      <Table.Td>
        <Badge variant="light" color={QUALITY_COLORS[episode.quality]} radius="sm">
          {episode.quality}
        </Badge>
      </Table.Td>
    </Table.Tr>
  );
}

function CurrentAssignments({ requestId }: { requestId: string }) {
  const [page, setPage] = useState(1);
  const assignments = useAssignments(requestId, { page });
  const unassign = useUnassignEpisode(requestId);
  const [error, setError] = useState<string | null>(null);

  const remove = async (episodeId: string) => {
    setError(null);
    try {
      await unassign.mutateAsync(episodeId);
      // The last episode on a later page: that page no longer exists, so show the one before it.
      if (page > 1 && assignments.data?.results.length === 1) setPage(page - 1);
      notifications.show({ color: "gray", title: "Episode removed", message: `${episodeId} is free for other requests.` });
    } catch (failure) {
      setError(describeError(failure));
    }
  };

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={2} fz="h4">
            Assigned to this request
          </Title>
          {assignments.data && (
            <Text size="sm" c="dimmed">
              {plural(assignments.data.count, "episode")}
            </Text>
          )}
        </Group>
        {error && (
          <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
            {error}
          </Alert>
        )}
        {assignments.isPending ? (
          <TableSkeleton rows={3} />
        ) : assignments.isError ? (
          <LoadError what="the assigned episodes" error={assignments.error} onRetry={() => void assignments.refetch()} />
        ) : assignments.data.results.length === 0 ? (
          <Text size="sm" c="dimmed">
            Nothing assigned yet.
          </Text>
        ) : (
          <EpisodeTable
            rows={assignments.data.results}
            actions={(row) => (
              <Tooltip label="Remove from this request">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  aria-label={`Remove ${row.episode.episode_id}`}
                  loading={unassign.isPending && unassign.variables === row.episode.episode_id}
                  onClick={() => void remove(row.episode.episode_id)}
                >
                  <IconTrash size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          />
        )}
        {assignments.data && (
          <Pager
            label="Assigned episode pages"
            page={page}
            pages={Math.ceil(assignments.data.count / ASSIGNMENTS_PAGE_SIZE)}
            onChange={setPage}
          />
        )}
      </Stack>
    </Paper>
  );
}

const REASONS: Record<string, string> = {
  unknown: "Not in the catalogue",
  bad_quality: "Bad quality (only good or usable episodes can be assigned)",
  task_mismatch: "Recorded for another task",
};

/** The API refuses a bulk assignment as a whole and says why, per episode: show all of it at once. */
function describeFailure(error: unknown): ReactNode {
  if (!(error instanceof ApiError) || error.status === 0 || error.status >= 500) return `${describeError(error)} Nothing was assigned.`;
  const details = (error.details ?? {}) as Record<string, string | string[]>;
  if (error.code === "episodes_already_assigned") {
    return (
      <Stack gap={4}>
        <Text size="sm">{error.message}</Text>
        <List size="sm">
          {Object.entries(details).map(([episodeId, holder]) => (
            <List.Item key={episodeId}>
              {episodeId} is on{" "}
              <Anchor component={Link} to={`/requests/${String(holder)}`} size="sm">
                another request
              </Anchor>
            </List.Item>
          ))}
        </List>
      </Stack>
    );
  }
  if (error.code === "episodes_not_assignable") {
    return (
      <Stack gap={4}>
        <Text size="sm">{error.message}</Text>
        <List size="sm">
          {Object.entries(details).map(([reason, ids]) => (
            <List.Item key={reason}>
              {REASONS[reason] ?? reason}: {(Array.isArray(ids) ? ids : [ids]).join(", ")}
            </List.Item>
          ))}
        </List>
      </Stack>
    );
  }
  return describeError(error);
}
