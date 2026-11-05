# RES-588 — UX/UI design gate artifacts

This directory contains the evidence for **Section 11 (P0 UX/UI Product Reset)**
of RES-588. The current production experience has been audited and rejected as
the product baseline. No production UI was modified during this gate.

**Latest owner-requested synthesis:** Direction D, **The Research Atelier** —
[`RES-588_UX_DIRECTION_D_ATELIER.md`](RES-588_UX_DIRECTION_D_ATELIER.md) and
[`compare/atelier.html`](compare/atelier.html). It combines A’s activity model,
B’s editorial margin and C’s object thread.

Start with:

- [`RES-588_UX_DIRECTION_D_ATELIER.md`](RES-588_UX_DIRECTION_D_ATELIER.md) —
  the recommended hybrid: four screens, design rationale, cost and tradeoffs.
- [`RES-588_UX_AUDIT_AND_DIRECTIONS.md`](RES-588_UX_AUDIT_AND_DIRECTIONS.md) —
  the original audit, directions A/B/C, comparison and decision request.
- [`compare/atelier.html`](compare/atelier.html) — the Direction D gallery.
- [`compare/index.html`](compare/index.html) — the A/B/C comparison gallery.

## Directory map

| Path | Contents |
|---|---|
| `audit/production/` | Production screenshots at 1440, 1280 and 1024, layout metrics, keyboard/interaction audit and runtime request receipts |
| `screens/` | Rendered design-direction screenshots at 1440×900 and 1280×800 |
| `prototypes/a|b|c|d/` | Static, read-only HTML/CSS/JS prototypes; `d/` is the Research Atelier synthesis |
| `prototypes/shared/` | Aggregate-only data fixture and dependency-free SVG chart renderers |
| `compare/` | Contact sheets, the A/B/C gallery and the Direction D atelier gallery |

## Scientific data in the mockups

The prototypes use aggregate values only from the persisted real-data study
`STUDY-U-EE7514BB` and run `RUN-U-0001`:

- 21 athletes, 82 complete CMJ observations; 2 missing occasion-4 rows.
- Occasion means 38.53, 39.60, 41.12 and 41.40 cm.
- MixedLM random slope: +0.998 cm/occasion (95% CI 0.622–1.375).
- Occasion 1→4 change: +2.995 cm (95% CI 1.866–4.124).
- Single-arm observational design; occasions are not calendar weeks.

No participant-level records, names, free-text identifiers or private raw data
are included in these artifacts.

## Reproduction

See §12 of the audit document and the scripts in `scripts/`:

- `res588_ux_audit.py` — read-only production capture and layout measurement.
- `res588_ux_interactions.py` — click path, focus order and palette-scope audit.
- `res588_render_designs.py` — render the six A/B/C prototypes at both viewports.
- `res588_render_atelier.py` — render the four Direction D screens at both viewports.
- `res588_capture_gallery.py` — capture the A/B/C comparison gallery.
- `res588_capture_atelier_gallery.py` — capture the Direction D gallery.

The design prototypes are served as static files from the repository root:
`python -m http.server 4173 --bind 127.0.0.1`.
