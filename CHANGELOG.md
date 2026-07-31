# Changelog

All notable changes to LiveFireTTX are documented here.

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
