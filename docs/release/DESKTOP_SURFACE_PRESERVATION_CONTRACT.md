# Desktop surface preservation contract

Elysia's established Desktop rooms are release contracts, not disposable release-checklist entries. Release hardening follows this order:

1. inspect the real surface and backend;
2. repair a fixable defect;
3. preserve the room, navigation entry, and honest runtime state;
4. test the user workflow;
5. request the operator's explicit approval **by surface name** before deprecation or removal.

An incomplete dependency does not authorize hiding its room, replacing it with a no-op, or erasing its navigation. The room may truthfully show a bounded unavailable or degraded state when a real dependency is absent, but active-looking controls must remain backed by a working path.

The machine-readable inventory is `config/release/protected_desktop_surfaces.json`. `tests/test_desktop_surface_preservation.py` fails when an inventoried room disappears from startup preferences, the left rail, or the application renderer. A deliberate change therefore requires a reviewed contract change as well as implementation changes.

The companion capability inventory is `config/release/protected_desktop_capabilities.json`. It protects the complete Settings truth inventory and established workflows even when they do not own a top-level room. It also records the critical historical distinction between a real capability and an active-looking prototype control that never called a backend. Preservation means keeping and completing the capability; it does not mean resurrecting a no-op or binding Elysia permanently to an old vendor.

This contract protects the Chamber, Conversations, Projects, Artifacts, Requests, Memory, Personal Identity, Governance, Capabilities, Add-ons, and Health. It does not prohibit an operator-approved redesign or deprecation; it makes that decision visible and intentional.
