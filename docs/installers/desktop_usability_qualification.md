# Desktop usability qualification — 2026-09-14

This correction keeps Elysia and Codev at **v1.0.0**. It is an installed-product
qualification of the review candidate, not a new tagged or frozen release.

## Confirmed causes and corrections

| Surface | Cause | Correction |
| --- | --- | --- |
| Conversations | A positional grid row template no longer matched the controls in the active thread. Fixed shell columns and viewport constraints squeezed the composer. | Natural-height thread and composer; a room-owned vertical document; collapsible conversation list; shared navigation and Inspector dialogs when space is limited. |
| Requests | Summary cards consumed the viewport while the ledger/detail split shrank into the remaining height. | Nonshrinking cards and detail sections in the room's scrolling document; stacked details and lookup controls at narrow widths. |
| Capabilities | Inline overflow and shrinking split-pane rules defeated page scrolling, even at large sizes. | Visible page scrollbar, naturally sized catalog/detail, responsive stacking, selection-to-detail navigation and return focus to the actual activated card. |
| Identity photo | Sealed copying succeeded, but the image used a direct HTTP preview URL instead of authenticated native IPC. Replacement also retained failed-image state. Extension-only validation allowed undecodable files. | One parented native chooser for creation/profile editing; immediate validated preview; authenticated owner-bound JSON thumbnail transport; decoded-image validation, replacement/reset and explicit errors. |
| Linux snapping | The 1080×720 logical minimum became a 2160×1440 physical X11 minimum at 2× scale, wider than a half-screen tile. | Minimum 560×360 logical; native decorations and resizability retained. No application snapping coordinates or tiling emulation. |

Shell columns yield at 1500 logical pixels (Inspector) and 1100 (room rail).
Room container queries respond to actual remaining space, including 820/600 pixel
transitions. Short-window spacing changes at 550 pixels high. Critical controls
remain in the scrolling room or labeled, keyboard-operable dialogs. Inspector
has one scrolling body, including its portrait; close remains reachable.

Identity photos support JPEG, PNG and WebP, bounded to 10 MiB and 40 megapixels.
Originals retain existing private local storage semantics; thumbnails are at
most 512 pixels, apply orientation, and omit source metadata. Ordinary preview
responses carry an asset identifier and data URL, never an arbitrary native
path. Owner/session checks remain in the backend. The native preview command
accepts no caller-supplied file path; it reads only the user-selected regular
file, with symlink/nonregular-file and size guards. No network photo upload or
new workspace authority is introduced.

## Installed artifact and provenance

The final application was built from public review commit
`2e968e0b0e1a6728705d4cd84679fb088c8f4677` and installed through the canonical
user-local installer, then launched through its normal freedesktop entry.
The installed executable path was checked against the package digest.

| Artifact | SHA-256 |
| --- | --- |
| `Elysia_1.0.0_amd64.deb` | `681bd7a4fb11f6533f60217f030b5061588669d1e7f879848f9f2e709f166d6a` |
| Companion `Codev_Core_1.0.0_amd64.deb` | `64d02ff65a695e33c21d088eb5785e0c72a7ff0cb617660095f84decf299e7c7` |
| Compiled Core executable | `1655d6788ca55a62eeaefabe2279dcc2c0f96baa9e8cf5843b3f3afc662191d0` |

The final frontend-only focus correction rebuilt an identical Core executable;
the already installed matching Core was retained. Application installs preserve
account/configuration/data. The original user's profile fields and original
photo bytes were compared with a private recovery snapshot and preserved.
Private photos, databases, credentials, and machine screenshots are excluded
from Git and the public review payload.

## Actual GNOME and visual matrix

Qualified on the installed amd64 application on Ubuntu 24.04 GNOME/X11,
3840×2400 physical display at 2× scale. These are measured client dimensions,
not synthetic browser viewports. GNOME shortcuts performed the tiling; X11
resize operations were used only for ordinary manual-size checks.

| Shape | Logical client size | Coverage |
| --- | --- | --- |
| Maximized | 1854×1131 | All three rooms; full shell and Inspector |
| Standard large | 1440×920 | All three rooms and Personal Identity |
| Left and right halves | 927×1131 | Native tiling both sides; representative three-room review on left |
| All four corners | 927×547 | Native tiling all corners; representative three-room review at quarter size |
| Top and bottom halves | 1854×547 | GNOME-provided top/bottom tiling; short-height room scrolling |
| Tall narrow | 640×1000 | All three rooms; stacked catalog and scroll endpoints |
| Wide short | 1400×400 | All three rooms; readable content rather than shrinking panes |
| Medium | 1100×750 | All three rooms and collapsed shell panels |
| Supported minimum | 560×360 | All three rooms; composer text entry/Send visibility, request lookup, catalog detail, Inspector |

Screenshots were captured and visually reviewed for overlap, wrapping, clipped
controls, horizontal overflow, visible scrollbars and reachable content.
Keyboard End and mouse-wheel checks reached the Requests operator boundary;
catalog navigation reached the last cards, full selected detail and final
operator boundary. Inspector scrolling and Escape dismissal passed. Native
WebKit initially exposed incorrect return focus after a non-focusing pointer
activation; the final installed build passes that exact regression.

Photo qualification used the real native chooser in two installed contexts:
the existing user profile and an isolated XDG first-run account store. The latter
completed ordinary offline Setup/Doctor, selected a real image before account
creation, displayed it immediately, and retained it after creation and restart.
Invalid image selection showed a clear error without replacing the prior photo;
Remove and Replace passed. The existing user's photo survived room changes and
application relaunch. The isolated account was never added to the real store.

Codev remained Ready with no workspace on the normal installed profile. The
isolated installed app without Core showed ordinary rooms and no Codev room.
No workspace trust was granted for these checks. The VS Code controller was
never restarted, reloaded, closed, or used as a lifecycle test target.

## Regression and package checks

- Desktop React: **130 passed, 28 files**, including installation gating,
  shared panel behavior, photo rendering/replacement and capability return focus.
- Focused account service/routes/session/privacy/runtime projection: **32 passed**.
- Rust/native: **10 passed, 1 deliberately ignored subprocess helper**; final
  parented chooser also passed `cargo check` and release compilation.
- Final TypeScript typecheck, Vite build, Tauri Debian build and CSP asset gate:
  passed. The build produced no inline executable scripts/event handlers.
- Compiled Core required-route smoke and private Unix runtime gates: passed
  with three concurrent clients sharing one runtime in both XDG and fallback
  locations, mode 0600, and retained unauthenticated-session rejection.
- Companion Core artifact lifecycle: install/repair/remove/reinstall and
  identity/permission/data-preservation gates retained from this build pass.
- Public source/history hygiene: zero findings before publication.

The initial sandbox-only native socket failures were rerun successfully under
the ordinary host user with local IPC permission; they are not product failures.
The earlier unrelated full backend and Debian/Ubuntu Codev lifecycle evidence
was reused for unchanged code. No claim is made that those VM visual matrices
were repeated for this desktop polish pass.

## Required packaged-product gate for future changes

For shell sizing, native window or identity transport changes, React assertions
alone do not qualify the product. Build and install the distributable; record
the source revision, package digest and running executable. Use the normal
desktop launcher, inspect real window-manager hints, and perform native tiling
plus representative manual dimensions from the matrix above. Inspect screenshots
and scroll endpoints, exercise keyboard/focus and composer input, and test the
native photo chooser before and after account creation, including invalid input,
replacement/removal and restart persistence. Preserve the primary account and
run first-account/lifecycle tests in an isolated data store. Protect the editor
hosting the test controller.

This pass qualifies the stated GNOME/X11 host and Debian artifact. Wayland,
other compositors, fractional scaling, ARM, and a newly built AppImage were not
qualified here. Small displays whose quarter tile is below 560×360 logical
pixels cannot satisfy this supported minimum. Release numbering, tags, frozen
artifacts and independent approval before merging protected main remain deferred.
