# Elysia 1.0.0 system requirements

The supported Linux qualification baseline is Ubuntu 24.04 on x86-64. Elysia Core is CPU-capable and does not require an NVIDIA GPU, public Website account, external model service, container engine, or optional profile.

The `.deb` uses conventional package-manager paths; the AppImage executable is relocatable while profile, account, Memory, configuration, cache, state, and runtime data remain in their XDG locations. A graphical Linux session with the native WebKit/GTK dependencies declared by the package is required for the Desktop. Installation and lifecycle actions must preview any privilege requirement and never silently invoke `sudo`.

Optional profiles have additional requirements recorded by the authoritative component graph and acquisition manifests in `config/install/`:

- Workstation/Research can use declared document, OCR, media, SearXNG, Qdrant, and local embedding components.
- Creator/Perception can require substantial disk, RAM, model downloads, and—only when selected and Doctor-approved—supported CUDA resources.
- Developer/Codev requires a supported VS Code-family host and Git; repository approval and workspace trust remain separate.
- Scientific/Engineering supports declared CPU environments and a Doctor-selected CUDA path on supported NVIDIA hardware/drivers.
- Complete MEGA composes the approved components without weakening safety or privacy floors.

Exact package versions, hashes, native prerequisites, model terms, acquisition behavior, download/installed-size previews, CPU/GPU selection, and health probes are machine-readable in the signed release component/profile and acquisition manifests. Unsupported GPU, insufficient disk, unavailable network, missing dependency, corrupt material, or wrong checksum/signature must produce a truthful blocked/degraded state rather than a false healthy result.
