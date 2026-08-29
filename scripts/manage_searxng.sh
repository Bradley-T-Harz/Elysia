#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="${1:-status}"
CONTAINER_NAME="elysia-searxng"
IMAGE="${ELYSIA_SEARXNG_IMAGE:-docker.io/searxng/searxng@sha256:bbd44b09b83e4ea8b8ab80953e5eed24837ff02d00fc752bd1762b9fc244eaa9}"
PORT="8888"
USER_HOME="${HOME:?HOME is required}"
CONFIG_BASE="${XDG_CONFIG_HOME:-$USER_HOME/.config}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
STATE_BASE="${XDG_STATE_HOME:-$USER_HOME/.local/state}"
SEARXNG_CONFIG="$CONFIG_BASE/elysia/services/searxng"
SEARXNG_DATA="$DATA_BASE/elysia/services/searxng"
SEARXNG_STATE="$STATE_BASE/elysia/services/searxng"
WORKER_OVERRIDE="$CONFIG_BASE/elysia/workers/searxng.yaml"
ENV_FILE="$SEARXNG_STATE/container.env"
OWNERSHIP_RECEIPT="$SEARXNG_STATE/ownership.json"
OWNER_LABEL="llc.ecosyneva.elysia.owner=managed-searxng"

usage() {
  echo "Usage: scripts/manage_searxng.sh [status|install|start|stop|verify|uninstall]"
  echo "The install action explicitly acquires the official SearXNG container image and binds it to 127.0.0.1:8888 only."
}

case "$ACTION" in
  status|install|start|stop|verify|uninstall) ;;
  *) usage >&2; exit 2 ;;
esac

if command -v podman >/dev/null 2>&1; then
  RUNTIME="podman"
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  RUNTIME="docker"
else
  echo "Podman or an accessible Docker service is required for the optional local SearXNG profile." >&2
  exit 1
fi

exists() { "$RUNTIME" container exists "$CONTAINER_NAME" >/dev/null 2>&1; }
owned() {
  exists && [[ "$("$RUNTIME" inspect "$CONTAINER_NAME" --format '{{ index .Config.Labels "llc.ecosyneva.elysia.owner" }}' 2>/dev/null || true)" == "managed-searxng" ]]
}

write_receipt() {
  local ownership="$1"
  umask 077
  mkdir -p "$SEARXNG_STATE"
  printf '{"contract":"elysia-searxng-ownership-v1","container_id":"elysia-searxng","ownership":"%s","image_digest":"sha256:bbd44b09b83e4ea8b8ab80953e5eed24837ff02d00fc752bd1762b9fc244eaa9","configuration_preserved_on_remove":true,"raw_paths_exposed":false}\n' "$ownership" >"$OWNERSHIP_RECEIPT"
  chmod 0600 "$OWNERSHIP_RECEIPT"
}

repair_rootless_bind_ownership() {
  [[ "$RUNTIME" == "podman" ]] || return 0
  local target
  for target in "$SEARXNG_CONFIG" "$SEARXNG_DATA"; do
    [[ -e "$target" && ! -O "$target" ]] || continue
    # Older managed containers allowed the upstream root entrypoint to chown
    # these dedicated bind mounts to the container's searxng UID. In a
    # rootless user namespace that becomes an unmapped subordinate host UID,
    # making a later repair/reinstall unable to update its own configuration.
    # Reclaim only Elysia's dedicated service roots through Podman's namespace;
    # container UID 0 maps back to the invoking local user.
    podman unshare chown -R 0:0 "$target"
  done
}

write_config() {
  umask 077
  repair_rootless_bind_ownership
  mkdir -p "$SEARXNG_CONFIG" "$SEARXNG_DATA" "$SEARXNG_STATE" "$(dirname "$WORKER_OVERRIDE")"
  if [[ ! -f "$SEARXNG_CONFIG/settings.yml" ]]; then
    printf '%s\n' \
      'use_default_settings: true' \
      'general:' \
      '  debug: false' \
      '  instance_name: Elysia local SearXNG' \
      'search:' \
      '  safe_search: 2' \
      '  autocomplete: ""' \
      '  formats:' \
      '    - html' \
      '    - json' \
      'server:' \
      '  limiter: false' \
      '  image_proxy: true' \
      >"$SEARXNG_CONFIG/settings.yml"
    chmod 0600 "$SEARXNG_CONFIG/settings.yml"
  fi
  if [[ ! -f "$ENV_FILE" ]]; then
    SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    printf 'SEARXNG_SECRET=%s\nSEARXNG_BASE_URL=http://127.0.0.1:%s/\n' "$SECRET" "$PORT" >"$ENV_FILE"
    chmod 0600 "$ENV_FILE"
  fi
}

verify() {
  python3 - "$PORT" <<'PY'
import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

port = int(sys.argv[1])
url = f"http://127.0.0.1:{port}/search?" + urlencode({"q": "Elysia SearXNG readiness", "format": "json", "safesearch": "2"})
with urlopen(url, timeout=20) as response:
    payload = json.loads(response.read(2 * 1024 * 1024))
if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
    raise SystemExit("SearXNG did not return the expected JSON search contract.")
print(f"Loopback SearXNG returned a valid bounded JSON result set ({len(payload['results'])} results).")
PY
}

is_ready() {
  verify >/dev/null 2>&1
}

wait_ready() {
  for _attempt in $(seq 1 120); do
    if is_ready; then
      verify
      return
    fi
    sleep 0.5
  done
  echo "The managed SearXNG service did not become ready within 60 seconds." >&2
  return 1
}

case "$ACTION" in
  install)
    write_config
    if ! is_ready && ! exists; then
      "$RUNTIME" pull "$IMAGE"
      "$RUNTIME" create \
        --name "$CONTAINER_NAME" \
        --label "$OWNER_LABEL" \
        --restart=on-failure \
        --env FORCE_OWNERSHIP=false \
        --env-file "$ENV_FILE" \
        --publish "127.0.0.1:$PORT:8080" \
        --volume "$SEARXNG_CONFIG:/etc/searxng:Z" \
        --volume "$SEARXNG_DATA:/var/cache/searxng:Z" \
        "$IMAGE" >/dev/null
    fi
    if ! is_ready; then
      owned || {
        echo "A container named $CONTAINER_NAME exists without Elysia ownership; refusing to start or replace it." >&2
        exit 1
      }
      "$RUNTIME" start "$CONTAINER_NAME" >/dev/null
    fi
    wait_ready
    printf 'version: 1\nservice:\n  enabled: true\n  base_url: http://127.0.0.1:%s\n' "$PORT" >"$WORKER_OVERRIDE"
    chmod 0600 "$WORKER_OVERRIDE"
    if owned; then
      write_receipt managed
      "$RUNTIME" inspect "$CONTAINER_NAME" --format 'SearXNG managed container image: {{.ImageName}} ({{.Image}})'
    else
      write_receipt external_loopback
      echo "A valid pre-existing loopback SearXNG service was adopted without replacing it."
    fi
    ;;
  start)
    if ! is_ready; then
      owned || { echo "Install the Elysia-owned optional SearXNG service first." >&2; exit 1; }
      "$RUNTIME" start "$CONTAINER_NAME" >/dev/null
    fi
    wait_ready
    ;;
  stop)
    owned || { echo "No Elysia-owned SearXNG service is installed; external services were not touched."; exit 0; }
    "$RUNTIME" stop "$CONTAINER_NAME" >/dev/null
    echo "The optional SearXNG service is stopped; its user-owned configuration and data were preserved."
    ;;
  uninstall)
    if ! owned; then
      echo "No Elysia-owned SearXNG container is installed; nothing external was removed."
      exit 0
    fi
    if [[ "$RUNTIME" == "podman" ]]; then
      "$RUNTIME" stop --ignore "$CONTAINER_NAME" >/dev/null 2>&1 || true
    else
      "$RUNTIME" stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
    "$RUNTIME" rm "$CONTAINER_NAME" >/dev/null
    write_receipt removed_container_configuration_preserved
    echo "The Elysia-owned SearXNG container was removed; private configuration and cache were preserved."
    ;;
  verify)
    verify
    ;;
  status)
    if is_ready; then
      echo "status=ready port=127.0.0.1:8888 json-search=valid"
    elif exists; then
      "$RUNTIME" inspect "$CONTAINER_NAME" --format 'status={{.State.Status}} image={{.ImageName}} port=127.0.0.1:8888'
    else
      echo "status=not-installed port=127.0.0.1:8888"
    fi
    ;;
esac
