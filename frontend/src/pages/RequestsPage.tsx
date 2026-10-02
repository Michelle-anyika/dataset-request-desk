import { Stack, Text, Title } from "@mantine/core";

import { useUser } from "../auth/AuthProvider";
import { usePageTitle } from "../usePageTitle";

/** The request list: "My requests" for clients, the request queue for staff. */
export function RequestsPage() {
  const user = useUser();
  const title = user.role === "client" ? "My requests" : "Request queue";
  usePageTitle(title);
  return (
    <Stack>
      <Title order={1}>{title}</Title>
      <Text c="dimmed">Requests appear here.</Text>
    </Stack>
  );
}
