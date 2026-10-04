import { Alert, Anchor, Button, Group, NumberInput, Paper, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconArrowLeft } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { describeError } from "../api/errors";
import { newIdempotencyKey } from "../api/idempotency";
import { useSubmitRequest } from "../api/requests";
import { PageHeader } from "../components/states";
import { todayIso } from "../format";
import { usePageTitle } from "../usePageTitle";

const MAX_EPISODES = 1_000_000; // as the API (MAX_EPISODES_PER_REQUEST)

export function NewRequestPage() {
  usePageTitle("New request");
  const navigate = useNavigate();
  const submit = useSubmitRequest();
  // One key per filled-in form: if the network fails after the server saved it, resubmitting is safe.
  const [key] = useState(newIdempotencyKey);
  const [formError, setFormError] = useState<string | null>(null);

  const form = useForm({
    initialValues: { task_name: "", episodes_requested: 100 as number | string, deadline: "", notes: "" },
    validate: {
      task_name: (value) => (value.trim() ? null : "Describe the task."),
      episodes_requested: (value) =>
        Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= MAX_EPISODES
          ? null
          : `Enter a whole number from 1 to ${MAX_EPISODES.toLocaleString("en-GB")}.`,
      deadline: (value) => (!value ? "Choose a deadline." : value < todayIso() ? "The deadline can't be in the past." : null),
    },
  });

  const onSubmit = form.onSubmit(async (values) => {
    setFormError(null);
    try {
      const created = await submit.mutateAsync({
        key,
        request: {
          task_name: values.task_name.trim(),
          episodes_requested: Number(values.episodes_requested),
          deadline: values.deadline,
          notes: values.notes.trim(),
        },
      });
      notifications.show({ color: "teal", title: "Request submitted", message: "The team has been notified." });
      void navigate(`/requests/${created.id}`, { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) {
        form.setErrors(error.fieldErrors());
        if (!Object.keys(error.fieldErrors()).length) setFormError(error.message);
      } else {
        setFormError(describeError(error));
      }
    }
  });

  return (
    <>
      <Anchor component={Link} to="/requests" size="sm" c="dimmed">
        <Group gap={4}>
          <IconArrowLeft size={14} /> My requests
        </Group>
      </Anchor>
      <PageHeader title="New request">
        <Text c="dimmed">Tell the team what you need. They'll be notified as soon as you submit.</Text>
      </PageHeader>
      <Paper withBorder radius="md" p="lg" maw={640}>
        <form onSubmit={onSubmit} noValidate>
          <Stack>
            {formError && (
              <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
                {formError}
              </Alert>
            )}
            <TextInput
              label="Task"
              description="What the robot does in the episodes, e.g. “pick cup”."
              required
              maxLength={120}
              {...form.getInputProps("task_name")}
            />
            <Group grow align="flex-start">
              <NumberInput
                label="Episodes requested"
                required
                min={1}
                max={MAX_EPISODES}
                allowDecimal={false}
                allowNegative={false}
                thousandSeparator=","
                {...form.getInputProps("episodes_requested")}
              />
              <TextInput label="Deadline" type="date" required min={todayIso()} {...form.getInputProps("deadline")} />
            </Group>
            <Textarea
              label="Notes"
              description="Anything that helps: environment, objects, what to avoid."
              autosize
              minRows={3}
              maxLength={2000}
              {...form.getInputProps("notes")}
            />
            <Group justify="flex-end" mt="xs">
              <Button component={Link} to="/requests" variant="default">
                Cancel
              </Button>
              <Button type="submit" loading={submit.isPending}>
                Submit request
              </Button>
            </Group>
          </Stack>
        </form>
      </Paper>
    </>
  );
}
