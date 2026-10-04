# Performance and concurrency

How the API behaves under load, how we measured it, and what we changed.

## The load test

[`loadtest/api-load.js`](../loadtest/api-load.js) (k6) sends **10,000 requests from 200 concurrent users**:
5,000 full-year analytics reports and 5,000 request-list pages, all at once. The database holds 100,000
dataset requests and the 200,000-row episode export.

```bash
THROTTLE_USER_RATE=1000000/hour docker compose up --build -d --wait   # lift the per-user limit for the test
docker run --rm --network dataset-request-desk_default -v "$PWD/loadtest:/scripts" \
  -e BASE_URL=http://api:8000 grafana/k6 run /scripts/api-load.js
```

## Results (one laptop, Docker Desktop)

| | Before | After |
|---|---|---|
| Completed | 8,702 of 10,000 (stopped at the 10 min limit) | **10,000 of 10,000 in 92 s** |
| Failed | 2.26 % | **0 %** |
| Throughput | 14.5 req/s | **108 req/s** (7.5x) |
| p95 latency | ~18 s | **3.6 s** |

With 200 users on 24 server threads, most of the remaining latency is waiting for a free thread. That is
fixed by adding workers or instances, not by changing code.

## What changed, and why

1. **Analytics cache with stampede protection** ([`apps/analytics/cache.py`](../backend/apps/analytics/cache.py)).
   Every staff member sees the same numbers for a range, so one computed report serves everyone.
   - *Correct by invalidation, not by expiry.* Results are stored under a data version. A submission, a
     status change or an import sets a new version after its transaction commits, so a stale report is
     never read.
   - *Single flight.* When many requests miss the cache at once, one takes a short lock (`cache.add`, which
     is atomic) and computes. The others wait for its result instead of all running the same aggregation.
   - The cache is database-backed, so all workers and containers share it.
2. **Request list: per-row subquery instead of `JOIN … GROUP BY`.** The active-assignment count was being
   aggregated across the whole table on every page, about 3 s a page at 100k requests, with the database
   at 800 % CPU. It is now a correlated subquery that PostgreSQL runs only for the 25 rows on the page.
   A test fails if `GROUP BY` comes back.
3. **Indexes** for the hot filters: `dataset_requests(created_at)` and `episodes(task_name, recorded_at)`.
   The task episode count went from 52.9 ms to 0.11 ms, and the request list from a sequential scan and
   sort to a 0.3 ms index scan.
4. **Gunicorn with threads** ([`gunicorn.conf.py`](../backend/gunicorn.conf.py)): 3 workers x 8 threads, since
   requests mostly wait on PostgreSQL. A 30 s timeout kills stuck requests, and workers restart after
   about 1,000 requests to guard against memory growth.
5. **Query budgets in tests.** List and report endpoints assert a maximum number of queries, so an N+1
   regression fails CI.

## Concurrency safety (writes)

- **Locks:** state changes take row locks (`select_for_update`). A partial unique index makes the database
  refuse two active requests on one episode. The CSV import holds an advisory lock so two imports cannot
  interleave.
- **Idempotency:** re-importing the same file updates rows instead of duplicating them, and reminders are
  sent once per request per day.
- **Rate limits:** per IP and per user, with stricter limits on login.
