# v1.3 Release Checklist

## Code and Data

- [ ] `app/version.py`, `pyproject.toml`, and changelog versions match.
- [ ] Database migration and restore tests pass.
- [ ] Schema version 5 creates pack, profile, account, session, and provenance records.
- [ ] No generated packages, databases, backups, or secrets are tracked.
- [ ] `git diff --check` passes.

## Automated Gates

- [ ] `make release-check`
- [ ] `make app-container-smoke`
- [ ] `make docker-smoke`
- [ ] GitHub Actions passes on Python 3.11, 3.12, and 3.13.
- [ ] CodeQL analysis passes.
- [ ] Wheel and source distribution install in a clean Python 3.11+ environment.

## Exercise Acceptance

- [ ] Every scenario generates and compiles.
- [ ] Generated target and controller report matching exercise IDs.
- [ ] Each scenario action starts, records evidence, resets, and leaves clear state.
- [ ] Playbook validation, safety budgets, pause/resume/skip/stop, and replay work.
- [ ] Dependency map changes to degraded and returns to healthy after reset.
- [ ] Emergency stop ends all active actions and playbooks.
- [ ] Clock start, pause, resume, complete, and reset transitions retain time.
- [ ] Due narrative injects deliver once and pause with exercise time.
- [ ] Scheduler-disabled startup retains schedules for manual delivery.
- [ ] MSEL ordering, due-state, checkpoint completion, and objective links work.
- [ ] Participant display reveals delivered information only.
- [ ] Evaluator observations and corrective-action state persist and export.
- [ ] Direct-host lifecycle controls use only the generated Compose package.
- [ ] Container mode leaves one-click Docker controls disabled.
- [ ] Evidence and after-action exports open successfully.
- [ ] Cleanup removes generated Docker resources.
- [ ] Built-in scenario packs seed idempotently and retain immutable checksums.
- [ ] Exercise capture/export/import/recreate round trip excludes runtime IDs and paths.
- [ ] Imported packs cannot reference actions outside their base scenario allowlist.
- [ ] Organization profiles apply business system, roles, and objectives.
- [ ] Anonymous shared-mode access requires sign-in.
- [ ] Administrator, facilitator, evaluator, and participant route boundaries pass.
- [ ] Logout, password reset, account disablement, and expiration revoke sessions.
- [ ] Backup snapshots contain users but no active authentication sessions.

## Documentation and Security

- [ ] README quick start succeeds on a clean host.
- [ ] Configuration and upgrade guides match actual behavior.
- [ ] Safety and threat-model reviews are current.
- [ ] Release security review covers the v1.3 portability and authentication delta.
- [ ] Dependency and secret scanning show no unaccepted release blocker.
- [ ] Documented security exceptions still match upstream package constraints.
- [ ] No open critical or high-severity defects remain.

## Publication

- [ ] Merge the release branch.
- [ ] Create signed tag `v1.3.0`.
- [ ] Confirm the release workflow publishes source and wheel artifacts.
- [ ] Publish release notes and known limitations.
