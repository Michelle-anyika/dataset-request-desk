// Load test: 5,000 requests per scenario from 100 concurrent virtual users, against the running stack.
//   docker run --rm --network dataset-request-desk_default -v "$PWD/loadtest:/scripts" \
//     -e BASE_URL=http://api:8000 grafana/k6 run /scripts/api-load.js
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  scenarios: {
    analytics_one_year: {
      executor: "shared-iterations",
      vus: 100,
      iterations: 5000,
      maxDuration: "10m",
      exec: "analytics",
    },
    request_list: {
      executor: "shared-iterations",
      vus: 100,
      iterations: 5000,
      maxDuration: "10m",
      startTime: "0s",
      exec: "requestList",
    },
  },
  thresholds: {
    "http_req_failed{scenario:analytics_one_year}": ["rate<0.01"],
    "http_req_failed{scenario:request_list}": ["rate<0.01"],
    // 200 users at once on 24 server threads (3 workers x 8): most of the latency is waiting in line,
    // so these bounds fit one laptop. Measured on one: p95 3.5 s (analytics), 3.7 s (request list).
    "http_req_duration{scenario:analytics_one_year}": ["p(95)<5000"],
    "http_req_duration{scenario:request_list}": ["p(95)<5000"],
  },
};

export function setup() {
  const login = http.post(
    `${BASE_URL}/api/auth/login/`,
    JSON.stringify({ email: "ops1@example.com", password: "ops123" }),
    { headers: { "Content-Type": "application/json" } },
  );
  return { access: login.json("access") };
}

const auth = (data) => ({ headers: { Authorization: `Bearer ${data.access}` } });

export function analytics(data) {
  const res = http.get(`${BASE_URL}/api/analytics/?from=2025-09-02&to=2026-09-01`, auth(data));
  check(res, { "analytics 200": (r) => r.status === 200 });
}

export function requestList(data) {
  const res = http.get(`${BASE_URL}/api/requests/`, auth(data));
  check(res, { "requests 200": (r) => r.status === 200 });
}
