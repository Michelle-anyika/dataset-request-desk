import { Alert, Box, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertCircle } from "@tabler/icons-react";
import { useState } from "react";
import { Navigate, useLocation, useNavigate, type Location } from "react-router";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { BrandMark } from "../layout/BrandMark";
import { HOME } from "../navigation";
import { usePageTitle } from "../usePageTitle";

/** The API says "Expected available in 540 seconds"; people read minutes. */
export function signInError(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    const seconds = Number(/(\d{1,6}) seconds/.exec(error.message)?.[1] ?? 60);
    const minutes = Math.max(1, Math.ceil(seconds / 60));
    return `Too many attempts. Try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`;
  }
  if (error instanceof ApiError && error.status < 500) return error.message;
  return "We couldn't reach the server. Check your connection and try again.";
}

/** A quick shape check before calling the API, which validates properly. No regex: nothing to backtrack. */
export function looksLikeEmail(value: string) {
  const at = value.indexOf("@");
  return at > 0 && value.indexOf(".", at + 2) > at + 1 && !value.endsWith(".") && !/\s/.test(value);
}

export function LoginPage() {
  usePageTitle("Sign in");
  const { status, user, signIn } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: Location } | null)?.from;
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: (value) =>
        !value.trim() ? "Enter your email address." : looksLikeEmail(value.trim()) ? null : "Enter a valid email address.",
      password: (value) => (value ? null : "Enter your password."),
    },
  });

  const destination = from ? `${from.pathname}${from.search}` : HOME;

  if (status === "signed-in" && user) return <Navigate to={destination} replace />;

  const submit = form.onSubmit(async ({ email, password }) => {
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      void navigate(destination, { replace: true });
    } catch (failure) {
      setError(signInError(failure));
      setSubmitting(false);
    }
  });

  return (
    <Center mih="100vh" p="md" bg="light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))">
      <Box w="100%" maw={400}>
        <Stack align="center" gap={6} mb="lg">
          <BrandMark size={44} />
          <Title order={1} fz="h2" ta="center">
            Sign in
          </Title>
          <Text c="dimmed" size="sm" ta="center">
            Dataset Request Desk
          </Text>
        </Stack>
        <Paper withBorder shadow="sm" radius="md" p="xl">
          <form onSubmit={submit} noValidate>
            <Stack>
              {error && (
                <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
                  {error}
                </Alert>
              )}
              <TextInput
                label="Email"
                type="email"
                autoComplete="username"
                required
                autoFocus
                {...form.getInputProps("email")}
              />
              <PasswordInput
                label="Password"
                autoComplete="current-password"
                required
                {...form.getInputProps("password")}
              />
              <Button type="submit" fullWidth loading={submitting} mt="xs">
                Sign in
              </Button>
            </Stack>
          </form>
        </Paper>
      </Box>
    </Center>
  );
}
