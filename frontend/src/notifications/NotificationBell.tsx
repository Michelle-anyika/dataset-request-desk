import { ActionIcon, Anchor, Badge, Box, Button, Divider, Group, Indicator, Popover, ScrollArea, Stack, Text } from "@mantine/core";
import { IconBell, IconChecks } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useMarkAllRead, useMarkRead, useNotifications, useUnreadCount, type Notification } from "../api/notifications";
import { daysSince, formatDateTime } from "../format";

/** "5 min ago", "3 h ago", "2 days ago", then the date. */
export function timeAgo(value: string, now = Date.now()) {
  const minutes = Math.floor((now - Date.parse(value)) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
  const days = daysSince(value, new Date(now));
  return days < 7 ? `${days} day${days === 1 ? "" : "s"} ago` : formatDateTime(value);
}

export function NotificationBell() {
  const [opened, setOpened] = useState(false);
  const summary = useUnreadCount();
  const unread = summary.data?.unread ?? 0;
  const recent = useNotifications({ page_size: 10 }, { enabled: opened });
  const markAll = useMarkAllRead();

  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-end" width={360} shadow="md" withinPortal>
      <Popover.Target>
        <Indicator
          disabled={!unread}
          label={unread > 99 ? "99+" : unread}
          size={18}
          offset={4}
          color="red"
          aria-hidden={false}
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            size="lg"
            aria-label={`Notifications, ${unread ? `${unread} unread` : "none unread"}`}
            onClick={() => setOpened((open) => !open)}
          >
            <IconBell size={20} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Group justify="space-between" px="md" py="sm">
          <Text fw={600}>Notifications</Text>
          {unread > 0 && (
            <Button
              size="compact-xs"
              variant="subtle"
              leftSection={<IconChecks size={14} />}
              loading={markAll.isPending}
              onClick={() => markAll.mutate()}
            >
              Mark all as read
            </Button>
          )}
        </Group>
        <Divider />
        <ScrollArea.Autosize mah={380}>
          {recent.isPending ? (
            <Text size="sm" c="dimmed" p="md">
              Loading…
            </Text>
          ) : recent.isError ? (
            <Text size="sm" c="dimmed" p="md">
              We couldn't load your notifications.
            </Text>
          ) : recent.data.results.length === 0 ? (
            <Text size="sm" c="dimmed" p="md">
              You're all caught up.
            </Text>
          ) : (
            <NotificationList notifications={recent.data.results} label="Recent notifications" onOpen={() => setOpened(false)} />
          )}
        </ScrollArea.Autosize>
        <Divider />
        <Box px="md" py="xs">
          <Anchor component={Link} to="/notifications" size="sm" onClick={() => setOpened(false)}>
            See all notifications
          </Anchor>
        </Box>
      </Popover.Dropdown>
    </Popover>
  );
}

/** A list of notifications; choosing one marks it read and opens its request. */
export function NotificationList({ notifications, label, onOpen }: { notifications: Notification[]; label: string; onOpen?: () => void }) {
  const navigate = useNavigate();
  const markRead = useMarkRead();
  return (
    <Stack component="ul" aria-label={label} gap={0} m={0} p={0} style={{ listStyle: "none" }}>
      {notifications.map((notification) => {
        const unread = !notification.read_at;
        return (
          <Box
            component="li"
            key={notification.id}
            px="md"
            py="sm"
            bg={unread ? "light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-6))" : undefined}
            style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}
          >
            <Anchor
              component={Link}
              to={`/requests/${notification.request.id}`}
              c="var(--mantine-color-text)"
              underline="never"
              fw={unread ? 600 : 400}
              size="sm"
              onClick={(event) => {
                event.preventDefault();
                // Closing the popover unmounts this list, which drops per-call mutate callbacks: so mark it
                // read and open the request straight away. The hook's own onSuccess refreshes the count.
                if (unread) markRead.mutate(notification.id);
                onOpen?.();
                void navigate(`/requests/${notification.request.id}`);
              }}
            >
              {notification.message}
            </Anchor>
            <Group gap={6} mt={4}>
              <Text size="xs" c="dimmed">
                {timeAgo(notification.created_at)}
              </Text>
              {unread && (
                <Badge size="xs" variant="dot" color="brand">
                  Unread
                </Badge>
              )}
            </Group>
          </Box>
        );
      })}
    </Stack>
  );
}
