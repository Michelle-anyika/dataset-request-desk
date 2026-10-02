import { Stack, Text, Title } from "@mantine/core";

import { useUser } from "../auth/AuthProvider";
import { MyRequestsPage } from "../requests/MyRequestsPage";
import { usePageTitle } from "../usePageTitle";

/** The request list: "My requests" for clients, the request queue for staff. */
export function RequestsPage() {
  const user = useUser();
  return user.role === "client" ? <MyRequestsPage /> : <RequestQueuePage />;
}

function RequestQueuePage() {
  usePageTitle("Request queue");
  return (
    <Stack>
      <Title order={1}>Request queue</Title>
      <Text c="dimmed">Requests appear here.</Text>
    </Stack>
  );
}
