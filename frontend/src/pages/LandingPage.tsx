import { Box, Button, Container, Group, Paper, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import {
  IconArrowRight,
  IconChecklist,
  IconFileImport,
  IconInbox,
  IconListCheck,
  IconSend,
  IconShieldLock,
  IconUserCog,
  type Icon,
} from "@tabler/icons-react";
import { Link, Navigate } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { FullPageLoader } from "../auth/RequireAuth";
import { BrandMark } from "../layout/BrandMark";
import { HOME } from "../navigation";
import { usePageTitle } from "../usePageTitle";

const ROLES: { icon: Icon; title: string; text: string }[] = [
  {
    icon: IconInbox,
    title: "Clients",
    text: "Ask for the episodes you need: the task, how many and by when. Follow each request, then accept the delivery or send it back with a reason.",
  },
  {
    icon: IconListCheck,
    title: "Operators",
    text: "Import recording sessions, work through the request queue and assign good or usable episodes until each request is complete.",
  },
  {
    icon: IconUserCog,
    title: "Admins",
    text: "Everything operators do, plus creating accounts, choosing each person's role and deactivating accounts that are no longer needed.",
  },
];

const STEPS: { icon: Icon; title: string; text: string }[] = [
  { icon: IconSend, title: "Request", text: "A client submits a dataset request." },
  { icon: IconFileImport, title: "Assign", text: "An operator assigns matching episodes from the catalogue." },
  { icon: IconChecklist, title: "Deliver", text: "Once enough are assigned, the operator delivers." },
  { icon: IconArrowRight, title: "Review", text: "The client accepts, or rejects it for rework." },
];

/** What a visitor sees first: what the platform is, who it's for and how to get in. Signed-in users go
 * straight to their requests. */
export function LandingPage() {
  usePageTitle("Robot teleoperation datasets, on request");
  const { status } = useAuth();
  if (status === "loading") return <FullPageLoader />;
  if (status === "signed-in") return <Navigate to={HOME} replace />;

  const signIn = (
    <Button component={Link} to="/login" size="md" rightSection={<IconArrowRight size={18} />}>
      Sign in
    </Button>
  );

  return (
    <Box mih="100vh" bg="light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))">
      <Box component="header" py="md" style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}>
        <Container size="lg">
          <Group justify="space-between">
            <Group gap={10}>
              <BrandMark size={32} />
              <Text fw={650}>Dataset Request Desk</Text>
            </Group>
            <Button component={Link} to="/login" variant="default">
              Sign in
            </Button>
          </Group>
        </Container>
      </Box>

      <Container component="main" size="lg" py={{ base: 40, sm: 72 }}>
        <Stack gap={56}>
          <Stack gap="md" maw={680}>
            <Text c="light-dark(var(--mantine-color-brand-8), var(--mantine-color-brand-3))" fw={600} size="sm" tt="uppercase">
              Robot teleoperation datasets
            </Text>
            <Title order={1} fz={{ base: 32, sm: 44 }} lh={1.15}>
              Request, assign and deliver robot training data in one place.
            </Title>
            <Text size="lg" c="dimmed">
              Dataset Request Desk replaces the operations spreadsheet. Clients ask for recorded episodes, operators
              fulfil them from the episode catalogue, and every step is tracked with who did it and when.
            </Text>
            <Group mt="sm">{signIn}</Group>
          </Stack>

          <Stack gap="md" component="section" aria-labelledby="roles-title">
            <Title order={2} fz="h3" id="roles-title">
              Who it's for
            </Title>
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              {ROLES.map(({ icon: RoleIcon, title, text }) => (
                <Paper key={title} withBorder radius="md" p="lg">
                  <ThemeIcon variant="light" size={40} radius="md" mb="sm" aria-hidden>
                    <RoleIcon size={22} />
                  </ThemeIcon>
                  <Title order={3} fz="h4" mb={6}>
                    {title}
                  </Title>
                  <Text size="sm" c="dimmed">
                    {text}
                  </Text>
                </Paper>
              ))}
            </SimpleGrid>
          </Stack>

          <Stack gap="md" component="section" aria-labelledby="how-title">
            <Title order={2} fz="h3" id="how-title">
              How it works
            </Title>
            <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} component="ol" m={0} p={0} style={{ listStyle: "none" }}>
              {STEPS.map(({ icon: StepIcon, title, text }, index) => (
                <Paper key={title} component="li" withBorder radius="md" p="md">
                  <Group gap="sm" mb={6} wrap="nowrap">
                    <ThemeIcon variant="filled" size={28} radius="xl" aria-hidden>
                      <StepIcon size={16} />
                    </ThemeIcon>
                    <Text fw={600}>
                      {index + 1}. {title}
                    </Text>
                  </Group>
                  <Text size="sm" c="dimmed">
                    {text}
                  </Text>
                </Paper>
              ))}
            </SimpleGrid>
          </Stack>

          <Paper withBorder radius="md" p="lg" component="section" aria-labelledby="access-title">
            <Group justify="space-between" gap="md">
              <Group gap="md" wrap="nowrap" align="flex-start">
                <ThemeIcon variant="light" size={40} radius="md" aria-hidden>
                  <IconShieldLock size={22} />
                </ThemeIcon>
                <Stack gap={4}>
                  <Title order={2} fz="h4" id="access-title">
                    Getting an account
                  </Title>
                  <Text size="sm" c="dimmed" maw={560}>
                    This is an internal platform, so there is no public sign-up. Your administrator creates your account
                    and chooses your role. Each person sees only what their role allows, and the server checks it on
                    every request.
                  </Text>
                </Stack>
              </Group>
              {signIn}
            </Group>
          </Paper>
        </Stack>
      </Container>

      <Box component="footer" py="lg" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
        <Container size="lg">
          <Text size="sm" c="dimmed">
            Dataset Request Desk · internal platform for robot teleoperation dataset requests
          </Text>
        </Container>
      </Box>
    </Box>
  );
}
