#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-status}"
CONTAINER_NAME="elysia-qdrant"
IMAGE="docker.io/qdrant/qdrant@sha256:a0e04fe623cb064502cd869cefc1dc7ce359d8edd481063b5bd351c0a0a2c91e"
IMAGE_VERSION="1.19.0-unprivileged"
PORT="6333"
USER_HOME="${HOME:?HOME is required}"
CONFIG_BASE="${XDG_CONFIG_HOME:-$USER_HOME/.config}"
CACHE_BASE="${XDG_CACHE_HOME:-$USER_HOME/.cache}"
STATE_BASE="${XDG_STATE_HOME:-$USER_HOME/.local/state}"
SERVICE_CONFIG="$CONFIG_BASE/elysia/services/qdrant"
SERVER_CONFIG="$SERVICE_CONFIG/production.yaml"
CLIENT_CONFIG="$SERVICE_CONFIG/client.json"
API_KEY_FILE="$SERVICE_CONFIG/api-key"
RUNTIME_FILE="$SERVICE_CONFIG/container-runtime"
PROJECTION_ROOT="$CACHE_BASE/elysia/memory/semantic-qdrant"
STORAGE="$PROJECTION_ROOT/storage"
SNAPSHOTS="$PROJECTION_ROOT/snapshots"
RECOVERY_ROOT="$STATE_BASE/elysia/recoverable-semantic-projections"
MEMORY_LIMIT="${ELYSIA_QDRANT_MEMORY_LIMIT:-24g}"
CPU_LIMIT="${ELYSIA_QDRANT_CPU_LIMIT:-16}"
RUNTIME_UID="$(id -u)"
RUNTIME_GID="$(id -g)"

usage() {
  echo "Usage: scripts/manage_qdrant.sh [status|install|start|stop|restart|verify|snapshot|upgrade|reset-derived|uninstall]"
  echo "Install/upgrade explicitly acquire one pinned official image; the service binds only 127.0.0.1:6333 and never auto-starts."
}

case "$ACTION" in
  status|install|start|stop|restart|verify|snapshot|upgrade|reset-derived|uninstall) ;;
  *) usage >&2; exit 2 ;;
esac

for candidate in "$CONFIG_BASE" "$CACHE_BASE" "$STATE_BASE"; do
  [[ "$candidate" = /* ]] || { echo "XDG locations must be absolute." >&2; exit 2; }
done

select_runtime() {
  if [[ -f "$RUNTIME_FILE" ]]; then
    FILE_MODE=$((8#$(stat -c '%a' "$RUNTIME_FILE")))
    if [[ -L "$RUNTIME_FILE" ]] || (( (FILE_MODE & 077) != 0 )); then
      echo "The semantic container-runtime receipt is unsafe." >&2
      exit 1
    fi
    RUNTIME="$(<"$RUNTIME_FILE")"
    [[ "$RUNTIME" == "podman" || "$RUNTIME" == "docker" ]] || {
      echo "The semantic container-runtime receipt is invalid." >&2
      exit 1
    }
    if ! command -v "$RUNTIME" >/dev/null 2>&1 || ! "$RUNTIME" info >/dev/null 2>&1; then
      echo "The recorded semantic container runtime is unavailable." >&2
      exit 1
    fi
    return
  fi
  # Upgrade older installs by adopting the exact existing managed container;
  # never switch engines merely because discovery order changed.
  if command -v podman >/dev/null 2>&1 && podman inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    RUNTIME="podman"
  elif command -v docker >/dev/null 2>&1 && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    RUNTIME="docker"
  elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    RUNTIME="podman"
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    RUNTIME="docker"
  else
    echo "An accessible rootless Podman or bounded Docker runtime is required for the optional semantic profile." >&2
    exit 1
  fi
  umask 077
  mkdir -p "$SERVICE_CONFIG"
  printf '%s\n' "$RUNTIME" >"$RUNTIME_FILE"
  chmod 0600 "$RUNTIME_FILE"
}

select_runtime

exists() { "$RUNTIME" inspect "$CONTAINER_NAME" >/dev/null 2>&1; }

verify_container_contract() {
  exists || { echo "The managed semantic container is not installed." >&2; return 1; }
  python3 - "$RUNTIME" "$CONTAINER_NAME" "$IMAGE" "$RUNTIME_UID:$RUNTIME_GID" \
    "$SERVER_CONFIG" "$STORAGE" "$SNAPSHOTS" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

runtime, name, expected_image, expected_user, config, storage, snapshots = sys.argv[1:]
try:
    payload = json.loads(subprocess.check_output(
        [runtime, "inspect", name], text=True, timeout=20,
    ))
    item = payload[0]
except (OSError, subprocess.SubprocessError, ValueError, IndexError, TypeError) as exc:
    raise SystemExit("The managed semantic container contract could not be inspected.") from exc

container = item.get("Config") or {}
host = item.get("HostConfig") or {}
image = str(container.get("Image") or "")
expected_digest = expected_image.rsplit("@", 1)[-1]
if image != expected_image and not image.endswith("@" + expected_digest):
    raise SystemExit("The managed semantic container image is not the pinned digest.")
if str(container.get("User") or "") != expected_user:
    raise SystemExit("The managed semantic container user contract changed.")
if str(host.get("NetworkMode") or "") != "host" or host.get("PortBindings") not in (None, {}):
    raise SystemExit("The managed semantic container network contract changed.")
if host.get("ReadonlyRootfs") is not True or host.get("Privileged") is True:
    raise SystemExit("The managed semantic container confinement contract changed.")
restart_name = str((host.get("RestartPolicy") or {}).get("Name") or "").lower()
if restart_name not in {"", "no", "none"}:
    raise SystemExit("The managed semantic container acquired an auto-restart policy.")
if host.get("CapAdd") not in (None, []):
    raise SystemExit("The managed semantic container acquired added capabilities.")
security = " ".join(str(value).lower() for value in (host.get("SecurityOpt") or []))
if "no-new-privileges" not in security:
    raise SystemExit("The managed semantic container lost no-new-privileges.")

expected_mounts = {
    "/qdrant/config/production.yaml": (str(Path(config).resolve()), False),
    "/qdrant/storage": (str(Path(storage).resolve()), True),
    "/qdrant/snapshots": (str(Path(snapshots).resolve()), True),
}
observed = {}
for mount in item.get("Mounts") or []:
    destination = str(mount.get("Destination") or "")
    if destination in expected_mounts:
        observed[destination] = (
            str(Path(str(mount.get("Source") or "")).resolve()),
            bool(mount.get("RW")),
        )
if observed != expected_mounts:
    raise SystemExit("The managed semantic container XDG mount contract changed.")
PY
}

write_config() {
  umask 077
  mkdir -p "$SERVICE_CONFIG" "$STORAGE" "$SNAPSHOTS" "$RECOVERY_ROOT"
  chmod 0700 "$SERVICE_CONFIG" "$PROJECTION_ROOT" "$STORAGE" "$SNAPSHOTS" "$RECOVERY_ROOT"
  if [[ ! -f "$API_KEY_FILE" ]]; then
    python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(48))' >"$API_KEY_FILE"
    chmod 0600 "$API_KEY_FILE"
  fi
  API_KEY_VALUE="$(<"$API_KEY_FILE")"
  [[ ${#API_KEY_VALUE} -ge 32 ]] || { echo "The protected Qdrant API key is invalid." >&2; exit 1; }
  printf '%s\n' \
    'log_level: INFO' \
    'telemetry_disabled: true' \
    'service:' \
    '  host: 127.0.0.1' \
    "  http_port: $PORT" \
    '  grpc_port: null' \
    '  enable_cors: false' \
    "  api_key: '$API_KEY_VALUE'" \
    'storage:' \
    '  storage_path: /qdrant/storage' \
    '  snapshots_path: /qdrant/snapshots' \
    >"$SERVER_CONFIG"
  chmod 0600 "$SERVER_CONFIG"
  write_client_config true
}

write_client_config() {
  ENABLED_VALUE="$1"
  printf '%s\n' \
    '{' \
    '  "version": 1,' \
    "  \"enabled\": $ENABLED_VALUE," \
    '  "qdrant_url": "http://127.0.0.1:6333",' \
    '  "api_key_file": "api-key",' \
    '  "collection": "elysia_memory_semantic_v1",' \
    '  "ollama_url": "http://127.0.0.1:11434",' \
    '  "embedding_model": "qwen3-embedding:0.6b",' \
    '  "embedding_num_gpu": -1' \
    '}' \
    >"$CLIENT_CONFIG"
  chmod 0600 "$CLIENT_CONFIG"
}

create_container() {
  exists && { echo "The managed Qdrant container already exists." >&2; exit 1; }
  RUNTIME_ARGS=()
  CONFIG_VOLUME="$SERVER_CONFIG:/qdrant/config/production.yaml:ro"
  STORAGE_VOLUME="$STORAGE:/qdrant/storage"
  SNAPSHOT_VOLUME="$SNAPSHOTS:/qdrant/snapshots"
  if [[ "$RUNTIME" == "podman" ]]; then
    RUNTIME_ARGS+=(--userns=keep-id)
    CONFIG_VOLUME="$CONFIG_VOLUME,Z"
    STORAGE_VOLUME="$STORAGE_VOLUME:Z"
    SNAPSHOT_VOLUME="$SNAPSHOT_VOLUME:Z"
  fi
  "$RUNTIME" create \
    --name "$CONTAINER_NAME" \
    --restart=no \
    --network=host \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --pids-limit=512 \
    --memory="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --user="$RUNTIME_UID:$RUNTIME_GID" \
    "${RUNTIME_ARGS[@]}" \
    --volume "$CONFIG_VOLUME" \
    --volume "$STORAGE_VOLUME" \
    --volume "$SNAPSHOT_VOLUME" \
    "$IMAGE" >/dev/null
  verify_container_contract
}

verify() {
  python3 - "$PORT" "$API_KEY_FILE" <<'PY'
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

port = int(sys.argv[1])
key_path = Path(sys.argv[2])
if not key_path.is_file() or key_path.stat().st_mode & 0o077:
    raise SystemExit("The protected Qdrant API-key file is unavailable or too broad.")
request = Request(
    f"http://127.0.0.1:{port}/collections",
    headers={"api-key": key_path.read_text(encoding="utf-8").strip()},
)
with urlopen(request, timeout=10) as response:
    payload = json.loads(response.read(2 * 1024 * 1024))
if not isinstance(payload, dict) or payload.get("status") != "ok":
    raise SystemExit("Qdrant did not return its authenticated collection contract.")
print("Loopback Qdrant returned a valid authenticated REST contract.")
PY
}

start_service() {
  exists || { echo "Install the optional local semantic profile first." >&2; exit 1; }
  verify_container_contract
  if ! verify >/dev/null 2>&1; then
    "$RUNTIME" start "$CONTAINER_NAME" >/dev/null
  fi
  for _attempt in $(seq 1 120); do
    verify >/dev/null 2>&1 && { verify; return; }
    sleep 0.5
  done
  echo "The managed Qdrant service did not become ready within 60 seconds." >&2
  exit 1
}

stop_service() {
  exists || { echo "The optional local semantic service is not installed."; return; }
  "$RUNTIME" stop -t 30 "$CONTAINER_NAME" >/dev/null 2>&1 || true
  echo "The loopback Qdrant service is stopped; its rebuildable cache and protected configuration are preserved."
}

snapshot_collection() {
  verify >/dev/null
  python3 - "$PORT" "$API_KEY_FILE" <<'PY'
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

request = Request(
    f"http://127.0.0.1:{int(sys.argv[1])}/collections/elysia_memory_semantic_v1/snapshots?wait=true",
    data=b"{}",
    method="POST",
    headers={"Content-Type": "application/json", "api-key": Path(sys.argv[2]).read_text(encoding="utf-8").strip()},
)
try:
    with urlopen(request, timeout=300) as response:
        response.read(2 * 1024 * 1024)
except HTTPError as exc:
    if exc.code == 404:
        print("No semantic collection exists yet; canonical Memory remains sufficient for rebuild.")
        raise SystemExit(0)
    raise
print("A local derived-projection snapshot was created; canonical Memory remains authoritative.")
PY
}

case "$ACTION" in
  install)
    write_config
    if ! exists; then
      "$RUNTIME" pull "$IMAGE"
      create_container
    fi
    start_service
    echo "Installed pinned Qdrant $IMAGE_VERSION with telemetry disabled, REST-only loopback authentication, and no auto-start policy."
    ;;
  start) start_service ;;
  stop) stop_service ;;
  restart)
    stop_service
    start_service
    ;;
  verify) verify ;;
  snapshot) snapshot_collection ;;
  upgrade)
    write_config
    if exists; then verify_container_contract; fi
    if exists && verify >/dev/null 2>&1; then snapshot_collection; fi
    if exists; then stop_service; "$RUNTIME" rm "$CONTAINER_NAME" >/dev/null; fi
    "$RUNTIME" pull "$IMAGE"
    create_container
    start_service
    echo "The pinned Qdrant service was recreated; XDG config, cache, and snapshots were preserved."
    ;;
  reset-derived)
    if exists; then stop_service; "$RUNTIME" rm "$CONTAINER_NAME" >/dev/null; fi
    if [[ -d "$PROJECTION_ROOT" ]]; then
      RECOVERY_TARGET="$RECOVERY_ROOT/semantic-qdrant-$(date -u +%Y%m%dT%H%M%SZ)"
      [[ ! -e "$RECOVERY_TARGET" ]] || { echo "The recoverable projection target already exists." >&2; exit 1; }
      mv "$PROJECTION_ROOT" "$RECOVERY_TARGET"
    fi
    write_config
    create_container
    echo "The corrupt derived projection was moved to recoverable state. Canonical Memory was not changed; start and rebuild explicitly."
    ;;
  uninstall)
    if exists; then stop_service; "$RUNTIME" rm "$CONTAINER_NAME" >/dev/null; fi
    # Keep the governed client contract enabled while preserved vectors exist.
    # Privacy transitions then fail closed until reinstall instead of silently
    # retaining an old Normal vector after a record becomes Private or Sealed.
    # Canonical Memory and its mandatory FTS path remain available throughout.
    echo "The managed service was removed with no orphan. Configuration, snapshots, and rebuildable cache were preserved; canonical Memory was untouched. Privacy-changing mutations remain fail-closed until reinstall or an explicit derived reset."
    ;;
  status)
    if verify >/dev/null 2>&1; then
      if verify_container_contract >/dev/null 2>&1; then
        echo "status=ready listener=127.0.0.1:6333 auth=required telemetry=disabled autostart=disabled derived-only=true"
      else
        echo "status=invalid-container-contract listener=untrusted derived-only=true"
        exit 1
      fi
    elif exists; then
      if verify_container_contract >/dev/null 2>&1; then
        echo "status=installed-not-running listener=127.0.0.1:6333 auth=required telemetry=disabled autostart=disabled derived-only=true"
      else
        echo "status=invalid-container-contract listener=untrusted derived-only=true"
        exit 1
      fi
    else
      echo "status=not-installed listener=127.0.0.1:6333 derived-only=true"
    fi
    ;;
esac
