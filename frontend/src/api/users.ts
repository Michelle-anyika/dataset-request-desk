import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";
import type { Page, Role } from "./types";

export type ManagedUser = components["schemas"]["ManagedUser"];
export type NewUser = components["schemas"]["UserCreateRequest"];
export type UserChanges = components["schemas"]["PatchedUserUpdateRequest"];

export interface UserFilters {
  search?: string;
  role?: Role;
  is_active?: "true" | "false";
  page?: number;
}

export function useUsers(filters: UserFilters) {
  return useQuery({
    queryKey: ["users", filters],
    queryFn: () => api<Page<ManagedUser>>("/api/users/", { query: { ...filters } }),
    placeholderData: keepPreviousData,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ user, key }: { user: NewUser; key: string }) =>
      api<ManagedUser>("/api/users/", { method: "POST", body: user, headers: { "Idempotency-Key": key } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: UserChanges) => api<ManagedUser>(`/api/users/${id}/`, { method: "PATCH", body: changes }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}
