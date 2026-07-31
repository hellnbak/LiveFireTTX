# Security Exceptions

## Starlette 0.49.3

The v1.0 runtime pins the newest Starlette release compatible with FastAPI
0.128.8. On 2026-07-30, the vulnerability service reports the following
advisories with fixes only in Starlette 1.x:

- `PYSEC-2026-161`
- `PYSEC-2026-248`
- `PYSEC-2026-249`
- `PYSEC-2026-2280`
- `PYSEC-2026-2281`

FastAPI 0.128.8 declares `starlette>=0.40.0,<1.0.0`, so those fix versions
cannot be installed without violating the framework's published compatibility
contract.

## Mitigations

- The v1.0 facilitator and generated services bind to localhost.
- The application is not supported as an internet-facing or multi-user service.
- Multipart parsing was removed; playbook imports use bounded raw YAML.
- URL-encoded form parsing is bounded by bytes and field count.
- Generated controllers accept no arbitrary target address, command, or path.
- Input, YAML, archive, package, and filesystem boundaries are explicitly
  validated.

The release audit ignores only the five IDs above. Any other advisory fails the
release gate. This exception must be revisited when FastAPI publishes Starlette
1.x compatibility.
