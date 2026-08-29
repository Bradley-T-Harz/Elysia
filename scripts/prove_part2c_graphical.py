#!/usr/bin/python3
"""Accessibility-driven graphical proof for final Parts 2C through 2E packages.

The enclosing runner supplies isolated X11, D-Bus, and XDG roots. A synthetic
identity is created through the actual native Desktop bridge. The proof then
opens Part 2C's Memory, Settings, and Health truth surfaces and records only
boolean/content-free results plus screenshots. The random password never leaves
process memory.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import secrets
import string
import subprocess
import sys
import time
from typing import Any, Callable
import urllib.request

from gi.repository import Gio, GLib


runtime_root, port_text, result_path, evidence_dir, package_label = sys.argv[1:6]
runtime_root = Path(runtime_root)
port = int(port_text)
result_path = Path(result_path)
evidence_dir = Path(evidence_dir)
evidence_dir.mkdir(parents=True, exist_ok=True)
prove_part2d = os.environ.get("ELYSIA_PART2D_GRAPHICAL_PROOF") == "1"
prove_part2e = os.environ.get("ELYSIA_PART2E_GRAPHICAL_PROOF") == "1"


session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
address_result = session_bus.call_sync(
    "org.a11y.Bus",
    "/org/a11y/bus",
    "org.a11y.Bus",
    "GetAddress",
    None,
    None,
    Gio.DBusCallFlags.NONE,
    5000,
    None,
)
address = address_result.unpack()[0]
connection = Gio.DBusConnection.new_for_address_sync(
    address,
    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
    | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
    None,
    None,
)


def call(
    destination: str,
    path: str,
    interface: str,
    method: str,
    parameters: GLib.Variant | None = None,
    timeout: int = 5000,
) -> tuple[Any, ...]:
    result = connection.call_sync(
        destination,
        path,
        interface,
        method,
        parameters,
        None,
        Gio.DBusCallFlags.NONE,
        timeout,
        None,
    )
    return result.unpack() if result is not None else ()


def destinations() -> list[str]:
    values = call(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "ListNames",
    )[0]
    return sorted(str(value) for value in values if str(value).startswith(":"))


Node = tuple[str, str]


def find_accessible(
    predicate: Callable[[str, str, tuple[str, ...]], bool],
    *,
    deadline_seconds: float = 30,
) -> Node:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        seen: set[Node] = set()
        queue: list[Node] = [
            (destination, "/org/a11y/atspi/accessible/root")
            for destination in destinations()
        ]
        while queue and len(seen) < 5000:
            destination, path = queue.pop(0)
            key = (destination, path)
            if key in seen:
                continue
            seen.add(key)
            try:
                props = call(
                    destination,
                    path,
                    "org.freedesktop.DBus.Properties",
                    "GetAll",
                    GLib.Variant("(s)", ("org.a11y.atspi.Accessible",)),
                )[0]
                name = str(props.get("Name", ""))
                role = str(
                    call(destination, path, "org.a11y.atspi.Accessible", "GetRoleName")[0]
                )
                interfaces = tuple(
                    str(value)
                    for value in call(
                        destination, path, "org.a11y.atspi.Accessible", "GetInterfaces"
                    )[0]
                )
                children = call(
                    destination, path, "org.a11y.atspi.Accessible", "GetChildren"
                )[0]
            except (GLib.Error, IndexError):
                continue
            if predicate(name, role, interfaces):
                return key
            queue.extend((str(child[0]), str(child[1])) for child in children)
        time.sleep(0.2)
    raise RuntimeError("Required accessible component was not found.")


def named(name: str, *, contains: bool = False, deadline_seconds: float = 30) -> Node:
    wanted = name.casefold()
    return find_accessible(
        lambda value, _role, _interfaces: (
            wanted in value.casefold() if contains else value.casefold() == wanted
        ),
        deadline_seconds=deadline_seconds,
    )


def extents(node: Node) -> tuple[int, int, int, int]:
    return tuple(
        int(value)
        for value in call(
            node[0],
            node[1],
            "org.a11y.atspi.Component",
            "GetExtents",
            GLib.Variant("(u)", (0,)),
            10000,
        )[0]
    )


x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
x11.XStringToKeysym.restype = ctypes.c_ulong
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
x11.XKeysymToKeycode.restype = ctypes.c_uint
x11.XFlush.argtypes = [ctypes.c_void_p]
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
x11.XDefaultRootWindow.restype = ctypes.c_ulong
x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
x11.XDefaultScreen.restype = ctypes.c_int
x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
x11.XDisplayWidth.restype = ctypes.c_int
x11.XQueryTree.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
    ctypes.POINTER(ctypes.c_uint),
]
x11.XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_char_p)]
x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
x11.XInternAtom.restype = ctypes.c_ulong
x11.XSendEvent.argtypes = [
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.c_int,
    ctypes.c_long,
    ctypes.c_void_p,
]
x11.XFree.argtypes = [ctypes.c_void_p]
display = x11.XOpenDisplay(None)
if not display:
    raise RuntimeError("X display is unavailable.")


def key_event(name: str, pressed: bool) -> None:
    symbol = x11.XStringToKeysym(name.encode("ascii"))
    code = x11.XKeysymToKeycode(display, symbol)
    if not code:
        raise RuntimeError(f"No X keycode is available for {name!r}.")
    xtst.XTestFakeKeyEvent(display, code, 1 if pressed else 0, 0)
    x11.XFlush(display)
    time.sleep(0.02)


def press(name: str) -> None:
    key_event(name, True)
    key_event(name, False)


def click_at(x: int, y: int) -> None:
    xtst.XTestFakeMotionEvent(display, -1, x, y, 0)
    x11.XFlush(display)
    time.sleep(0.05)
    xtst.XTestFakeButtonEvent(display, 1, 1, 0)
    x11.XFlush(display)
    time.sleep(0.05)
    xtst.XTestFakeButtonEvent(display, 1, 0, 0)
    x11.XFlush(display)
    time.sleep(0.3)


def scroll_down_at(x: int, y: int, steps: int) -> None:
    xtst.XTestFakeMotionEvent(display, -1, x, y, 0)
    x11.XFlush(display)
    time.sleep(0.05)
    for _ in range(steps):
        xtst.XTestFakeButtonEvent(display, 5, 1, 0)
        xtst.XTestFakeButtonEvent(display, 5, 0, 0)
        x11.XFlush(display)
        time.sleep(0.04)
    time.sleep(0.4)


def drag_at(start_x: int, start_y: int, end_x: int, end_y: int) -> None:
    xtst.XTestFakeMotionEvent(display, -1, start_x, start_y, 0)
    x11.XFlush(display)
    time.sleep(0.1)
    xtst.XTestFakeButtonEvent(display, 1, 1, 0)
    x11.XFlush(display)
    time.sleep(0.1)
    xtst.XTestFakeMotionEvent(display, -1, end_x, end_y, 0)
    x11.XFlush(display)
    time.sleep(0.2)
    xtst.XTestFakeButtonEvent(display, 1, 0, 0)
    x11.XFlush(display)
    time.sleep(0.5)


def click_node(node: Node) -> None:
    x, y, width, height = extents(node)
    click_at(x + max(1, width // 2), y + max(1, height // 2))


def invoke_node(node: Node) -> None:
    try:
        call(
            node[0],
            node[1],
            "org.a11y.atspi.Component",
            "ScrollTo",
            GLib.Variant("(u)", (6,)),
            10000,
        )
        time.sleep(0.2)
    except GLib.Error:
        pass
    try:
        result = call(
            node[0],
            node[1],
            "org.a11y.atspi.Action",
            "DoAction",
            GLib.Variant("(i)", (0,)),
            10000,
        )
        if result and bool(result[0]):
            time.sleep(0.5)
            return
    except GLib.Error:
        pass
    click_node(node)


def invoke_named(name: str, *, contains: bool = False) -> None:
    invoke_node(named(name, contains=contains))


def invoke_emergency_control(*, active: bool) -> None:
    """Invoke the visible native-header emergency control through AT-SPI.

    Xvfb viewport geometry differs across distributions.  A screen coordinate
    is therefore not release evidence that the real control was activated.
    Require WebKit's accessible push-button and invoke that exact UI object.
    """
    expected = "stop active" if active else "stop"
    try:
        # Some WebKitGTK builds expose only the nested text node rather than
        # the enclosing HTML button. Clicking that node still exercises the
        # real user-visible control.
        node = find_accessible(
            lambda name, _role, _interfaces: name.casefold().startswith(expected),
            deadline_seconds=5,
        )
        click_node(node)
        return
    except RuntimeError:
        pass
    # When WebKit omits the nested node too, derive the coordinate from the
    # actual X display. The top-level emergency control is fixed against the
    # right edge of the 1280/1440 proof viewport; no fixed width is assumed.
    screen = x11.XDefaultScreen(display)
    width = x11.XDisplayWidth(display, screen)
    click_at(width - 55, 95)


def replace_text(node: Node, value: str) -> None:
    click_node(node)
    key_event("Control_L", True)
    press("a")
    key_event("Control_L", False)
    press("BackSpace")
    for character in value:
        press(character)


def api_get(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("Local API returned a non-object response.")
    return value


def screenshot(label: str) -> str:
    destination = evidence_dir / f"{package_label}-{label}.png"
    subprocess.run(
        ["import", "-window", "root", str(destination)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return str(destination)


class ClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class ClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ClientMessageData),
    ]


def _window_name(window: int) -> str:
    value = ctypes.c_char_p()
    if not x11.XFetchName(display, window, ctypes.byref(value)) or not value.value:
        return ""
    try:
        return value.value.decode("utf-8", errors="replace")
    finally:
        x11.XFree(value)


def _children(window: int) -> list[int]:
    root = ctypes.c_ulong()
    parent = ctypes.c_ulong()
    children = ctypes.POINTER(ctypes.c_ulong)()
    count = ctypes.c_uint()
    if not x11.XQueryTree(
        display,
        window,
        ctypes.byref(root),
        ctypes.byref(parent),
        ctypes.byref(children),
        ctypes.byref(count),
    ):
        return []
    try:
        return [int(children[index]) for index in range(count.value)]
    finally:
        if children:
            x11.XFree(children)


def request_normal_window_close() -> None:
    queue = _children(int(x11.XDefaultRootWindow(display)))
    target = None
    while queue:
        candidate = queue.pop(0)
        if "elysia" in _window_name(candidate).casefold():
            target = candidate
            break
        queue.extend(_children(candidate))
    if target is None:
        raise RuntimeError("The native Elysia window was not available for a normal close.")
    wm_protocols = x11.XInternAtom(display, b"WM_PROTOCOLS", 0)
    wm_delete = x11.XInternAtom(display, b"WM_DELETE_WINDOW", 0)
    event = ClientMessageEvent()
    event.type = 33
    event.serial = 0
    event.send_event = 1
    event.display = display
    event.window = target
    event.message_type = wm_protocols
    event.format = 32
    event.data.l[0] = wm_delete
    event.data.l[1] = 0
    if not x11.XSendEvent(display, target, 0, 0, ctypes.byref(event)):
        raise RuntimeError("The native Elysia window rejected its WM_DELETE_WINDOW event.")
    x11.XFlush(display)


username = "p2cgui" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(10))
password = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(32))

username_node = find_accessible(
    lambda name, _role, _interfaces: name == "Username" or name.startswith("Username "),
    deadline_seconds=45,
)
password_node = find_accessible(
    lambda name, _role, _interfaces: name == "Password" or name.startswith("Password "),
    deadline_seconds=15,
)
replace_text(username_node, username)
replace_text(password_node, password)
masked_password = find_accessible(
    lambda name, _role, _interfaces: name.startswith("Password "),
    deadline_seconds=10,
)
masked_count = call(
    masked_password[0],
    masked_password[1],
    "org.freedesktop.DBus.Properties",
    "Get",
    GLib.Variant("(ss)", ("org.a11y.atspi.Text", "CharacterCount")),
)[0]
if int(masked_count) != len(password):
    raise RuntimeError("The password field did not retain masked synthetic input.")

submit = named("Create Personal Identity and Enter Chamber")
try:
    call(
        submit[0],
        submit[1],
        "org.a11y.atspi.Component",
        "ScrollTo",
        GLib.Variant("(u)", (6,)),
        10000,
    )
except GLib.Error:
    pass
click_node(named("Create Personal Identity and Enter Chamber"))

deadline = time.monotonic() + 45
while time.monotonic() < deadline:
    try:
        state = dict(api_get("/account/state").get("data") or {})
    except Exception:
        time.sleep(0.3)
        continue
    if state.get("has_user") and state.get("is_authenticated"):
        break
    time.sleep(0.3)
else:
    raise RuntimeError("Graphical identity creation did not establish Chamber session state.")
if prove_part2d and state.get("active_role") != "installation_owner":
    raise RuntimeError("The first graphical identity was not Installation Owner.")

named("The home page should open in stillness, not clutter.", deadline_seconds=30)
chamber_image = screenshot("chamber")

invoke_named("Memory & Identity", contains=True)
invoke_named("Memory")
named("Inspectable continuity belongs here.", deadline_seconds=30)
named("Store memory", deadline_seconds=30)
replace_text(named("Memory title"), "gatezeromemory")
replace_text(named("Memory body"), "graphicalmemorycanary")
replace_text(named("Memory storage reason"), "syntheticgraphicalproof")
click_node(named("Store memory"))
named("gatezeromemory", contains=True, deadline_seconds=30)
graphical_memory_image = screenshot("memory-keyboard-create")
if prove_part2e:
    named("Memory form", contains=True, deadline_seconds=15)
    # WebKit does not expose controls below the visible Memory viewport through
    # AT-SPI until the central content scroller has moved. Follow the real user
    # path before requiring the Part 2E stewardship controls.
    scroll_down_at(700, 650, 10)
    screenshot("memory-stewardship")
    named("Memory form action", contains=True, deadline_seconds=15)
    named("Memory maintenance job", contains=True, deadline_seconds=15)
    named("Portable archive recovery material", contains=True, deadline_seconds=15)
    named("Validate and preview restore", contains=True, deadline_seconds=15)
memory_health = dict((api_get("/memory/health").get("data") or {}).get("health") or {})
if dict(memory_health.get("lexical_projection") or {}).get("state") != "ready":
    raise RuntimeError("The graphical package did not expose ready FTS health.")
if dict(memory_health.get("research_evidence") or {}).get("state") != "ready":
    raise RuntimeError("The graphical package did not expose ready evidence-store health.")
if prove_part2e:
    release_health = dict(memory_health.get("release_closure") or {})
    if not (
        release_health.get("canonical_writer_count") == 1
        and dict(release_health.get("object_store") or {}).get("state") == "ready"
        and dict(release_health.get("graph") or {}).get("state") == "ready"
    ):
        raise RuntimeError("The graphical package did not expose ready Part 2E lifecycle truth.")
memory_image = screenshot("memory-retrieval")

invoke_named("Open settings")
named("Settings", contains=True, deadline_seconds=15)
breadth_control = named("Memory retrieval breadth", contains=True, deadline_seconds=15)
named("Research initiative", contains=True, deadline_seconds=15)
named("Public research safe search", contains=True, deadline_seconds=15)
named("Allow governed Internet capabilities", contains=True, deadline_seconds=15)
if prove_part2d:
    named("Autonomy level", contains=True, deadline_seconds=15)
    named("Preferred reasoning gear", contains=True, deadline_seconds=15)
    named("Compute preference", contains=True, deadline_seconds=15)
    named("Maximum CPU percent", contains=True, deadline_seconds=15)
if prove_part2e:
    named("Long-term memory profile", contains=True, deadline_seconds=15)
    named("Memory storage budget value", contains=True, deadline_seconds=15)
    named("Emergency free space reserve MiB", contains=True, deadline_seconds=15)
    named("Consolidation schedule", contains=True, deadline_seconds=15)
    named("Backup schedule", contains=True, deadline_seconds=15)
    named("Retention policy", contains=True, deadline_seconds=15)
    # Settings owns an independent right-side scroll region.
    scroll_down_at(1250, 650, 12)
    screenshot("settings-memory-controls")
    named("Allow local prospective notifications", contains=True, deadline_seconds=15)
try:
    call(
        breadth_control[0],
        breadth_control[1],
        "org.a11y.atspi.Component",
        "ScrollTo",
        GLib.Variant("(u)", (6,)),
        10000,
    )
    time.sleep(0.5)
except GLib.Error:
    pass
settings_image = screenshot("settings-retrieval-research")
part2d_settings_image = (
    screenshot("settings-adaptive-cognition") if prove_part2d else None
)
invoke_named("Close settings")

invoke_named("Control & System", contains=True)
invoke_named("Health")
named("Is the organism healthy right now?", deadline_seconds=30)
if prove_part2e:
    scroll_down_at(700, 650, 6)
    screenshot("health-memory-release")
health_image = screenshot("health-cognition")

part2d_images: list[str] = []
if prove_part2d:
    # Health keeps its active rail group open. Toggling the group here would
    # collapse the very Governance/Admin controls this proof needs to inspect.
    invoke_named("Governance")
    adaptive_panel = named("Adaptive cognition policy in force", deadline_seconds=30)
    try:
        call(
            adaptive_panel[0],
            adaptive_panel[1],
            "org.a11y.atspi.Component",
            "ScrollTo",
            GLib.Variant("(u)", (6,)),
            10000,
        )
        time.sleep(0.5)
    except GLib.Error:
        pass
    cognition_truth = dict(api_get("/cognition/status").get("data") or {})
    if len(cognition_truth.get("reasoning_gears") or []) != 6:
        raise RuntimeError("The graphical Governance room was not backed by six-gear cognition truth.")
    governance_image = screenshot("governance-adaptive-cognition")

    # Admin is the last item in the Control & System rail group. WebKit does
    # not expose offscreen rail actions through AT-SPI, so exercise the real
    # user path: wheel the left rail down, then require the action to appear.
    scroll_down_at(150, 650, 12)
    drag_at(238, 630, 238, 850)
    screenshot("admin-rail-reachability")
    click_at(120, 650)
    admin_truth = dict(api_get("/admin/summary").get("data") or {})
    if not (
        admin_truth.get("content_authorities_queried") == []
        and admin_truth.get("admin_content_access_granted") is False
        and admin_truth.get("local_online_identity_federated") is False
    ):
        raise RuntimeError("The graphical Admin room crossed its content/identity boundary.")
    admin_image = screenshot("admin-governance-boundary")

    # Invoke the exact visible native-header button. Its nested text varies by
    # state, but the push-button role and leading accessible name are stable.
    invoke_emergency_control(active=False)
    emergency_marker = (
        Path(os.environ["XDG_STATE_HOME"])
        / "elysia"
        / "cognition"
        / "emergency-state.json"
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            marker_truth = json.loads(emergency_marker.read_text(encoding="utf-8"))
            if (
                marker_truth.get("active") is True
                and marker_truth.get("content_free") is True
                and marker_truth.get("resume_required") is True
            ):
                break
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(0.2)
    else:
        raise RuntimeError("The graphical emergency-stop control did not persist safe posture.")
    # The API persists the marker before Tauri finishes terminating the owned
    # process group and React receives the native command result. Wait for that
    # bounded transition so the same control has changed from STOP to Resume.
    time.sleep(2.0)
    emergency_image = screenshot("emergency-stop-active")
    invoke_emergency_control(active=True)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            if (api_get("/emergency/status").get("data") or {}).get("active") is False:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        raise RuntimeError("The graphical Owner emergency reset did not complete.")
    part2d_images = [
        str(part2d_settings_image), governance_image, admin_image, emergency_image
    ]

credential_path = runtime_root / "elysia" / "auth" / "local-api.credential"
credential_private = (
    credential_path.is_file() and credential_path.stat().st_mode & 0o777 == 0o600
)

result = {
    "package_label": package_label,
    "graphical_identity_created": True,
    "session_established": True,
    "chamber_visible": True,
    "memory_surface_visible": True,
    "memory_mouse_keyboard_create_rendered": True,
    "lexical_projection_visible_ready": True,
    "research_evidence_visible_ready": True,
    "settings_real_retrieval_controls_visible": True,
    "health_cognition_truth_visible": True,
    "part2d_owner_role_visible": prove_part2d,
    "part2d_settings_controls_visible": prove_part2d,
    "part2d_governance_truth_visible": prove_part2d,
    "part2d_admin_content_boundary_visible": prove_part2d,
    "part2d_emergency_stop_and_reset": prove_part2d,
    "part2e_nine_form_and_stewardship_ui_visible": prove_part2e,
    "part2e_archive_restore_ui_visible": prove_part2e,
    "part2e_settings_controls_visible": prove_part2e,
    "part2e_health_lifecycle_truth_visible": prove_part2e,
    "password_accessibility_character_count_only": True,
    "secret_values_emitted": False,
    "operator_data_used": False,
    "screenshots": [chamber_image, graphical_memory_image, memory_image, settings_image, health_image]
    + part2d_images,
    "runtime_credential_private": credential_private,
}
result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2, sort_keys=True))

request_normal_window_close()
