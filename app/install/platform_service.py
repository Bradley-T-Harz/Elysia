"""Local package platform identity; no network, editor or workspace discovery."""
from pathlib import Path

DEBIAN_CORE_COMPONENTS = frozenset({"core_python_runtime", "desktop_shell", "identity_memory_fabric", "personal_onboarding", "local_connectors", "codev_companion", "local_model_provider"})


def operating_system(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    values = {"id": "unknown", "version_id": "unknown"}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key in {"ID", "VERSION_ID"}: values[key.lower()] = value.strip().strip('\"').strip("'")
    except OSError:
        pass
    return values


def core_platform_supported(value: dict[str, str]) -> bool:
    return (value["id"] == "ubuntu" and value["version_id"] == "24.04"
            or value["id"] == "debian" and value["version_id"].split(".", 1)[0] == "13")


def installed_desktop_form() -> str | None:
    # Codev may start the shared service before Desktop is installed. Determine
    # Desktop packaging when it is actually needed, not from the first starter.
    if (Path.home() / ".local/lib/elysia/current/usr/bin/elysia-desktop").is_file():
        return "user_local_desktop"
    if Path("/usr/bin/elysia-desktop").is_file():
        return "deb"
    return None
