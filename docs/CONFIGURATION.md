# Configuration

LiveFireTTX reads configuration from environment variables at process startup.

| Variable | Default | Validation |
| --- | --- | --- |
| `LIVEFIRE_DATA_ROOT` | `~/.livefirettx` | Resolved user-writable base path |
| `LIVEFIRE_DATABASE_PATH` | `<data-root>/livefirettx.db` | Resolved local path |
| `LIVEFIRE_GENERATED_ROOT` | `<data-root>/generated/exercises` | Resolved local path |
| `LIVEFIRE_BACKUP_ROOT` | `<data-root>/backups` | Resolved local path |
| `LIVEFIRE_CONTROL_URL` | `http://127.0.0.1:8090` | Must use an approved local origin |
| `LIVEFIRE_ALLOW_CONTAINER_HOST` | `false` | Allows the exact `host.docker.internal` controller origin |
| `LIVEFIRE_REQUEST_TIMEOUT_SECONDS` | `3` | Positive integer |

Generated package deployment also accepts:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LIVEFIRE_TARGET_HOST_PORT` | `8088` | Target host port |
| `LIVEFIRE_CONTROL_HOST_PORT` | `8090` | Controller host port |
| `LIVEFIRE_RUNTIME_UID` | Current user through `deploy.sh` | Generated container user ID |
| `LIVEFIRE_RUNTIME_GID` | Current group through `deploy.sh` | Generated container group ID |

Example:

```bash
export LIVEFIRE_DATA_ROOT="$HOME/.livefirettx"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The three specific storage variables override paths derived from
`LIVEFIRE_DATA_ROOT` when set.

## Operational Endpoints

- `GET /healthz` verifies the application process.
- `GET /readyz` verifies database integrity and reports schema/version context.
- `GET /admin/backup.zip` downloads a consistent local backup.

The application does not provide arbitrary remote-controller configuration in
v1.0. The container-only host bridge is disabled unless
`LIVEFIRE_ALLOW_CONTAINER_HOST=true`; it permits only the exact
`host.docker.internal` hostname over HTTP.
