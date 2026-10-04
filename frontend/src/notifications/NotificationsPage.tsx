import { Button, Group, Pagination, Paper, SegmentedControl, Stack, Text } from "@mantine/core";
import { IconChecks } from "@tabler/icons-react";
import { useState } from "react";

import { useMarkAllRead, useNotifications, useUnreadCount } from "../api/notifications";
import { EmptyState, LoadError, PageHeader, TableSkeleton } from "../components/states";
import { plural } from "../format";
import { usePageTitle } from "../usePageTitle";
import { NotificationList } from "./NotificationBell";

export function NotificationsPage() {
  usePageTitle("Notifications");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [page, setPage] = useState(1);
  const list = useNotifications({ unread: unreadOnly, page });
  const unread = useUnreadCount().data?.unread ?? 0;
  const markAll = useMarkAllRead();

  return (
    <>
      <PageHeader
        title="Notifications"
        action={
          unread > 0 && (
            <Button variant="default" leftSection={<IconChecks size={16} />} loading={markAll.isPending} onClick={() => markAll.mutate()}>
              Mark all as read
            </Button>
          )
        }
      >
        <Text c="dimmed">Status changes, reminders and deadlines for your requests. Important ones are emailed too.</Text>
      </PageHeader>
      <Stack>
        <SegmentedControl
          aria-label="Show"
          w="fit-content"
          value={unreadOnly ? "unread" : "all"}
          onChange={(value) => {
            setUnreadOnly(value === "unread");
            setPage(1);
          }}
          data={[
            { value: "all", label: "All" },
            { value: "unread", label: "Unread" },
          ]}
        />
        {list.isPending ? (
          <TableSkeleton />
        ) : list.isError ? (
          <LoadError what="your notifications" error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data.results.length === 0 ? (
          <EmptyState title={unreadOnly ? "Nothing unread" : "No notifications yet"}>You're all caught up.</EmptyState>
        ) : (
          <>
            <Paper withBorder radius="md" style={{ overflow: "hidden" }}>
              <NotificationList notifications={list.data.results} label="Notifications" />
            </Paper>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                {plural(list.data.count, "notification")}
              </Text>
              {list.data.count > 25 && <Pagination size="sm" value={page} onChange={setPage} total={Math.ceil(list.data.count / 25)} />}
            </Group>
          </>
        )}
      </Stack>
    </>
  );
}
