import { Alert, Button, Center, Group, Stack, Text, Title } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocation } from "react-router";

interface Props {
  children: ReactNode;
  fallback: ReactNode;
}

/** Catches a crash while rendering, so one broken screen shows a way out instead of a blank page. The error
 * itself stays in the console: its message is for developers, not for the people using the app. */
class Boundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error while rendering", error, info.componentStack);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function reload() {
  window.location.reload();
}

/** Around each page, inside the layout: navigation keeps working, and moving to another page starts afresh. */
export function PageErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <Boundary
      key={pathname}
      fallback={
        <Alert role="alert" color="red" variant="light" icon={<IconAlertTriangle size={18} />}>
          <Stack gap="xs" align="flex-start">
            {/* The page's own heading never rendered, so this is the page's heading now. */}
            <Title order={1} fz="h4">
              Something went wrong on this page
            </Title>
            <Text size="sm">Reload the page to try again. If it keeps happening, use the menu to carry on elsewhere.</Text>
            <Button size="xs" variant="light" color="red" onClick={reload}>
              Reload the page
            </Button>
          </Stack>
        </Alert>
      }
    >
      {children}
    </Boundary>
  );
}

/** The last resort, around the whole app. */
export function AppErrorBoundary({ children }: { children: ReactNode }) {
  return (
    <Boundary
      fallback={
        <Center mih="100vh" p="md">
          <Stack align="center" gap="sm" maw={420} ta="center">
            <Title order={1} fz="h3">
              Something went wrong
            </Title>
            <Text c="dimmed">Reload the page to try again.</Text>
            <Group>
              <Button onClick={reload}>Reload</Button>
            </Group>
          </Stack>
        </Center>
      }
    >
      {children}
    </Boundary>
  );
}
