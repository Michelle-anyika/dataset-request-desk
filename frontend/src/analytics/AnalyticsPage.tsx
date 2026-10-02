import "@mantine/charts/styles.css";

import { BarChart } from "@mantine/charts";
import {
  Alert,
  Button,
  Group,
  Paper,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  VisuallyHidden,
} from "@mantine/core";
import { IconAlertCircle, IconChartBar, IconTable } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useAnalytics, type Analytics } from "../api/analytics";
import { ApiError } from "../api/client";
import type { RequestStatus } from "../api/types";
import { LoadError, PageHeader, TableSkeleton } from "../components/states";
import { formatDate, plural, todayIso } from "../format";
import { STATUSES, STATUS_LABELS, StatusBadge } from "../requests/status";
import { usePageTitle } from "../usePageTitle";

const PRESETS = [
  { days: 7, label: "Last 7 days" },
  { days: 30, label: "Last 30 days" },
  { days: 90, label: "Last 90 days" },
  { days: 365, label: "Last 12 months" },
];
const ROBOT_COLORS = ["brand.6", "blue.6", "teal.6", "violet.6", "yellow.6", "gray.6"];

function daysBefore(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return todayIso(date);
}

/** "1.5 days" or "5 h": the median time from submission to first delivery. */
export function formatHours(hours: number | null) {
  if (hours === null) return "—";
  if (hours < 1) return "under 1 h";
  if (hours < 24) return `${Math.round(hours * 10) / 10} h`;
  return `${Math.round((hours / 24) * 10) / 10} days`;
}

export function AnalyticsPage() {
  usePageTitle("Analytics");
  const [params, setParams] = useSearchParams();
  const to = params.get("to") ?? todayIso();
  const from = params.get("from") ?? daysBefore(29);
  const preset = PRESETS.find((p) => from === daysBefore(p.days - 1) && to === todayIso());
  const analytics = useAnalytics(from, to);

  const setRange = (next: { from: string; to: string }) => setParams({ from: next.from, to: next.to });

  return (
    <>
      <PageHeader title="Analytics">
        <Text c="dimmed">Recording output and how fast requests are fulfilled, for any range up to a year.</Text>
      </PageHeader>
      <Stack gap="lg">
        <Group align="flex-end" gap="md">
          <SegmentedControl
            aria-label="Range"
            value={preset ? String(preset.days) : "custom"}
            onChange={(value) => {
              const days = Number(value);
              if (days) setRange({ from: daysBefore(days - 1), to: todayIso() });
            }}
            data={[...PRESETS.map((p) => ({ value: String(p.days), label: p.label })), { value: "custom", label: "Custom", disabled: true }]}
          />
          <TextInput type="date" label="From" size="xs" value={from} max={to} onChange={(e) => e.currentTarget.value && setRange({ from: e.currentTarget.value, to })} />
          <TextInput type="date" label="To" size="xs" value={to} min={from} max={todayIso()} onChange={(e) => e.currentTarget.value && setRange({ from, to: e.currentTarget.value })} />
        </Group>

        {analytics.isPending ? (
          <TableSkeleton rows={6} />
        ) : analytics.isError ? (
          analytics.error instanceof ApiError && analytics.error.status === 400 ? (
            <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />} title="That range can't be shown">
              {Object.values(analytics.error.fieldErrors()).join(" ") || analytics.error.message}
            </Alert>
          ) : (
            <LoadError what="the analytics" error={analytics.error} onRetry={() => void analytics.refetch()} />
          )
        ) : (
          <Dashboard data={analytics.data} />
        )}
      </Stack>
    </>
  );
}

function Dashboard({ data }: { data: Analytics }) {
  const totalEpisodes = data.episodes_per_day.reduce((sum, day) => sum + day.episodes, 0);
  const totalRequests = Object.values(data.requests.by_status).reduce((sum, count) => sum + count, 0);
  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
        <Kpi label="Episodes recorded" value={totalEpisodes.toLocaleString("en-GB")} hint={data.range.from && data.range.to ? `${formatDate(data.range.from)} – ${formatDate(data.range.to)}` : ""} />
        <Kpi label="Requests submitted" value={totalRequests.toLocaleString("en-GB")} hint="in this range, by current status" />
        <Kpi
          label="Median time to delivery"
          value={formatHours(data.requests.median_hours_to_delivery)}
          hint={data.requests.delivered_count ? `based on ${plural(data.requests.delivered_count, "delivery", "deliveries")}` : "no deliveries in this range"}
        />
        <Kpi label="Waiting for a client" value={(data.requests.by_status.delivered ?? 0).toLocaleString("en-GB")} hint="delivered, not yet reviewed" />
      </SimpleGrid>
      <EpisodesPerDay data={data} />
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <RequestsByStatus byStatus={data.requests.by_status} total={totalRequests} />
        <TopTasks tasks={data.top_tasks_by_good_episodes} />
      </SimpleGrid>
    </Stack>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fz={28} fw={700} lh={1.2} mt={4}>
        {value}
      </Text>
      <Text size="xs" c="dimmed" mt={4}>
        {hint}
      </Text>
    </Paper>
  );
}

function EpisodesPerDay({ data }: { data: Analytics }) {
  const [asTable, setAsTable] = useState(false);
  // One row per day, one column per robot: the shape both the chart and the table need.
  const { rows, robots } = useMemo(() => {
    const robotIds = [...new Set(data.episodes_per_day.map((day) => day.robot_id))].sort((a, b) => a.localeCompare(b));
    const byDate = new Map<string, Record<string, number>>();
    for (const { date, robot_id, episodes } of data.episodes_per_day) {
      const row = byDate.get(date) ?? {};
      row[robot_id] = episodes;
      byDate.set(date, row);
    }
    return {
      robots: robotIds,
      rows: [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, counts]) => ({ date, ...counts })),
    };
  }, [data]);

  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="md">
        <Title order={2} fz="h4">
          Episodes per day, by robot
        </Title>
        <Button
          size="xs"
          variant="default"
          leftSection={asTable ? <IconChartBar size={14} /> : <IconTable size={14} />}
          onClick={() => setAsTable(!asTable)}
        >
          {asTable ? "Show as chart" : "Show as table"}
        </Button>
      </Group>
      {rows.length === 0 ? (
        <Text size="sm" c="dimmed">
          No episodes were recorded in this range.
        </Text>
      ) : asTable ? (
        <Table.ScrollContainer minWidth={480}>
          <Table fz="sm" verticalSpacing={4} aria-label="Episodes per day">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Day</Table.Th>
                {robots.map((robot) => (
                  <Table.Th key={robot} ta="right">
                    {robot}
                  </Table.Th>
                ))}
                <Table.Th ta="right">Total</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => {
                const counts = row as Record<string, number | string>;
                return (
                  <Table.Tr key={row.date}>
                    <Table.Td>{formatDate(row.date)}</Table.Td>
                    {robots.map((robot) => (
                      <Table.Td key={robot} ta="right">
                        {Number(counts[robot] ?? 0)}
                      </Table.Td>
                    ))}
                    <Table.Td ta="right" fw={600}>
                      {robots.reduce((sum, robot) => sum + Number(counts[robot] ?? 0), 0)}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      ) : (
        <>
          <VisuallyHidden>
            Stacked bar chart of episodes per day for each robot. Use “Show as table” for the numbers.
          </VisuallyHidden>
          <BarChart
            h={280}
            data={rows.map((row) => ({ ...row, day: formatDate(row.date).replace(/ \d{4}$/, "") }))}
            dataKey="day"
            type="stacked"
            withLegend
            legendProps={{ verticalAlign: "bottom" }}
            series={robots.map((robot, index) => ({ name: robot, color: ROBOT_COLORS[index % ROBOT_COLORS.length] ?? "gray.6" }))}
            tickLine="y"
          />
        </>
      )}
    </Paper>
  );
}

function RequestsByStatus({ byStatus, total }: { byStatus: Record<string, number>; total: number }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Title order={2} fz="h4" mb="md">
        Requests by status
      </Title>
      <Stack component="ul" aria-label="Requests by status" gap="sm" m={0} p={0} style={{ listStyle: "none" }}>
        {STATUSES.map((status: RequestStatus) => {
          const count = byStatus[status] ?? 0;
          return (
            <li key={status}>
              <Group justify="space-between" mb={4}>
                <StatusBadge status={status} />
                <Text size="sm" fw={600}>
                  <VisuallyHidden>{STATUS_LABELS[status]} </VisuallyHidden>
                  {count}
                </Text>
              </Group>
              <Progress value={total ? (count / total) * 100 : 0} size="sm" color="gray" aria-hidden />
            </li>
          );
        })}
      </Stack>
    </Paper>
  );
}

function TopTasks({ tasks }: { tasks: Analytics["top_tasks_by_good_episodes"] }) {
  const best = tasks[0]?.good_episodes ?? 0;
  return (
    <Paper withBorder radius="md" p="md">
      <Title order={2} fz="h4" mb="md">
        Top tasks by good episodes
      </Title>
      {tasks.length === 0 ? (
        <Text size="sm" c="dimmed">
          No good episodes in this range.
        </Text>
      ) : (
        <Stack component="ol" aria-label="Top tasks by good episodes" gap="sm" m={0} p={0} style={{ listStyle: "none" }}>
          {tasks.map((task, index) => (
            <li key={task.task_name}>
              <Group justify="space-between" mb={4}>
                <Text size="sm">
                  {index + 1}. {task.task_name}
                </Text>
                <Text size="sm" fw={600}>
                  {task.good_episodes.toLocaleString("en-GB")}
                </Text>
              </Group>
              <Progress value={best ? (task.good_episodes / best) * 100 : 0} size="sm" color="teal" aria-hidden />
            </li>
          ))}
        </Stack>
      )}
    </Paper>
  );
}
