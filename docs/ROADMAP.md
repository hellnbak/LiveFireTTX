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

## Next: chaos orchestration

- Duration and automatic rollback for chaos actions
- Multi-step chaos sequences and saved playbooks
- Health probes with guardrails and stop conditions
- Timer-based optional inject scheduling
- Facilitator-defined safe artifact injects
- Richer action telemetry and observed-impact capture
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
