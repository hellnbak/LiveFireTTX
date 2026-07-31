#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
smoke_root="${repo_root}/.release-smoke"
python_bin="${PYTHON:-python3}"
export LIVEFIRE_GENERATED_ROOT="${smoke_root}/exercises"
export LIVEFIRE_DATABASE_PATH="${smoke_root}/livefirettx.db"
read -r LIVEFIRE_TARGET_HOST_PORT LIVEFIRE_CONTROL_HOST_PORT <<<"$(
  "${python_bin}" - <<'PY'
import socket

sockets = []
ports = []
for _ in range(2):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sockets.append(sock)
    ports.append(str(sock.getsockname()[1]))
print(" ".join(ports))
for sock in sockets:
    sock.close()
PY
)"
export LIVEFIRE_TARGET_HOST_PORT
export LIVEFIRE_CONTROL_HOST_PORT
export LIVEFIRE_TARGET_URL="http://127.0.0.1:${LIVEFIRE_TARGET_HOST_PORT}"
export LIVEFIRE_RUNTIME_UID="${LIVEFIRE_RUNTIME_UID:-$(id -u)}"
export LIVEFIRE_RUNTIME_GID="${LIVEFIRE_RUNTIME_GID:-$(id -g)}"

cleanup() {
  if [[ -n "${package_path:-}" && -d "${package_path}/target" ]]; then
    docker compose -f "${package_path}/target/docker-compose.yml" down -v || true
  fi
  rm -rf "${smoke_root}"
}
trap cleanup EXIT

rm -rf "${smoke_root}"
package_path="$(
  cd "${repo_root}"
  "${python_bin}" - <<'PY'
from app.models import ExerciseCreate
from app.services.generator import create_exercise_from_request

exercise, _ = create_exercise_from_request(
    ExerciseCreate(
        name="v1 release smoke",
        scenario_type="dependency_cascade",
        business_system="Digital Commerce",
    )
)
print(exercise.package_path)
PY
)"

docker compose -f "${package_path}/target/docker-compose.yml" up -d --build
"${package_path}/target/validate.sh"
(
  cd "${package_path}/chaos"
  "${python_bin}" chaos_cli.py preflight
  "${python_bin}" chaos_cli.py run payment_failure \
    --intensity low \
    --duration 15
  "${python_bin}" - <<'PY'
import json
import os
import time
import urllib.request

url = f"{os.environ['LIVEFIRE_TARGET_URL']}/health"
for _ in range(30):
    with urllib.request.urlopen(url, timeout=2) as response:
        state = json.loads(response.read())
    if state["conditions"]["payment_failure_rate"] > 0:
        print(json.dumps({"observed_dependency_impact": state["conditions"]}))
        break
    time.sleep(0.2)
else:
    raise SystemExit("Target did not observe the payment failure condition")
PY
  "${python_bin}" chaos_cli.py reset
  "${python_bin}" - <<'PY'
import json
import os
import time
import urllib.request

url = f"{os.environ['LIVEFIRE_TARGET_URL']}/health"
for _ in range(30):
    with urllib.request.urlopen(url, timeout=2) as response:
        state = json.loads(response.read())
    if not any(state["conditions"].values()):
        print(json.dumps({"observed_dependency_recovery": True}))
        break
    time.sleep(0.2)
else:
    raise SystemExit("Target did not clear the dependency condition after reset")
PY
)
