# Elysia / Codev 1.1.0 candidate limits

The final artifact gate is pending. Prior implementation evidence covers amd64
Debian 13 and Ubuntu 24.04; desktop photo/responsive/native snapping evidence
covers GNOME/X11. These results do not substitute for the new package install
and original-public-1.0.0 upgrade matrix.

No new ARM, Wayland, Windows, macOS, or universal model-performance support is
claimed. Models, GIS, and optional hardware dependencies retain their existing
separate requirements. CPU reasoning latency depends on the selected model.

The 1.1.0 AppImage channel is omitted until artifact-specific guest qualification
is possible. The original 1.0.0 AppImage remains historical and is not relabeled.
The direct VSIX channel is retained; no new marketplace registry enrollment or
publisher credential has been introduced.

Stable publication requires the existing offline Ed25519 signing authority,
focused Debian/Ubuntu final artifact lifecycle checks, and actual public-byte
verification. Website current-download pointers remain on the previous verified
release until both coordinated product releases satisfy those gates.
