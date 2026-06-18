# LiveFireTTX

LiveFireTTX is a local-first MVP for building and running live-fire tabletop exercises. It helps facilitators generate a scenario-specific target environment, a safe chaos environment, inject options, exercise artifacts, and a web console where the tabletop leader can manually trigger injects during the exercise.

> **Status:** MVP / prototype. Use only in controlled lab environments.

## What it does

- Creates tabletop and live-fire exercises from guided scenario inputs
- Generates a structured exercise package for each run
- Builds a local Docker Compose target environment
- Builds safe local chaos scripts for controlled simulation
- Provides a facilitator inject console
- Lets the exercise leader manually trigger narrative injects and chaos actions
- Supports multiple inject/chaos options per exercise stage
- Logs facilitator actions, inject triggers, and manual notes
- Generates after-action report templates

## Supported starter scenarios

- Ransomware / business interruption
- Cloud or regional service outage
- Supply-chain / dependency compromise
- Database corruption / restore failure
- Identity provider outage

## Safety model

LiveFireTTX is designed for safe simulation. It does **not** generate malware, credential theft tooling, exploit chains, persistence, evasion, destructive payloads, anti-forensics, or real-world unauthorized access tooling.

Chaos actions in this MVP create synthetic artifacts, local state changes, fake alerts, safe test-file renames, simulated service degradation, and report files. They are intended to create realistic exercise pressure without unsafe behavior.

See [docs/SAFETY.md](docs/SAFETY.md).

## Quick start

Requirements:

- Python 3.11+
- Docker Desktop, if you want to run generated local target environments

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Create and run an exercise

1. Open the web UI.
2. Click **New Exercise**.
3. Choose a scenario type and fill in the business system, participants, duration, and objectives.
4. Click **Generate Exercise**.
5. Open the exercise console.
6. Trigger narrative injects or chaos actions manually from the facilitator console.
7. Add facilitator notes as the team makes decisions.
8. Download the generated exercise package.

Generated packages are created under:

```text
generated/exercises/<exercise-id>/
```

Deploy the generated local target environment:

```bash
cd generated/exercises/<exercise-id>/target
./deploy.sh
```

Open the mock target app:

```text
http://127.0.0.1:8088
```

Cleanup:

```bash
cd generated/exercises/<exercise-id>/cleanup
./destroy.sh
```

## Repository layout

```text
app/
  main.py                  # FastAPI app and routes
  models.py                # Scenario library, dataclasses, SQLite persistence
  services/generator.py    # Exercise package, target, and chaos generation
  templates/               # Jinja2 UI templates and CSS
docs/
  ARCHITECTURE.md
  SAFETY.md
  ROADMAP.md
examples/
  scenario-input-example.yml
.github/workflows/
  ci.yml
LICENSE
NOTICE
README.md
requirements.txt
```

## Architecture

```text
Scenario Builder
  -> Scenario Definition
  -> Target Environment Generator
  -> Chaos Environment Generator
  -> Facilitator Inject Console
  -> Run Log
  -> After-Action Report Template
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

LiveFireTTX is licensed under the Functional Source License, Version 1.1, ALv2 Future License (`FSL-1.1-ALv2`).

Copyright (c) 2026 Steve Manzuik.

See [LICENSE](LICENSE)
