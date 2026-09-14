# Codev Core installation and optional VS Code adapter

Codev is an independently installed local capability. Elysia, the optional VS Code adapter and explicitly paired website surfaces share one governed Core. A checkout, a VSIX file, an editor extension or a trusted repository does not establish Core installation.

## Install and use

Use the reviewed `Codev_Core_1.0.0_amd64.deb` with the system software installer, or install it with the package manager:

```bash
sudo apt install ./Codev_Core_1.0.0_amd64.deb
```

For installation without administrator privileges, the distributable includes a user installer and uninstaller. Preview the selected artifact, then apply that exact selection:

```bash
bash install_codev_core_user.sh --deb /absolute/path/Codev_Core_1.0.0_amd64.deb
bash install_codev_core_user.sh --deb /absolute/path/Codev_Core_1.0.0_amd64.deb --apply
```

Open Elysia normally. Codev appears under WORKROOMS without selecting a repository, trusting a workspace or refreshing the connection. Local account setup remains separate. The workroom supports a normal no-workspace state; selecting a root shares no file list or contents until explicitly requested. Installation grants no files, writes, commands, network, model downloads or website access.

An existing window refreshes installation truth while visible and on focus. When Core is absent, the entire Elysia Codev entry is absent. A damaged or temporarily unavailable installed Core retains its entry with the appropriate status.

## Optional editor

Install a supported VS Code-family editor in either order, then install the adapter bundled with Core:

```bash
codev codev-adapter --editor code
codev codev-adapter --editor code --profile "My development profile"
```

Use `codium` explicitly to choose VSCodium. Editor publisher terms and profile choices remain explicit. A user installation places the launcher at `$HOME/.local/bin/codev`; use that absolute launcher when the current shell has not yet loaded its login PATH. Reinstalling the editor or adding another profile does not require source or a Core rebuild.

The adapter's default endpoint is discovered from the private installed runtime. `elysia.apiUrl` is an optional machine-scoped legacy development override when Core is absent, with no automatic TCP probing. Repository configuration cannot redirect an installed client. Workspace trust and exact repository approval remain separate from connection readiness.

## Upgrade, repair, uninstall, reinstall

Install a reviewed replacement artifact to upgrade; product identity remains v1.0.0 during this correction cycle and binary hashes distinguish builds. The package manager handles system repair/removal. For user installations, rerun the supplied installer to repair contents and permissions. Damaged payloads are retained in the user's Codev recoverable directory before replacement.

```bash
sudo apt remove codev-core
# Or, for the user installation:
bash uninstall_codev_core_user.sh --apply
```

Uninstall removes installation identity and startup integration while preserving accounts, memory, models, repositories and the optional editor adapter. It revokes prior installation-bound Codev actors. Reinstall selects a new installation generation; prior workspace grants do not reactivate. The service can remain alive for Elysia, but all Codev operations fail closed when Core is absent.

## Canonical paths and lifecycle

| Purpose | Location |
|---|---|
| System payload/manifest | `/usr/lib/codev/{codev-core,runtime.json}` |
| User payload/manifest | `${XDG_DATA_HOME:-$HOME/.local/share}/codev/current/usr/lib/codev/` |
| User releases | `${XDG_DATA_HOME:-$HOME/.local/share}/codev/releases/` |
| Private socket/locks | `$XDG_RUNTIME_DIR/elysia/`, or `${XDG_STATE_HOME:-$HOME/.local/state}/elysia/runtime/` |
| API credential | `auth/local-api.credential` below that private runtime directory |
| Durable data/config/logs | Existing Elysia XDG data/config/state roots |
| Login startup | System `/etc/xdg/autostart/codev-core.desktop`, or the user's XDG config autostart entry |

The service starts on desktop login or on first native client use. Concurrent clients use one instance lock. Unix directory mode is 0700 and socket mode 0600. Native identity binds version, runtime contract, UID, PID, boot ID, process start time, instance ID and executable SHA-256. Existing API authentication remains required. A changed binary is replaced through verified process identity and bounded graceful shutdown; a busy/unresponsive upgrade reports a pending state rather than granting authority or starting a competing service.

The browser broker remains a distinct explicit pairing interface. Websites do not probe installation. `Sync Codev` begins account-bound pairing, native confirmation precedes connection, and a separate workspace grant precedes any source transfer. Pairing alone shares no files.

## Qualification and support scope

The correction targets amd64 Debian 13 and Ubuntu 24.04 LTS for Core/Codev and the Elysia desktop. Other optional profiles retain their existing platform gates. These packages require glibc 2.39 or newer. Other CPU architectures and Debian-family releases are not qualified by this pass. CPU inference additionally requires an explicitly installed local model and sufficient resources; Core installation does not promise or enable an external model.

Before release, run both compiled product gates:

```bash
python3 scripts/verify_packaged_native_runtime.py /absolute/compiled-core
python3 scripts/verify_codev_core_package.py /absolute/Codev_Core_1.0.0_amd64.deb
```

The second gate uses the installer/uninstaller distributed beside the artifact. It verifies install, private transport, no initial authority, permission repair, uninstall/reinstall, installation generation and preservation of data from a separate home with spaces and a minimal environment. These gates supplement actual packaged GUI, editor, clean guest, reboot and website qualification; unit fixtures are not sufficient acceptance evidence.

The legacy `elysia codev-install --vsix ... [--select-profile]` remains available for compatibility with the original reviewed v1.0.0 adapter. Its optional profile selection is explicit and does not establish neutral Core installation or grant repository authority. Frozen release artifacts remain unchanged.
