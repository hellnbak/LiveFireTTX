# Changelog

All notable changes to LiveFireTTX are documented here.

## 1.4.0 - 2026-07-31

### Added

- Signed evidence manifests using an installation-specific HMAC-SHA256 key and
  detached `manifest.sig` metadata
- SHA-256 digest and byte-count verification for every file declared by an
  evidence manifest
- `livefirettx verify-evidence` for offline verification with the originating
  installation key or an explicitly supplied key file
- Per-exercise retained evidence-export history with configurable age and count
  limits and integrity status in command-center and evaluator views
- Chromium end-to-end journeys covering exercise creation, evidence export,
  facilitator, evaluator, participant, desktop, and mobile experiences
- Browser accessibility checks for labels, landmarks, heading order, control
  names, duplicate IDs, keyboard skip navigation, and responsive overflow

### Changed

- Evidence manifest schema advanced to version 4 and now rejects undeclared,
  missing, modified, duplicated, oversized, symlinked, or unsafe archive entries
- Evidence downloads are retained under their validated exercise package and
  verified again before a retained archive is served
- Release automation installs Chromium and includes browser regression testing
  in the release gate
- Development environments pin vulnerability-fixed packaging tools so local and
  hosted dependency audits evaluate the same release toolchain
- Core templates now declare document language, expose a keyboard skip link,
  provide visible focus states, and honor reduced-motion preferences

### Security

- Signing keys are generated with operating-system randomness, stored outside
  generated packages with owner-only permissions, and never embedded in evidence
  archives or application backups
- Retention cleanup can delete only application-generated filenames within the
  path-contained per-exercise evidence directory
- Archive verification is bounded by compressed size, expanded size, member
  count, safe names, regular-file requirements, and constant-time signature
  comparison

## 1.3.0 - 2026-07-31

### Added

- Portable scenario-pack schema with bounded JSON import, export, capture, and
  one-click exercise instantiation
- Immutable local scenario-pack versions with seeded built-in designs and
  content checksums
- Immutable organization-profile versions for reusable business systems,
  participant roles, and objectives
- Exercise provenance linking generated packages to their scenario pack and
  organization profile
- Opt-in shared deployment mode with administrator, facilitator, evaluator, and
  participant route permissions
- Server-side sessions, PBKDF2-SHA256 passwords, administrator account
  management, secure-cookie controls, and explicit trusted-host configuration

### Changed

- SQLite schema version 5 persists design-library, profile, account, session,
  and exercise-provenance records
- Built-in scenarios are seeded into the versioned design library at startup
- Guided setup can apply a reusable organization profile
- Backups retain accounts but intentionally exclude active sessions

### Security

- Imported packs cannot choose arbitrary paths, scripts, targets, or actions;
  chaos references must remain inside the base scenario allowlist
- Non-loopback application hosts require shared mode, and shared mode defaults
  to HTTPS-only session cookies
- Authentication tokens are random, stored only as hashes, revocable, bounded
  by expiration, and omitted from backups
- Role enforcement occurs before route dispatch and keeps participant and
  evaluator accounts outside facilitator, design, Docker, and administrator
  controls

## 1.2.0 - 2026-07-31

### Added

- Unified Master Scenario Events List combining scheduled injects, artifacts,
  safe chaos controls, and objective-linked evaluator checkpoints
- Focused facilitator run mode with next-action guidance and complete timeline
- Participant-safe presentation display that reveals only delivered information
- Dedicated evaluator workspace with observations, objective assessments, and
  corrective-action ownership, due dates, and status tracking
- Optional one-click host lab launch, validation, repair, and teardown controls
- MSEL checkpoints and improvement-plan data in after-action and evidence exports

### Changed

- New exercises include three default decision and recovery checkpoints
- SQLite schema version 4 persists checkpoints and improvement actions
- Evidence manifest schema version 3 includes MSEL and corrective-action CSVs
- Application container keeps host Docker control disabled by default

### Security

- Lab lifecycle operations use only fixed Docker Compose commands against the
  path-contained generated package; arbitrary commands and paths are rejected
- Participant status responses omit future injects, chaos controls, evaluator
  data, package paths, and facilitator notes

## 1.1.0 - 2026-07-31

### Added

- Facilitator exercise clock with start, pause, resume, complete, and reset
  controls
- Scheduled narrative injects with facilitator-prompt and automatic-delivery
  modes
- Atomic scheduled delivery events and duplicate-dispatch protection
- Live elapsed, remaining, overtime, and progress indicators in the command
  center
- Configurable scheduler enablement and polling interval
- Exercise clock metadata in after-action reports and evidence manifests

### Changed

- New exercises include automatic T+0 opening and T+20 executive narrative
  injects
- Recent exercise cards expose their current lifecycle state
- SQLite schema version 3 retains clock and inject schedule state across restarts
- Docker Compose passes through scheduler enablement and polling configuration

## 1.0.0 - 2026-07-30

### Added

- Dependency-realism actions for payment, queue, object storage, vendor APIs,
  and observability
- Critical dependency cascade scenario and live dependency maps
- Guided scenario presets, recommended roles, role briefs, facilitator
  checklist, and sample data
- Environment-driven configuration and local administration CLI
- Versioned SQLite migrations, health checks, backup, and guarded restore
- Installable package, application container, CI, CodeQL, and release workflows
- Python 3.11–3.13 quality matrix and generated Docker lifecycle smoke test

### Changed

- Chaos controller and state schema advanced to v1.0
- Exercise impact scoring includes dependency and queue conditions
- Setup and command-center interfaces expose generated materials and topology
- Documentation now defines the v1 local safety and support contract
- Installed builds now store persistent data under the user-writable
  `~/.livefirettx` root by default

### Security

- Added trusted-host and same-origin mutation enforcement, defensive response
  headers, structured request identifiers, and repeatable secret scanning
- Added ZIP traversal, symlink, schema-version, and database-integrity checks
- Preserved localhost-only controller configuration and generated service binds,
  with an explicit container-host bridge opt-in
- Added generated-root path containment, symlink-safe package downloads,
  validated relative redirects, and public error-detail redaction

## 0.6.0

- Added the visual Scenario Design Studio, playbook versioning, and safe artifact
  designer.

## 0.5.0

- Added objective scoring, run comparison, and evidence exports.

## 0.4.0

- Added deterministic playbook orchestration and safety budgets.
