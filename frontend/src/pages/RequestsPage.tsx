import { useUser } from "../auth/AuthProvider";
import { MyRequestsPage } from "../requests/MyRequestsPage";
import { RequestQueuePage } from "../requests/RequestQueuePage";

/** The request list: "My requests" for clients, the request queue for staff. */
export function RequestsPage() {
  const user = useUser();
  return user.role === "client" ? <MyRequestsPage /> : <RequestQueuePage />;
}
