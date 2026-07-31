# Upgrading

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
