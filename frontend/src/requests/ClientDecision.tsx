import { Alert, Button, Group, Modal, Paper, Stack, Text, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconCheck, IconX } from "@tabler/icons-react";
import { useState } from "react";

import { describeError } from "../api/errors";
import { newIdempotencyKey } from "../api/idempotency";
import { isConflict, useTransition } from "../api/requests";
import type { DatasetRequest } from "../api/types";
import { daysSince, plural } from "../format";

type Decision = "accepted" | "rejected";

/** A delivered request waits for the client: accept it, or reject it with a reason for the rework. */
export function ClientDecision({ request }: { request: DatasetRequest }) {
  const [open, setOpen] = useState<Decision | null>(null);
  const waiting = daysSince(request.status_changed_at);
  return (
    <Paper withBorder radius="md" p="md" bg="var(--mantine-color-violet-light)">
      <Group justify="space-between" gap="md">
        <Stack gap={2}>
          <Text fw={600}>This delivery is waiting for your review</Text>
          <Text size="sm" c="dimmed">
            {plural(request.assigned_count, "episode")} delivered
            {waiting > 0 ? `, ${plural(waiting, "day")} ago` : " today"}. Check them below, then decide.
          </Text>
        </Stack>
        <Group gap="xs">
          <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setOpen("rejected")}>
            Reject
          </Button>
          <Button color="teal" leftSection={<IconCheck size={16} />} onClick={() => setOpen("accepted")}>
            Accept delivery
          </Button>
        </Group>
      </Group>
      {open && <DecisionModal request={request} decision={open} onClose={() => setOpen(null)} />}
    </Paper>
  );
}

function DecisionModal({ request, decision, onClose }: { request: DatasetRequest; decision: Decision; onClose: () => void }) {
  const transition = useTransition(request.id);
  const [key] = useState(newIdempotencyKey); // one key per decision: a retry can't decide twice
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rejecting = decision === "rejected";

  const confirm = async () => {
    if (rejecting && !reason.trim()) {
      setReasonError("Tell the team what to fix.");
      return;
    }
    setError(null);
    try {
      await transition.mutateAsync({ to: decision, comment: reason.trim(), key });
      notifications.show({
        color: rejecting ? "orange" : "teal",
        title: rejecting ? "Delivery rejected" : "Delivery accepted",
        message: rejecting ? "The team will rework it and deliver again." : "Thank you. The request is complete.",
      });
      onClose();
    } catch (failure) {
      if (isConflict(failure)) {
        // Decided elsewhere meanwhile (another tab or colleague): this dialog no longer applies.
        notifications.show({ color: "orange", title: "This delivery has changed", message: `${describeError(failure)} The page now shows its current status.` });
        onClose();
        return;
      }
      setError(describeError(failure));
    }
  };

  return (
    <Modal opened onClose={onClose} title={rejecting ? "Reject this delivery?" : "Accept this delivery?"} centered>
      <Stack>
        {error && (
          <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
            {error}
          </Alert>
        )}
        {rejecting ? (
          <Textarea
            label="Reason"
            description="What's wrong with the episodes? The team reworks the request from this."
            required
            autosize
            minRows={3}
            maxLength={2000}
            value={reason}
            error={reasonError}
            onChange={(event) => {
              setReason(event.currentTarget.value);
              setReasonError(null);
            }}
            data-autofocus
          />
        ) : (
          <Text size="sm">Accepting confirms the episodes meet your request. The request is then complete.</Text>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color={rejecting ? "orange" : "teal"} loading={transition.isPending} onClick={() => void confirm()}>
            {rejecting ? "Reject delivery" : "Accept"}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
