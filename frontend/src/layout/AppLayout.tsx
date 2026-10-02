import {
  ActionIcon,
  AppShell,
  Avatar,
  Burger,
  Group,
  Menu,
  NavLink,
  Text,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconChevronDown, IconDevices, IconLogout, IconMoon, IconSun } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Link, NavLink as RouterNavLink, Outlet } from "react-router";

import { useAuth, useUser } from "../auth/AuthProvider";
import { navFor } from "../navigation";
import { BrandMark } from "./BrandMark";

const ROLE_LABELS = { client: "Client", operator: "Operator", admin: "Admin" } as const;

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

/** The frame of every signed-in page: header, role navigation and the page itself. */
export function AppLayout({ headerExtras }: { headerExtras?: ReactNode }) {
  const user = useUser();
  const [opened, { toggle, close }] = useDisclosure();

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="lg"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <UnstyledButton component={Link} to="/" aria-label="Dataset Request Desk, start page">
              <Group gap={10} wrap="nowrap">
                <BrandMark />
                <Text fw={650} visibleFrom="xs">
                  Dataset Request Desk
                </Text>
              </Group>
            </UnstyledButton>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {headerExtras}
            <ColorSchemeToggle />
            <AccountMenu />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" aria-label="Main">
        {navFor(user.role).map((item) => (
          <NavLink
            key={`${item.to}-${item.label}`}
            component={RouterNavLink}
            to={item.to}
            end={item.to === "/requests"}
            label={item.label}
            leftSection={<item.icon size={18} stroke={1.7} />}
            onClick={close}
            styles={{ root: { borderRadius: "var(--mantine-radius-md)" } }}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("light");
  const next = scheme === "dark" ? "light" : "dark";
  return (
    <ActionIcon
      variant="subtle"
      color="gray"
      size="lg"
      onClick={() => setColorScheme(next)}
      aria-label={`Switch to ${next} mode`}
    >
      {scheme === "dark" ? <IconSun size={20} /> : <IconMoon size={20} />}
    </ActionIcon>
  );
}

function AccountMenu() {
  const user = useUser();
  const { signOut, signOutEverywhere } = useAuth();
  return (
    <Menu position="bottom-end" width={240} withinPortal>
      <Menu.Target>
        <UnstyledButton aria-label="Account menu">
          <Group gap={8} wrap="nowrap">
            <Avatar color="brand" radius="xl" size={32}>
              {initials(user.full_name)}
            </Avatar>
            <Text size="sm" fw={500} visibleFrom="sm">
              {user.full_name}
            </Text>
            <IconChevronDown size={14} />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>
          {user.email} · {ROLE_LABELS[user.role]}
        </Menu.Label>
        <Menu.Item leftSection={<IconLogout size={16} />} onClick={() => void signOut()}>
          Sign out
        </Menu.Item>
        <Menu.Item leftSection={<IconDevices size={16} />} onClick={() => void signOutEverywhere()}>
          Sign out of all devices
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
