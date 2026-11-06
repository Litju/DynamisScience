"""RES-588 Performance OS browser validation.

Runs the approved operational workflows through a real Chromium browser at the
three required desktop sizes, captures screenshots, checks for console errors
and horizontal overflow, and writes a machine-readable receipt.

Usage (backend on :8000, production web on :3000):
    uv run --directory services/science python ../../scripts/res588_performance_validate.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design" / "res588-ux" / "implemented"
BASE = "http://127.0.0.1:3000"

VIEWPORTS = [(1440, 900), (1280, 800), (1024, 800)]
ROUTES = [
    ("today", "/today", "Squad command"),
    ("plan", "/plan", "Planned versus actual load"),
    ("monitor", "/monitor", "Team training impulse"),
    ("test", "/test", "Within-session reliability"),
    ("research", "/research", "Research projects"),
    ("report", "/report", "Reports"),
    ("atlas", "/atlas", "Units registry"),
    ("athlete", "/athletes/ATH-003", "ATH-003"),
]


def wait(page: Page, ms: int = 500) -> None:
    page.wait_for_timeout(ms)


def check_no_overflow(page: Page) -> dict[str, int]:
    return page.evaluate(
        """() => ({
          innerWidth: window.innerWidth,
          bodyScrollWidth: document.body.scrollWidth,
          rootScrollWidth: document.documentElement.scrollWidth,
          bodyScrollHeight: document.body.scrollHeight,
        })"""
    )


def capture(page: Page, name: str, width: int) -> dict:
    page.screenshot(path=str(OUT / f"{name}-{width}.png"))
    return {
        "image": str((OUT / f"{name}-{width}.png").relative_to(ROOT)).replace("\\", "/"),
        **check_no_overflow(page),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    receipt: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": BASE,
        "synthetic_snapshot": "DS-SYNTH-001",
        "viewports": [f"{w}x{h}" for w, h in VIEWPORTS],
        "screens": [],
        "console_errors": [],
        "workflows": {},
        "checks": {},
    }
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in VIEWPORTS:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            for name, route, expected in ROUTES:
                page.goto(BASE + route, wait_until="networkidle", timeout=120_000)
                wait(page, 500)
                text = page.locator("body").inner_text()
                if expected not in text:
                    raise AssertionError(f"{name} at {width}: expected {expected!r}")
                receipt["screens"].append(capture(page, name, width))
            page.close()

        # Full-desktop workflow evidence and interactive checks.
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        # Workflow 1: Today -> Athlete 360 -> Monitor -> Test -> Research -> Evidence -> Report.
        page.goto(BASE + "/today", wait_until="networkidle")
        page.locator(".pos-ath-row").first.click()
        page.wait_for_url("**/athletes/ATH-003")
        page.wait_for_load_state("networkidle")
        wait(page)
        receipt["workflows"]["today_to_athlete"] = page.url
        receipt["screens"].append(capture(page, "workflow-athlete", 1440))
        page.get_by_role("link", name="Monitor trajectory").click()
        page.wait_for_url("**/monitor?athlete=ATH-003")
        page.wait_for_load_state("networkidle")
        wait(page)
        if page.locator(".pos-module-head", has_text="individual trajectory").count() == 0:
            raise AssertionError("Athlete trajectory did not open in Monitor")
        receipt["workflows"]["athlete_to_monitor"] = page.url

        page.get_by_role("link", name="Test").first.click()
        page.wait_for_url("**/test")
        page.wait_for_load_state("networkidle")
        wait(page)
        if page.get_by_role("button", name="Run reliability check").count():
            page.get_by_role("button", name="Run reliability check").click()
            wait(page, 1400)
        receipt["workflows"]["monitor_to_test"] = page.url
        receipt["screens"].append(capture(page, "workflow-test", 1440))

        page.get_by_role("link", name="Research").first.click()
        page.wait_for_url("**/research")
        page.wait_for_load_state("networkidle")
        page.get_by_role("tab", name="Evidence ledger").click()
        wait(page)
        receipt["screens"].append(capture(page, "workflow-evidence", 1440))
        page.wait_for_selector(".pos-table tbody tr a", timeout=15_000)
        first_evidence = page.locator(".pos-table tbody tr").first.locator("a").first
        first_evidence.click()
        page.wait_for_url("**/research/studies/**", timeout=30_000)
        page.wait_for_load_state("networkidle")
        wait(page, 900)
        inspector_text = page.locator(".pane-insp").inner_text().upper()
        if "EVID-" not in inspector_text:
            raise AssertionError("Evidence inspector did not open from the evidence ledger")
        receipt["workflows"]["evidence_to_workbench"] = page.url
        receipt["screens"].append(capture(page, "workflow-evidence-workbench", 1440))

        page.goto(BASE + "/research", wait_until="networkidle")
        wait(page)
        page.get_by_role("tab", name="Model lab").click()
        wait(page, 1800)
        if page.locator(".pos-error").count():
            raise AssertionError("Model lab failed to load")
        page.get_by_role("button", name="Run scenario").click()
        wait(page, 1600)
        receipt["checks"]["model_scenario"] = page.locator(".pos-research-card", has_text="SCENARIO").count() > 0
        receipt["screens"].append(capture(page, "workflow-model-lab", 1440))

        page.goto(BASE + "/report", wait_until="networkidle")
        wait(page)
        if page.locator(".pos-report-preview h2").count() == 0:
            page.get_by_role("button", name="Compose coach report").click()
            wait(page, 1600)
        receipt["workflows"]["report_preview"] = page.locator(".pos-report-preview h2").inner_text()
        if page.get_by_role("button", name="Freeze").count():
            page.get_by_role("button", name="Freeze").click()
            wait(page, 900)
        receipt["screens"].append(capture(page, "workflow-report", 1440))

        # Workflow 2: Plan -> training load -> monitoring -> testing -> report.
        page.goto(BASE + "/plan", wait_until="networkidle")
        wait(page)
        first_load = page.locator(".pos-plan-table input[type=number]").first
        first_load.fill("54")
        page.get_by_role("button", name="Publish week").click()
        wait(page, 1200)
        page.reload(wait_until="networkidle")
        wait(page)
        persisted = page.locator(".pos-plan-table input[type=number]").first.input_value()
        if persisted != "54":
            raise AssertionError(f"Plan did not persist: {persisted}")
        receipt["workflows"]["plan_publish_persisted_au"] = persisted
        receipt["screens"].append(capture(page, "workflow-plan-published", 1440))

        page.get_by_role("link", name="Open training load").click()
        page.wait_for_url("**/monitor?metric=load")
        page.wait_for_load_state("networkidle")
        wait(page)
        receipt["workflows"]["plan_to_load"] = page.url
        page.get_by_role("link", name="Test").first.click()
        page.wait_for_load_state("networkidle")
        wait(page)
        page.get_by_role("link", name="Reports").first.click()
        page.wait_for_load_state("networkidle")
        wait(page)
        receipt["workflows"]["testing_to_report"] = page.url

        # Role-aware navigation and report default.
        page.goto(BASE + "/report", wait_until="networkidle")
        wait(page)
        page.get_by_label("Performance role").select_option("medical")
        wait(page, 500)
        medical_default = page.locator(".pos-report-card.is-active .pos-k").first.inner_text()
        receipt["checks"]["medical_role_default_report"] = medical_default
        receipt["screens"].append(capture(page, "workflow-role-medical", 1440))
        page.get_by_label("Performance role").select_option("head")
        wait(page, 300)

        # Scientific report surface remains available.
        page.goto(BASE + "/research/studies/STUDY-001?mode=report", wait_until="networkidle")
        wait(page, 900)
        receipt["screens"].append(capture(page, "scientific-report", 1440))

        # Visual comparison pages use the approved prototype and implemented screenshots.
        for name in ("comparison-command", "comparison-atlas"):
            page.goto((OUT / f"{name}.html").as_uri(), wait_until="load")
            wait(page, 300)
            receipt["screens"].append(capture(page, name, 1440))

        # Verify the required data-honesty statements are visible.
        page.goto(BASE + "/today", wait_until="networkidle")
        wait(page)
        today_text = page.locator("body").inner_text()
        receipt["checks"]["injury_module_unavailable"] = "Injury module unavailable" in today_text
        receipt["checks"]["roster_only"] = "roster status only" in today_text
        receipt["checks"]["bounded_gps"] = "bounded segment" in today_text.lower()
        receipt["checks"]["unit_chip_present"] = any(unit in today_text for unit in ["cm", "N", "AU"])

        page.goto(BASE + "/atlas", wait_until="networkidle")
        wait(page, 500)
        atlas_text = page.locator("body").inner_text()
        receipt["checks"]["threshold_owner_visible"] = "Head of Performance" in atlas_text
        receipt["checks"]["unit_registry_visible"] = "Units registry" in atlas_text
        receipt["checks"]["no_fake_injury_rate"] = "1000 h" in atlas_text and "Not admitted" in atlas_text

        browser.close()

    receipt["console_errors"] = console_errors
    if console_errors:
        raise AssertionError(f"Console errors: {console_errors[:5]}")
    overflow = [
        screen
        for screen in receipt["screens"]
        if screen["bodyScrollWidth"] > screen["innerWidth"] + 1
        or screen["rootScrollWidth"] > screen["innerWidth"] + 1
    ]
    if overflow:
        raise AssertionError(f"Horizontal overflow: {overflow[:3]}")
    receipt["checks"]["no_horizontal_overflow"] = True
    receipt["checks"]["no_console_errors"] = True
    (OUT / "validation-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("viewports", "checks", "workflows")}, indent=2))


if __name__ == "__main__":
    main()
