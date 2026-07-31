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

## v0.4 Chaos Orchestration Studio

- Multi-step chaos sequences and saved playbooks
- Timer-based inject and action scheduling
- Playbook pause, resume, skip, and emergency-stop controls
- Health-gated transitions between playbook stages
- Scenario-specific reusable playbook templates
- Steady, ramp, burst, flap, and seeded jitter fault patterns
- Concurrency, severity, and total-runtime safety budgets
- Deterministic playbook replay
- Live observed-impact telemetry and command-center UI
- Validated YAML playbook configuration

## v0.5 Exercise intelligence

- Run comparison and impact charts
- Markdown/CSV evidence package export
- Exercise scoring rubric and objective tracking
- Provisional readiness scoring with visible component signals
- Persisted facilitator ratings and evidence notes
- Generated after-action Markdown reports
- JSON state snapshot and export manifest
- Spreadsheet formula-injection protection in CSV evidence

## Next: v0.6 scenario design studio

- Visual drag-and-drop playbook builder
- Facilitator-defined safe artifact injects
- Additional simulated service dependencies
- Saved playbook template library
- Playbook import, export, clone, and version history
- Scenario preview and validation workspace

## Near-term exercise workflow

- Better scenario templates
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
- Signed and retention-managed evidence archives
