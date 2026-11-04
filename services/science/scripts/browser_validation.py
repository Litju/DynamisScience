"""Rendered-product validation at the viewports required by RES-587.

Run while the local science service (port 8000) and Next.js app (port 3000)
are running:

    python scripts/browser_validation.py

The script uses the installed Microsoft Edge through Playwright, so it does
not download a browser.  Screenshots and a machine-readable report are written
under ``$DYNAMISSCIENCE_DATA_ROOT/reports/browser``.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(
    os.environ.get("DYNAMISSCIENCE_DATA_ROOT", ROOT / "data" / "real")
).expanduser()
REPORT_DIR = DATA_ROOT / "reports" / "browser"
BASE = os.environ.get("DYNAMISSCIENCE_BROWSER_BASE", "http://localhost:3000")

VIEWPORTS = [
    {"name": "desktop-1440", "width": 1440, "height": 900},
    {"name": "desktop-1280", "width": 1280, "height": 800},
    {"name": "narrow-1024", "width": 1024, "height": 800},
]

PAGES = [
    ("admission", "/data/admission", "Deposited files"),
    ("snapshot", "/data/DS-REAL-MENDELEY-2C44490E08AD", "Tables"),
    ("study-longitudinal", "/research/studies/STUDY-REAL-001", "Real-data scientific investigation"),
    ("study-measurement", "/research/studies/STUDY-REAL-002", "Peak-force reliability"),
]


def _overflow(page) -> dict:
    return page.evaluate(
        """() => ({
          innerWidth: window.innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          bodyScrollWidth: document.body.scrollWidth,
          overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
        })"""
    )


def run() -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = {"started_at": datetime.now(timezone.utc).isoformat(), "base": BASE, "viewports": []}
    edge = _edge_path()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
        try:
            for viewport in VIEWPORTS:
                context = browser.new_context(
                    viewport={"width": viewport["width"], "height": viewport["height"]},
                    device_scale_factor=1,
                )
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                failed_requests: list[dict] = []
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on(
                    "response",
                    lambda response: failed_requests.append(
                        {"url": response.url, "status": response.status}
                    )
                    if response.status >= 400
                    else None,
                )
                entries = []
                for name, path, marker in PAGES:
                    page.goto(f"{BASE}{path}", wait_until="domcontentloaded", timeout=60000)
                    try:
                        page.get_by_text(marker, exact=False).first.wait_for(timeout=30000)
                    except Exception:
                        page.wait_for_timeout(3000)
                    overflow = _overflow(page)
                    screenshot = REPORT_DIR / f"{viewport['name']}-{name}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    entries.append(
                        {
                            "page": name,
                            "url": page.url,
                            "title": page.title(),
                            "marker": marker,
                            "marker_visible": page.get_by_text(marker, exact=False).count() > 0,
                            "overflow": overflow,
                            "screenshot": str(screenshot),
                        }
                    )
                # Report mode on the longitudinal study.
                page.goto(f"{BASE}/research/studies/STUDY-REAL-001", wait_until="domcontentloaded", timeout=60000)
                try:
                    page.get_by_text("Real-data scientific investigation", exact=False).first.wait_for(timeout=30000)
                except Exception:
                    page.wait_for_timeout(3000)
                report_button = page.get_by_role("button", name="Report", exact=True)
                if report_button.count():
                    report_button.first.click()
                    try:
                        page.get_by_text("REPORT-REAL-001", exact=False).first.wait_for(timeout=30000)
                    except Exception:
                        page.wait_for_timeout(2000)
                    filename = REPORT_DIR / f"{viewport['name']}-report.png"
                    page.screenshot(path=str(filename), full_page=True)
                    entries.append(
                        {
                            "page": "report",
                            "url": page.url,
                            "title": page.title(),
                            "marker": "REPORT-REAL-001",
                            "marker_visible": page.get_by_text("REPORT-REAL-001", exact=False).count() > 0,
                            "overflow": _overflow(page),
                            "screenshot": str(filename),
                        }
                    )
                results["viewports"].append(
                    {
                        **viewport,
                        "pages": entries,
                        "console_errors": sorted(set(console_errors)),
                        "page_errors": sorted(set(page_errors)),
                        "failed_requests": failed_requests,
                    }
                )
                context.close()
        finally:
            browser.close()
    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    results["status"] = "PASS" if all(
        not item["console_errors"]
        and not item["page_errors"]
        and not item["failed_requests"]
        and all(not page["overflow"]["overflow"] for page in item["pages"])
        and all(page["marker_visible"] for page in item["pages"])
        for item in results["viewports"]
    ) else "ATTENTION"
    (REPORT_DIR / "browser_validation.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return results


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "viewports": [
        {
            "name": viewport["name"],
            "console_errors": len(viewport["console_errors"]),
            "page_errors": len(viewport["page_errors"]),
            "failed_requests": len(viewport["failed_requests"]),
            "overflow": [page["page"] for page in viewport["pages"] if page["overflow"]["overflow"]],
            "markers": {page["page"]: page["marker_visible"] for page in viewport["pages"]},
        }
        for viewport in result["viewports"]
    ]}, indent=2))
    sys.exit(0 if result["status"] == "PASS" else 1)
