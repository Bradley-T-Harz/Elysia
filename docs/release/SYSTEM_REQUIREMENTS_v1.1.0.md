# Elysia / Codev 1.1.0 target system requirements

Final candidate targets: Linux amd64, Debian 13 and Ubuntu 24.04. Final package
qualification is pending. Native desktop evidence is GNOME/X11 only. The Core
package requires glibc >= 2.39, libstdc++6, libgcc-s1, and zlib1g; the Debian
desktop package additionally declares its exact GTK/WebKit runtime dependencies.
Use the package manager to resolve those declared dependencies.

CPU-only local operation is supported by the architecture; no NVIDIA GPU,
Conda installation, source checkout, VS Code, or website account is required to
install Codev Core. Models are separate, and their actual memory/runtime needs
must be assessed before acquisition. VS Code adapter requires VS Code >= 1.96
within its declared compatible major range. Storage and memory estimates in
component/acquisition manifests are guidance, not silent download approval.
