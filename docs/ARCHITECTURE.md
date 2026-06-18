# LiveFireTTX Architecture

LiveFireTTX is intentionally local-first. The current MVP uses a FastAPI backend, Jinja2 templates, SQLite persistence, and generated Docker Compose labs.

## Core flow

```text
Facilitator input
  -> ExerciseCreate request
  -> Scenario library lookup
  -> Exercise + inject options
  -> Generated package
  -> Facilitator console
  -> Triggered injects / chaos actions
  -> Run log
  -> After-action report template
```

## Components

### Scenario Builder

The web form captures scenario type, business system, difficulty, participants, duration, and objectives.

### Scenario Library

`app/models.py` contains the starter scenario library. Each scenario defines labels, descriptions, target modules, chaos modules, and default objectives.

### Exercise Generator

`app/services/generator.py` creates:

- `exercise.yml`
- `facilitator_guide.md`
- `participant_brief.md`
- `target/` Docker Compose lab
- `chaos/` safe simulation scripts
- `artifacts/` exercise artifacts
- `reports/after_action_template.md`
- `cleanup/destroy.sh`

### Facilitator Console

The console groups injects by stage and lets the exercise leader manually trigger each inject. Triggered actions are stored in SQLite and shown in the run log.

### Target Environment

The target environment is generated per exercise. The local MVP generates a small FastAPI target app with health and order endpoints.

### Chaos Environment

The chaos environment is generated separately from the target environment. Chaos scripts create safe synthetic events and local state changes.

## Future renderers

The generator is structured so additional renderers can be added later:

- AWS Terraform
- AWS Fault Injection Service templates
- Azure Chaos Studio
- Kubernetes / Helm
- SIEM / EDR synthetic alert connectors
- Jira / ServiceNow / Slack / Teams inject delivery
