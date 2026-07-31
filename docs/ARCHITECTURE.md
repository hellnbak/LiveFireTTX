# LiveFireTTX Architecture

LiveFireTTX v1.2 is intentionally local-first. The facilitator application uses
FastAPI, Jinja2, SQLite, and filesystem-backed generated packages. Every
exercise receives a separate Docker Compose target and chaos controller bound
to localhost.

## Core Flow

```text
Guided scenario preset
  -> validated exercise definition
  -> role briefs + sample data + dependency map
  -> generated target and scenario-scoped controller
  -> unified MSEL, facilitator injects, and bounded playbooks
  -> shared synthetic state
  -> observable dependency behavior
  -> objective assessment, corrective actions, and run intelligence
  -> evidence archive and after-action report / improvement plan
```

## Application Components

### Configuration

`app/config.py` resolves database, generated-package, backup, controller, and
timeout settings. The v1 controller URL is restricted to localhost.

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

The Jinja2 interface includes guided scenario setup, a focused facilitator run
mode, a participant-safe presentation display, an evaluator workspace,
dependency topology, exercise intelligence, artifact design, live telemetry,
run control, and the visual playbook editor. Browser checks improve feedback,
while the generated controller remains authoritative for playbook validation.

### Exercise Intelligence

`app/services/intelligence.py` combines facilitator ratings, events, inject
coverage, run lifecycles, playbook outcomes, observations, and artifacts.
Impact comparison includes application, access, payment, queue, storage,
third-party, and telemetry signals. Facilitators—not the application—determine
whether objectives were achieved.

### Facilitator Operations

SQLite schema version 4 persists the exercise lifecycle clock, accumulated
pause time, completion time, narrative schedules, and automatic-delivery mode.
`app/services/facilitator.py` owns clock transitions, elapsed-time calculation,
schedule state, and atomic due-inject delivery. A configurable local scheduler
polls running exercises; pause and completion states block new deliveries.

The command center reconciles its one-second browser clock against server
snapshots returned with live controller status. Every clock transition,
schedule edit, and automatic delivery is also written to the exercise event
log for after-action evidence.

### Exercise Operations

`app/services/operations.py` builds a unified MSEL from injects and persisted
evaluator checkpoints, selects the next scheduled action, and creates a
participant-safe status projection containing only delivered narrative and
artifact information. Checkpoints can link to exercise objectives and record
expected participant actions.

`app/services/labs.py` provides optional one-click deployment, validation, and
teardown for direct host installs. It derives the Compose file from the
validated exercise ID, rejects symlinks, invokes no shell, accepts no arbitrary
command or path input, and uses a narrow environment allowlist. Application
container deployments disable this feature instead of mounting the Docker
socket.

Improvement actions retain an owner, optional due date, state, and success
criteria. Exercise intelligence exports both MSEL checkpoints and corrective
actions as part of the AAR/IP evidence package.

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
evidence model. They are not part of the v1 local safety contract.
