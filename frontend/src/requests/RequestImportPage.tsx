import { Alert, Anchor, Badge, Button, Code, FileInput, Group, Paper, Stack, Table, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconCircleCheck, IconFileSpreadsheet } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router";

import { describeError } from "../api/errors";
import { newIdempotencyKey } from "../api/idempotency";
import {
  useCommitRequestImport,
  usePreviewRequestImport,
  type RequestImportReport,
  type RequestImportRow,
} from "../api/requestImports";
import { Pager } from "../components/Pager";
import { PageHeader } from "../components/states";
import { plural } from "../format";
import { checkUpload } from "../imports/ImportsPage";
import { usePageTitle } from "../usePageTitle";

const ROWS_PER_PAGE = 50;
const ACTIONS: Record<RequestImportRow["action"], { label: string; color: string }> = {
  create: { label: "New", color: "teal" },
  unchanged: { label: "Imported before", color: "gray" },
  skip: { label: "Skipped", color: "orange" },
};

/** Admins move the requests tracked in the old spreadsheet into the platform: preview, then import. */
export function RequestImportPage() {
  usePageTitle("Migrate requests");
  const preview = usePreviewRequestImport();
  const commit = useCommitRequestImport();
  const [file, setFile] = useState<File | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<RequestImportReport | null>(null);
  const [done, setDone] = useState<RequestImportReport | null>(null);
  const [key, setKey] = useState(newIdempotencyKey); // one key per chosen file: a retry can't import twice

  const choose = (next: File | null) => {
    setFile(next);
    setFieldError(null);
    setError(null);
    setReport(null); // a preview belongs to the file it was made from
    setDone(null);
    setKey(newIdempotencyKey());
  };

  const runPreview = async () => {
    setError(null);
    const problem = checkUpload(file);
    setFieldError(problem);
    if (problem || !file) return;
    try {
      setReport(await preview.mutateAsync(file));
    } catch (failure) {
      setError(describeError(failure));
    }
  };

  const runImport = async () => {
    if (!file) return;
    setError(null);
    try {
      setDone(await commit.mutateAsync({ file, key }));
      setReport(null);
    } catch (failure) {
      setError(describeError(failure));
    }
  };

  return (
    <>
      <PageHeader title="Migrate requests">
        <Text c="dimmed" maw={760}>
          Move the requests tracked in the operations spreadsheet into the platform. Preview first: nothing is saved
          until you import. Rows are matched on their reference, so importing the same file again creates nothing.
        </Text>
      </PageHeader>
      <Stack gap="lg">
        <Paper withBorder radius="md" p="md">
          <Stack gap="sm">
            <Text size="sm">
              Columns: <Code>reference</Code>, <Code>client_email</Code>, <Code>task_name</Code>,{" "}
              <Code>episodes_requested</Code>, <Code>deadline</Code> (2026-11-01), <Code>notes</Code> and{" "}
              <Code>status</Code> (submitted, in_progress, accepted or rejected). Each client needs an account first.
            </Text>
            {error && (
              <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
                {error}
              </Alert>
            )}
            <Group align="flex-end" gap="sm">
              <FileInput
                label="Spreadsheet"
                description="CSV (UTF-8) or Excel (.xlsx, first sheet), up to 20 MB."
                placeholder="Choose a .csv or .xlsx file"
                accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                leftSection={<IconFileSpreadsheet size={18} />}
                clearable
                value={file}
                error={fieldError}
                onChange={choose}
                w={{ base: "100%", sm: 360 }}
              />
              <Button variant="default" loading={preview.isPending} onClick={() => void runPreview()}>
                Preview
              </Button>
            </Group>
          </Stack>
        </Paper>

        {done && <Result report={done} />}
        {report && <Preview report={report} importing={commit.isPending} onImport={() => void runImport()} />}
      </Stack>
    </>
  );
}

function Counts({ report, created }: { report: RequestImportReport; created: string }) {
  return (
    <Group gap="xs">
      <Badge color="teal" variant="light" radius="sm">
        {plural(report.create, "request")} {created}
      </Badge>
      <Badge color="gray" variant="light" radius="sm">
        {report.unchanged} imported before
      </Badge>
      <Badge color="orange" variant="light" radius="sm">
        {report.skip} skipped
      </Badge>
    </Group>
  );
}

function Preview({ report, importing, onImport }: { report: RequestImportReport; importing: boolean; onImport: () => void }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Group justify="space-between" gap="sm">
          <Stack gap={4}>
            <Title order={2} fz="h4">
              Preview
            </Title>
            <Counts report={report} created="to create" />
          </Stack>
          <Button disabled={report.create === 0} loading={importing} onClick={onImport}>
            {report.create ? `Import ${plural(report.create, "request")}` : "Nothing to import"}
          </Button>
        </Group>
        {report.skip > 0 && (
          <Text size="sm" c="dimmed">
            Skipped rows are not imported. Fix them in the spreadsheet and import it again: nothing is duplicated.
          </Text>
        )}
        <Rows rows={report.rows} />
      </Stack>
    </Paper>
  );
}

function Result({ report }: { report: RequestImportReport }) {
  return (
    <Alert color="teal" variant="light" icon={<IconCircleCheck size={18} />} title="Import finished">
      <Stack gap="xs">
        <Counts report={report} created="created" />
        <Text size="sm">
          They are in the{" "}
          <Anchor component={Link} to="/requests" size="sm">
            request queue
          </Anchor>
          , each with an &ldquo;imported&rdquo; step in its history.
        </Text>
        {report.skip > 0 && <Rows rows={report.rows.filter((row) => row.action === "skip")} />}
      </Stack>
    </Alert>
  );
}

function Rows({ rows }: { rows: RequestImportRow[] }) {
  const [page, setPage] = useState(1);
  const shown = rows.slice((page - 1) * ROWS_PER_PAGE, page * ROWS_PER_PAGE);
  return (
    <Stack gap="sm">
      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing={6} fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th ta="right">Row</Table.Th>
              <Table.Th>Reference</Table.Th>
              <Table.Th>Client</Table.Th>
              <Table.Th>Task</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Result</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {shown.map((row) => (
              <Table.Tr key={row.row}>
                <Table.Td ta="right">{row.row}</Table.Td>
                <Table.Td ff="monospace">{row.reference || "—"}</Table.Td>
                <Table.Td>{row.client_email || "—"}</Table.Td>
                <Table.Td>{row.task_name || "—"}</Table.Td>
                <Table.Td>{row.status || "—"}</Table.Td>
                <Table.Td>
                  <Badge color={ACTIONS[row.action].color} variant="light" radius="sm">
                    {ACTIONS[row.action].label}
                  </Badge>
                  {row.message && (
                    <Text size="xs" mt={4}>
                      {row.message}
                    </Text>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Pager label="Row pages" page={page} pages={Math.ceil(rows.length / ROWS_PER_PAGE)} onChange={setPage} />
    </Stack>
  );
}
