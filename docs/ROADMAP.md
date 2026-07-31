# Roadmap

## Released Foundation

### v0.1–v0.3

- Local scenario builder and generated Docker target
- Scenario-scoped safe chaos API and CLI
- Reversible actions, bounded duration, preflight, guardrails, and emergency stop
- Lifecycle evidence and target-side expiration

### v0.4 Chaos Orchestration Studio

- Multi-stage playbooks, scheduling, safety budgets, and health gates
- Pause, resume, skip, stop, and deterministic replay
- Steady, ramp, burst, flap, and seeded jitter patterns
- Live telemetry and validated YAML configuration

### v0.5 Exercise Intelligence

- Objective rubric, evidence notes, and explainable readiness signals
- Run comparisons and observed-impact charts
- Markdown, CSV, JSON, state, and manifest evidence export
- Generated after-action reports

### v0.6 Scenario Design Studio

- Drag-and-drop playbook builder with timeline preview
- Template clone, import/export, validation, and version history
- Facilitator-defined watermarked artifact injects
- Local cycle, ID, timing, and safety-budget checks

## v1.0 Complete

### Dependency Realism

- Simulated payment processor failures
- Queue backlog and delayed consumers
- Object-storage throttling and stale reads
- Third-party API degradation and retry pressure
- Observability gaps and delayed synthetic telemetry
- Live cross-service dependency maps

### Exercise Workflow

- Guided scenario presets
- Critical dependency cascade scenario
- Recommended role and objective profiles
- Role-specific participant briefs
- Facilitator readiness checklist
- Built-in sample orders, dependencies, and communications
- Improved setup and command-center interface

### Release Hardening

- Environment-driven local configuration
- Versioned SQLite migrations, integrity checks, WAL, and foreign keys
- Versioned backup and guarded restore tooling
- Application health and readiness endpoints
- Structured request logs and defensive response headers
- Installable Python package and local application container
- Router separation for system and package endpoints
- CI across Python 3.11–3.13, mypy, lint, coverage, CodeQL, package builds,
  and generated Docker lifecycle smoke tests
- Upgrade, configuration, threat-model, and release-checklist documentation

## Next: v1.1

- Facilitator clock, scheduled narrative injects, and exercise pause/resume
- Scenario-pack import/export independent of generated exercise instances
- More detailed role permissions and observer-only views
- Signed evidence manifests and configurable retention
- Browser-driven accessibility and end-to-end UI regression tests

## Future Cloud and Enterprise

- AWS Terraform and Fault Injection Service renderers
- Kubernetes / Helm and Azure Chaos Studio renderers
- Slack, Teams, Jira, ServiceNow, SIEM, and EDR connectors
- Multi-user authentication and organization workspaces
- Shared versioned scenario library

Cloud and enterprise work does not weaken the v1.0 local safety boundary.
