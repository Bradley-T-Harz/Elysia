from pathlib import Path
import os
import subprocess
import pytest


_SYNTHETIC_SUPABASE = "https://readiness-fixture.supabase.co"
_SYNTHETIC_ONLINE_BUILD_READY = False


def _online_dist_has_synthetic_fixture(online: Path) -> bool:
    assets = online / "dist" / "assets"
    if not assets.is_dir():
        return False

    for path in assets.glob("*.js"):
        try:
            if _SYNTHETIC_SUPABASE in path.read_text(
                encoding="utf-8",
                errors="ignore",
            ):
                return True
        except OSError:
            continue

    return False


def _ensure_synthetic_online_build(online: Path) -> None:
    global _SYNTHETIC_ONLINE_BUILD_READY

    if (
        _SYNTHETIC_ONLINE_BUILD_READY
        and _online_dist_has_synthetic_fixture(online)
    ):
        return

    if not _online_dist_has_synthetic_fixture(online):
        result = subprocess.run(
            [
                "node",
                "scripts/runReadinessChecks.mjs",
                "build",
            ],
            cwd=online,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, result.stderr + result.stdout

    assert _online_dist_has_synthetic_fixture(online), (
        "Codev browser qualification requires the isolated synthetic "
        "Online readiness build."
    )

    _SYNTHETIC_ONLINE_BUILD_READY = True


@pytest.mark.parametrize("browser_family", ["chromium", "firefox"])
def test_actual_browser_signed_broker_transport(browser_family):
    online = Path(__file__).resolve().parents[2] / "Elysia-Ecobotics-Online"
    script = online / "scripts" / "codevBrokerBrowserTest.mjs"
    if not (online / "node_modules" / "playwright").is_dir():
        pytest.skip("Online Playwright dependency is unavailable")
    environment = os.environ.copy()
    environment["ELYSIA_CODEV_BROWSER_FAMILY"] = browser_family
    if environment.get("ELYSIA_CODEV_BROWSER_EVIDENCE"):
        target = Path(environment["ELYSIA_CODEV_BROWSER_EVIDENCE"])
        environment["ELYSIA_CODEV_BROWSER_EVIDENCE"] = str(target.with_stem(target.stem + "-" + browser_family))
    # Reuse installed browser executables read-only; browser profiles remain disposable.
    cached_browsers = Path.home() / ".cache" / "ms-playwright"
    if cached_browsers.is_dir():
        environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(cached_browsers))
    result = subprocess.run(["node", str(script)], cwd=online, env=environment, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "actual_browser_signed_codev_broker_ok" in result.stdout


@pytest.mark.parametrize("browser_family", ["chromium", "firefox"])
def test_actual_codev_website_pages(browser_family):
    online = Path(__file__).resolve().parents[2] / "Elysia-Ecobotics-Online"
    if not (online / "node_modules" / "playwright").is_dir():
        pytest.skip("Online Playwright dependency is unavailable")
    _ensure_synthetic_online_build(online)
    environment = os.environ.copy()
    environment["ELYSIA_CODEV_FORGE_BROWSER"] = "1"
    environment["ELYSIA_CODEV_BROWSER_FAMILY"] = browser_family
    evidence = environment.get("ELYSIA_CODEV_MARKETPLACE_EVIDENCE", "/tmp/elysia-codev-marketplace-browser")
    environment["ELYSIA_CODEV_MARKETPLACE_EVIDENCE"] = evidence + "-" + browser_family
    cached_browsers = Path.home() / ".cache" / "ms-playwright"
    if cached_browsers.is_dir():
        environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(cached_browsers))
    result = subprocess.run(["node", "scripts/codevMarketplaceBrowserTest.mjs"], cwd=online, env=environment,
                            capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "actual_marketplace_codev_browser_ok" in result.stdout
    assert "actual_forge_codev_browser_ok" in result.stdout
