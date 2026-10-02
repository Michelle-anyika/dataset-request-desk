import { Alert, Button, Group, Modal, Paper, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconListCheck, IconPlayerPlay, IconRefresh, IconTruckDelivery } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { useRequestEvents, useTransition } from "../api/requests";
import type { DatasetRequest, RequestStatus } from "../api/types";
import { daysSince, plural } from "../format";

/** What staff can do next with a request. The workflow's own rules (apps.requests_desk.workflow) decide;
 * this only offers the steps that are possible, and shows the API's reason if one is refused. */
export function StaffActions({ request }: { request: DatasetRequest }) {
  const transition = useTransition(request.id);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelivery, setConfirmDelivery] = useState(false);

  const move = async (to: RequestStatus, done: string) => {
    setError(null);
    try {
      await transition.mutateAsync({ to, key: newIdempotencyKey() });
      notifications.show({ color: "teal", title: done, message: `${request.client.full_name} has been notified.` });
      setConfirmDelivery(false);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "We couldn't reach the server. Try again.");
    }
  };

  const errorAlert = error && (
    <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
      {error}
    </Alert>
  );
  const missing = request.episodes_requested - request.assigned_count;
  const assignLink = (
    <Button component={Link} to={`/requests/${request.id}/assign`} variant="default" leftSection={<IconListCheck size={16} />}>
      Assign episodes
    </Button>
  );

  switch (request.status) {
    case "submitted":
      return (
        <Panel title={`New request from ${request.client.full_name}`} text="Start work to assign episodes to it." error={errorAlert}>
          <Button leftSection={<IconPlayerPlay size={16} />} loading={transition.isPending} onClick={() => void move("in_progress", "Work started")}>
            Start work
          </Button>
        </Panel>
      );
    case "in_progress":
      return (
        <Panel
          title={missing > 0 ? `${plural(request.assigned_count, "episode")} of ${request.episodes_requested.toLocaleString("en-GB")} assigned` : "All episodes assigned"}
          text={missing > 0 ? `Assign ${plural(missing, "more episode")} to deliver.` : "Deliver when you've checked them."}
          error={confirmDelivery ? null : errorAlert}
        >
          {assignLink}
          <Button leftSection={<IconTruckDelivery size={16} />} disabled={missing > 0} onClick={() => setConfirmDelivery(true)}>
            Mark as delivered
          </Button>
          <Modal opened={confirmDelivery} onClose={() => setConfirmDelivery(false)} title="Deliver this request?" centered>
            <Stack>
              {errorAlert}
              <Text size="sm">
                {request.client.full_name} will be asked to review {plural(request.assigned_count, "episode")} and accept or
                reject the delivery.
              </Text>
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setConfirmDelivery(false)}>
                  Cancel
                </Button>
                <Button loading={transition.isPending} onClick={() => void move("delivered", "Delivered")}>
                  Deliver
                </Button>
              </Group>
            </Stack>
          </Modal>
        </Panel>
      );
    case "rejected":
      return <RejectedPanel request={request} error={errorAlert} pending={transition.isPending} onRework={() => void move("in_progress", "Rework started")} assignLink={assignLink} />;
    case "delivered":
      return (
        <Panel
          title={`Waiting for ${request.client.full_name} to review`}
          text={`Delivered ${daysSince(request.status_changed_at) ? `${plural(daysSince(request.status_changed_at), "day")} ago` : "today"}. The client is reminded automatically, and you're told if it waits too long.`}
        />
      );
    default:
      return <Panel title="Complete" text={`${request.client.full_name} accepted the delivery.`} />;
  }
}

function RejectedPanel({
  request,
  error,
  pending,
  onRework,
  assignLink,
}: {
  request: DatasetRequest;
  error: ReactNode;
  pending: boolean;
  onRework: () => void;
  assignLink: ReactNode;
}) {
  const events = useRequestEvents(request.id);
  const rejection = events.data?.results.filter((event) => event.to_status === "rejected").at(-1);
  const who = rejection?.changed_by.full_name ?? request.client.full_name;
  return (
    <Panel
      title={`${who} rejected the delivery`}
      text={rejection?.comment ? `“${rejection.comment}”` : "Start the rework, fix the episodes and deliver again."}
      error={error}
    >
      {assignLink}
      <Button leftSection={<IconRefresh size={16} />} loading={pending} onClick={onRework}>
        Start rework
      </Button>
    </Panel>
  );
}

function Panel({ title, text, error, children }: { title: string; text: string; error?: ReactNode; children?: ReactNode }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        {error}
        <Group justify="space-between" gap="md">
          <Stack gap={2}>
            <Text fw={600}>{title}</Text>
            <Text size="sm" c="dimmed">
              {text}
            </Text>
          </Stack>
          {children && <Group gap="xs">{children}</Group>}
        </Group>
      </Stack>
    </Paper>
  );
}
