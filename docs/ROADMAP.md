# Roadmap

## v0.1 MVP

- Local FastAPI app
- Scenario builder
- Scenario-specific generated packages
- Local Docker Compose target environment
- Safe chaos scripts
- Manual facilitator inject console
- Run log
- After-action report template

## v0.2 Safe chaos control

- Scenario-scoped chaos control API and CLI
- Low, medium, and high intensity profiles
- Reversible state with per-action and full reset
- Repeatable chaos actions from the facilitator console
- Live chaos state and execution count in the console
- Target endpoints that react to simulated conditions
- Localhost-only generated service bindings
- Automated smoke tests for every generated scenario package

## v0.3 Guarded chaos runs

- Target and controller preflight checks
- Bounded run durations with automatic rollback
- Pending, active, completed, aborted, and failed lifecycle states
- Strict, standard, and observe guardrail profiles
- Latency, error-rate, availability, and exercise-identity stop conditions
- Before/after and periodic target observations
- Facilitator emergency stop
- Target-side expiration when the controller is unavailable

## Next: v0.4 chaos orchestration

- Multi-step chaos sequences and saved playbooks
- Timer-based inject and action scheduling
- Playbook pause, resume, skip, and emergency-stop controls
- Health-gated transitions between playbook stages
- Scenario-specific reusable playbook templates
- Richer observed-impact charts and telemetry
- Facilitator-defined safe artifact injects
- Additional simulated service dependencies

## Near-term exercise workflow

- Export run logs to Markdown/CSV
- Better scenario templates
- Exercise scoring rubric
- Role-specific participant views
- Built-in sample data sets
- Improved UI and branding

## Cloud / enterprise

- AWS Terraform renderer
- AWS Fault Injection Service renderer
- Kubernetes / Helm renderer
- Azure Chaos Studio renderer
- Slack and Teams inject delivery
- Jira and ServiceNow ticket injects
- SIEM and EDR synthetic alert connectors
- Multi-user authentication
- Organization/workspace support
- Versioned scenario library
- Evidence package export
