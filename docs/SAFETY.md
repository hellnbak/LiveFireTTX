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

The generated v0.2 chaos controller:

- Exposes only actions allowlisted for the selected scenario
- Changes generated test state and synthetic artifacts only
- Uses bounded low, medium, and high intensity profiles
- Supports reset without deleting evidence artifacts
- Binds generated host ports to `127.0.0.1`
- Rejects facilitator scripts that resolve outside the generated chaos directory
- Does not accept shell commands, executable payloads, target addresses, or arbitrary file paths

## Operator guidance

Run generated environments only in isolated lab systems. Review generated packages before executing them. Do not expose the chaos control API beyond localhost, point generated controls at production systems, or replace generated actions with unreviewed code. Use cloud renderers only with scoped lab accounts when those features are added.
