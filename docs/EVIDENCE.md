# Signed Evidence

LiveFireTTX v1.4 produces tamper-evident evidence packages for controlled
exercise review. Signing establishes that an archive matches the state exported
by an installation holding the same key. It does not establish participant
identity, legal non-repudiation, or the truth of facilitator observations.

## Archive Format

Evidence manifest schema 4 includes:

- Exercise identifier, export time, and lifecycle clock state
- One path, byte count, and SHA-256 digest for every evidence file
- HMAC-SHA256 algorithm and installation key ID metadata
- A detached `manifest.sig` containing the manifest digest and signature

Verification rejects missing, changed, duplicate, undeclared, oversized,
symlinked, or unsafely named members before returning a valid result.

## Key Handling

The first export creates a random 32-byte key at
`LIVEFIRE_EVIDENCE_SIGNING_KEY_PATH`, which defaults to
`~/.livefirettx/evidence-signing.key`. POSIX key permissions must be owner-only:

```bash
chmod 600 ~/.livefirettx/evidence-signing.key
```

The key is not included in evidence archives, generated exercise downloads, or
LiveFireTTX backups. Preserve it separately if old exports must remain
verifiable after host loss or restore. Transfer it only through a secure channel
separate from the archive.

## Verification

Verify with the originating installation key:

```bash
livefirettx verify-evidence exercise-evidence.zip
```

Verify with an explicitly supplied key:

```bash
livefirettx verify-evidence exercise-evidence.zip \
  --key-file /secure/path/origin-evidence.key
```

A successful result reports `valid: true`, the exercise ID, export time, key ID,
and verified evidence-file count. Any verification error exits without claiming
the archive is valid.

## Retention

Each new export is retained under the exercise's `reports/evidence/` directory.
After writing an export, LiveFireTTX removes strict application-generated files
that exceed either:

- `LIVEFIRE_EVIDENCE_RETENTION_DAYS`, default `365`
- `LIVEFIRE_EVIDENCE_RETENTION_COUNT`, default `25` per exercise

The command center and evaluator workspace show retained exports and their
verification state. A retained archive is verified again before download.

Retention is not archival backup. Copy required evidence and the separately
protected verification key into the organization's approved record system.
