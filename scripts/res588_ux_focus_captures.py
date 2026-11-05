"""Focused audit captures: analysis, diagnostics, figure, create-study form, monitoring schedule."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3001"
OUT = Path(__file__).resolve().parents[1] / "docs" / "design" / "res588-ux" / "audit" / "production"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(BASE + "/research/studies/STUDY-U-EE7514BB", wait_until="networkidle")
    page.wait_for_selector(".bench")

    for label, filename in [("Analysis", "study-mendeley-analysis-block"), ("Diagnostics", "study-mendeley-diagnostics"), ("Figure", "study-mendeley-figure")]:
        block = page.locator(".block", has_text=label).first
        block.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / f"{filename}-1440x900.png"))

    # Open the new-study composer in the project without submitting.
    page.goto(BASE + "/research/projects/PRJ-FB8A479E", wait_until="networkidle")
    page.get_by_role("button", name="New study").click()
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "project-new-study-form-1440x900.png"))

    # Monitoring schedule block.
    page.goto(BASE + "/research/studies/PROG-U-7B9AB9FE", wait_until="networkidle")
    page.wait_for_selector(".bench")
    schedule = page.locator(".block", has_text="Schedule").first
    schedule.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "monitoring-schedule-block-1440x900.png"))

    browser.close()
print("focused captures written")
