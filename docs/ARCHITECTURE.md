# LiveFireTTX Architecture

LiveFireTTX is intentionally local-first. Version 0.6 uses a FastAPI facilitator app, Jinja2 templates, SQLite persistence, exercise-intelligence and artifact services, and generated Docker Compose labs with a separate chaos orchestration service.

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
  -> Objective assessment + run intelligence
  -> Run log
  -> Evidence package + after-action report
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

### Facilitator Command Center

The console groups injects by stage and lets the exercise leader manually trigger each inject. It also displays live condition telemetry, active fault patterns, playbook safety budgets, and orchestration timelines. Facilitators can edit validated YAML, launch or replay playbooks, pause future scheduling, skip stages, stop runs, reset state, or activate the global emergency stop. Trigger counts and action results are stored in SQLite and shown in the run log.

### Exercise Intelligence

`app/services/intelligence.py` combines objective assessments, facilitator
events, inject coverage, chaos lifecycles, playbook outcomes, observations, and
artifact references into explainable exercise signals. It does not infer that an
objective was met; only the facilitator can assign a rubric rating.

The service calculates normalized run-impact comparisons from observed latency,
error, authentication, and DNS conditions. It also generates an after-action
Markdown report and a ZIP evidence package containing Markdown, CSV, JSON state,
and a manifest. Objective ratings and notes are persisted in SQLite, while
generated reports are written into the exercise package under `reports/`.

### Scenario Design Studio

The visual designer edits the same playbook schema used by the generated chaos
controller. Browser-side checks provide immediate feedback for IDs,
dependencies, cycles, timing, and designed budget peaks. The controller remains
the source of truth and performs the final allowlist and safety validation before
save or launch.

Playbook files are stored under `chaos/playbooks/`. When an accepted definition
changes, the prior YAML is copied into an ID-scoped `history/` directory.
Templates can be cloned, imported, exported, or restored without adding another
database or bypassing controller validation.

### Safe Artifact Designer

`app/services/artifacts.py` creates facilitator-defined messages, alerts,
tickets, and advisories under `artifacts/facilitator/`. Filenames are generated
internally, content is size-limited, and every file is visibly marked as
simulated. The resulting item is persisted as a normal artifact inject so its
creation and trigger are included in the exercise event log and evidence export.

### Target Environment

The target environment is generated per exercise. It exposes safe business and dependency endpoints that react to shared simulation conditions such as latency, application errors, authentication failures, DNS failures, backup delays, blocked builds, and seeded-record integrity issues.

### Chaos Orchestration Control Plane

The chaos environment is generated separately from the target environment and runs on `127.0.0.1:8090`. Its API and CLI share an allowlisted lifecycle engine. Each generated exercise contains only the actions relevant to its scenario and one editable scenario playbook. State updates use file locking and atomic replacement, while synthetic artifacts, playbook snapshots, seeds, and run observations are retained for exercise evidence.

```text
Facilitator Console or Chaos API
  -> Controller and target preflight
  -> Scenario action allowlist
  -> Manual action or validated playbook
  -> Intensity + fault pattern + duration
  -> Concurrency + severity + time budgets
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

The controller scheduler evaluates playbook stages and fault patterns every second. It records target
observations and aborts runs when the target becomes unreachable, reports a
different exercise ID, or exceeds configured latency or error-rate thresholds.
The target independently ignores expired effects, preserving rollback behavior
if the controller is temporarily unavailable.

Playbook stages are copied into each run so later configuration edits cannot
change an active or historical execution. Replays reuse that captured definition
and seed. Pausing stops future stage scheduling but intentionally leaves active,
bounded action runs in place until they expire, are skipped, or are stopped.

### Runtime Safety Boundary

`app/services/runtime.py` verifies the running controller and target belong to the selected exercise, validates intensity, pattern, duration, and guardrail selections, and routes v0.4 actions and playbook controls through the orchestration API. YAML configuration is size-limited, parsed safely, validated by the scenario-scoped engine, and persisted only after the controller accepts it. Legacy package execution remains path-contained and time-bounded.

## Future renderers

The generator is structured so additional renderers can be added later:

- AWS Terraform
- AWS Fault Injection Service templates
- Azure Chaos Studio
- Kubernetes / Helm
- SIEM / EDR synthetic alert connectors
- Jira / ServiceNow / Slack / Teams inject delivery
