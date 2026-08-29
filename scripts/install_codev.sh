#!/usr/bin/env bash
set -Eeuo pipefail

MODE="dry-run"
SELECT_PROFILE="false"
VSIX_PATH=""
EDITOR_COMMAND=""
CODEV_VERSION="1.0.0"
EXTENSION_ID="ecosyneva-commons.elysia-codev"
CONTRACT_VERSION="vscode-coding-agent-contract-0.1"

usage() {
  printf '%s\n' "Usage: scripts/install_codev.sh --vsix /absolute/path/elysia-codev-1.0.0.vsix [--editor code|codium|/absolute/path] [--apply] [--select-profile]"
  printf '%s\n' "Default is dry-run. --apply installs only the reviewed local VSIX; it does not download, publish, push, or enable shell/network authority."
}

while (($#)); do
  case "$1" in
    --vsix)
      VSIX_PATH="${2:-}"
      shift 2
      ;;
    --editor)
      EDITOR_COMMAND="${2:-}"
      shift 2
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    --select-profile)
      SELECT_PROFILE="true"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$VSIX_PATH" = /* && -f "$VSIX_PATH" && ! -L "$VSIX_PATH" ]] || {
  printf '%s\n' "A non-symlink absolute path to a local VSIX is required." >&2
  exit 2
}
[[ "$VSIX_PATH" == *.vsix ]] || {
  printf '%s\n' "The reviewed package must use the .vsix extension." >&2
  exit 2
}
[[ $(stat -c %s "$VSIX_PATH") -le 52428800 ]] || {
  printf '%s\n' "The Codev VSIX exceeds the 50 MiB local package limit." >&2
  exit 2
}
command -v unzip >/dev/null || {
  printf '%s\n' "unzip is required for local static VSIX validation; nothing was installed." >&2
  exit 2
}
command -v sha256sum >/dev/null || {
  printf '%s\n' "sha256sum is required to bind the local install receipt; nothing was installed." >&2
  exit 2
}

ENTRY_COUNT="$(unzip -Z1 "$VSIX_PATH" | awk 'END {print NR + 0}')"
[[ "$ENTRY_COUNT" -le 500 ]] || {
  printf '%s\n' "The Codev VSIX exceeds the 500-entry local package limit." >&2
  exit 2
}
UNCOMPRESSED_BYTES="$(unzip -Z -l "$VSIX_PATH" | awk '$1 ~ /^[-dlcbps]/ {total += $4} END {printf "%.0f", total}')"
[[ "$UNCOMPRESSED_BYTES" -le 104857600 ]] || {
  printf '%s\n' "The Codev VSIX exceeds the 100 MiB uncompressed package limit." >&2
  exit 2
}
if unzip -Z -l "$VSIX_PATH" | awk '$1 ~ /^[lcbps]/ {unsafe = 1} END {exit unsafe ? 0 : 1}'; then
  printf '%s\n' "The Codev VSIX contains a symlink or special-file entry; nothing was installed." >&2
  exit 2
fi

MANIFEST_COUNT="$(unzip -Z1 "$VSIX_PATH" | awk '$0 == "extension/package.json" {count += 1} END {print count + 0}')"
[[ "$MANIFEST_COUNT" == "1" ]] || {
  printf '%s\n' "The VSIX must contain exactly one extension/package.json manifest." >&2
  exit 2
}
while IFS= read -r MEMBER; do
  case "$MEMBER" in
    /*|../*|*/../*|*/..|*\\*|[A-Za-z]:*)
      printf '%s\n' "The VSIX contains an unsafe archive path; nothing was installed." >&2
      exit 2
      ;;
  esac
  LOWER_MEMBER="${MEMBER,,}"
  MEMBER_BASENAME="${LOWER_MEMBER##*/}"
  case "$MEMBER_BASENAME" in
    .env|.env.*|id_rsa|id_dsa|id_ed25519|*.pem|*.key|credentials|credentials.*|token|tokens|token.*|tokens.*)
      printf '%s\n' "The VSIX contains credential-shaped material; nothing was installed." >&2
      exit 2
      ;;
  esac
done < <(unzip -Z1 "$VSIX_PATH")

MANIFEST="$(unzip -p "$VSIX_PATH" extension/package.json)"
grep -Eq '"name"[[:space:]]*:[[:space:]]*"elysia-codev"' <<<"$MANIFEST" || {
  printf '%s\n' "The VSIX manifest does not identify Elysia Codev." >&2
  exit 2
}
grep -Eq '"publisher"[[:space:]]*:[[:space:]]*"ecosyneva-commons"' <<<"$MANIFEST" || {
  printf '%s\n' "The VSIX publisher identity is not the official Codev identity." >&2
  exit 2
}
grep -Eq '"version"[[:space:]]*:[[:space:]]*"1\.0\.0"' <<<"$MANIFEST" || {
  printf '%s\n' "The VSIX version does not match the qualified stable v1.0.0 contract." >&2
  exit 2
}
PACKAGE_HASH="$(sha256sum "$VSIX_PATH" | awk '{print $1}')"

if [[ -z "$EDITOR_COMMAND" ]]; then
  EDITOR_COMMAND="$(command -v code || command -v codium || true)"
fi
[[ -n "$EDITOR_COMMAND" ]] || {
  printf '%s\n' "No compatible VS Code-family editor command was found; nothing was installed." >&2
  exit 2
}
if [[ "$EDITOR_COMMAND" == */* ]]; then
  [[ "$EDITOR_COMMAND" = /* && -x "$EDITOR_COMMAND" ]] || {
    printf '%s\n' "The explicit editor command must be an executable absolute path." >&2
    exit 2
  }
else
  EDITOR_COMMAND="$(command -v "$EDITOR_COMMAND" || true)"
  [[ -n "$EDITOR_COMMAND" ]] || {
    printf '%s\n' "The requested editor command is unavailable." >&2
    exit 2
  }
fi
if [[ "$MODE" == "apply" ]]; then
  case "$(basename "$EDITOR_COMMAND")" in
    code|code-insiders|codium|vscodium) ;;
    *)
      printf '%s\n' "Apply mode requires an explicitly supported VS Code-family editor command." >&2
      exit 2
      ;;
  esac
fi

printf '%s\n' "Codev package: validated local VSIX basename $(basename "$VSIX_PATH")"
printf '%s\n' "Package SHA-256: $PACKAGE_HASH"
printf '%s\n' "Extension identity: $EXTENSION_ID@$CODEV_VERSION"
printf '%s\n' "Install mode: $MODE"
printf '%s\n' "Developer profile selection requested: $SELECT_PROFILE"
printf '%s\n' "No download, Marketplace publication, remote push, shell authority, or arbitrary package script is requested."

if [[ "$MODE" != "apply" ]]; then
  printf '%s\n' "Dry-run complete. Rerun with --apply only after reviewing this exact local VSIX."
  exit 0
fi

"$EDITOR_COMMAND" --install-extension "$VSIX_PATH" --force

USER_HOME="${HOME:?HOME is required}"
DATA_BASE="${XDG_DATA_HOME:-$USER_HOME/.local/share}"
CONFIG_BASE="${XDG_CONFIG_HOME:-$USER_HOME/.config}"
RECEIPT_DIR="$DATA_BASE/elysia/developer"
RECEIPT_PATH="$RECEIPT_DIR/codev-install.json"
mkdir -p -m 700 "$RECEIPT_DIR"
TEMP_RECEIPT="$(mktemp "$RECEIPT_DIR/.codev-install.XXXXXX")"
trap 'rm -f "$TEMP_RECEIPT"' EXIT
chmod 600 "$TEMP_RECEIPT"
printf '%s\n' '{' >"$TEMP_RECEIPT"
printf '  "schema_version": 1,\n' >>"$TEMP_RECEIPT"
printf '  "extension_id": "%s",\n' "$EXTENSION_ID" >>"$TEMP_RECEIPT"
printf '  "version": "%s",\n' "$CODEV_VERSION" >>"$TEMP_RECEIPT"
printf '  "contract_version": "%s",\n' "$CONTRACT_VERSION" >>"$TEMP_RECEIPT"
printf '  "install_state": "installed_by_user",\n' >>"$TEMP_RECEIPT"
printf '  "package_sha256": "%s",\n' "$PACKAGE_HASH" >>"$TEMP_RECEIPT"
printf '  "raw_paths_exposed": false\n' >>"$TEMP_RECEIPT"
printf '%s\n' '}' >>"$TEMP_RECEIPT"
mv "$TEMP_RECEIPT" "$RECEIPT_PATH"
trap - EXIT

if [[ "$SELECT_PROFILE" == "true" ]]; then
  PROFILE_DIR="$CONFIG_BASE/elysia/install"
  PROFILE_PATH="$PROFILE_DIR/profiles.yaml"
  mkdir -p -m 700 "$PROFILE_DIR"
  if [[ -e "$PROFILE_PATH" ]]; then
    printf '%s\n' "Existing local profile selection was preserved. Select Developer explicitly in the existing private profile file." >&2
  else
    TEMP_PROFILE="$(mktemp "$PROFILE_DIR/.profiles.XXXXXX")"
    chmod 600 "$TEMP_PROFILE"
    printf '%s\n' 'version: 1' >"$TEMP_PROFILE"
    printf '%s\n' 'contract_version: elysia-local-profile-selection-1.0' >>"$TEMP_PROFILE"
    printf '%s\n' 'active_profile: developer' >>"$TEMP_PROFILE"
    printf '%s\n' 'additional_profiles: []' >>"$TEMP_PROFILE"
    mv "$TEMP_PROFILE" "$PROFILE_PATH"
  fi
fi

printf '%s\n' "Codev local installation completed. Run Elysia doctor to verify Developer-profile and API compatibility truth."
