# LiveFireTTX Architecture

LiveFireTTX v1.0 is intentionally local-first. The facilitator application uses
FastAPI, Jinja2, SQLite, and filesystem-backed generated packages. Every
exercise receives a separate Docker Compose target and chaos controller bound
to localhost.

## Core Flow

```text
Guided scenario preset
  -> validated exercise definition
  -> role briefs + sample data + dependency map
  -> generated target and scenario-scoped controller
  -> facilitator injects and bounded playbooks
  -> shared synthetic state
  -> observable dependency behavior
  -> objective assessment and run intelligence
  -> evidence archive and after-action report
```

## Application Components

### Configuration

`app/config.py` resolves database, generated-package, backup, controller, and
timeout settings. The v1.0 controller URL is restricted to localhost.

### Persistence

`app/models.py` owns SQLite access. Ordered migrations are recorded in
`schema_migrations`. Connections enable foreign keys, a busy timeout, and WAL.
Health checks run SQLite quick-check and expose the active schema version.

`app/services/backups.py` uses SQLite's backup API to create a consistent
snapshot, packages generated exercises with a versioned manifest, validates ZIP
paths and symlinks, checks database integrity, and rejects newer schema versions
before restore.

### Scenario and Exercise Generation

`app/models.py` defines scenario presets, dependency topology, recommended
roles, target modules, safe chaos modules, and default objectives.

`app/services/generator.py` and `app/services/lab_renderer.py` create:

- Exercise and chaos-plan YAML
- Facilitator guide and readiness checklist
- Shared and role-specific participant briefs
- Simulated orders, dependencies, and communications data
- Target and chaos-controller Docker sources
- Safe artifacts and reports
- Cleanup scripts

### HTTP and UI

`app/main.py` hosts the facilitator workflow and inject/playbook routes.
`app/routes/system.py` contains operational health, readiness, and backup
endpoints. `app/routes/packages.py` serves path-contained participant material.

The Jinja2 interface includes guided scenario setup, dependency topology,
exercise intelligence, artifact design, live telemetry, run control, and the
visual playbook editor. Browser checks improve feedback, while the generated
controller remains authoritative for playbook validation.

### Exercise Intelligence

`app/services/intelligence.py` combines facilitator ratings, events, inject
coverage, run lifecycles, playbook outcomes, observations, and artifacts.
Impact comparison includes application, access, payment, queue, storage,
third-party, and telemetry signals. Facilitators—not the application—determine
whether objectives were achieved.

## Generated Dependency Target

The target reads shared controller state and exposes:

- Application, order, authentication, DNS, backup, and build endpoints
- Payment authorization
- Queue health and consumer delay
- Object reads with synthetic throttling and stale responses
- Third-party availability and retry pressure
- Delayed or missing synthetic telemetry
- A dependency map with live healthy/degraded status

Expired action effects are ignored by the target even when the controller is
temporarily unavailable.

## Chaos Control Plane

```text
Facilitator Console / API / CLI
  -> exercise identity and target preflight
  -> scenario action allowlist
  -> validated manual action or captured playbook
  -> bounded duration + intensity + pattern
  -> concurrency + severity + total-time budgets
  -> atomic state update and synthetic artifact
  -> target observation and guardrail checks
  -> automatic completion, abort, or failure
  -> retained evidence and reversible state
```

The controller uses file locking and atomic replacement. Active playbook stages
capture their definition and replay seed so later edits cannot alter historical
execution. Pausing prevents future scheduling without extending active actions.

## Safety Boundary

`app/services/runtime.py` verifies controller metadata, exercise identity,
options, duration, patterns, and guardrails. YAML is size-limited and loaded
safely. Package and artifact paths are resolved and contained. The controller
accepts no shell commands, executable payloads, arbitrary target addresses, or
operator-selected output paths.

## Release Architecture

- `pyproject.toml` defines the installable application and `livefirettx` CLI.
- `Dockerfile` and `compose.yml` provide a localhost-bound application runtime.
- `.github/workflows/ci.yml` validates Python 3.11–3.13 and generated packages.
- `.github/workflows/codeql.yml` performs scheduled and pull-request analysis.
- `.github/workflows/release.yml` builds artifacts only after release gates pass.
- `scripts/docker_release_smoke.sh` exercises generated target deployment,
  preflight, bounded dependency injection, reset, and teardown.

## Future Renderers

Cloud and enterprise renderers remain adapters around the stable scenario and
evidence model. They are not part of the v1.0 local safety contract.
