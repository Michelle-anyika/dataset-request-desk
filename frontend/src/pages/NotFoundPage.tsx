import { Button, Center, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router";

import { usePageTitle } from "../usePageTitle";

export function NotFoundPage() {
  usePageTitle("Page not found");
  return (
    <Center mih="60vh" p="md">
      <Stack align="center" gap="sm">
        <Title order={1}>Page not found</Title>
        <Text c="dimmed">The address may be mistyped, or the page isn't available to your account.</Text>
        <Button component={Link} to="/" variant="light">
          Go to the start page
        </Button>
      </Stack>
    </Center>
  );
}
