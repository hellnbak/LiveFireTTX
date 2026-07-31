# Shared Deployments

LiveFireTTX remains local-first. Shared mode is intended for a controlled,
HTTPS-protected exercise network where multiple trusted users need separate
facilitator, evaluator, participant, or administrator access.

## Deployment Boundary

- Bind Uvicorn to loopback and place an authenticated network path behind a
  maintained HTTPS reverse proxy.
- Set an explicit `LIVEFIRE_ALLOWED_HOSTS` value. Non-loopback hosts require
  `LIVEFIRE_SHARED_MODE=true`.
- Keep generated target and chaos-controller ports bound to loopback.
- Do not publish the application container's port broadly or mount the Docker
  socket into it.
- Restrict proxy-header trust to the reverse proxy address.

## First Start

```bash
export LIVEFIRE_SHARED_MODE=true
export LIVEFIRE_ALLOWED_HOSTS=livefire.example
export LIVEFIRE_BOOTSTRAP_ADMIN_USERNAME=admin
export LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD='replace-with-a-long-random-password'
export LIVEFIRE_SECURE_COOKIES=true
uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips=127.0.0.1
```

After signing in as the initial administrator, open **Users** and create
role-scoped accounts. Remove the bootstrap password from the service
environment after the first successful account creation.

## Roles

- **Administrator:** accounts, backups, design, facilitation, and evaluation
- **Facilitator:** packs, profiles, exercise generation, run and chaos controls,
  and evaluation
- **Evaluator:** evaluator workspace, evidence, objective ratings, reports, and
  corrective actions
- **Participant:** participant display and role briefs

Permissions are enforced before route dispatch. A participant-safe presentation
projection still removes future injects, chaos controls, facilitator notes,
evaluations, package paths, and corrective actions.

## Authentication Controls

- PBKDF2-SHA256 password hashing with random salts
- Random opaque session tokens stored only as SHA-256 hashes
- HttpOnly, SameSite Strict cookies that default to Secure in shared mode
- Fixed session expiration and revocation on logout, password reset, or account
  disablement
- Last-active-administrator protection
- Same-origin mutation checks and explicit trusted-host enforcement
- No active sessions in backup archives

Shared mode does not add organization tenancy, external identity providers,
internet-facing hardening, or authorization for real cloud fault injection.
Operate it only on a controlled exercise network and follow the threat model.
