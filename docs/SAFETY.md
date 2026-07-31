# Safety Model

LiveFireTTX is intended for controlled tabletop and resilience exercises. It
simulates incident symptoms and decision pressure without creating malicious or
destructive capability.

## Allowed Simulation Patterns

- Synthetic alerts, messages, tickets, and advisories
- Safe renaming of generated test files
- Local application latency and error conditions
- Synthetic DNS and authentication failures
- Backup uncertainty and seeded data-integrity warnings
- Simulated payment failure, queue backlog, storage throttle, stale reads,
  vendor API failure, retry pressure, and telemetry delay
- Facilitator notes, assessments, and package-contained evidence

## Disallowed Behavior

LiveFireTTX must not generate, execute, or facilitate:

- Malware, ransomware, credential theft, or exploit chains
- Persistence, evasion, anti-forensics, or destructive deletion
- Unauthorized scanning, access, or data exfiltration
- Security-control bypass logic
- Arbitrary commands, executable injects, remote target addresses, or
  operator-selected filesystem paths

## v1.2 Safety Guardrails

- Allows only actions included in the generated scenario
- Modifies generated synthetic state and package artifacts only
- Binds target, controller, and facilitator services to localhost
- Requires matching target and controller exercise identities
- Bounds runs to 15–3600 seconds
- Supports only approved intensity profiles and fault patterns
- Validates playbooks before save and execution
- Limits stage count, total time, concurrency, and severity
- Captures immutable definitions and deterministic replay seeds
- Monitors target availability, identity, latency, and error rate
- Automatically rolls back expired and guardrail-aborted effects
- Provides per-action reset and global emergency stop
- Preserves evidence when state is reset
- Rejects paths that resolve outside generated package boundaries
- Restricts automatic scheduling to narrative injects; chaos actions always
  require an explicit facilitator or playbook control request
- Restricts one-click lab lifecycle to fixed Docker Compose operations against
  a generated, path-contained, non-symlinked exercise definition
- Keeps host Docker control disabled in the application container
- Reveals only delivered narrative and artifact information in participant view

Dependency faults alter local API behavior only. They do not contact payment
processors, queues, storage providers, telemetry systems, or third-party APIs.

## Artifact and Evidence Safety

- Facilitator artifacts are approved plain-Markdown types with generated names.
- Artifacts are visibly watermarked at the beginning and end.
- Titles, audiences, stages, content size, and resolved paths are validated.
- CSV formula-leading cells are escaped.
- Readiness scores are provisional exercise signals, not compliance findings.
- Evidence archives may contain participant notes and should be reviewed before
  external sharing.

## Operator Guidance

Run only on isolated lab systems. Review generated packages before deployment.
Do not expose ports beyond localhost, point generated controls at production, or
replace safe actions with unreviewed code. Use emergency stop whenever observed
impact exceeds the exercise plan.
