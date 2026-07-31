# Threat Model

## Assets

- Local exercise definitions, participant notes, and objective assessments
- Generated target/controller packages and playbooks
- Synthetic artifacts, run observations, and evidence archives
- Local SQLite database and backups

## Trust Boundaries

- Browser to facilitator application on `127.0.0.1:8000`
- Facilitator application to generated controller on `127.0.0.1:8090`
- Generated controller to generated target over the Docker network
- Shared generated state and artifact volumes
- Backup archives crossing the local filesystem boundary

## Primary Risks and Controls

### Unintended Real-World Impact

Controls: localhost binds, local-only controller URL validation, an explicit
container-host opt-in limited to `host.docker.internal`, generated target
identity checks, action allowlists, no arbitrary addresses, bounded durations,
automatic expiration, reset, and emergency stop.

### Command or Path Injection

Controls: no shell-command API, approved action identifiers, generated filenames,
resolved path containment, upload size limits, YAML safe loading, ZIP traversal
and symlink rejection, and fixed generated scripts.

### State Corruption or Loss

Controls: SQLite WAL, foreign keys, busy timeout, ordered migrations, atomic
controller state replacement, SQLite backup API, integrity checks, schema
compatibility checks, and versioned manifests.

### Misleading Exercise Evidence

Controls: visible simulation watermarks, immutable playbook snapshots and seeds,
explicit facilitator ratings, provisional score labeling, retained reset/abort
events, and formula-safe CSV export.

### Unattended Scheduled Actions

Controls: automatic scheduling is limited to non-executable narrative injects,
delivery is atomic and idempotent, pause/completion states block dispatch, and
every schedule change and delivery is retained in the exercise event log.

### Local Web Exposure

Controls: documented localhost operation, container port binding to 127.0.0.1,
trusted-host validation, same-origin enforcement for state changes, defensive
response headers, request identifiers, and no v1 remote-controller
configuration. v1.1 does not claim multi-user authentication; operators must
not expose the facilitator application to untrusted networks.

## Out of Scope

- Production infrastructure fault injection
- Internet-facing multi-user deployment
- Malicious code execution or offensive security tooling
- Cloud account authorization and organization tenancy
