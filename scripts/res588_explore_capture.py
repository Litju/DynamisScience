from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "docs" / "design" / "res588-ux" / "audit" / "production"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:3001/research/studies/STUDY-U-EE7514BB", wait_until="networkidle")
    page.wait_for_selector(".bench")
    block = page.locator(".block", has=page.locator(".block-type", has_text="Explore")).first
    block.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    # Element-only capture: excludes the cohort participant chips above the block.
    block.screenshot(path=str(OUT / "study-mendeley-explore-block-1440x900.png"))
    browser.close()
print("redacted element capture written")
