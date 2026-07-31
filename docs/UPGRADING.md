# Upgrading

## From v1.3 to v1.4

1. Stop the facilitator application and create a backup.
2. Preserve the complete data root. v1.4 has no database migration and keeps
   schema version 5.
3. Install v1.4 with Python 3.11 or newer and start the application.
4. The first evidence export creates
   `<data-root>/evidence-signing.key`. Keep the file owner-only and on persistent
   storage. Existing unsigned evidence ZIPs remain readable but cannot be
   upgraded into signed historical exports without regenerating them from
   retained exercise state.
5. Set `LIVEFIRE_EVIDENCE_RETENTION_DAYS` and
   `LIVEFIRE_EVIDENCE_RETENTION_COUNT` before export if the defaults of 365 days
   and 25 exports per exercise do not match local policy.
6. Create and verify a signed export:

   ```bash
   livefirettx verify-evidence <downloaded-evidence.zip>
   ```

7. Preserve the signing key separately from LiveFireTTX backups when old
   evidence must remain verifiable after host restore.
8. Development and release environments must install Chromium with
   `python -m playwright install chromium` before `make release-check`.

## From v1.2 to v1.3

1. Stop the facilitator application and create a backup.
2. Install v1.3 with Python 3.11 or newer.
3. Start the application once. Schema migration 5 adds immutable scenario-pack
   and organization-profile libraries, exercise provenance, users, and sessions.
   Existing exercises and generated packages are unchanged.
4. Built-in scenario packs are seeded as version `1.0.0`. Existing exercises do
   not receive pack provenance automatically; capture them from the command
   center if they should become reusable designs.
5. Local mode remains the default and requires no accounts or login.
6. Before enabling shared mode, configure an HTTPS reverse proxy, an explicit
   allowed host, and an initial administrator password. Follow
   [`SHARED_DEPLOYMENTS.md`](SHARED_DEPLOYMENTS.md).
7. After the first administrator account exists, remove
   `LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD` from the runtime environment and create
   role-scoped accounts from **Users**.
8. Create a new v1.3 backup. Account records are retained, but active sessions
   are intentionally removed from every backup snapshot.

## From v1.1 to v1.2

1. Stop the facilitator application and create a backup.
2. Install v1.2 with Python 3.11 or newer.
3. Start the application once. Schema migration 4 adds MSEL checkpoint and
   improvement-action tables without modifying existing exercise packages.
4. Existing exercises retain their inject schedules but receive no automatic
   default checkpoints. Add checkpoints from the command center as needed.
5. Newly generated exercises include three objective-linked operational
   checkpoints and expose Run, Presentation, and Evaluator views.
6. Direct host installs enable fixed one-click Docker lifecycle controls by
   default. Set `LIVEFIRE_LAB_CONTROLS_ENABLED=false` to require manual package
   scripts. Application container deployments already disable these controls.

## From v1.0 to v1.1

1. Stop the facilitator application and create a backup.
2. Install v1.1 with Python 3.11 or newer.
3. Start the application once. Schema migration 3 adds nullable clock and
   schedule fields without changing existing exercise packages or evidence.
4. Existing exercises remain in `created` state with no schedules. Configure
   narrative timing from each exercise command center.
5. Newly generated exercises include automatic T+0 and T+20 narrative injects.
   Set `LIVEFIRE_SCHEDULER_ENABLED=false` before startup to retain manual-only
   delivery.

## From v0.6 to v1.0

1. Stop the facilitator application and generated Docker environments.
2. Copy `livefirettx.db` and `generated/exercises/` to a safe location.
3. Choose where v1.0 should keep the existing state. To continue using the
   project directory, set the data root while your shell is in the repository:

   ```bash
   export LIVEFIRE_DATA_ROOT="$PWD"
   ```

   Otherwise, copy the database and generated directory into the new default
   `~/.livefirettx` data root before starting v1.0.
4. Install v1.0 with Python 3.11 or newer:

   ```bash
   pip install -e .
   ```

5. Start the application once. Ordered migrations add the schema metadata and
   preserve the existing trigger-count migration.
6. Run:

   ```bash
   livefirettx doctor
   ```

7. Regenerate exercises that need v1.0 dependency actions or the v1.0
   controller. Existing v0.x packages remain readable but do not gain new
   generated endpoints automatically.
8. Create a v1 backup:

   ```bash
   livefirettx backup
   ```

## Restore

Stop the application before restore:

```bash
livefirettx inspect-backup <archive.zip>
livefirettx restore <archive.zip> --confirm
```

Restore rejects unsafe ZIP paths, symbolic links, invalid SQLite snapshots, and
database schemas newer than the running application.
