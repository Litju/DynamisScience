"""RES-588 rendered-product validation against the production build.

Run while the science service (port 8000) and the production Next.js build
(port 3001) are running:

    $env:DYNAMISSCIENCE_DATA_ROOT = Join-Path $env:LOCALAPPDATA 'DynamisScience'
    $env:DYNAMISSCIENCE_BROWSER_BASE = 'http://localhost:3001'
    python scripts/res588_validation.py

The script reads the two demonstration studies and the monitoring program from
the local science service, exercises them at 1440x900, 1280x800 and 1024x800,
downloads both HTML reports, checks keyboard access, console/page/network
errors and horizontal overflow, and writes a machine-readable report.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

DATA_ROOT = Path(os.environ.get("DYNAMISSCIENCE_DATA_ROOT", Path(__file__).resolve().parents[1] / "data" / "real"))
REPORT_DIR = DATA_ROOT / "reports" / "browser-res588"
API = os.environ.get("DYNAMISSCIENCE_SCIENCE_API", "http://127.0.0.1:8000")
BASE = os.environ.get("DYNAMISSCIENCE_BROWSER_BASE", "http://localhost:3001")
VIEWPORTS = [
    {"name": "desktop-1440", "width": 1440, "height": 900},
    {"name": "desktop-1280", "width": 1280, "height": 800},
    {"name": "narrow-1024", "width": 1024, "height": 800},
]


def discover() -> dict:
    studies = [item for item in httpx.get(f"{API}/studies", timeout=30).json() if item.get("kind") == "STUDY"]
    programs = [item for item in httpx.get(f"{API}/studies", timeout=30).json() if item.get("kind") == "MONITORING"]
    if len(studies) < 2 or not programs:
        raise SystemExit("RES-588 demonstrations are not present in the local data root")
    manifest = {
        "study_a": studies[0]["id"],
        "study_b": studies[1]["id"],
        "program": programs[0]["id"],
        "project_a": studies[0]["project_id"],
        "project_b": studies[1]["project_id"],
        "snapshot_a": studies[0]["dataset_snapshot_id"],
        "snapshot_b": studies[1]["dataset_snapshot_id"],
    }
    manifest["run_a"] = httpx.get(f"{API}/runs?study_id={manifest['study_a']}", timeout=30).json()[0]["id"]
    manifest["run_b"] = httpx.get(f"{API}/runs?study_id={manifest['study_b']}", timeout=30).json()[0]["id"]
    manifest["evidence_a"] = httpx.get(f"{API}/evidence?study_id={manifest['study_a']}", timeout=30).json()[0]["id"]
    manifest["evidence_b"] = httpx.get(f"{API}/evidence?study_id={manifest['study_b']}", timeout=30).json()[0]["id"]
    return manifest


def overflow(page) -> dict:
    return page.evaluate(
        "() => ({ innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth, overflow: document.documentElement.scrollWidth > window.innerWidth + 1 })"
    )


def run() -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = discover()
    results = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base": BASE,
        "api": API,
        "manifest": manifest,
        "viewports": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            executable_path=edge_path(),
            args=["--disable-gpu"],
        )
        try:
            for viewport in VIEWPORTS:
                context = browser.new_context(viewport={"width": viewport["width"], "height": viewport["height"]}, accept_downloads=True)
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                failed_requests: list[dict] = []
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on(
                    "response",
                    lambda response: failed_requests.append({"url": response.url, "status": response.status})
                    if response.status >= 400 and "favicon" not in response.url
                    else None,
                )
                entries = []

                def capture(name: str, marker: str, action=None) -> None:
                    page.goto(f"{BASE}{name if name.startswith('/') else '/' + name}", wait_until="domcontentloaded", timeout=60000)
                    try:
                        page.get_by_text(marker, exact=False).first.wait_for(timeout=30000)
                    except Exception:
                        page.wait_for_timeout(2500)
                    if action:
                        action()
                    screenshot = REPORT_DIR / f"{viewport['name']}-{name.strip('/').replace('/', '-').replace('?', '-')}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    entries.append(
                        {
                            "page": name,
                            "url": page.url,
                            "title": page.title(),
                            "marker": marker,
                            "marker_visible": page.get_by_text(marker, exact=False).count() > 0,
                            "overflow": overflow(page),
                            "screenshot": str(screenshot),
                        }
                    )

                capture("/research", "CMJ Response to 8-Week Strength Intervention")
                capture(f"/research/projects/{manifest['project_a']}", "Weekly CMJ monitoring program")
                capture(f"/research/projects/{manifest['project_b']}", "Wearable force-plate measurement study")
                capture(f"/research/studies/{manifest['study_a']}", "Primary analysis")
                capture(f"/research/studies/{manifest['study_a']}?mode=setup", "Study setup")
                capture(f"/research/studies/{manifest['program']}", "Monitoring schedule")
                capture(f"/research/studies/{manifest['study_b']}", "Trial-to-trial reliability")

                # Report modes and downloadable HTML reports.
                for label, study in (("report-a", manifest["study_a"]), ("report-b", manifest["study_b"])):
                    page.goto(f"{BASE}/research/studies/{study}", wait_until="domcontentloaded", timeout=60000)
                    page.get_by_role("group", name="Study mode").get_by_role("button", name="Report").click()
                    page.get_by_role("link", name="Export HTML").wait_for(timeout=30000)
                    screenshot = REPORT_DIR / f"{viewport['name']}-{label}.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    with page.expect_download(timeout=30000) as download_info:
                        page.get_by_role("link", name="Export HTML").click()
                    download = download_info.value
                    export_path = REPORT_DIR / f"{viewport['name']}-{label}.html"
                    download.save_as(str(export_path))
                    html = export_path.read_text(encoding="utf-8")
                    entries.append(
                        {
                            "page": label,
                            "url": page.url,
                            "title": page.title(),
                            "marker": "Export HTML",
                            "marker_visible": "id=\"manifest\"" in html and "RUN-U-" in html,
                            "overflow": overflow(page),
                            "screenshot": str(screenshot),
                            "export": str(export_path),
                            "export_bytes": export_path.stat().st_size,
                        }
                    )

                # Keyboard access: command palette opens with Ctrl+K and closes with Escape.
                page.goto(f"{BASE}/research", wait_until="networkidle", timeout=60000)
                page.locator("body").click(position={"x": 700, "y": 400})
                page.keyboard.press("Control+K")
                try:
                    page.get_by_role("dialog").wait_for(timeout=5000)
                except Exception:
                    pass
                palette_open = page.get_by_role("dialog").count() > 0
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
                keyboard = {"ctrl_k_palette_open": palette_open}

                # Existing RES-116 / RES-587 surfaces remain present.
                capture("/research/studies/STUDY-001", "Primary Intervention Analysis")
                capture("/data/admission", "Deposited files")
                capture(f"/data/{manifest['snapshot_a']}", "Tables")
                capture("/library", "Library")

                results["viewports"].append(
                    {
                        **viewport,
                        "pages": entries,
                        "console_errors": sorted(set(console_errors)),
                        "page_errors": sorted(set(page_errors)),
                        "failed_requests": failed_requests,
                        "keyboard": keyboard,
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
        and all(not entry["overflow"]["overflow"] for entry in item["pages"])
        and all(entry["marker_visible"] for entry in item["pages"])
        and item["keyboard"]["ctrl_k_palette_open"]
        for item in results["viewports"]
    ) else "ATTENTION"
    (REPORT_DIR / "res588_validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {
                "status": result["status"],
                "viewports": [
                    {
                        "name": item["name"],
                        "console_errors": len(item["console_errors"]),
                        "page_errors": len(item["page_errors"]),
                        "failed_requests": len(item["failed_requests"]),
                        "overflow": [entry["page"] for entry in item["pages"] if entry["overflow"]["overflow"]],
                        "markers": {entry["page"]: entry["marker_visible"] for entry in item["pages"]},
                        "keyboard": item["keyboard"],
                    }
                    for item in result["viewports"]
                ],
            },
            indent=2,
        )
    )
    sys.exit(0 if result["status"] == "PASS" else 1)
