import { Badge } from "@mantine/core";

import type { RequestStatus } from "../api/types";

export const STATUS_LABELS: Record<RequestStatus, string> = {
  submitted: "Submitted",
  in_progress: "In progress",
  delivered: "Delivered",
  accepted: "Accepted",
  rejected: "Rejected",
};

// Never the brand red, and never colour alone: the label always says the status.
const STATUS_COLORS: Record<RequestStatus, string> = {
  submitted: "gray",
  in_progress: "blue",
  delivered: "violet",
  accepted: "teal",
  rejected: "orange",
};

export const STATUSES = Object.keys(STATUS_LABELS) as RequestStatus[];

export function StatusBadge({ status }: { status: RequestStatus }) {
  return (
    <Badge color={STATUS_COLORS[status]} variant="light" radius="sm">
      {STATUS_LABELS[status]}
    </Badge>
  );
}
