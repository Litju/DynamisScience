"""Render Direction E — Fieldlab brief/lab at 1440x900 and 1280x800."""
from __future__ import annotations
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:4173/docs/design/res588-ux/prototypes/e"
OUT = ROOT / "docs" / "design" / "res588-ux" / "screens"

PAGES = [("brief", "e-brief"), ("lab", "e-lab")]
VIEWPORTS = [(1440, 900, "1440x900"), (1280, 800, "1280x800")]
receipt = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    for width, height, label in VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = context.new_page()
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        for name, slug in PAGES:
            page.goto(f"{BASE}/{name}.html", wait_until="networkidle", timeout=60000)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(700)
            page.screenshot(path=str(OUT / f"{slug}-{label}.png"), full_page=False)
            metrics = page.evaluate("""
            () => {
              const box = (sel) => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)}; };
              return {viewport:{w:innerWidth,h:innerHeight}, scroll:{w:document.documentElement.scrollWidth,h:document.documentElement.scrollHeight}, chart:box('.chart-wrap'), brief:box('.brief'), mainScrollH:document.querySelector('.main')?.scrollHeight, mainClientH:document.querySelector('.main')?.clientHeight};
            }
            """)
            receipt.append({"page": name, "viewport": label, "metrics": metrics, "console": list(errors)})
        context.close()
    browser.close()
(OUT / "render-receipt-e.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
