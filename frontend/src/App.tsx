import { Center, Stack, Text, Title } from "@mantine/core";
import { Route, Routes } from "react-router";

function Home() {
  return (
    <Center mih="100vh" p="md">
      <Stack align="center" gap="xs">
        <Title order={1}>Dataset Request Desk</Title>
        <Text c="dimmed">Request, fulfil and review robot training datasets.</Text>
      </Stack>
    </Center>
  );
}

function NotFound() {
  return (
    <Center mih="100vh" p="md">
      <Stack align="center" gap="xs">
        <Title order={1}>Page not found</Title>
        <Text c="dimmed">The address may be mistyped, or the page has moved.</Text>
      </Stack>
    </Center>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
