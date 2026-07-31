#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python3}"
host_port="$(
  "${python_bin}" - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
container_name="livefirettx-release-smoke-${host_port}"
volume_name="${container_name}-data"

cleanup() {
  docker rm -f "${container_name}" >/dev/null 2>&1 || true
  docker volume rm -f "${volume_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "${repo_root}"
docker build -t livefirettx:release-smoke .
docker volume create "${volume_name}" >/dev/null
docker run \
  --detach \
  --name "${container_name}" \
  --publish "127.0.0.1:${host_port}:8000" \
  --volume "${volume_name}:/data" \
  livefirettx:release-smoke >/dev/null

LIVEFIRE_APP_URL="http://127.0.0.1:${host_port}" "${python_bin}" - <<'PY'
import json
import os
import time
import urllib.parse
import urllib.request
from zipfile import ZipFile
from io import BytesIO

base_url = os.environ["LIVEFIRE_APP_URL"]
for _ in range(60):
    try:
        with urllib.request.urlopen(f"{base_url}/readyz", timeout=2) as response:
            readiness = json.loads(response.read())
        with urllib.request.urlopen(f"{base_url}/new", timeout=2) as response:
            setup = response.read().decode()
        if readiness["ready"] and "Critical Dependency Cascade" in setup:
            print(json.dumps({"application_ready": True, "version": readiness["version"]}))
            break
    except OSError:
        pass
    time.sleep(0.25)
else:
    raise SystemExit("Application container did not become ready")

payload = urllib.parse.urlencode(
    {
        "name": "Container release smoke",
        "scenario_type": "dependency_cascade",
        "platform": "local_docker",
        "business_system": "Digital Commerce",
        "difficulty": "advanced",
        "duration_minutes": "90",
        "participants": "Incident Commander, SRE",
        "objectives": "Map impact\nRecover safely",
    }
).encode()
request = urllib.request.Request(f"{base_url}/exercises", data=payload)
with urllib.request.urlopen(request, timeout=10) as response:
    exercise_url = response.geturl()
exercise_id = exercise_url.rstrip("/").rsplit("/", 1)[-1]
with urllib.request.urlopen(
    f"{base_url}/exercises/{exercise_id}/download",
    timeout=10,
) as response:
    package = response.read()
with ZipFile(BytesIO(package)) as archive:
    required = {
        "exercise.yml",
        "target/docker-compose.yml",
        "chaos/control.json",
    }
    if not required.issubset(archive.namelist()):
        raise SystemExit("Container-generated package is incomplete")
print(json.dumps({"package_downloaded": True, "exercise_id": exercise_id}))
PY
