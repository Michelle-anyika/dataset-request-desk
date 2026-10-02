import { Alert, Anchor, Badge, Group, Pagination, Paper, SegmentedControl, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconArrowLeft, IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { useImport, useImportIssues, type ImportBatch, type IssueSeverity } from "../api/imports";
import { EmptyState, LoadError, TableSkeleton } from "../components/states";
import { formatDateTime, plural } from "../format";
import { usePageTitle } from "../usePageTitle";
import { ImportStatusBadge, reasonLabel } from "./report";

export function ImportReportPage() {
  const { id = "" } = useParams();
  const batch = useImport(id);
  usePageTitle(batch.data ? `Import: ${batch.data.file_name}` : "Import");

  const back = (
    <Anchor component={Link} to="/imports" size="sm" c="dimmed">
      <Group gap={4}>
        <IconArrowLeft size={14} /> Imports
      </Group>
    </Anchor>
  );

  if (batch.isPending) return <TableSkeleton rows={6} />;
  if (batch.isError) {
    if (batch.error instanceof ApiError && batch.error.status === 404) {
      return (
        <>
          {back}
          <EmptyState title="Import not found" />
        </>
      );
    }
    return <LoadError what="this import" onRetry={() => void batch.refetch()} />;
  }

  const data = batch.data;
  const seconds = data.finished_at ? Math.max(1, Math.round((Date.parse(data.finished_at) - Date.parse(data.started_at)) / 1000)) : null;
  return (
    <Stack gap="lg">
      <Stack gap={6}>
        {back}
        <Group gap="sm">
          <Title order={1} fz="h2">
            {data.file_name}
          </Title>
          <ImportStatusBadge status={data.status} />
        </Group>
        <Text size="sm" c="dimmed">
          Uploaded by {data.uploaded_by.full_name} · {formatDateTime(data.started_at)}
          {seconds !== null && ` · took ${plural(seconds, "second")}`}
        </Text>
      </Stack>

      {data.status === "failed" && (
        <Alert role="alert" color="orange" variant="light" icon={<IconAlertTriangle size={18} />} title="The import failed; nothing was changed">
          {data.error_message}
        </Alert>
      )}
      {data.previously_imported && (
        <Alert color="blue" variant="light" icon={<IconInfoCircle size={18} />}>
          This exact file was imported before. Re-importing is safe: rows that haven't changed are left as they are.
        </Alert>
      )}

      {data.status !== "failed" && <Counts batch={data} />}
      <Issues id={id} />
    </Stack>
  );
}

function Counts({ batch }: { batch: ImportBatch }) {
  const counts = [
    ["Rows read", batch.total_rows, undefined],
    ["Created", batch.created_count, "teal"],
    ["Updated", batch.updated_count, "blue"],
    ["Unchanged", batch.unchanged_count, undefined],
    ["Skipped", batch.skipped_count, "orange"],
    ["Imported after fixes", batch.fixed_count, "violet"],
  ] as const;
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
      {counts.map(([label, value, color]) => (
        <Paper key={label} withBorder radius="md" p="md">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
            {label}
          </Text>
          <Text fz={26} fw={700} c={value && color ? `${color}.7` : undefined}>
            {value.toLocaleString("en-GB")}
          </Text>
        </Paper>
      ))}
    </SimpleGrid>
  );
}

function Issues({ id }: { id: string }) {
  const [severity, setSeverity] = useState<IssueSeverity | undefined>();
  const [page, setPage] = useState(1);
  const issues = useImportIssues(id, { severity, page });

  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="sm" gap="sm">
        <Stack gap={2}>
          <Title order={2} fz="h4">
            Rows skipped or fixed
          </Title>
          <Text size="sm" c="dimmed">
            The line in the file, and what happened to it.
          </Text>
        </Stack>
        <SegmentedControl
          size="xs"
          aria-label="Show"
          value={severity ?? "all"}
          onChange={(next) => {
            setSeverity(next === "all" ? undefined : (next as IssueSeverity));
            setPage(1);
          }}
          data={[
            { value: "all", label: "All" },
            { value: "skipped", label: "Skipped" },
            { value: "fixed", label: "Fixed" },
          ]}
        />
      </Group>
      {issues.isPending ? (
        <TableSkeleton />
      ) : issues.isError ? (
        <LoadError what="the rows" onRetry={() => void issues.refetch()} />
      ) : issues.data.results.length === 0 ? (
        <Text size="sm" c="dimmed">
          {severity ? `No ${severity} rows.` : "Every row was clean."}
        </Text>
      ) : (
        <>
          <Table.ScrollContainer minWidth={680}>
            <Table verticalSpacing={6} fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th ta="right">Line</Table.Th>
                  <Table.Th>Episode</Table.Th>
                  <Table.Th>Outcome</Table.Th>
                  <Table.Th>Reason</Table.Th>
                  <Table.Th>Detail</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {issues.data.results.map((issue, index) => (
                  <Table.Tr key={`${issue.row_number}-${issue.reason_code}-${index}`}>
                    <Table.Td ta="right">{issue.row_number}</Table.Td>
                    <Table.Td ff="monospace">{issue.episode_id || "—"}</Table.Td>
                    <Table.Td>
                      <Badge size="sm" radius="sm" variant="light" color={issue.severity === "skipped" ? "orange" : "violet"}>
                        {issue.severity}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{reasonLabel(issue.reason_code)}</Table.Td>
                    <Table.Td>{issue.message}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {issues.data.count > 50 && (
            <Pagination mt="sm" size="sm" value={page} onChange={setPage} total={Math.ceil(issues.data.count / 50)} />
          )}
        </>
      )}
    </Paper>
  );
}
