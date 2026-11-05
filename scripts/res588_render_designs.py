"""Render the three RES-588 design directions at 1440x900 and 1280x800."""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:4173/docs/design/res588-ux/prototypes"
OUT = ROOT / "docs" / "design" / "res588-ux" / "screens"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("a", "analyze", "a-analyze"),
    ("a", "design", "a-design"),
    ("b", "analyze", "b-analyze"),
    ("b", "new-study", "b-new-study"),
    ("c", "analyze", "c-analyze"),
    ("c", "monitoring", "c-monitoring"),
]

VIEWPORTS = [(1440, 900, "1440x900"), (1280, 800, "1280x800")]

receipt: list[dict] = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height, label in VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = context.new_page()
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        for direction, page_name, slug in PAGES:
            url = f"{BASE}/{direction}/{page_name}.html"
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(700)
            path = OUT / f"{slug}-{label}.png"
            page.screenshot(path=str(path), full_page=False)
            metrics = page.evaluate("""
            () => {
              const box = (sel) => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)}; };
              return {
                viewport: {w: innerWidth, h: innerHeight},
                scroll: {w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight},
                chart: box('.chart-wrap, .monitor-timeline'),
                page: box('.page'),
                canvas: box('.canvas'),
              };
            }
            """)
            receipt.append({"slug": slug, "viewport": label, "metrics": metrics, "console_errors": list(console_errors)})
        context.close()
    browser.close()

(OUT / "render-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
