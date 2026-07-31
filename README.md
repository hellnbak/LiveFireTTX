# LiveFireTTX

LiveFireTTX is a safe, local-first platform for designing and running live-fire
tabletop exercises. It generates a scenario-specific target, a guarded chaos
control plane, facilitator injects, participant materials, sample data, and an
evidence-ready command center.

> **Status:** v1.3.0. Run only in controlled lab environments.

## Highlights

- Guided scenario packs with recommended roles, objectives, dependencies, and timing
- Local Docker Compose target and scenario-scoped chaos controller
- Payment, queue, object-storage, vendor API, telemetry, DNS, identity, backup,
  data-integrity, build, file-impact, EDR, and application simulations
- Low, medium, and high intensity with steady, ramp, burst, flap, and seeded
  jitter patterns
- Bounded durations, target preflight, safety budgets, emergency stop, and
  automatic rollback
- Visual playbook design, timeline preview, YAML fallback, version history,
  import/export, cloning, and deterministic replay
- Live dependency map, condition telemetry, and run lifecycle evidence
- Role-specific participant briefs, facilitator checklist, and sample data
- Persistent facilitator clock with pause/resume and scheduled narrative injects
- Unified MSEL run-of-show with next-action facilitator guidance
- Participant presentation and evaluator/AAR improvement-planning workspaces
- Optional one-click host lab launch, validation, and teardown
- Immutable local scenario-pack versions with validated JSON import/export
- Reusable organization profiles for systems, roles, and objectives
- Opt-in shared deployment mode with authenticated administrator, facilitator,
  evaluator, and participant permissions
- Safe watermarked artifact injects
- Objective scoring, run comparison, after-action reports, and ZIP evidence export
- Versioned SQLite migrations plus local backup and restore tooling
- Installable Python package, application container, CI, CodeQL, and Docker
  release smoke testing

## Supported scenarios

- Ransomware / business interruption
- Cloud or regional service outage
- Supply-chain / dependency compromise
- Database corruption / restore failure
- Identity provider outage
- Critical dependency cascade

## Quick Start

Requirements:

- Python 3.11+
- Docker Desktop or Docker Engine with Compose

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Containerized startup:

```bash
docker compose up -d --build
```

The application container binds only to `127.0.0.1:8000` and stores local data
in the managed `livefirettx-data` Docker volume. Set
`LIVEFIRE_APP_HOST_PORT` when port `8000` is already in use. Scheduler settings
can also be supplied to Docker Compose with the same environment variables
listed below.

One-click lab controls are intentionally disabled inside the application
container because LiveFireTTX does not mount the host Docker socket. Run the
Python application directly on the Docker host to use one-click lifecycle
controls, or continue using the generated package scripts.

Download a generated exercise package from the interface, unpack it on the
host, and run its `target/deploy.sh`. The Compose configuration lets the
facilitator container reach that host controller through the explicit
`host.docker.internal` bridge while the browser-facing ports remain bound to
localhost.

## Run an Exercise

1. Select a scenario pack and review its dependency map.
2. Tailor the business system, duration, roles, and objectives.
3. Generate the exercise, review role briefs, and adjust the unified run of show.
4. When running LiveFireTTX directly on the Docker host, select **Run Exercise**
   and then **Launch Lab & Start**. In container or manual mode, deploy the
   generated target:

   ```bash
   cd generated/exercises/<exercise-id>/target
   ./deploy.sh
   ./validate.sh
   ```

5. Use focused Run Mode for next-action guidance, or the command center and
   generated CLI for detailed controls:

   ```bash
   cd generated/exercises/<exercise-id>/chaos
   python3 chaos_cli.py list
   python3 chaos_cli.py preflight
   python3 chaos_cli.py run payment_failure --intensity medium --pattern burst --duration 300
   python3 chaos_cli.py state
   python3 chaos_cli.py reset
   ```

6. Pause or resume the exercise as needed; scheduled narratives freeze with the
   clock and resume from the same exercise time.
7. Stop active runs, complete the exercise, assess objectives, assign corrective
   actions in the Evaluator Workspace, and download the AAR/IP evidence package.
8. Clean up:

   ```bash
   cd generated/exercises/<exercise-id>/cleanup
   ./destroy.sh
   ```

Generated services:

- Target: [http://127.0.0.1:8088](http://127.0.0.1:8088)
- Chaos API: [http://127.0.0.1:8090/docs](http://127.0.0.1:8090/docs)

Set `LIVEFIRE_TARGET_HOST_PORT` or `LIVEFIRE_CONTROL_HOST_PORT` before
deployment when the default host ports are already in use.

## Portable Design Library

Open **Design Library** to launch a built-in pack, create an immutable
organization-profile version, import a validated scenario-pack JSON file, or
export a pack for another LiveFireTTX installation. From an exercise command
center, use **Capture this design as a reusable scenario pack** to retain the
exercise defaults, inject design, safe action references, and checkpoints while
excluding runtime IDs, package paths, trigger history, and evidence.

Imported packs cannot add actions outside the selected built-in scenario's
allowlist. See [`docs/SCENARIO_PACKS.md`](docs/SCENARIO_PACKS.md) and
[`examples/scenario-pack-example.json`](examples/scenario-pack-example.json).

## Shared Deployment

Local mode remains the default and requires no sign-in. For an HTTPS-protected
shared facilitator deployment, enable shared mode and provide an initial
administrator password:

```bash
export LIVEFIRE_SHARED_MODE=true
export LIVEFIRE_ALLOWED_HOSTS=livefire.example
export LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD='replace-with-a-long-random-password'
export LIVEFIRE_SECURE_COOKIES=true
uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

Place an HTTPS reverse proxy in front of the loopback-bound process. After the
first administrator account is created, remove the bootstrap password from the
runtime environment. See
[`docs/SHARED_DEPLOYMENTS.md`](docs/SHARED_DEPLOYMENTS.md).

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `LIVEFIRE_DATA_ROOT` | `~/.livefirettx` | Base directory for persistent local data |
| `LIVEFIRE_DATABASE_PATH` | `<data-root>/livefirettx.db` | SQLite application database |
| `LIVEFIRE_GENERATED_ROOT` | `<data-root>/generated/exercises` | Generated exercise packages |
| `LIVEFIRE_BACKUP_ROOT` | `<data-root>/backups` | CLI backup destination |
| `LIVEFIRE_CONTROL_URL` | `http://127.0.0.1:8090` | Local chaos controller |
| `LIVEFIRE_ALLOW_CONTAINER_HOST` | `false` | Permit the exact container-to-host bridge |
| `LIVEFIRE_REQUEST_TIMEOUT_SECONDS` | `3` | Controller request timeout |
| `LIVEFIRE_SCHEDULER_ENABLED` | `true` | Enable automatic narrative delivery |
| `LIVEFIRE_SCHEDULER_INTERVAL_SECONDS` | `2` | Scheduled-delivery polling interval |
| `LIVEFIRE_LAB_CONTROLS_ENABLED` | `true` | Enable fixed one-click Docker controls on a direct host install |
| `LIVEFIRE_LAB_COMMAND_TIMEOUT_SECONDS` | `180` | Maximum lifecycle operation time |
| `LIVEFIRE_SHARED_MODE` | `false` | Require authenticated role permissions |
| `LIVEFIRE_ALLOWED_HOSTS` | Loopback hosts | Trusted browser hostnames; non-loopback requires shared mode |
| `LIVEFIRE_SESSION_TTL_MINUTES` | `480` | Server-side session lifetime |
| `LIVEFIRE_SECURE_COOKIES` | Shared-mode value | Require HTTPS-only session cookies |
| `LIVEFIRE_BOOTSTRAP_ADMIN_USERNAME` | `admin` | First shared-mode administrator username |
| `LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD` | unset | First shared-mode administrator password; 12–1024 characters |

The control URL must remain on loopback unless the container-only
`host.docker.internal` bridge is explicitly enabled. See
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Backup and Restore

Download a backup from the home screen or use the local administration CLI:

```bash
livefirettx doctor
livefirettx backup
livefirettx inspect-backup backups/livefirettx-<timestamp>.zip
livefirettx restore backups/livefirettx-<timestamp>.zip --confirm
```

Stop the application before restoring. Archives contain the SQLite snapshot,
generated exercise packages, and a versioned manifest. Active authentication
sessions are intentionally excluded.

## Development and Release Gates

```bash
pip install -r requirements-dev.txt
make test
make release-check
make app-container-smoke
make docker-smoke
```

`make release-check` runs linting, Python compilation, mypy, service coverage,
application smoke checks, dependency and secret scanning, and package builds.
GitHub Actions repeats these checks on Python 3.11, 3.12, and 3.13. The Docker
gate generates a critical
dependency exercise, deploys both generated services, validates them, applies
and resets a bounded fault, and tears the environment down.

## Safety

LiveFireTTX simulates symptoms and operational pressure. It does not generate
malware, credential theft, exploit chains, persistence, evasion,
anti-forensics, destructive payloads, or unauthorized access tooling.

Generated actions modify synthetic state and package-contained artifacts only.
Review [`docs/SAFETY.md`](docs/SAFETY.md) and
[`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) before operation.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)
- [`docs/SCENARIO_PACKS.md`](docs/SCENARIO_PACKS.md)
- [`docs/SHARED_DEPLOYMENTS.md`](docs/SHARED_DEPLOYMENTS.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/SAFETY.md`](docs/SAFETY.md)
- [`docs/RELEASE_SECURITY_REVIEW.md`](docs/RELEASE_SECURITY_REVIEW.md)
- [`docs/SECURITY_EXCEPTIONS.md`](docs/SECURITY_EXCEPTIONS.md)
- [`docs/UPGRADING.md`](docs/UPGRADING.md)
- [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)

## License

LiveFireTTX is licensed under the Functional Source License, Version 1.1, ALv2
Future License (`FSL-1.1-ALv2`).

Copyright (c) 2026 Steve Manzuik.

See [`LICENSE`](LICENSE).
