# Release Security Review

## v1.3 Portable Design and Shared Access Delta

Date: 2026-07-31

The v1.3 design-library, organization-profile, and authenticated shared-mode
features were reviewed with the following controls:

- Schema migration 5 is additive and preserves existing exercises, generated
  packages, evidence, checkpoints, and improvement actions.
- Scenario-pack imports are JSON-only, limited to 256 KB, count bounded, and
  normalized into a fixed schema before persistence or generation.
- Imported packs cannot choose commands, scripts, binaries, addresses,
  controller origins, generated paths, or output paths. Chaos references must
  already exist in the selected built-in scenario allowlist.
- Pack export excludes exercise IDs, package paths, lifecycle status, trigger
  history, events, assessments, corrective actions, and evidence. Immutable
  slug/version pairs use canonical SHA-256 content checksums.
- Organization profiles are immutable bounded versions and cannot alter the
  selected scenario action boundary.
- Non-loopback trusted hosts require shared mode. Shared mode uses explicit host
  validation and exact same-origin mutation checks for HTTP or HTTPS.
- Passwords use PBKDF2-SHA256 with random salts. Random opaque session tokens
  are stored only as SHA-256 hashes, expire server-side, and are revoked on
  logout, password reset, or account disablement.
- Session cookies are HttpOnly and SameSite Strict and default to Secure in
  shared mode. Secure-cookie deployments emit HSTS.
- Role capabilities are enforced before route dispatch. Participant and
  evaluator accounts cannot reach design, facilitator, chaos, Docker, backup,
  or account-administration controls.
- The last active administrator cannot be disabled. Authentication failures use
  generic public messages.
- Backup snapshots retain account hashes but delete active sessions so restore
  cannot resurrect browser access.
- Portability, action allowlisting, immutable versions, provenance, password
  verification, session revocation, role routing, and session-free backups are
  covered by automated tests.

Shared mode is for controlled HTTPS-protected exercise networks. It does not
claim internet-facing tenancy, external identity integration, or authorization
for production fault injection.

## v1.2 Exercise Operations Delta

Date: 2026-07-31

The v1.2 MSEL, role views, improvement planning, and direct-host lifecycle
controls were reviewed with the following controls:

- Schema migration 4 is additive and preserves existing exercises and packages.
- MSEL checkpoints and corrective actions use bounded fields, validated
  objective references, constrained states, and same-origin-protected POST
  routes.
- Participant status projections contain only delivered narrative and artifact
  injects; future operations, chaos controls, notes, and evaluations are not
  serialized.
- Lab requests select from `deploy`, `validate`, and `destroy`; `launch` maps to
  the fixed deploy operation and starts the existing facilitator clock only
  after successful deployment.
- The Docker binary is resolved locally, Compose paths derive from validated
  exercise IDs, symlinks are rejected, subprocesses do not use a shell, and a
  narrow environment allowlist and timeout are enforced.
- Failed Docker output is retained only in local logs rather than returned in
  public HTTP error detail.
- Container deployment disables lifecycle controls and does not mount the host
  Docker socket.
- Migration, MSEL ordering, participant isolation, subprocess arguments, route
  behavior, and evidence export are covered by automated tests.

The local-only browser and controller boundary remained unchanged in v1.2. Role
views in that release were workflow projections rather than authenticated
multi-user authorization; v1.3 adds the opt-in authorization layer.

## v1.1 Facilitator Operations Delta

Date: 2026-07-31

The v1.1 facilitator clock and narrative scheduler were reviewed with the
following controls:

- Schema migration 3 is additive and preserves existing exercises, packages,
  and evidence.
- Automatic scheduling is limited to existing narrative inject records; it
  cannot invoke chaos actions, playbooks, commands, targets, or file paths.
- Clock and schedule mutations use same-origin-protected POST routes, while
  status reads remain side-effect free.
- Due-inject delivery is transactional, rechecks that the exercise is running,
  and records one delivery event to prevent duplicate dispatch.
- Paused, completed, and reset exercises cannot receive automatic deliveries.
- Operators can disable the scheduler without discarding configured schedules
  by setting `LIVEFIRE_SCHEDULER_ENABLED=false`.
- Clock transitions, schedule changes, and automatic deliveries are retained in
  the exercise event log and exported evidence manifest.
- Lifecycle, pause-freeze, duplicate-delivery, scheduler configuration, route,
  and evidence behavior are covered by automated tests.

The existing local-only deployment boundary and generated-controller safety
controls remain unchanged.

## v1.0 Release Review

Date: 2026-07-30

The v1.0 release candidate was prepared with the following controls:

- Removed Python bytecode and `__pycache__` directories.
- Confirmed local runtime artifacts such as `livefirettx.db` and `generated/` are excluded by `.gitignore` and not present in the packaged repository.
- Scanned for obvious secrets and sensitive patterns, including common API keys, AWS keys, GitHub tokens, Slack tokens, private-key headers, password/token/secret assignments, private local paths, and unrelated internal project references.
- Updated the license summary to reference LiveFireTTX and substantially similar live-fire tabletop / exercise orchestration products rather than unrelated project names.
- Confirmed the Python package compiles successfully.
- Added path-contained, schema-aware backup and restore validation.
- Derived exercise package access from the configured generated-data root,
  normalized paths with symlink-aware containment checks, and stopped trusting
  persisted package paths for filesystem access.
- Replaced path-based download responses with bounded in-memory archives that
  reject symbolic links and oversized package trees.
- Added localhost-only controller configuration validation.
- Added trusted-host, same-origin mutation, and browser security-header
  enforcement for the facilitator interface.
- Canonicalized post-action redirects as validated relative URLs and removed
  exception and local-path details from public health responses.
- Added CI lint, type, coverage, dependency audit, secret scan, package-build,
  generated Docker smoke, and CodeQL workflows.
- Added a documented threat model and release checklist.
- Removed the multipart runtime dependency and upgraded all runtime pins to the
  newest published compatible releases.
- Documented the temporary Starlette upstream exceptions whose fixes require a
  version outside FastAPI's published compatibility range.

No obvious secrets, tokens, private endpoints, local filesystem paths, or unrelated internal project references were found by the scan performed during packaging.

This review is a best-effort engineering review, not a legal review. Final
publication still requires the automated release checklist and GitHub security
results to pass.
