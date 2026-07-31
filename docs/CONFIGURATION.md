# Configuration

LiveFireTTX reads configuration from environment variables at process startup.

| Variable | Default | Validation |
| --- | --- | --- |
| `LIVEFIRE_DATA_ROOT` | `~/.livefirettx` | Resolved user-writable base path |
| `LIVEFIRE_DATABASE_PATH` | `<data-root>/livefirettx.db` | Resolved local path |
| `LIVEFIRE_GENERATED_ROOT` | `<data-root>/generated/exercises` | Resolved local path |
| `LIVEFIRE_BACKUP_ROOT` | `<data-root>/backups` | Resolved local path |
| `LIVEFIRE_CONTROL_URL` | `http://127.0.0.1:8090` | Must use an approved local origin |
| `LIVEFIRE_ALLOW_CONTAINER_HOST` | `false` | Allows the exact `host.docker.internal` controller origin |
| `LIVEFIRE_REQUEST_TIMEOUT_SECONDS` | `3` | Positive integer |
| `LIVEFIRE_SCHEDULER_ENABLED` | `true` | Boolean controlling automatic narrative delivery |
| `LIVEFIRE_SCHEDULER_INTERVAL_SECONDS` | `2` | Positive polling interval in seconds |
| `LIVEFIRE_LAB_CONTROLS_ENABLED` | `true` | Boolean enabling fixed Docker lifecycle controls |
| `LIVEFIRE_LAB_COMMAND_TIMEOUT_SECONDS` | `180` | Positive lifecycle timeout in seconds |
| `LIVEFIRE_SHARED_MODE` | `false` | Boolean enabling authentication and route permissions |
| `LIVEFIRE_ALLOWED_HOSTS` | `127.0.0.1,localhost,[::1],testserver` | Comma-separated exact or wildcard trusted hosts |
| `LIVEFIRE_SESSION_TTL_MINUTES` | `480` | Positive server-side session lifetime |
| `LIVEFIRE_SECURE_COOKIES` | Same as shared mode | Boolean requiring HTTPS-only session cookies |
| `LIVEFIRE_BOOTSTRAP_ADMIN_USERNAME` | `admin` | Valid lowercase first-administrator username |
| `LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD` | unset | First-administrator password, 12–1024 characters |
| `LIVEFIRE_EVIDENCE_SIGNING_KEY_PATH` | `<data-root>/evidence-signing.key` | Resolved owner-only key path |
| `LIVEFIRE_EVIDENCE_RETENTION_DAYS` | `365` | Integer from 1 through 36,500 |
| `LIVEFIRE_EVIDENCE_RETENTION_COUNT` | `25` | Integer from 1 through 10,000 per exercise |

Generated package deployment also accepts:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LIVEFIRE_TARGET_HOST_PORT` | `8088` | Target host port |
| `LIVEFIRE_CONTROL_HOST_PORT` | `8090` | Controller host port |
| `LIVEFIRE_RUNTIME_UID` | Current user through `deploy.sh` | Generated container user ID |
| `LIVEFIRE_RUNTIME_GID` | Current group through `deploy.sh` | Generated container group ID |

Example:

```bash
export LIVEFIRE_DATA_ROOT="$HOME/.livefirettx"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The specific database, generated-package, backup, and signing-key variables
override paths derived from `LIVEFIRE_DATA_ROOT` when set.

The scheduler only delivers narrative injects explicitly marked for automatic
delivery. Pausing an exercise freezes elapsed exercise time and prevents new
scheduled deliveries until the clock resumes. Disabling the scheduler retains
schedules and due-state prompts for manual facilitator delivery.

The application Compose service passes both scheduler variables through from
the host environment. It also passes the shared-mode variables; the blank
Compose bootstrap-password default is treated as unset. For example, start in
manual-only mode with:

```bash
LIVEFIRE_SCHEDULER_ENABLED=false docker compose up -d --build
```

## Evidence Signing and Retention

The first signed evidence export creates a random 32-byte key at
`LIVEFIRE_EVIDENCE_SIGNING_KEY_PATH`. On POSIX systems the key must remain a
regular, non-symlinked, owner-only file. The application refuses to sign or
verify evidence when that key is missing after initial creation, malformed,
oversized, symlinked, or readable by group or other users.

The default path follows `LIVEFIRE_DATA_ROOT`; an explicit key path does not.
Keep the key on persistent storage and copy it through a separate secure channel
when evidence must be verified elsewhere. Application backups deliberately omit
the signing key. Retained evidence ZIPs are stored under each generated package
and pruned after export when either retention limit is exceeded.

## Shared Deployment

Non-loopback values in `LIVEFIRE_ALLOWED_HOSTS` are rejected unless
`LIVEFIRE_SHARED_MODE=true`. Wildcards use the `*.example.com` form; schemes,
ports, paths, credentials, and a global `*` are not accepted.

On the first shared-mode startup, the user database is empty and
`LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD` is required. LiveFireTTX creates the initial
administrator and never stores the cleartext password. Later startups do not
use the bootstrap value once an account exists, so remove it from the runtime
environment after successful initialization.

Shared mode defaults `LIVEFIRE_SECURE_COOKIES=true`. Run behind an HTTPS reverse
proxy and configure Uvicorn to trust proxy headers only from that proxy:

```bash
export LIVEFIRE_SHARED_MODE=true
export LIVEFIRE_ALLOWED_HOSTS=livefire.example
export LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD='replace-with-a-long-random-password'
uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips=127.0.0.1
```

The proxy must preserve the approved `Host` header and set
`X-Forwarded-Proto: https`. Do not set `LIVEFIRE_SECURE_COOKIES=false` for an
untrusted or internet-routable network. Shared authentication protects the
facilitator application; generated target and controller ports must remain on
loopback.

Role capabilities:

| Role | Capabilities |
| --- | --- |
| Administrator | User administration, backups, design, facilitation, evaluation, participant material |
| Facilitator | Design library, exercise generation, run controls, chaos controls, evaluation |
| Evaluator | Evaluator workspace, observations, assessments, reports, corrective actions |
| Participant | Participant display and role briefs |

Sessions are random opaque tokens stored only as SHA-256 hashes with a fixed
expiration. Passwords use PBKDF2-SHA256. Disabling an account revokes its active
sessions, and application backups intentionally contain no active sessions.

## One-Click Lab Controls

Direct host installations can deploy, validate, repair, and destroy each
generated lab from Run Mode. Commands are fixed Docker Compose operations
against the generated exercise package; request data cannot choose a command,
binary, Compose file, working directory, target, or output path.

The application container sets `LIVEFIRE_LAB_CONTROLS_ENABLED=false`. Mounting
the host Docker socket into the application container is not a supported
deployment pattern. Use generated `deploy.sh`, `validate.sh`, and `destroy.sh`
scripts when running the facilitator as a container.

## Operational Endpoints

- `GET /healthz` verifies the application process.
- `GET /readyz` verifies database integrity and reports schema/version context.
- `GET /admin/backup.zip` downloads a consistent local backup.

In shared mode, readiness remains public for orchestration, while backup access
requires an administrator account.

The application does not provide arbitrary remote-controller configuration in
v1. The container-only host bridge is disabled unless
`LIVEFIRE_ALLOW_CONTAINER_HOST=true`; it permits only the exact
`host.docker.internal` hostname over HTTP.
