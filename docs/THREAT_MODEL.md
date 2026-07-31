# Threat Model

## Assets

- Local exercise definitions, participant notes, and objective assessments
- Generated target/controller packages and playbooks
- Synthetic artifacts, run observations, and evidence archives
- Local SQLite database and backups
- Scenario packs, organization profiles, account hashes, and session records
- Evidence signing key and retained signed evidence history

## Trust Boundaries

- Browser to facilitator application on `127.0.0.1:8000`
- Facilitator application to generated controller on `127.0.0.1:8090`
- Generated controller to generated target over the Docker network
- Shared generated state and artifact volumes
- Optional direct-host facilitator access to the local Docker CLI
- Backup archives crossing the local filesystem boundary
- Optional HTTPS reverse proxy to shared facilitator application boundary

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
events, formula-safe CSV export, per-file SHA-256 digests, and detached manifest
authentication with an installation-specific key.

The HMAC signature establishes integrity only for a verifier that securely
possesses the same key. It is not participant identity proof or public-key legal
non-repudiation.

### Evidence Archive Tampering or Retention Escape

Controls: owner-only random signing key stored outside generated packages,
constant-time HMAC verification, bounded compressed and expanded sizes, member
count limits, safe member names, duplicate and symlink rejection, exact declared
file matching, digest and byte-count checks, strict retained-export filenames,
exercise-derived path containment, and verification before retained download.

The key is intentionally excluded from archives and backups. Operators must
preserve it separately for disaster recovery and independent verification.

### Unattended Scheduled Actions

Controls: automatic scheduling is limited to non-executable narrative injects,
delivery is atomic and idempotent, pause/completion states block dispatch, and
every schedule change and delivery is retained in the exercise event log.

### Host Docker Control

Controls: one-click lifecycle support is direct-host only and can be disabled;
the application container does not mount the Docker socket. The service uses a
fixed operation allowlist, a validated exercise-derived Compose path, symlink
rejection, no shell invocation, a narrow environment allowlist, bounded output,
and a timeout. Operators must still review generated packages before launch.

### Participant Information Leakage

Controls: the presentation status endpoint returns only basic exercise state,
clock data, and already-delivered narrative or artifact injects. It excludes
future injects, schedules, chaos controls, facilitator notes, evaluations,
package paths, and improvement actions.

### Malicious or Oversized Scenario-Pack Import

Controls: JSON-only import, 256 KB request bound, fixed schema version, field and
count limits, semantic-version and slug validation, canonical normalization,
immutable checksummed versions, supported base scenarios, package-contained
artifact rules, and base-scenario chaos allowlists. Packs cannot provide code,
commands, scripts, addresses, controller configuration, or filesystem paths.

### Account or Session Compromise

Controls: opt-in shared mode, explicit trusted hosts, exact same-origin mutation
checks, PBKDF2-SHA256 password hashing with random salts, generic login errors,
random opaque tokens stored only as hashes, fixed expiration, HttpOnly and
SameSite Strict cookies, Secure cookies by shared-mode default, revocation on
logout/password reset/disablement, last-administrator protection, and exclusion
of active sessions from backups.

Residual risks: LiveFireTTX does not provide MFA, external identity providers,
account lockout, organization tenancy, or internet-edge protection. Use a
controlled HTTPS exercise network and protective reverse proxy controls.

### Local Web Exposure

Controls: default localhost operation, container port binding to 127.0.0.1,
trusted-host validation, same-origin enforcement for state changes, defensive
response headers, request identifiers, no v1 remote-controller configuration,
and opt-in authenticated shared mode. Non-loopback allowed hosts are rejected
unless shared mode is enabled.

## Out of Scope

- Production infrastructure fault injection
- Public internet-facing or multi-tenant deployment
- Malicious code execution or offensive security tooling
- Cloud account authorization and organization tenancy
- Public-key evidence notarization or legal non-repudiation
