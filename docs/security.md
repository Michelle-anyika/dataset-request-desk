# Security design

What we protect, what we protect it from, and the control for each threat. Every control lists the issue that
implements it, so this document doubles as a checklist. Architecture context is in
[architecture.md](architecture.md).

## 1. What we protect

| Asset | Why it matters | Main risk |
|---|---|---|
| **Client data**: requests, notes, organisation, delivered episodes | Clients are separate companies: each must never see another's data | Broken access control between tenants |
| **Workflow integrity**: status, assignments, audit events | Deliveries and acceptances have business and contractual weight | Unauthorised or untraceable changes |
| **Accounts and sessions** | One stolen operator or admin session exposes every client | Credential stuffing, token theft |
| **Availability** | Operations staff depend on the desk daily | Brute force, oversized uploads, unbounded queries |

## 2. Threats and controls

| Threat | Control | Issue |
|---|---|---|
| Client reads or changes another client's request (IDOR) | Querysets scoped by owner, so other clients' rows don't exist for them (404, not 403); UUID ids; role × endpoint test matrix | #7 |
| Low-privilege user calls an operator or admin endpoint | Deny by default (`IsAuthenticated` globally), role permission classes on every view, role read from the database on every request | #5, #7 |
| Password guessing and credential stuffing | Login throttled per IP and per email, shared across workers; generic error; slow Argon2id hashing | #5 |
| Stolen access token | Access tokens live 10 minutes and only in memory, never in browser storage | #5, #18 |
| Stolen refresh token (XSS) | Refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie, which JavaScript can't read; strict Content Security Policy | #5, #18, #41 |
| Replayed refresh token | Rotation on every use; the old token is blacklisted; **reuse of a revoked token revokes all of that user's sessions** | #5 |
| Session survives deactivation, password or role change | A `session_version` on the user is copied into every token; raising it rejects every older token immediately, access tokens included | #5, #16 |
| Cross-site request forgery | Same-origin API (the frontend proxies `/api`); `SameSite=Strict` cookie scoped to `/api/auth/`; bearer access tokens can't be sent by another site | #5, #18, #25 |
| Eavesdropping, downgrade to HTTP | HTTPS only: redirect, HSTS (1 year), `Secure` cookies | #41 |
| Clickjacking, MIME sniffing | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff` | #41 |
| SQL injection | ORM or parameterised SQL only, including analytics | all |
| Oversized or malicious uploads | Size limit, allowed extensions, parsed as data with the `csv` module, never executed; row-level validation | #11, #41 |
| Unbounded queries (denial of service) | Pagination with a maximum page size; API rate limits for authenticated and anonymous users | #41 |
| Secrets leaked in the repository | Environment variables only; `.env` git-ignored; private-key pre-commit hook; GitHub secret scanning with push protection (enabled) | done |
| Vulnerable dependency | Pinned versions; Dependabot version and **security** updates (enabled); `pip-audit` and `npm audit` in CI | #42 |
| Insecure code pattern | Ruff security rules (Bandit) and CodeQL in CI | #42 |
| Sensitive data in logs | No query strings, bodies, tokens or passwords logged; emails in security events are hashed; Sentry without default PII | #3, #5, #32 |
| Misconfigured production | `DEBUG` off; `manage.py check --deploy` fails CI on any warning; separate JWT signing key | #41 |
| Untraceable actions | Append-only status events (who, when); security audit log for authentication events with request ID | #5, #10 |

## 3. Authentication

### Tokens

| | Access token | Refresh token |
|---|---|---|
| Format | Signed JWT (HS256) | Signed JWT (HS256), tracked server-side for revocation |
| Lifetime | 10 minutes | 12 hours (a working day) |
| Stored in | Frontend memory only | `HttpOnly; Secure; SameSite=Strict; Path=/api/auth/` cookie |
| Sent as | `Authorization: Bearer …` | Cookie, only to `/api/auth/refresh/` and `/api/auth/logout/` |
| Revocation | `session_version` and inactive check on every request | Blacklist (rotation, logout) and `session_version` |

- **Rotation with reuse detection:** each refresh returns a new refresh token and blacklists the old one. If a
  blacklisted token is presented again, someone has a copy, so **all sessions of that user are revoked** and a
  security event is logged at `ERROR`, which error tracking turns into an alert.
  - A reuse **within 10 seconds** of rotation is treated as two browser tabs refreshing at once: refused, but the
    session survives.
  - The token's row is **locked** while it is rotated, so two simultaneous refreshes can't both succeed.
  - The revocation is committed separately from the failed refresh, so raising the error can't roll it back.
- **Why a version counter, not a timestamp:** the first design compared the token's `iat` with a
  `tokens_valid_after` timestamp. JWT timestamps have one-second precision, so a token issued in the same second
  as a revocation survived it (or a fresh login was refused). A counter is exact.
- **Expired tokens** are rejected by their signed `exp` claim and need no blacklist entry. The daily
  `flushexpiredtokens` job removes blacklist rows for tokens that have expired anyway (scheduler, #34).
- **Signing key:** `JWT_SIGNING_KEY`, separate from `DJANGO_SECRET_KEY`, so tokens can be rotated (logging everyone
  out) without affecting other signed data.

### Endpoints

| Endpoint | Behaviour |
|---|---|
| `POST /api/auth/login/` | Email and password. Returns the access token and user profile; sets the refresh cookie. Wrong email or password → `401` with the same message. Throttled. |
| `POST /api/auth/refresh/` | Reads the cookie, rotates it, returns a new access token |
| `POST /api/auth/logout/` | Blacklists this session's refresh token and clears the cookie |
| `POST /api/auth/logout-all/` | Revokes every session of the current user |
| `GET /api/auth/me/` | Current user's id, email, name, role, organisation |

### Passwords
- **Argon2id** (the OWASP first choice). PBKDF2 stays as a fallback hasher, so older hashes are upgraded
  transparently on the next successful login.
- New and changed passwords: at least **12 characters**, not a common password, not similar to the email, not all
  digits. The demo accounts from `users.json` are exempt because they're seeded directly, and they're never created
  in production.
- Unknown emails still run the hasher, so response time doesn't reveal whether an account exists.

### Brute-force protection
- `10/minute` per IP and `5 per 15 minutes` per email on login. Counters live in the **database cache**, so all
  gunicorn workers and containers share them. A per-process memory cache would let an attacker multiply attempts by
  the number of workers.
- Throttled responses are `429` with `Retry-After`.

### Security audit log
JSON events on the `desk.security` logger, with `request_id` and client IP:
`auth.login_succeeded`, `auth.login_failed` (email as a SHA-256 hash, never the password), `auth.logout`,
`auth.logout_all`, `auth.refresh_reuse_detected`, `auth.throttled`.

## 4. Authorization

- **Deny by default:** every endpoint requires authentication unless it explicitly opts out (`/health`, login,
  refresh).
- **Roles from the database:** the role is never trusted from the token, so a role change applies on the next request.
- **Object scoping:** clients get querysets filtered to their own rows. Anything else is "not found".
- **Admin safety:** an admin can't deactivate or demote themselves, and the last active admin can't be removed.
- **Workflow ownership:** only the owning client accepts or rejects; only operators and admins perform the other
  steps (PLAN §7.2).

## 5. Transport and browser

| Setting | Value (production) |
|---|---|
| `SECURE_SSL_REDIRECT` | on, with `SECURE_PROXY_SSL_HEADER` for the hosting proxy |
| HSTS | 1 year, include subdomains |
| Cookies | `Secure`, `HttpOnly` (refresh), `SameSite=Strict` |
| API responses | `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin` |
| Frontend | `Content-Security-Policy: default-src 'self'` (no inline scripts), same headers as above |
| CORS | Not needed: the frontend and API share one origin through the `/api` proxy |

## 6. OWASP Top 10 (2021)

| Risk | Where it's addressed |
|---|---|
| A01 Broken access control | §4; role × endpoint matrix tests; tenant scoping |
| A02 Cryptographic failures | HTTPS and HSTS; Argon2id; signed tokens with a dedicated key |
| A03 Injection | ORM and parameterised SQL; CSV parsed as data; React escapes output |
| A04 Insecure design | This threat model; workflow as a single state machine; database constraints back up code rules |
| A05 Security misconfiguration | `check --deploy` gate; settings from validated environment variables; `DEBUG` off |
| A06 Vulnerable components | Dependabot security updates; `pip-audit` and `npm audit` in CI |
| A07 Identification and authentication failures | §3: throttling, rotation, reuse detection, revocation, password policy |
| A08 Software and data integrity failures | Protected branches with required checks; pinned dependencies; append-only audit events |
| A09 Logging and monitoring failures | Request and security audit logs; Sentry; uptime monitoring |
| A10 Server-side request forgery | The API makes no requests to user-supplied URLs |

## 7. Known gaps and next steps

Deliberately not built in this version, in priority order:
1. **MFA (TOTP) for operators and admins:** one stolen password is currently enough for full access.
2. **Self-service password reset** by single-use email link.
3. **Single sign-on** for staff (OIDC) instead of local passwords.
4. **Per-tenant encryption** or row-level security in PostgreSQL as defence in depth for client separation.

The two vulnerabilities that worry us most in this kind of system:
1. **Broken object-level authorization:** one missed queryset filter exposes another client's data. Mitigation:
   scoping in one place per resource, the 404 policy, and a test matrix that tries every endpoint as every role.
2. **Session theft through XSS:** a single injected script could act as the user. Mitigation: the refresh token is
   out of JavaScript's reach, access tokens are short-lived and memory-only, and a strict CSP blocks inline scripts.
