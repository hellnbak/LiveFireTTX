# Safety Model

LiveFireTTX is intended for controlled tabletop and resilience exercises. The platform should simulate incident symptoms and decision pressure without creating unsafe capability.

## Allowed simulation patterns

The MVP supports safe patterns such as:

- Synthetic alert generation
- Safe test-file renames
- Fake ransom-note artifacts clearly marked as simulated
- Local app degradation flags
- Synthetic DNS/auth failure artifacts
- Backup uncertainty reports
- Dependency advisory artifacts
- Data integrity warning artifacts
- Facilitator notes and manual injects

## Disallowed behavior

LiveFireTTX should not generate, execute, or facilitate:

- Malware or ransomware
- Credential theft
- Exploit chains
- Persistence
- Evasion
- Anti-forensics
- Destructive deletion
- Unauthorized scanning
- Real-world data exfiltration
- Bypass logic for security controls

## Design principle

Simulate indicators and operational impact. Do not create real malicious capability.

## Chaos controller guardrails

The generated v0.4 chaos controller:

- Exposes only actions allowlisted for the selected scenario
- Changes generated test state and synthetic artifacts only
- Uses bounded low, medium, and high intensity profiles
- Requires a matching target and controller preflight
- Limits every run to 15–3600 seconds
- Applies only steady, ramp, burst, flap, or seeded jitter multipliers
- Validates YAML playbooks before saving or execution
- Limits playbooks to 20 stages and 60–7200 seconds
- Enforces per-playbook concurrency and severity budgets
- Captures immutable definitions and seeds for auditable replay
- Pauses future scheduling without extending active action duration
- Monitors latency, error rate, target availability, and exercise identity
- Automatically rolls back expired or guardrail-aborted effects
- Stops active playbooks and actions through one emergency control
- Supports reset and emergency stop without deleting evidence artifacts
- Binds generated host ports to `127.0.0.1`
- Rejects facilitator scripts that resolve outside the generated chaos directory
- Does not accept shell commands, executable payloads, target addresses, or arbitrary file paths

## Operator guidance

Run generated environments only in isolated lab systems. Review generated packages before executing them. Do not expose the chaos control API beyond localhost, point generated controls at production systems, or replace generated actions with unreviewed code. Use cloud renderers only with scoped lab accounts when those features are added.

## Evidence and scoring safety

- Readiness scores are provisional exercise signals, not compliance findings.
- Objective ratings are explicitly assigned by the facilitator and are never inferred.
- Evidence exports contain local exercise data, notes, state, and artifact references.
- CSV cells beginning with spreadsheet formula characters are escaped on export.
- Operators should review evidence packages before sharing them outside the exercise team.

## Facilitator artifact safety

- Artifact types are restricted to messages, alerts, tickets, and advisories.
- Artifact files receive generated names and remain under `artifacts/facilitator/`.
- Titles and audiences must be single-line values; content is size-limited.
- Every artifact is watermarked as simulated at the beginning and end.
- Triggering an artifact verifies the resolved path remains inside the package.
- Artifacts cannot contain executable payloads or select an output path.
