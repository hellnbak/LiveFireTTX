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

## Operator guidance

Run generated environments only in isolated lab systems. Review generated packages before executing them. Do not point generated scripts at production systems. Use cloud renderers only with scoped lab accounts when those features are added.
