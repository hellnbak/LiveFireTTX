from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.request import urlopen
import os
import re
import shutil
import socket
import subprocess
import sys
import time

from playwright.sync_api import Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / ".e2e-artifacts"


def main() -> int:
    shutil.rmtree(ARTIFACT_ROOT, ignore_errors=True)
    ARTIFACT_ROOT.mkdir(parents=True)
    with TemporaryDirectory() as temporary:
        port = _available_port()
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update(
            {
                "LIVEFIRE_DATA_ROOT": temporary,
                "LIVEFIRE_SCHEDULER_ENABLED": "false",
                "LIVEFIRE_LAB_CONTROLS_ENABLED": "false",
                "PYTHONUNBUFFERED": "1",
            }
        )
        with (ARTIFACT_ROOT / "server.log").open("w") as server_log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                _wait_until_ready(base_url, server)
                _run_browser_journey(base_url)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
    print(f"Browser accessibility and UI regression checks passed: {ARTIFACT_ROOT}")
    return 0


def _run_browser_journey(base_url: str) -> None:
    browser_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on(
            "console",
            lambda message: browser_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        try:
            page.goto(base_url, wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="LiveFireTTX")).to_be_visible()
            _assert_skip_link(page)
            _audit_page(page, "home-desktop")

            page.get_by_role("link", name="Create Exercise").click()
            expect(
                page.get_by_role("heading", name="Create a LiveFireTTX Exercise")
            ).to_be_visible()
            _audit_page(page, "setup-desktop")
            page.locator("#exercise-name").fill("v1.4 browser regression")
            page.locator("#business-system").fill("Customer Checkout")
            page.locator("#duration-minutes").fill("60")
            page.get_by_role("button", name="Generate Exercise Package").click()
            expect(page).to_have_url(re.compile(r"/exercises/ttx_[a-f0-9]{12}$"))
            exercise_url = page.url
            expect(page.get_by_text("Signed & Retained Exports")).to_be_visible()
            _audit_page(page, "command-center-desktop")

            with page.expect_download() as download_info:
                page.get_by_role("link", name="Create Signed Export").click()
            download_info.value.save_as(ARTIFACT_ROOT / "signed-evidence.zip")
            page.goto(exercise_url, wait_until="domcontentloaded")
            expect(page.get_by_text("Verified", exact=True)).to_be_visible()

            for suffix, heading, name in [
                ("/run", "Facilitator Run Mode", "run-desktop"),
                ("/evaluate", "Evaluator Workspace", "evaluate-desktop"),
                ("/present", "v1.4 browser regression", "present-desktop"),
            ]:
                page.goto(exercise_url + suffix, wait_until="domcontentloaded")
                expect(page.get_by_text(heading, exact=True).first).to_be_visible()
                _audit_page(page, name)

            mobile = context.new_page()
            mobile.set_viewport_size({"width": 390, "height": 844})
            for url, name in [
                (base_url, "home-mobile"),
                (base_url + "/new", "setup-mobile"),
                (exercise_url, "command-center-mobile"),
                (exercise_url + "/run", "run-mobile"),
                (exercise_url + "/evaluate", "evaluate-mobile"),
                (exercise_url + "/present", "present-mobile"),
            ]:
                mobile.goto(url, wait_until="domcontentloaded")
                _audit_page(mobile, name)
            mobile.close()
        except Exception:
            page.screenshot(path=ARTIFACT_ROOT / "failure.png", full_page=True)
            raise
        finally:
            context.close()
            browser.close()
    if browser_errors:
        raise AssertionError("Browser errors: " + " | ".join(browser_errors))


def _audit_page(page: Page, name: str) -> None:
    violations = page.evaluate(
        """() => {
          const issues = [];
          if (document.documentElement.lang !== "en") issues.push("document language");
          if (!document.querySelector("main")) issues.push("main landmark");
          if (document.querySelectorAll("h1").length !== 1) issues.push("single h1");
          const ids = [...document.querySelectorAll("[id]")].map((node) => node.id);
          if (new Set(ids).size !== ids.length) issues.push("duplicate ids");
          document.querySelectorAll("input:not([type=hidden]), select, textarea").forEach((field) => {
            if (!field.labels?.length && !field.getAttribute("aria-label") && !field.getAttribute("aria-labelledby")) {
              issues.push(`unlabelled field ${field.id || field.name || field.tagName}`);
            }
          });
          document.querySelectorAll("img").forEach((image) => {
            if (!image.hasAttribute("alt")) issues.push("image without alt");
          });
          document.querySelectorAll("a, button").forEach((control) => {
            const name = control.getAttribute("aria-label") || control.textContent.trim();
            if (!name) issues.push(`unnamed ${control.tagName.toLowerCase()}`);
          });
          const headings = [...document.querySelectorAll("h1, h2, h3, h4, h5, h6")];
          let previous = 0;
          headings.forEach((heading) => {
            const level = Number(heading.tagName.slice(1));
            if (previous && level > previous + 1) issues.push(`heading jump ${previous}-${level}`);
            previous = level;
          });
          if (document.documentElement.scrollWidth > window.innerWidth + 1) {
            issues.push(`horizontal overflow ${document.documentElement.scrollWidth}/${window.innerWidth}`);
          }
          return issues;
        }"""
    )
    if violations:
        raise AssertionError(f"{name} accessibility failures: {', '.join(violations)}")
    page.screenshot(path=ARTIFACT_ROOT / f"{name}.png", full_page=True)


def _assert_skip_link(page: Page) -> None:
    page.locator("body").press("Tab")
    expect(page.locator(":focus")).to_have_text("Skip to main content")
    page.locator(":focus").press("Enter")
    expect(page.locator("#main-content")).to_be_focused()


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(base_url: str, server: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"UI test server exited with status {server.returncode}")
        try:
            with urlopen(f"{base_url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("UI test server did not become ready")


if __name__ == "__main__":
    raise SystemExit(main())
