import { Alert, Anchor, Badge, Button, FileInput, Group, Pagination, Paper, Stack, Table, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconFileTypeCsv, IconUpload } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { useImports, useUploadImport, type ImportBatch } from "../api/imports";
import { EmptyState, LoadError, PageHeader, TableSkeleton } from "../components/states";
import { formatDateTime } from "../format";
import { usePageTitle } from "../usePageTitle";
import { ImportStatusBadge, ResultSummary } from "./report";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024; // as the API (IMPORT_MAX_UPLOAD_BYTES)

export function checkUpload(file: File | null): string | null {
  if (!file) return "Choose the CSV export to import.";
  if (!file.name.toLowerCase().endsWith(".csv")) return "Choose the CSV export (a .csv file).";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than 20 MB. Split the export and import each part.";
  return null;
}

export function ImportsPage() {
  usePageTitle("Imports");
  const [page, setPage] = useState(1);
  const imports = useImports(page);

  return (
    <>
      <PageHeader title="Episode imports">
        <Text c="dimmed">
          Upload the recording system's CSV export. Messy rows are fixed or skipped, and every one is reported.
          Importing the same file again changes nothing.
        </Text>
      </PageHeader>
      <Stack gap="lg">
        <UploadCard />
        <Paper withBorder radius="md" p="md">
          <Title order={2} fz="h4" mb="sm">
            Previous imports
          </Title>
          {imports.isPending ? (
            <TableSkeleton />
          ) : imports.isError ? (
            <LoadError what="the imports" onRetry={() => void imports.refetch()} />
          ) : imports.data.results.length === 0 ? (
            <EmptyState title="No imports yet">The first export you upload appears here with its report.</EmptyState>
          ) : (
            <>
              <Table.ScrollContainer minWidth={720}>
                <Table verticalSpacing="sm" highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>File</Table.Th>
                      <Table.Th>Uploaded</Table.Th>
                      <Table.Th>Result</Table.Th>
                      <Table.Th>Status</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {imports.data.results.map((batch) => (
                      <ImportRow key={batch.id} batch={batch} />
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {imports.data.count > 25 && (
                <Pagination mt="sm" size="sm" value={page} onChange={setPage} total={Math.ceil(imports.data.count / 25)} />
              )}
            </>
          )}
        </Paper>
      </Stack>
    </>
  );
}

function UploadCard() {
  const navigate = useNavigate();
  const upload = useUploadImport();
  const [file, setFile] = useState<File | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [key, setKey] = useState(newIdempotencyKey); // one key per chosen file: a retry can't import twice

  const submit = async () => {
    setError(null);
    const problem = checkUpload(file);
    setFieldError(problem);
    if (problem || !file) return;
    try {
      const batch = await upload.mutateAsync({ file, key });
      void navigate(`/imports/${batch.id}`);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "We couldn't reach the server. Try again.");
    }
  };

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        {error && (
          <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
            {error}
          </Alert>
        )}
        <Group align="flex-end" gap="sm">
          <FileInput
            label="CSV export"
            description="Up to 20 MB, UTF-8."
            placeholder="Choose a .csv file"
            accept=".csv,text/csv"
            leftSection={<IconFileTypeCsv size={18} />}
            clearable
            value={file}
            error={fieldError}
            onChange={(next) => {
              setFile(next);
              setFieldError(null);
              setKey(newIdempotencyKey());
            }}
            w={{ base: "100%", sm: 380 }}
          />
          <Button leftSection={<IconUpload size={16} />} loading={upload.isPending} onClick={() => void submit()}>
            Import
          </Button>
        </Group>
        {upload.isPending && (
          <Text size="sm" c="dimmed">
            Importing… large exports can take a minute. Keep this page open.
          </Text>
        )}
      </Stack>
    </Paper>
  );
}

function ImportRow({ batch }: { batch: ImportBatch }) {
  return (
    <Table.Tr>
      <Table.Td>
        <Anchor component={Link} to={`/imports/${batch.id}`} c="var(--mantine-color-text)" fw={500}>
          {batch.file_name}
        </Anchor>
        {batch.previously_imported && (
          <Badge ml="xs" size="xs" variant="light" color="gray">
            Same file as before
          </Badge>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="sm">{formatDateTime(batch.started_at)}</Text>
        <Text size="xs" c="dimmed">
          {batch.uploaded_by.full_name}
        </Text>
      </Table.Td>
      <Table.Td>
        <ResultSummary batch={batch} />
      </Table.Td>
      <Table.Td>
        <ImportStatusBadge status={batch.status} />
      </Table.Td>
    </Table.Tr>
  );
}
