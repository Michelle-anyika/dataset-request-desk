# Architecture

This document describes the Dataset Request Desk from the outside in, following the
[C4 model](https://c4model.com): system context, containers, then components, followed by the
behaviour that matters most (request lifecycle, status workflow, CSV import) and how the system is
built and deployed.

Diagrams are written in [Mermaid](https://mermaid.js.org) so they are versioned and reviewed with
the code. The data model is in [erd.dbml](erd.dbml) (render at [dbdiagram.io](https://dbdiagram.io)).
The reasoning behind each choice is in the decision log in [PLAN.md](../PLAN.md#14-decision-log-for-notesmd).

## 1. System context

Who uses the system and what it depends on.

```mermaid
flowchart LR
    client(["<b>Client</b><br/>Robotics company<br/>that needs training data"])
    operator(["<b>Operator</b><br/>Operations staff who<br/>fulfil requests"])
    admin(["<b>Admin</b><br/>Manages accounts<br/>and roles"])

    desk["<b>Dataset Request Desk</b><br/>Tracks dataset requests from<br/>submission to acceptance"]

    recording["<b>Recording system</b><br/>Existing system that<br/>captures teleoperation episodes"]

    client -- "Submits requests,<br/>accepts or rejects deliveries" --> desk
    operator -- "Imports episodes, assigns them,<br/>moves requests through the workflow" --> desk
    admin -- "Creates users,<br/>changes roles" --> desk
    recording -. "CSV export<br/>(episodes.csv)" .-> operator

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff
    classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
    class client,operator,admin person
    class desk system
    class recording external
```

The recording system is **not integrated directly**: operators upload its CSV export. This keeps
the first version decoupled from a system we don't control, and the import is built to be re-run
safely on the same file.

## 2. Containers

The separately running parts and how they communicate.

```mermaid
flowchart LR
    user(["<b>User</b><br/>Client, operator or admin"])

    subgraph desk["Dataset Request Desk"]
        direction LR
        web["<b>Web app</b><br/><i>React, TypeScript, Vite</i><br/>Role-based screens,<br/>notification bell"]
        api["<b>API</b><br/><i>Django REST Framework, gunicorn</i><br/>Authentication, authorization,<br/>domain rules, import, analytics"]
        scheduler["<b>Scheduler</b><br/><i>manage.py send_reminders</i><br/>Hourly reminders and<br/>deadline warnings"]
        cli["<b>Management commands</b><br/><i>manage.py</i><br/>seed, import_episodes"]
        db[("<b>Database</b><br/><i>PostgreSQL 16</i><br/>Users, episodes, requests,<br/>events, assignments,<br/>notifications, imports")]
    end

    email[["<b>Email</b><br/>SMTP provider,<br/>to the user's inbox"]]
    sentry[["<b>Error tracking</b><br/>Sentry"]]
    logs[["<b>Platform logs</b><br/>stdout, one JSON line<br/>per request"]]
    uptime[["<b>Uptime monitor</b><br/>calls /health"]]

    user -- "HTTPS" --> web
    web -- "JSON over HTTPS<br/>Bearer JWT" --> api
    api -- "SQL" --> db
    scheduler -- "SQL" --> db
    cli -- "SQL" --> db
    api -- "delivery and<br/>rejection emails" --> email
    scheduler -- "reminder emails" --> email
    api -. "unhandled errors" .-> sentry
    api -. "structured logs" .-> logs
    uptime -. "GET /health" .-> api

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef container fill:#438dd5,stroke:#2e6295,color:#fff
    classDef external fill:#8a8a8a,stroke:#6b6b6b,color:#fff
    class user person
    class web,api,scheduler,cli,db container
    class email,sentry,logs,uptime external
    style desk fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
```

| Container | Responsibility | Holds state? |
|---|---|---|
| Web app | Screens per role; talks only to the API | No: only UI state and the session tokens |
| API | Every rule is enforced here: authentication, role and ownership checks, workflow, assignment rules | No: stateless, so it scales horizontally |
| Scheduler | Runs the idempotent `send_reminders` command every hour: delivery reminders, escalations, deadline warnings, email retries | No |
| Management commands | Seeding and CLI import; reuse the same domain services as the API | No |
| Database | Single source of truth; constraints back up the rules in code | **Yes** |

## 3. Backend components

How the API is layered. Business rules live in **services**, not in views, so the HTTP API and the
management commands share exactly the same logic. The database is the last line of defence.

```mermaid
flowchart TB
    http(["HTTP request"]) --> mw
    mw["<b>Middleware</b><br/>request ID · JSON access log · security headers · CORS"]
    mw --> authn["<b>Authentication</b><br/>SimpleJWT · rejects inactive users"]
    authn --> perms["<b>Permission classes</b><br/>role checks · ownership checks"]
    perms --> views["<b>Views and serializers</b><br/>input validation · response shape · pagination"]
    views --> services
    cmd(["manage.py<br/>seed · import_episodes · send_reminders"]) --> services

    subgraph services["Domain services: all business rules"]
        direction LR
        workflow["<b>Workflow</b><br/>state machine<br/>audit events"]
        assign["<b>Assignments</b><br/>quality rule<br/>one active request"]
        importer["<b>Episode import</b><br/>normalise · validate<br/>upsert · report"]
        analytics["<b>Analytics</b><br/>SQL aggregation"]
        notify["<b>Notifications</b><br/>in-app and email<br/>reminders"]
    end

    services --> models["<b>Models and constraints</b><br/>partial unique index · CHECK constraints · foreign keys<br/>transactions and row locks"]
    models --> pg[("PostgreSQL")]

    classDef layer fill:#85bbf0,stroke:#5d82a8,color:#000
    classDef entry fill:#e8e8e8,stroke:#999,color:#000
    class mw,authn,perms,views,workflow,assign,importer,analytics,notify,models layer
    class http,cmd entry
    style services fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
```

Two parts sit beside this chain: an **error handler** turns failures from any layer into one JSON error
shape, and **`/health`** answers without authentication so load balancers and uptime checks can call it.

| Django app | Owns |
|---|---|
| `core` | Settings helpers, health check, logging middleware, error handling, shared permissions |
| `accounts` | Custom user (email login, role), authentication, user management, seed command |
| `catalog` | Robots, episodes, CSV import service, `import_episodes` command, import reports |
| `requests_desk` | Dataset requests, status workflow and events, assignments |
| `notifications` | Notification records, inbox endpoints, email delivery, `send_reminders` command |
| `analytics` | Read-only analytics endpoint backed by SQL aggregation |

## 4. Request lifecycle

One authenticated call end to end, using a client rejecting a delivery as the example.

```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant W as Web app
    participant M as Middleware
    participant V as Transition view
    participant S as Workflow service
    participant D as PostgreSQL

    C->>W: Click "Reject" and enter a reason
    W->>M: POST /api/requests/{id}/transitions/<br/>{to_status: "rejected", comment}
    M->>V: assign request ID, start timer
    V->>V: authenticate JWT, load user
    V->>S: transition(request, user, "rejected", comment)
    S->>D: BEGIN, SELECT request FOR UPDATE
    alt request belongs to another client
        S-->>V: not found
        V-->>M: 404
    else transition not allowed from current status
        S-->>V: invalid transition
        V-->>M: 409 with error code and message
    else allowed
        S->>D: UPDATE status, INSERT status event (who, when, reason)
        S->>D: COMMIT
        S-->>V: updated request
        V-->>M: 200 with request JSON
    end
    M->>M: log method, path, status, duration_ms, user_id, request_id
    M-->>W: response and X-Request-ID header
    W-->>C: Show new status and timeline
```

The row lock (`SELECT … FOR UPDATE`) makes concurrent actions on the same request safe: two
operators clicking "Deliver" at the same moment are serialised, and the second one sees the new
status.

## 5. Request status workflow

The only allowed transitions. Anything else returns **409 Conflict**; the right transition by the
wrong role returns **403 Forbidden**. Every change writes an audit event.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> submitted: client creates request
    submitted --> in_progress: operator starts work
    in_progress --> delivered: operator delivers (assigned ≥ requested)
    delivered --> accepted: client accepts
    delivered --> rejected: client rejects (reason required)
    rejected --> in_progress: operator reworks
    accepted --> [*]
```

| Transition | Allowed roles | Guard |
|---|---|---|
| `submitted → in_progress` | operator, admin | – |
| `in_progress → delivered` | operator, admin | active assignments ≥ `episodes_requested` |
| `delivered → accepted` | owning client | – |
| `delivered → rejected` | owning client | reason required |
| `rejected → in_progress` | operator, admin | – |

Episodes can only be assigned or unassigned while a request is `in_progress`.

## 6. CSV import pipeline

The export is messy, so every row is normalised, validated and either upserted or reported. The
same file can be imported any number of times without creating duplicates.

```mermaid
flowchart TB
    file(["CSV file"]) --> header{"Header valid?"}
    header -- no --> fail["Import fails with a clear error"]
    header -- yes --> normalise

    subgraph perrow["For each data row"]
        direction TB
        normalise["<b>Normalise</b><br/>trim · case · date formats · durations"]
        normalise --> valid{"Valid?"}
        valid -- yes --> seen{"Already seen in this file?"}
        seen -- no --> guard{"Would turn an assigned<br/>episode bad?"}
        guard -- no --> upsert["<b>Upsert</b> on episode_id<br/>created · updated · unchanged"]
        valid -- no --> skip["<b>Skip</b><br/>reason code and row number"]
        seen -- yes --> skip
        guard -- yes --> skip
    end

    upsert --> report["<b>Import report</b><br/>counts and issues, stored per batch"]
    skip --> report

    classDef bad fill:#f8d7da,stroke:#c0392b,color:#000
    classDef good fill:#d4edda,stroke:#2e7d32,color:#000
    classDef step fill:#85bbf0,stroke:#5d82a8,color:#000
    class fail,skip bad
    class upsert good
    class normalise,report step
    style perrow fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
```

Values that can be safely fixed (casing, whitespace, alternative date formats) are imported and
noted in the report as *fixed*. Each case and its decision is listed in PLAN.md §8.

## 7. How problems reach people

Nobody watches logs all day, so the system pushes problems to the people who can act on them. Logs are kept for
*explaining* a problem once someone knows about it.

| Situation | Who finds out | How |
|---|---|---|
| A delivery waits for the client's decision | Client, then the delivering operator | Reminder email and in-app notification every 3 days (at most 3), then an escalation to the operator |
| A deadline is 2 days away and nothing is delivered | Operators | In-app deadline warning, once per request |
| The API throws an unhandled error | Development team | Sentry email with stack trace, request and user id |
| The API or database is down | Development team | Uptime monitor calls `/health` and alerts on failure |
| Investigating any of the above | Development team | JSON logs, found by the `X-Request-ID` shown to the user |

## 8. Deployment

Three environments with the same container image and configuration from environment variables.

```mermaid
flowchart LR
    subgraph local["Local · docker compose up"]
        direction TB
        lweb["web"] --> lapi["api"] --> ldb[("db<br/>postgres:16")]
    end

    subgraph dev["Dev · branch develop"]
        direction TB
        dweb["Vercel<br/>dev domain"] --> dapi["Render<br/>desk-api-dev"] --> ddb[("Neon<br/>branch dev")]
    end

    subgraph prod["Production · branch main"]
        direction TB
        pweb["Vercel<br/>production"] --> papi["Render<br/>desk-api"] --> pdb[("Neon<br/>branch main")]
    end

    local ~~~ dev ~~~ prod

    classDef env fill:#85bbf0,stroke:#5d82a8,color:#000
    class lweb,lapi,dweb,dapi,pweb,papi env
    style local fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
    style dev fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
    style prod fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
```

| Concern | Approach |
|---|---|
| HTTPS | Terminated by Vercel and Render |
| Secrets | Host environment settings and GitHub Actions secrets; never in the repository |
| Migrations | Applied by the container entrypoint on start |
| Configuration | Environment variables only (see `.env.example`); missing required values stop startup |

## 9. Delivery pipeline

How a change reaches production. Nothing merges without passing checks, and nothing reaches
production without a release PR and manual approval.

```mermaid
flowchart LR
    branch["Work branch<br/>feat/ fix/ chore/ …"] --> pr["Pull request<br/>into develop"]

    subgraph checks["Required checks"]
        direction TB
        naming["Branch naming"]
        commits["Conventional commits"]
        ci["CI: hygiene · backend tests<br/>frontend build · compose smoke test"]
    end

    pr --> checks --> develop["Merge into develop"]
    develop --> devdeploy["Deploy to dev"]
    develop --> release["Release PR<br/>develop → main"]
    release --> approve(["Manual approval<br/>production environment"])
    approve --> proddeploy["Deploy to production"]

    classDef step fill:#85bbf0,stroke:#5d82a8,color:#000
    classDef check fill:#e8e8e8,stroke:#999,color:#000
    classDef deploy fill:#d4edda,stroke:#2e7d32,color:#000
    classDef gate fill:#fff3cd,stroke:#b58900,color:#000
    class branch,pr,develop,release step
    class naming,commits,ci check
    class devdeploy,proddeploy deploy
    class approve gate
    style checks fill:transparent,stroke:#5d82a8,stroke-width:1px,stroke-dasharray:5 4
```
