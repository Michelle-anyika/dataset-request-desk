import { Badge, Group, Text } from "@mantine/core";

import type { ImportBatch } from "../api/imports";

const STATUS = {
  running: { label: "Running", color: "blue" },
  completed: { label: "Completed", color: "teal" },
  failed: { label: "Failed", color: "orange" },
} as const;

export function ImportStatusBadge({ status }: { status: ImportBatch["status"] }) {
  return (
    <Badge variant="light" radius="sm" color={STATUS[status].color}>
      {STATUS[status].label}
    </Badge>
  );
}

/** "173 created · 17 skipped": only the outcomes that happened. */
export function ResultSummary({ batch }: { batch: ImportBatch }) {
  if (batch.status === "failed") {
    return (
      <Text size="sm" c="dimmed">
        Nothing imported
      </Text>
    );
  }
  const parts = [
    [batch.created_count, "created"],
    [batch.updated_count, "updated"],
    [batch.unchanged_count, "unchanged"],
    [batch.skipped_count, "skipped"],
  ] as const;
  return (
    <Group gap={6}>
      {parts
        .filter(([count]) => count > 0)
        .map(([count, label]) => (
          <Text key={label} size="sm" c={label === "skipped" ? "var(--mantine-color-orange-light-color)" : undefined}>
            {count.toLocaleString("en-GB")} {label}
          </Text>
        ))
        .flatMap((part, index) => (index ? [<Text key={`dot-${index}`} size="sm" c="dimmed">·</Text>, part] : [part]))}
    </Group>
  );
}

/** `duplicate_in_file` → "Duplicate in file". */
export function reasonLabel(code: string) {
  const words = code.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
