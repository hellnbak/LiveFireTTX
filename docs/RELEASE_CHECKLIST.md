# v1.0 Release Checklist

## Code and Data

- [ ] `app/version.py`, `pyproject.toml`, and changelog versions match.
- [ ] Database migration and restore tests pass.
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
- [ ] Evidence and after-action exports open successfully.
- [ ] Cleanup removes generated Docker resources.

## Documentation and Security

- [ ] README quick start succeeds on a clean host.
- [ ] Configuration and upgrade guides match actual behavior.
- [ ] Safety and threat-model reviews are current.
- [ ] Dependency and secret scanning show no unaccepted release blocker.
- [ ] Documented security exceptions still match upstream package constraints.
- [ ] No open critical or high-severity defects remain.

## Publication

- [ ] Merge the release branch.
- [ ] Create signed tag `v1.0.0`.
- [ ] Confirm the release workflow publishes source and wheel artifacts.
- [ ] Publish release notes and known limitations.
