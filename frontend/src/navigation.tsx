import { IconInbox, IconListDetails, IconUsers } from "@tabler/icons-react";
import type { ComponentType } from "react";

import type { Role } from "./api/types";

export interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<{ size?: number; stroke?: number }>;
  roles: Role[];
}

const STAFF: Role[] = ["operator", "admin"];

/** The main navigation. Each role sees only its own pages; the API enforces the same rules. */
export const NAV_ITEMS: NavItem[] = [
  { label: "My requests", to: "/requests", icon: IconInbox, roles: ["client"] },
  { label: "Request queue", to: "/requests", icon: IconListDetails, roles: STAFF },
  { label: "Users", to: "/users", icon: IconUsers, roles: ["admin"] },
];

export function navFor(role: Role) {
  return NAV_ITEMS.filter((item) => item.roles.includes(role));
}

/** Where everyone starts after signing in: the request list, which is "My requests" for clients and the
 * request queue for staff. */
export const HOME = "/requests";
