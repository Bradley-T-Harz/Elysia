from pathlib import Path
import os
import subprocess
import pytest


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
    if not (online / "dist" / "index.html").is_file():
        pytest.skip("Build the isolated Online frontend before full-page qualification")
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
