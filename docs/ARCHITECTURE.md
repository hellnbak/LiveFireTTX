# LiveFireTTX Architecture

LiveFireTTX is intentionally local-first. Version 0.3 uses a FastAPI facilitator app, Jinja2 templates, SQLite persistence, and generated Docker Compose labs with a separate guarded chaos control service.

## Core flow

```text
Facilitator input
  -> ExerciseCreate request
  -> Scenario library lookup
  -> Exercise + inject options
  -> Generated package
  -> Facilitator console
  -> Triggered injects / safe chaos controller
  -> Shared simulation state
  -> Observable target behavior
  -> Run log
  -> After-action report template
```

## Components

### Scenario Builder

The web form captures scenario type, business system, difficulty, participants, duration, and objectives.

### Scenario Library

`app/models.py` contains the starter scenario library. Each scenario defines labels, descriptions, target modules, chaos modules, and default objectives.

### Exercise Generator

`app/services/generator.py` and `app/services/lab_renderer.py` create:

- `exercise.yml`
- `facilitator_guide.md`
- `participant_brief.md`
- `target/` Docker Compose lab
- `chaos/` scenario-scoped API, CLI, state engine, and artifacts
- `artifacts/` exercise artifacts
- `reports/after_action_template.md`
- `cleanup/destroy.sh`

### Facilitator Console

The console groups injects by stage and lets the exercise leader manually trigger each inject. Guarded chaos runs support low, medium, and high intensity, bounded durations, reusable stop-condition profiles, repeat execution, reset, and emergency stop. Trigger counts and action results are stored in SQLite and shown in the run log.

### Target Environment

The target environment is generated per exercise. It exposes safe business and dependency endpoints that react to shared simulation conditions such as latency, application errors, authentication failures, DNS failures, backup delays, blocked builds, and seeded-record integrity issues.

### Guarded Chaos Control Plane

The chaos environment is generated separately from the target environment and runs on `127.0.0.1:8090`. Its API and CLI share an allowlisted lifecycle engine. Each generated exercise contains only the actions relevant to its scenario. State updates use file locking and atomic replacement, while synthetic artifacts and run observations are retained for exercise evidence.

```text
Facilitator Console or Chaos API
  -> Controller and target preflight
  -> Scenario action allowlist
  -> Intensity + duration + stop conditions
  -> Pending run
  -> Locked state update
  -> Active run
  -> Synthetic artifact
  -> Target reads shared state
  -> Observable simulated impact
  -> Duration elapsed or guardrail violation
  -> Automatic rollback
  -> Completed / aborted / failed run
```

The controller monitors active runs every two seconds. It records target
observations and aborts runs when the target becomes unreachable, reports a
different exercise ID, or exceeds configured latency or error-rate thresholds.
The target independently ignores expired effects, preserving rollback behavior
if the controller is temporarily unavailable.

### Runtime Safety Boundary

`app/services/runtime.py` verifies the running controller and target belong to the selected exercise, validates intensity, duration, and guardrail selections, and routes v0.3 actions through the guarded API. Legacy package execution remains path-contained and time-bounded.

## Future renderers

The generator is structured so additional renderers can be added later:

- AWS Terraform
- AWS Fault Injection Service templates
- Azure Chaos Studio
- Kubernetes / Helm
- SIEM / EDR synthetic alert connectors
- Jira / ServiceNow / Slack / Teams inject delivery
