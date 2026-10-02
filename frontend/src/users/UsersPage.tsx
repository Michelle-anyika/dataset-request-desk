import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  NativeSelect,
  Pagination,
  Paper,
  PasswordInput,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconPencil, IconSearch, IconUserPlus } from "@tabler/icons-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import type { Role } from "../api/types";
import { useCreateUser, useUpdateUser, useUsers, type ManagedUser, type UserChanges } from "../api/users";
import { useUser } from "../auth/AuthProvider";
import { EmptyState, LoadError, PageHeader, TableSkeleton } from "../components/states";
import { formatDateTime, plural } from "../format";
import { usePageTitle } from "../usePageTitle";

const ROLES: { value: Role; label: string }[] = [
  { value: "client", label: "Client" },
  { value: "operator", label: "Operator" },
  { value: "admin", label: "Admin" },
];
const ROLE_COLORS: Record<Role, string> = { client: "gray", operator: "blue", admin: "brand" };
const roleLabel = (role: Role) => ROLES.find((r) => r.value === role)?.label ?? role;

export function UsersPage() {
  usePageTitle("Users");
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search.trim(), 300);
  const [role, setRole] = useState<Role | "">("");
  const [active, setActive] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<ManagedUser | "new" | null>(null);
  const users = useUsers({ search: debouncedSearch || undefined, role: role || undefined, is_active: active || undefined, page });

  return (
    <>
      <PageHeader
        title="Users"
        action={
          <Button leftSection={<IconUserPlus size={16} />} onClick={() => setEditing("new")}>
            New user
          </Button>
        }
      >
        <Text c="dimmed">Accounts for clients and staff. Accounts are deactivated, never deleted, so history keeps its authors.</Text>
      </PageHeader>
      <Stack>
        <Group gap="sm" align="flex-end">
          <TextInput
            type="search"
            aria-label="Search by name or email"
            placeholder="Search by name or email"
            leftSection={<IconSearch size={16} />}
            value={search}
            onChange={(event) => {
              setSearch(event.currentTarget.value);
              setPage(1);
            }}
            w={{ base: "100%", sm: 280 }}
          />
          <NativeSelect
            aria-label="Role"
            value={role}
            onChange={(event) => {
              setRole(event.currentTarget.value as Role | "");
              setPage(1);
            }}
            data={[{ value: "", label: "All roles" }, ...ROLES]}
          />
          <NativeSelect
            aria-label="Status"
            value={active}
            onChange={(event) => {
              setActive(event.currentTarget.value as "" | "true" | "false");
              setPage(1);
            }}
            data={[
              { value: "", label: "Active and deactivated" },
              { value: "true", label: "Active" },
              { value: "false", label: "Deactivated" },
            ]}
          />
        </Group>

        {users.isPending ? (
          <TableSkeleton />
        ) : users.isError ? (
          <LoadError what="the accounts" onRetry={() => void users.refetch()} />
        ) : users.data.results.length === 0 ? (
          <EmptyState title="No accounts match">Try another search or filter.</EmptyState>
        ) : (
          <>
            <Paper withBorder radius="md">
              <Table.ScrollContainer minWidth={760}>
                <Table verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Name</Table.Th>
                      <Table.Th>Organisation</Table.Th>
                      <Table.Th>Role</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Last sign-in</Table.Th>
                      <Table.Th aria-label="Actions" />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {users.data.results.map((account) => (
                      <Table.Tr key={account.id} c={account.is_active ? undefined : "dimmed"}>
                        <Table.Td>
                          <Text size="sm" fw={500}>
                            {account.full_name}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {account.email}
                          </Text>
                        </Table.Td>
                        <Table.Td>{account.organisation || "—"}</Table.Td>
                        <Table.Td>
                          <Badge variant="light" radius="sm" color={ROLE_COLORS[account.role]}>
                            {roleLabel(account.role)}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Badge variant={account.is_active ? "light" : "outline"} radius="sm" color={account.is_active ? "teal" : "gray"}>
                            {account.is_active ? "Active" : "Deactivated"}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{account.last_login ? formatDateTime(account.last_login) : "Never"}</Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Tooltip label="Edit">
                            <ActionIcon variant="subtle" color="gray" aria-label={`Edit ${account.full_name}`} onClick={() => setEditing(account)}>
                              <IconPencil size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Paper>
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                {plural(users.data.count, "account")}
              </Text>
              {users.data.count > 25 && <Pagination size="sm" value={page} onChange={setPage} total={Math.ceil(users.data.count / 25)} />}
            </Group>
          </>
        )}
      </Stack>
      {editing === "new" && <CreateUserModal onClose={() => setEditing(null)} />}
      {editing && editing !== "new" && <EditUserModal account={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function ErrorAlert({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Alert role="alert" color="red" variant="light" icon={<IconAlertCircle size={18} />}>
      {message}
    </Alert>
  );
}

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const create = useCreateUser();
  const [key] = useState(newIdempotencyKey); // one account per form, however many times it's submitted
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { email: "", full_name: "", role: "client" as Role, organisation: "", password: "" },
    validate: {
      email: (value) => (value.includes("@") ? null : "Enter the person's email address."),
      full_name: (value) => (value.trim() ? null : "Enter their name."),
      password: (value) => (value.length >= 12 ? null : "Use at least 12 characters."),
    },
  });

  const submit = form.onSubmit(async (values) => {
    setError(null);
    try {
      const created = await create.mutateAsync({ user: { ...values, email: values.email.trim(), full_name: values.full_name.trim() }, key });
      notifications.show({ color: "teal", title: "Account created", message: `${created.email} can sign in now.` });
      onClose();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 400) form.setErrors(failure.fieldErrors());
      else setError(failure instanceof ApiError ? failure.message : "We couldn't reach the server. Try again.");
    }
  });

  return (
    <Modal opened onClose={onClose} title="New user" centered>
      <form onSubmit={submit} noValidate>
        <Stack>
          <ErrorAlert message={error} />
          <TextInput label="Email" type="email" required data-autofocus {...form.getInputProps("email")} />
          <TextInput label="Full name" required {...form.getInputProps("full_name")} />
          <NativeSelect label="Role" data={ROLES} {...form.getInputProps("role")} />
          <TextInput label="Organisation" description="For clients: the company they order for." {...form.getInputProps("organisation")} />
          <PasswordInput
            label="Password"
            description="At least 12 characters. Share it with them safely; they can't reset it themselves yet."
            required
            autoComplete="new-password"
            {...form.getInputProps("password")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create user
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function EditUserModal({ account, onClose }: { account: ManagedUser; onClose: () => void }) {
  const me = useUser();
  const isMe = me.id === account.id;
  const update = useUpdateUser(account.id);
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      full_name: account.full_name,
      role: account.role,
      organisation: account.organisation,
      is_active: account.is_active,
      password: "",
    },
    validate: {
      full_name: (value) => (value.trim() ? null : "Enter their name."),
      password: (value) => (!value || value.length >= 12 ? null : "Use at least 12 characters, or leave it empty."),
    },
  });

  const submit = form.onSubmit(async (values) => {
    // Only what changed: the audit log then records exactly what the admin did.
    const changes: UserChanges = {};
    if (values.full_name.trim() !== account.full_name) changes.full_name = values.full_name.trim();
    if (values.role !== account.role) changes.role = values.role;
    if (values.organisation !== account.organisation) changes.organisation = values.organisation;
    if (values.is_active !== account.is_active) changes.is_active = values.is_active;
    if (values.password) changes.password = values.password;
    if (!Object.keys(changes).length) return onClose();

    setError(null);
    try {
      await update.mutateAsync(changes);
      notifications.show({ color: "teal", title: "Account updated", message: account.email });
      onClose();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 400) form.setErrors(failure.fieldErrors());
      else setError(failure instanceof ApiError ? failure.message : "We couldn't reach the server. Try again.");
    }
  });

  return (
    <Modal opened onClose={onClose} title={`Edit ${account.email}`} centered>
      <form onSubmit={submit} noValidate>
        <Stack>
          <ErrorAlert message={error} />
          <TextInput label="Full name" required {...form.getInputProps("full_name")} />
          <NativeSelect label="Role" data={ROLES} disabled={isMe} {...form.getInputProps("role")} />
          <TextInput label="Organisation" {...form.getInputProps("organisation")} />
          <Switch
            label="Active"
            description={
              isMe
                ? "You can't demote or deactivate your own account; ask another admin."
                : "Deactivating ends their sessions at once. Their history stays."
            }
            disabled={isMe}
            {...form.getInputProps("is_active", { type: "checkbox" })}
          />
          <PasswordInput
            label="New password"
            description="Leave empty to keep the current one. Changing it ends their sessions."
            autoComplete="new-password"
            {...form.getInputProps("password")}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={update.isPending}>
              Save changes
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
