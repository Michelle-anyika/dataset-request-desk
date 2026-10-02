import { Stack, Title } from "@mantine/core";

import { usePageTitle } from "../usePageTitle";

export function UsersPage() {
  usePageTitle("Users");
  return (
    <Stack>
      <Title order={1}>Users</Title>
    </Stack>
  );
}
