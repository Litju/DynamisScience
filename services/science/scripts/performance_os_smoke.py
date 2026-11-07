"""Smoke-test the synthetic Performance OS routes in a real browser."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from dynamis_science.data_root import data_root

BASE = os.environ.get("DYNAMISSCIENCE_BROWSER_BASE", "http://127.0.0.1:3001")
ROUTES = [
    ("plan", "/plan", "Plan"),
    ("monitor", "/monitor", "Monitor"),
    ("test", "/test", "Test"),
    ("research", "/research", "Research"),
    ("report", "/report", "Reports"),
]


def run() -> dict:
    output = data_root() / "reports" / "browser-res589"
    output.mkdir(parents=True, exist_ok=True)
    results = {
        "base": BASE,
        "viewport": {"width": 1440, "height": 900},
        "pages": [],
        "console_errors": [],
        "page_errors": [],
        "failed_responses": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=results["viewport"])
        page.on(
            "console",
            lambda message: results["console_errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
        page.on(
            "response",
            lambda response: results["failed_responses"].append(
                {"url": response.url, "status": response.status}
            )
            if response.status >= 400
            else None,
        )

        def capture(name: str, path: str, marker: str, status: int) -> None:
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth > window.innerWidth + 1"
            )
            screenshot = output / f"{name}-1440x900.png"
            page.screenshot(path=str(screenshot), full_page=True)
            results["pages"].append(
                {
                    "name": name,
                    "path": path,
                    "marker": marker,
                    "http_status": status,
                    "overflow": overflow,
                    "screenshot": str(screenshot),
                }
            )

        response = page.goto(f"{BASE}/today", wait_until="domcontentloaded", timeout=60000)
        page.get_by_role("heading", name="Squad command", exact=True).wait_for(timeout=30000)
        capture("today", "/today", "Squad command", response.status if response else 0)

        athlete_link = page.locator('a[href^="/athletes/ATH-"]').first
        athlete_path = athlete_link.get_attribute("href")
        if not athlete_path:
            raise RuntimeError("Today did not render an Athlete 360 link")
        athlete_link.click()
        page.wait_for_url("**" + athlete_path, timeout=30000)
        athlete_id = athlete_path.rsplit("/", 1)[1]
        page.get_by_role("heading", name=athlete_id, exact=True).wait_for(timeout=30000)
        response = page.goto(f"{BASE}{athlete_path}", wait_until="domcontentloaded", timeout=60000)
        page.get_by_role("heading", name=athlete_id, exact=True).wait_for(timeout=30000)
        capture("athlete-360", athlete_path, athlete_id, response.status if response else 0)

        for name, path, marker in ROUTES:
            response = page.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=60000)
            page.get_by_role("heading", name=marker, exact=True).wait_for(timeout=30000)
            capture(name, path, marker, response.status if response else 0)

        browser.close()

    results["console_errors"] = sorted(set(results["console_errors"]))
    results["page_errors"] = sorted(set(results["page_errors"]))
    results["status"] = "PASS" if all(
        page["http_status"] == 200 and not page["overflow"] for page in results["pages"]
    ) and not results["console_errors"] and not results["page_errors"] and not results["failed_responses"] else "ATTENTION"
    (output / "synthetic_os_smoke.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return results


if __name__ == "__main__":
    result = run()
    print(json.dumps({
        "status": result["status"],
        "pages": result["pages"],
        "console_errors": len(result["console_errors"]),
        "page_errors": len(result["page_errors"]),
        "failed_responses": len(result["failed_responses"]),
    }, indent=2))
    sys.exit(0 if result["status"] == "PASS" else 1)
