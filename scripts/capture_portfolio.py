"""Capture portfolio views from a running Flightline Lab site."""

from argparse import ArgumentParser
from pathlib import Path

from playwright.sync_api import sync_playwright


def capture(base_url: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    browser_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    browser_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=browser_path)

        desktop = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        desktop.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)
        desktop.goto(base_url, wait_until="networkidle")
        desktop.screenshot(path=output / "flightline-home-desktop.png", full_page=False)
        desktop.get_by_role("button", name="Try the public flight-data demo").click()
        desktop.locator(".evidence-map").wait_for(state="visible")
        desktop.locator(".result-area").scroll_into_view_if_needed()
        desktop.screenshot(path=output / "flightline-result-desktop.png", full_page=False)
        desktop.screenshot(path=output / "flightline-full-page.png", full_page=True)

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.on("console", lambda message: browser_errors.append(message.text) if message.type == "error" else None)
        mobile.goto(base_url, wait_until="networkidle")
        mobile.get_by_role("button", name="Try the public flight-data demo").click()
        mobile.locator(".evidence-map").wait_for(state="visible")
        mobile.locator(".result-area").scroll_into_view_if_needed()
        mobile.screenshot(path=output / "flightline-result-mobile.png", full_page=False)
        mobile.screenshot(path=output / "flightline-mobile-full-page.png", full_page=True)

        browser.close()

    if browser_errors:
        raise RuntimeError("Browser console errors: " + " | ".join(browser_errors))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5174")
    parser.add_argument("--output", type=Path, default=Path("screenshots"))
    arguments = parser.parse_args()
    capture(arguments.base_url.rstrip("/"), arguments.output)
