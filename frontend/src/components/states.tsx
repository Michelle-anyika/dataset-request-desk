import { Alert, Button, Center, Group, Skeleton, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle, IconInbox } from "@tabler/icons-react";
import type { ReactNode } from "react";

/** A failed load, with a way to try again. */
export function LoadError({ what, onRetry }: { what: string; onRetry?: () => void }) {
  return (
    <Alert role="alert" color="red" variant="light" icon={<IconAlertTriangle size={18} />} title={`We couldn't load ${what}`}>
      <Stack gap="xs" align="flex-start">
        <Text size="sm">Check your connection. If it keeps happening, the service may be down for a moment.</Text>
        {onRetry && (
          <Button size="xs" variant="light" color="red" onClick={onRetry}>
            Try again
          </Button>
        )}
      </Stack>
    </Alert>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <Center py={48}>
      <Stack align="center" gap="xs" maw={420} ta="center">
        <ThemeIcon size={48} radius="xl" variant="light" color="gray">
          <IconInbox size={26} />
        </ThemeIcon>
        <Title order={3} fz="h4">
          {title}
        </Title>
        {children && <Text c="dimmed">{children}</Text>}
        {action && <Group mt="xs">{action}</Group>}
      </Stack>
    </Center>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Stack gap="xs" aria-label="Loading" aria-busy>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} height={36} radius="sm" />
      ))}
    </Stack>
  );
}

/** Page title with an optional action on the right. */
export function PageHeader({ title, children, action }: { title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-start" mb="lg" gap="md">
      <Stack gap={4}>
        <Title order={1} fz="h2">
          {title}
        </Title>
        {children}
      </Stack>
      {action}
    </Group>
  );
}
