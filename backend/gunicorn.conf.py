"""Gunicorn (production server) settings. Every value can be changed with an environment variable.

Requests here mostly wait on PostgreSQL, so threaded workers serve several at once per process. Each thread
keeps its own database connection, so ``WEB_CONCURRENCY x GUNICORN_THREADS`` must stay below the database's
connection limit (PostgreSQL's default is 100; 3 x 8 = 24).
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "8"))

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))  # a stuck request is killed, freeing its worker
graceful_timeout = 30  # on deploy, in-flight requests get this long to finish
keepalive = 5

# Recycle each worker after about a thousand requests (jittered so they don't all restart together):
# protection against slow memory growth.
max_requests = 1000
max_requests_jitter = 100

# Worker heartbeat files in memory, not on a possibly slow container disk (Gunicorn docs' advice for
# containers). Only heartbeats live here, nothing sensitive, so the temp-dir warning does not apply.
worker_tmp_dir = "/dev/shm"  # noqa: S108
accesslog = None  # one structured line per request comes from RequestLoggingMiddleware instead
errorlog = "-"
