# Codev Developer Profile Install Contract

Codev is the official local Elysia Developer-profile add-on. The exact reviewed VSIX is distributed through the canonical Elysia Ecobotics Marketplace and may be installed explicitly with:

```bash
elysia codev-install --vsix /absolute/path/elysia-codev-1.0.0.vsix --select-profile
```

The packaged command is the public-user path. It validates the exact local
archive, invokes an allowlisted VS Code-family editor with fixed arguments,
records a sanitized XDG receipt, and leaves profile selection unchanged unless
`--select-profile` is supplied. That explicit request selects Developer even
when a Core selection already exists; non-Core selections are retained as
additional profiles. It does not download or publish Codev.

Source checkouts also retain the dry-run-first operator helper:

```bash
scripts/install_codev.sh --vsix /absolute/path/elysia-codev-1.0.0.vsix
scripts/install_codev.sh --vsix /absolute/path/elysia-codev-1.0.0.vsix --apply --select-profile
```

The first command is dry-run only. The second validates the exact local archive again, enforces compressed/uncompressed/file-count bounds, rejects unsafe paths, links, special files, and credential-shaped filenames, invokes an allowlisted VS Code-family host with that local VSIX, records its SHA-256 in a sanitized XDG receipt, and creates a Developer profile selection only when no private selection file already exists.

The installer never downloads Codev, uses Marketplace publication, changes a remote, pushes code, enables arbitrary shell, grants repository approval, or weakens Elysia governance. It changes profile selection only after the user supplies `--select-profile`, validates the existing selection, and writes the replacement atomically.

After installation, run `elysia doctor`. Doctor reports the Developer profile,
Codev version/contract, and aggregate exact-repository approval state without
printing the receipt path, repository path, or credential.

Workspace trust and repository approval remain separate from installation. Installing Codev does not authorize any repository, patch, command, network, package manager, Git mutation, push, publish, cloud upload, or Developer Lab task.
