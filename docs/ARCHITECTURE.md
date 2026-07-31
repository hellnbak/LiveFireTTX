# LiveFireTTX Architecture

LiveFireTTX is intentionally local-first. Version 0.2 uses a FastAPI facilitator app, Jinja2 templates, SQLite persistence, and generated Docker Compose labs with a separate safe chaos control service.

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

The console groups injects by stage and lets the exercise leader manually trigger each inject. Chaos actions support low, medium, and high intensity, repeat execution, and full reset. Trigger counts and action results are stored in SQLite and shown in the run log.

### Target Environment

The target environment is generated per exercise. It exposes safe business and dependency endpoints that react to shared simulation conditions such as latency, application errors, authentication failures, DNS failures, backup delays, blocked builds, and seeded-record integrity issues.

### Chaos Control Plane

The chaos environment is generated separately from the target environment and runs on `127.0.0.1:8090`. Its API and CLI share an allowlisted state engine. Each generated exercise contains only the actions relevant to its scenario. State updates use file locking and atomic replacement, while synthetic artifacts are retained for exercise evidence.

```text
Facilitator Console or Chaos API
  -> Scenario action allowlist
  -> Intensity profile
  -> Locked state update
  -> Synthetic artifact
  -> Target reads shared state
  -> Observable simulated impact
```

### Runtime Safety Boundary

`app/services/runtime.py` validates that locally executed scripts remain inside the generated `chaos/` directory, enforces the generated intensity allowlist, applies timeouts, and records failures.

## Future renderers

The generator is structured so additional renderers can be added later:

- AWS Terraform
- AWS Fault Injection Service templates
- Azure Chaos Studio
- Kubernetes / Helm
- SIEM / EDR synthetic alert connectors
- Jira / ServiceNow / Slack / Teams inject delivery
