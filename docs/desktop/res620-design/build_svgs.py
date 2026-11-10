"""Builds the frozen RES-620 design E SVG specification sheets.

Run from this folder:  python build_svgs.py
Tokens here are the single source; they match res620-prototypes/common.css (light)
and e-workbench/index.html (dark). Change a token here, then in the Qt theme.
"""
from pathlib import Path
from html import escape as esc

OUT = Path(__file__).parent
VERSION, DATE = "E 1.0", "2026-11-10"
SANS = "Segoe UI Variable Text, Segoe UI, sans-serif"
MONO = "Cascadia Mono, Consolas, monospace"
SERIF_NONE = None  # design E uses no serif

LIGHT = dict(desk="#E7E3DC", window="#F6F4F0", base="#FFFFFF", alt="#FAF8F5", chrome="#EFECE6", dock="#F2EFEA",
             line="#E2DDD4", line2="#CFC8BC", hover="#ECE8E1", text="#1B1D20", muted="#464B52", dim="#6D7178",
             faint="#A0A2A6", accent="#1F6B5A", accent_tint="#E3EFEB", obs="#2B2E33", mod="#2F59B0", hyp="#B7791F",
             real="#2B5F6E", synth="#7A4E9C", ok="#2E7D4F", warn="#A15C07", bad="#B42318")
DARK = dict(desk="#0B0C0E", window="#15171A", base="#1C1F23", alt="#191B1F", chrome="#121416", dock="#17191C",
            line="#2A2E33", line2="#383D44", hover="#24282D", text="#E7E4DE", muted="#C2BEB7", dim="#96928B",
            faint="#66635E", accent="#6DB39C", accent_tint="#1F2E29", obs="#D8D4CD", mod="#8DA9EA", hyp="#D9A55B",
            real="#7FB3C0", synth="#B79AD6", ok="#79C29A", warn="#D9A55B", bad="#E5867A")
QT = dict(desk="(outer frame)", window="QPalette.Window", base="QPalette.Base", alt="QPalette.AlternateBase",
          chrome="menu/status bars", dock="QDockWidget / options", line="borders", line2="control borders",
          hover="hover fill", text="WindowText · Text", muted="secondary text", dim="labels · axes", faint="hints · disabled",
          accent="Link · primary button", accent_tint="Highlight (selection)", obs="observed marks", mod="modeled marks",
          hyp="hypothetical marks", real="REAL provenance", synth="SYNTHETIC provenance", ok="qualified · up to date",
          warn="exploratory · stale", bad="missing · rejected · superseded")
T = LIGHT


def mix(hex_a, hex_b, t):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(a, b))


def txt(x, y, s, size=12.5, fill=None, weight=400, anchor="start", family=SANS, extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill or T["text"]}" text-anchor="{anchor}" {extra}>{esc(str(s))}</text>')


def rect(x, y, w, h, fill="none", stroke="none", r=0, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" {extra}/>'


DEFS = f'''<defs>
<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="#FFFFFF"/><line x1="0" y1="0" x2="0" y2="6" stroke="{mix(LIGHT['hyp'], '#FFFFFF', .35)}" stroke-width="2.4"/></pattern>
<pattern id="hatchd" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="{DARK['base']}"/><line x1="0" y1="0" x2="0" y2="6" stroke="{mix(DARK['hyp'], DARK['base'], .4)}" stroke-width="2.4"/></pattern>
<filter id="lift" x="-10%" y="-10%" width="120%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#3B3020" flood-opacity=".12"/></filter>
<filter id="shadow" x="-10%" y="-10%" width="120%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#3B3020" flood-opacity=".14"/></filter>
</defs>'''


def sheet(w, h, title, sub, body, bg=None):
    head = (rect(0, 0, w, h, bg or LIGHT["desk"]) + rect(0, 0, w, 86, LIGHT["text"])
            + txt(40, 40, "DynamisScience · Design E · Analysis Workbench", 13, "#C8C4BC", 600)
            + txt(40, 68, title, 22, "#FFFFFF", 600)
            + txt(w - 40, 40, f"FROZEN SPEC {VERSION} · {DATE}", 12, "#6DB39C", 700, "end")
            + txt(w - 40, 66, sub, 12, "#A9A49B", 400, "end"))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">{DEFS}{head}{body}</svg>')


# ---------------------------------------------------------------- chips
CHIPS = [("OBS", "obs", "fill"), ("MOD", "mod", "fill"), ("HYP", "hyp", "hatch"), ("REAL", "real", "outline"),
         ("SYNTHETIC", "synth", "outline"), ("QUALIFIED", "ok", "fill"), ("DESCRIPTIVE", "muted", "grey"),
         ("EXPLORATORY", "warn", "dash"), ("NOT QUALIFIED", "warn", "dash"), ("UNAVAILABLE", "faint", "dot"),
         ("SUPERSEDED", "bad", "strike"), ("FROZEN", "text", "outline"), ("DRAFT", "dim", "dashclear"),
         ("ILLUSTRATIVE DATA", "faint", "dot")]


def chip(x, y, label, key, style, P=None):
    P = P or T
    c = P[key]; w = 13 + len(label) * 6.6; h = 19; bg = P["base"]
    dark = P is DARK
    fillbg = {"fill": mix(c, bg, .14 if dark else .11), "grey": mix(c, bg, .12), "hatch": "url(#hatchd)" if dark else "url(#hatch)"}.get(style, bg if style != "dashclear" else "none")
    stroke = {"outline": mix(c, bg, .45), "dash": mix(c, bg, .45), "dot": P["line2"], "hatch": mix(c, bg, .5), "dashclear": P["line2"]}.get(style, "none")
    dash = {"dash": 'stroke-dasharray="3 2"', "dot": 'stroke-dasharray="1.5 2"', "dashclear": 'stroke-dasharray="3 2"'}.get(style, "")
    s = rect(x, y, w, h, fillbg, stroke, 9.5, dash)
    s += txt(x + w / 2, y + 13.5, label, 9.5, c, 700, "middle", extra='letter-spacing=".4"')
    if style == "strike":
        s += f'<line x1="{x + 6}" x2="{x + w - 6}" y1="{y + 10}" y2="{y + 10}" stroke="{c}" stroke-width="1"/>'
    return s, w


# ---------------------------------------------------------------- 01 tokens
def tokens():
    W, H = 1600, 1480
    b = ""
    groups = [("Surfaces", ["desk", "window", "base", "alt", "chrome", "dock", "line", "line2", "hover"]),
              ("Ink", ["text", "muted", "dim", "faint"]), ("Interaction", ["accent", "accent_tint"]),
              ("Kind of claim (never blended)", ["obs", "mod", "hyp"]), ("Provenance (separate axis)", ["real", "synth"]),
              ("Method / run status", ["ok", "warn", "bad"])]
    for col, (name, P, x0) in enumerate([("Light · Paper & Ink", LIGHT, 40), ("Dark · Warm graphite", DARK, 820)]):
        b += rect(x0 - 16, 110, 756, 760, P["window"], P["line"], 12)
        b += txt(x0, 142, name, 16, P["text"], 600)
        y = 168
        for g, keys in groups:
            b += txt(x0, y + 12, g.upper(), 10.5, P["dim"], 700, extra='letter-spacing=".6"')
            y += 22
            for i, k in enumerate(keys):
                cx = x0 + (i % 5) * 146; cy = y + (i // 5) * 74
                b += rect(cx, cy, 34, 34, P[k], P["line2"] if k in ("base", "window", "alt", "dock", "chrome") else "none", 7)
                if k == "hyp":
                    b += rect(cx, cy, 34, 34, "url(#hatchd)" if P is DARK else "url(#hatch)", "none", 7, 'opacity=".9"')
                b += txt(cx + 42, cy + 13, k.replace("_", "-"), 12, P["text"], 600)
                b += txt(cx + 42, cy + 29, P[k], 11, P["dim"], 400, family=MONO)
                b += txt(cx, cy + 50, QT[k], 9.8, P["faint"])
            y += 74 * ((len(keys) - 1) // 5 + 1) + 6
    # typography
    y0 = 900
    b += rect(24, y0, 1552, 450, LIGHT["base"], LIGHT["line"], 12)
    b += txt(40, y0 + 32, "TYPOGRAPHY", 10.5, LIGHT["dim"], 700, extra='letter-spacing=".6"')
    scale = [("Result title", 15.5, 600, SANS, "Linear Mixed Model"), ("Pane header", 12.5, 600, SANS, "Results"),
             ("Body · controls", 12.5, 400, SANS, "Dependent variable"), ("Table numbers", 12.5, 400, SANS, "0.998   0.622 – 1.375"),
             ("Caption · note", 11.5, 400, SANS, "Note. Wald intervals."), ("Section label", 11, 600, SANS, "ASSUMPTION CHECKS"),
             ("Chip", 9.5, 700, SANS, "QUALIFIED"), ("Syntax · data cells", 12, 400, MONO, 'smf.mixedlm("cmj_height ~ …")')]
    for i, (n, s, w, f, ex) in enumerate(scale):
        yy = y0 + 64 + i * 29
        b += txt(40, yy, n, 11.5, LIGHT["dim"]) + txt(220, yy, f"{s}px / {w}", 11.5, LIGHT["faint"], family=MONO)
        b += txt(360, yy, ex, s, LIGHT["text"], w, family=f)
    b += txt(820, y0 + 64, "Faces: Segoe UI Variable Text (UI), Cascadia Mono (syntax, data cells, digests).", 12, LIGHT["muted"])
    b += txt(820, y0 + 86, "Numbers: tabular figures in tables; right-aligned; minus sign is U+2212.", 12, LIGHT["muted"])
    b += txt(820, y0 + 108, "Qt: QFont('Segoe UI Variable Text', 9.5pt) at 96 DPI; never hard-code pixel heights.", 12, LIGHT["muted"])
    # spacing / radii / elevation
    b += txt(820, y0 + 150, "SPACING (px)", 10.5, LIGHT["dim"], 700, extra='letter-spacing=".6"')
    for i, v in enumerate([2, 4, 6, 8, 10, 12, 14, 16, 22]):
        b += rect(820 + i * 64, y0 + 166, v * 2, 14, LIGHT["accent"], r=2) + txt(820 + i * 64, y0 + 198, str(v), 11, LIGHT["dim"], family=MONO)
    b += txt(820, y0 + 232, "RADII", 10.5, LIGHT["dim"], 700, extra='letter-spacing=".6"')
    for i, (v, n) in enumerate([(4, "kbd"), (6, "controls"), (8, "slots · plots"), (10, "panes · blocks"), (999, "chips")]):
        b += rect(820 + i * 140, y0 + 244, 44, 30, LIGHT["alt"], LIGHT["line2"], min(v, 15)) + txt(872 + i * 140, y0 + 264, f"{v if v < 999 else 'pill'} {n}", 11, LIGHT["dim"])
    b += txt(40, y0 + 330, "ELEVATION", 10.5, LIGHT["dim"], 700, extra='letter-spacing=".6"')
    b += rect(40, y0 + 344, 220, 70, LIGHT["base"], LIGHT["line"], 10, 'filter="url(#lift)"') + txt(56, y0 + 384, "lift · result blocks, ribbon hover", 11.5, LIGHT["muted"])
    b += rect(290, y0 + 344, 220, 70, LIGHT["window"], LIGHT["line"], 10, 'filter="url(#shadow)"') + txt(306, y0 + 384, "shadow · panes on the desk", 11.5, LIGHT["muted"])
    b += txt(560, y0 + 372, "Qt: QGraphicsDropShadowEffect only on the three panes and overlays (palette, toast).", 12, LIGHT["muted"])
    b += txt(560, y0 + 394, "Everything else uses 1 px borders. No gradients except the 3D stage background.", 12, LIGHT["muted"])
    return sheet(W, H, "01 · Tokens", "Colour, type, spacing, radii, elevation", b)


# ---------------------------------------------------------------- 02 components
def components():
    W, H = 1600, 1500
    P = LIGHT; b = ""

    def card(x, y, w, h, title):
        return rect(x, y, w, h, P["base"], P["line"], 12) + txt(x + 18, y + 30, title.upper(), 10.5, P["dim"], 700, extra='letter-spacing=".6"')
    # chips light + dark
    b += card(24, 110, 1552, 200, "Chips: four separate axes")
    axes = [("Kind of claim", CHIPS[0:3]), ("Provenance", CHIPS[3:5]), ("Method status", CHIPS[5:11]), ("Record state", CHIPS[11:14])]
    x = 44
    for n, cs in axes:
        b += txt(x, 160, n, 11.5, P["muted"], 600)
        yy = 172; xx = x
        for lab, k, st in cs:
            s, w = chip(xx, yy, lab, k, st); b += s; xx += w + 8
            if xx > x + 330: xx = x; yy += 28
        x += 380
    b += rect(24, 236, 1552, 74, DARK["base"], "none", 0)
    xx = 44
    for lab, k, st in CHIPS:
        s, w = chip(xx, 262, lab, k, st, DARK); b += s; xx += w + 8
    b += txt(1556, 300, "dark", 10.5, DARK["faint"], anchor="end")
    # buttons and controls
    b += card(24, 330, 760, 300, "Buttons and controls")
    b += rect(44, 372, 110, 32, P["accent"], r=6) + txt(99, 393, "Add to report", 12.5, "#fff", 600, "middle")
    b += rect(166, 372, 96, 32, P["base"], P["line2"], 6) + txt(214, 393, "Export…", 12.5, P["text"], 400, "middle")
    b += rect(274, 372, 96, 32, P["hover"], r=6) + txt(322, 393, "Outline ▾", 12.5, P["text"], 400, "middle") + txt(322, 420, "hover", 10.5, P["faint"], anchor="middle")
    b += rect(382, 372, 150, 32, P["accent"], r=6) + txt(457, 393, "▶ Run · Ctrl ↵", 12.5, "#fff", 600, "middle")
    for i, (lab, st) in enumerate([("Mixed Models", "default"), ("Mixed Models", "hover"), ("Mixed Models", "selected")]):
        x0 = 44 + i * 120
        if st != "default":
            b += rect(x0, 440, 108, 56, P["base"], P["line2"] if st == "selected" else "none", 8, 'filter="url(#lift)"')
        b += f'<path d="M{x0 + 44} 466 L{x0 + 64} 458 M{x0 + 44} 462 L{x0 + 64} 454 M{x0 + 44} 470 L{x0 + 64} 462" stroke="{P["accent"] if st == "selected" else P["muted"]}" stroke-width="1.6"/>'
        b += txt(x0 + 54, 488, lab, 11.5, P["text"] if st != "default" else P["muted"], 400, "middle") + txt(x0 + 54, 512, st, 10.5, P["faint"], anchor="middle")
    b += rect(420, 446, 172, 28, P["alt"], P["line2"], 7) + rect(423, 449, 62, 22, P["base"], r=5, extra='filter="url(#lift)"')
    for i, s in enumerate(["By athlete", "Variables", "Rows"]):
        b += txt(454 + i * 56, 464, s, 10.5, P["text"] if i == 0 else P["dim"], 400, "middle")
    b += txt(420, 494, "segmented control", 10.5, P["faint"])
    for i, (st, on, dis) in enumerate([("on", 1, 0), ("off", 0, 0), ("disabled", 0, 1)]):
        y = 540 + i * 26
        b += rect(44, y, 15, 15, P["accent"] if on else P["base"], P["accent"] if on else P["line2"], 4, 'opacity=".55"' if dis else "")
        if on: b += txt(51.5, y + 11.5, "✓", 10, "#fff", 700, "middle")
        b += txt(68, y + 12, {"on": "Residuals vs fitted", "off": "Random-effect distribution", "disabled": "Influence (Cook's distance)"}[st], 12.5, P["faint"] if dis else P["text"])
        if dis: s, _ = chip(260, y - 2, "N/A", "faint", "dot"); b += s
    b += rect(420, 540, 200, 30, P["base"], P["line2"], 8) + txt(436, 559, "Search commands…", 12, P["faint"]) + rect(570, 547, 40, 16, P["base"], P["line2"], 4) + txt(590, 559, "Ctrl K", 9.5, P["dim"], anchor="middle", family=MONO)
    for i, (lab, c) in enumerate([("Results up to date", "ok"), ("Specification changed", "warn"), ("Running in worker…", "mod")]):
        b += rect(600, 372 + i * 40, 168, 28, P["base"], P["line"], 14) + f'<circle cx="616" cy="{386 + i * 40}" r="4" fill="{P[c]}"/>' + txt(628, 390 + i * 40, lab, 11.5, P["dim"])
    # role slots
    b += card(800, 330, 776, 300, "Variable assignment")
    for i, (t, l) in enumerate([("id", "ID"), ("o", "O"), ("n", "N"), ("c", "C")]):
        col = {"id": "#9A8F80", "o": "#8B6FB3", "n": "#2F7DA0", "c": "#6D7178"}[t]
        b += rect(820 + i * 120, 372, 14, 14, col, r=3) + txt(827 + i * 120, 382.5, l, 8.5, "#fff", 700, "middle") + txt(840 + i * 120, 384, {"id": "identifier", "o": "ordinal", "n": "numeric", "c": "nominal"}[t], 11.5, P["dim"])
    states = [("empty", P["line2"], "none", "Drop a variable", 'stroke-dasharray="4 3"'), ("filled", P["line2"], P["base"], None, ""),
              ("drag over", P["accent"], P["accent_tint"], None, ""), ("rejected", P["bad"], P["base"], None, "")]
    for i, (n, sc, fl, ph, d) in enumerate(states):
        x0 = 820 + (i % 2) * 380; y0 = 410 + (i // 2) * 96
        b += txt(x0, y0 + 10, n, 11, P["dim"], 600)
        if n == "drag over": b += rect(x0 - 3, y0 + 17, 346, 42, "none", mix(P["accent"], P["base"], .3), 10, 'stroke-width="3"')
        b += rect(x0, y0 + 20, 340, 36, fl if fl != "none" else P["alt"], sc, 8, d)
        if ph: b += txt(x0 + 12, y0 + 43, ph, 11, P["faint"])
        else:
            b += rect(x0 + 4, y0 + 24, 332, 28, P["alt"], r=6, extra='filter="url(#lift)"') + rect(x0 + 12, y0 + 31, 14, 14, "#2F7DA0", r=3) + txt(x0 + 19, y0 + 41.5, "N", 8.5, "#fff", 700, "middle")
            b += txt(x0 + 32, y0 + 43, "cmj_height", 12.5, P["text"]) + txt(x0 + 104, y0 + 43, "cm", 11, P["faint"]) + txt(x0 + 322, y0 + 43, "✕", 11, P["faint"], anchor="middle")
        if n == "rejected": b += txt(x0, y0 + 74, "Toast: “athlete_id is identifier. Outcome needs 1 numeric.” + 300 ms shake", 10.5, P["bad"])
    # data grid
    b += card(24, 650, 760, 300, "Data grid · by athlete")
    cols = [("Athlete", 60, "start"), ("Pre", 140, "end"), ("Post 0", 210, "end"), ("Post 10m", 300, "end"), ("Post 24h", 390, "end"), ("Δ 24 h", 460, "end"), ("Trend", 490, "start"), ("Sprint", 640, "end")]
    b += rect(44, 690, 720, 46, P["alt"]) + "".join(txt(x + 2, 712, n, 12, P["text"], 600, a) for n, x, a in cols)
    b += "".join(txt(x + 2, 728, u, 10, P["faint"], 400, a, family=MONO) for (n, x, a), u in zip(cols, ["", "cm", "cm", "cm", "cm", "cm", "", "s · Pre"]))
    data = [("A04", "28.4", "30.1", "32.6", "32.3", "+3.9", [28.4, 30.1, 32.6, 32.3], "2.96"), ("A05", "28.0", "27.6", None, "33.3", "+5.3", [28.0, 27.6, None, 33.3], "2.96"), ("A06", "34.5", "34.2", "33.0", "34.7", "+0.2", [34.5, 34.2, 33.0, 34.7], "3.13")]
    for r, row in enumerate(data):
        y = 760 + r * 36
        if r == 1: b += rect(44, y - 18, 720, 36, P["hover"])
        b += f'<line x1="44" x2="764" y1="{y + 18}" y2="{y + 18}" stroke="{P["line"]}"/>'
        b += txt(62, y + 5, row[0], 12.5, P["text"], 700)
        for v, (n, x, a) in zip(row[1:5], cols[1:5]):
            b += txt(x + 2, y + 5, v, 12.5, P["text"], 400, "end", MONO) if v else txt(x + 2, y + 5, "—", 12.5, P["bad"], 400, "end")
        b += txt(462, y + 5, row[5], 12.5, P["ok"], 400, "end", MONO)
        vals = row[6]; lo, hi = 27, 35
        pts = [(492 + i * 14, y + 8 - (v - lo) / (hi - lo) * 14) for i, v in enumerate(vals) if v is not None]
        b += f'<polyline points="{" ".join(f"{a},{c}" for a, c in pts)}" fill="none" stroke="{P["mod"]}" stroke-width="1.4"/>' + "".join(f'<circle cx="{a}" cy="{c}" r="1.8" fill="{P["obs"]}"/>' for a, c in pts)
        if None in vals: b += f'<circle cx="{492 + 2 * 14}" cy="{y + 1}" r="2.4" fill="none" stroke="{P["bad"]}" stroke-dasharray="1.5 1.5"/>'
        b += txt(642, y + 5, row[7], 12.5, P["text"], 400, "end", MONO)
    b += txt(44, 912, "Missing value: red em dash, red dashed ring in the sparkline. Change: green if positive, red if negative.", 11, P["dim"])
    b += txt(44, 930, "Qt: QSortFilterProxyModel pivot (long → wide); QStyledItemDelegate for sparklines; header click selects the variable.", 11, P["dim"])
    # result block + table + stale bar
    b += card(800, 650, 776, 300, "Result block")
    b += rect(820, 690, 736, 240, P["base"], P["line"], 10, 'filter="url(#lift)"')
    b += txt(840, 718, "Linear Mixed Model", 15.5, P["text"], 600)
    s, w = chip(992, 704, "MOD", "mod", "fill"); b += s
    s, w2 = chip(992 + w + 6, 704, "REAL", "real", "outline"); b += s
    b += txt(840, 740, "cmj_height ~ occasion_index + (1 | athlete_id)", 12, P["dim"], family=MONO)
    b += f'<line x1="840" x2="1300" y1="758" y2="758" stroke="{P["text"]}" stroke-width="1.5"/><line x1="840" x2="1300" y1="782" y2="782" stroke="{P["text"]}"/><line x1="840" x2="1300" y1="808" y2="808" stroke="{P["text"]}" stroke-width="1.5"/>'
    for (n, x) in [("Term", 848), ("Estimate", 990), ("SE", 1050), ("95% CI", 1170), ("z", 1220), ("p", 1290)]:
        b += txt(x, 775, n, 11.5, P["text"], 600, "start" if n == "Term" else "end")
    for v, x, c in [("occasion_index", 848, P["text"]), ("0.998", 990, P["mod"]), ("0.192", 1050, P["text"]), ("0.622 – 1.375", 1170, P["text"]), ("5.20", 1220, P["text"]), ("< .001", 1290, P["text"])]:
        b += txt(x, 800, v, 12.5, c, 600 if c == P["mod"] else 400, "start" if x == 848 else "end")
    b += txt(840, 830, "Note. Wald intervals. SE and z derived from the reported interval.", 11.5, P["dim"], extra='font-style="italic"')
    b += f'<line x1="840" x2="1536" y1="852" y2="852" stroke="{P["line"]}" stroke-dasharray="4 3"/>'
    s, w = chip(840, 862, "QUALIFIED", "ok", "fill"); b += s
    b += txt(840 + w + 8, 876, "RUN-REAL-0005 · digest 519fe130 · reproduced", 11, P["faint"]) + txt(1536, 876, "Promote to evidence", 11, P["accent"], 600, "end")
    b += txt(840, 912, "Every block: title + claim-kind chip + provenance chip, a note that states limits, and a provenance footer.", 11, P["dim"])
    # overlays
    b += card(24, 970, 1552, 230, "Overlays and feedback")
    b += rect(44, 1012, 560, 40, mix(P["warn"], P["base"], .14), mix(P["warn"], P["base"], .35)) + txt(60, 1037, "⚠  Specification changed. Results are for the previous spec.", 12, P["text"])
    b += rect(474, 1018, 120, 28, P["accent"], r=6) + txt(534, 1037, "▶ Run · Ctrl ↵", 12, "#fff", 600, "middle")
    b += txt(44, 1072, "Stale bar: sticky at the top of Results; dependent blocks drop to 45 % opacity + 60 % greyscale.", 11, P["dim"])
    b += rect(44, 1090, 330, 34, P["text"], r=8) + txt(60, 1112, "Syntax copied", 12, P["window"])
    b += txt(44, 1144, "Toast: bottom centre, 2.2 s, no actions.", 11, P["dim"])
    b += rect(620, 1006, 560, 176, P["base"], P["line2"], 12, 'filter="url(#shadow)"') + txt(640, 1036, "assign", 15, P["text"])
    b += f'<line x1="620" x2="1180" y1="1050" y2="1050" stroke="{P["line"]}"/>'
    for i, (t, g) in enumerate([("Assign cmj_height as dependent", "Variable"), ("Assign sprint_20m as dependent", "Variable"), ("Add occasion as factor", "Variable")]):
        if i == 0: b += rect(628, 1056 + i * 34, 544, 30, P["accent_tint"], r=7)
        b += txt(642, 1076 + i * 34, t, 12.5, P["text"]) + txt(1160, 1076 + i * 34, g, 11, P["faint"], anchor="end")
    b += txt(1200, 1036, "Command palette (Ctrl K)", 12, P["text"], 600)
    b += txt(1200, 1058, "Only valid actions are offered:", 11.5, P["dim"]) + txt(1200, 1076, "identifiers never appear as outcomes.", 11.5, P["dim"])
    b += txt(1200, 1098, "↑ ↓ move · ↵ run · Esc close", 11.5, P["dim"], family=MONO)
    b += txt(1200, 1120, "Qt: frameless QDialog + QLineEdit", 11.5, P["dim"]) + txt(1200, 1138, "+ filtered QListView.", 11.5, P["dim"])
    # claim marks in plots
    b += card(24, 1220, 1552, 250, "Marks in figures")
    b += f'<circle cx="70" cy="1300" r="3.5" fill="{P["obs"]}"/><circle cx="84" cy="1292" r="3.5" fill="{P["obs"]}"/><circle cx="98" cy="1306" r="3.5" fill="{P["obs"]}"/>' + txt(120, 1304, "Observed: solid graphite dots, 55–75 % opacity when dense", 12, P["text"])
    b += f'<polygon points="60,1360 160,1340 160,1366 60,1384" fill="{mix(P["mod"], P["base"], .14)}"/><line x1="60" y1="1372" x2="160" y2="1353" stroke="{P["mod"]}" stroke-width="2.2"/>' + txt(180, 1366, "Modeled: cobalt line with its interval band, always together", 12, P["text"])
    b += f'<polygon points="60,1430 160,1406 160,1432 60,1450" fill="url(#hatch)" stroke="{P["hyp"]}" stroke-dasharray="4 3"/><line x1="60" y1="1440" x2="160" y2="1419" stroke="{P["hyp"]}" stroke-width="2.2" stroke-dasharray="6 4"/>' + txt(180, 1434, "Hypothetical: hatched ochre band + dashed line, labelled HYPOTHETICAL (locked until RES-590)", 12, P["text"])
    b += txt(820, 1304, "Missing: red dashed ring at the expected position.", 12, P["text"])
    b += txt(820, 1330, "Exploratory diagnostics keep their exact RES-619 names (e.g. “marginal residual / conditional SD”).", 12, P["text"])
    b += txt(820, 1356, "Axes: dim labels, unit in the axis title, gridlines in --line, no chart borders.", 12, P["text"])
    b += txt(820, 1382, "Native: Matplotlib for exported figures (same tokens), pyqtgraph for interactive views,", 12, P["text"])
    b += txt(820, 1402, "pyqtgraph.opengl (GLViewWidget) for the 3D trajectories.", 12, P["text"])
    return sheet(W, H, "02 · Components", "Chips · controls · assignment · grid · results · overlays · figure marks", b)


# ---------------------------------------------------------------- 03 layout
def layout():
    W, H = 1600, 1180
    P = LIGHT; ox, oy = 80, 140; b = ""
    b += rect(ox, oy, 1440, 900, P["desk"], P["line2"], 10, 'filter="url(#shadow)"')
    bands = [("Title bar", 0, 34, P["chrome"]), ("Menu bar", 34, 26, P["chrome"]), ("Ribbon · analyses", 60, 66, P["window"])]
    for n, y, h, c in bands:
        b += rect(ox, oy + y, 1440, h, c, P["line"]) + txt(ox + 12, oy + y + h / 2 + 4, f"{n} · {h}px", 11.5, P["dim"], 600)
    y0 = oy + 126; ph = 900 - 126 - 26
    c1 = (1440 - 16 - 16 - 320) * 1.12 / 2.27; c3 = (1440 - 16 - 16 - 320) * 1.15 / 2.27
    xs = [ox + 8, ox + 8 + c1 + 8, ox + 8 + c1 + 8 + 320 + 8]
    ws = [c1, 320, c3]
    names = ["DATA\nBy athlete · Variables · Rows", "OPTIONS\nassignment · sections", "RESULTS\nblocks · syntax bar"]
    for x, w, n in zip(xs, ws, names):
        b += rect(x, y0 + 8, w, ph - 16, P["window"], P["line"], 10, 'filter="url(#lift)"')
        b += rect(x, y0 + 8, w, 42, P["base"], P["line"], 10) + txt(x + 12, y0 + 34, "Pane header · 42px", 11, P["dim"])
        t1, t2 = n.split("\n"); b += txt(x + w / 2, y0 + ph / 2, t1, 16, P["text"], 700, "middle") + txt(x + w / 2, y0 + ph / 2 + 22, t2, 12, P["dim"], 400, "middle")
        b += txt(x + w / 2, y0 + ph - 30, f"{round(w)} px", 12, P["accent"], 700, "middle", MONO)
    b += rect(xs[2], y0 + ph - 8 - 44, c3, 44, P["chrome"], P["line"]) + txt(xs[2] + 12, y0 + ph - 25, "Syntax bar · Python equivalent · Copy", 11, P["dim"])
    for x in (xs[1] - 8, xs[2] - 8):
        b += rect(x + 2.5, y0 + ph / 2 - 17, 3, 34, P["line2"], r=2)
    b += rect(ox, oy + 874, 1440, 26, P["chrome"], P["line"]) + txt(ox + 12, oy + 891, "Status bar · 26px · data root · provenance · counts · SQLite", 11, P["dim"])
    # dims
    b += txt(ox + 720, oy - 14, "1440 × 900 reference (100 %)", 13, P["text"], 600, "middle")
    b += txt(xs[1] + 160, y0 + 90, "fixed 320 px (min 260)", 11.5, P["muted"], 400, "middle")
    b += txt(xs[0] + c1 / 2, y0 + 90, "1.12 fr (min 300)", 11.5, P["muted"], 400, "middle")
    b += txt(xs[2] + c3 / 2, y0 + 90, "1.15 fr (min 420)", 11.5, P["muted"], 400, "middle")
    b += txt(xs[1] - 4, y0 + ph / 2 + 40, "8 px splitter", 10.5, P["faint"], 400, "middle", extra=f'transform="rotate(-90 {xs[1] - 4} {y0 + ph / 2 + 40})"')
    notes = ["QMainWindow → central QSplitter(3) with saved state (QSettings). Panes are QFrames with 10 px radius on the desk colour.",
             "1366 × 768 at 100 %: options 300 px; data and results share the rest; ribbon keeps labels (9 × 62 px). Verify in Qt.",
             "1366 × 768 at 150 % (≈ 910 × 512 logical): options becomes a drawer (Ctrl 2), data defaults to Variables, results take the width. Verify in Qt.",
             "Keyboard: Ctrl 1/2/3 focus Data/Options/Results · Ctrl K palette · Ctrl ↵ run · F6 cycles panes. Every control has an accessible name."]
    for i, n in enumerate(notes):
        b += txt(80, 1078 + i * 22, n, 12, P["muted"])
    return sheet(W, H, "03 · Layout anatomy", "Window regions, sizes, responsive and keyboard rules", b)


# ---------------------------------------------------------------- 04 annotated main screen
def annotated():
    W, H = 2000, 1140
    P = LIGHT; ox, oy = 40, 120
    b = rect(ox - 1, oy - 1, 1442, 902, "none", P["line2"]) + f'<image x="{ox}" y="{oy}" width="1440" height="900" href="screens/E4-mixed-model-light.svg" xlink:href="screens/E4-mixed-model-light.svg" preserveAspectRatio="xMidYMid slice"/>'
    pins = [(360, 133, "Ribbon of analyses, grouped like JASP/jamovi. Selected = raised card + accent icon."),
            (1073, 134, "Command palette (Ctrl K): analyses, valid assignments, data views, theme, run."),
            (1249, 134, "Run state pill: up to date · specification changed (pulsing) · running."),
            (382, 196, "Data views: By athlete (default) · Variables · Rows."),
            (382, 238, "Δ column and per-athlete sparkline: the sports reading of the data."),
            (274, 405, "Missing jump: red dash, never blank, never imputed."),
            (634, 324, "Variable list: type icon, • when used. Drag, click-then-click, or double-click."),
            (792, 279, "Role slots enforce type rules; rejects explain why."),
            (648, 648, "Options as collapsible sections; checks keep RES-619 labels."),
            (972, 264, "Every result says what kind of claim it is and where the data came from."),
            (1116, 461, "Publication-style table; estimate in the modeled colour."),
            (1138, 497, "Note states the limits of the estimate (Wald, clusters, open review)."),
            (1080, 544, "Provenance footer: method status, run, digest, reproduction."),
            (1325, 544, "Promote to evidence: qualified runs only."),
            (1138, 828, "Syntax bar: exact Python equivalent of the GUI state."),
            (547, 504, "8 px splitters; pane sizes persist.")]
    for i, (x, y, t) in enumerate(pins, 1):
        cx, cy = ox + x, oy + y
        bx, by = cx - 22, cy - 22
        b += (f'<line x1="{bx}" y1="{by}" x2="{cx}" y2="{cy}" stroke="{P["accent"]}" stroke-width="1.6"/><circle cx="{cx}" cy="{cy}" r="3.5" fill="{P["accent"]}" stroke="#fff" stroke-width="1.5"/>'
              f'<circle cx="{bx}" cy="{by}" r="11" fill="{P["accent"]}" stroke="#fff" stroke-width="2"/>' + txt(bx, by + 4.5, i, 11, "#fff", 700, "middle"))
        ly = oy + 8 + (i - 1) * 55
        b += f'<circle cx="1514" cy="{ly + 8}" r="12" fill="{P["accent"]}"/>' + txt(1514, ly + 12.5, i, 11.5, "#fff", 700, "middle")
        words, line, lines = t.split(), "", []
        for w in words:
            if len(line) + len(w) > 52: lines.append(line); line = w
            else: line = (line + " " + w).strip()
        lines.append(line)
        for k, l in enumerate(lines): b += txt(1536, ly + 13 + k * 17, l, 12.5, P["text"])
    return sheet(W, H, "04 · Main screen, annotated", "Mixed model · light · 1440 × 900", b)


# ---------------------------------------------------------------- 05 screen index
def screens():
    shots = [("E4-mixed-model-light", "Mixed model (recorded run)", "QUALIFIED · light"), ("E5-3d-dark", "3D trajectories", "drag · zoom · hover · presets"),
             ("E6-stale-light", "Specification changed", "stale results + live syntax"), ("E7-palette-dark", "Command palette", "valid actions only"),
             ("E8-descriptives-light", "Descriptives", "DESCRIPTIVE · box plot"), ("E9-ttest-dark", "Paired T-Test", "NOT QUALIFIED · line per athlete"),
             ("E10-anova-light", "Repeated-measures ANOVA", "NOT QUALIFIED · Holm post hoc"), ("E11-regression-light", "Linear regression + Variables view", "NOT QUALIFIED · CI band"),
             ("E12-athlete-change-dark", "Athlete change", "OBSERVED · practitioner threshold"), ("E13-reliability-light", "Reliability (recorded run)", "QUALIFIED · MoveSmart")]
    W = 1600; tw, th = 740, 462; H = 120 + 5 * (th + 70) + 20
    b = ""
    for i, (f, t, s) in enumerate(shots):
        x = 40 + (i % 2) * (tw + 40); y = 120 + (i // 2) * (th + 70)
        b += rect(x - 1, y - 1, tw + 2, th + 2, LIGHT["base"], LIGHT["line2"], 6, 'filter="url(#lift)"')
        b += f'<image x="{x}" y="{y}" width="{tw}" height="{th}" href="screens/{f}.svg" xlink:href="screens/{f}.svg" preserveAspectRatio="xMidYMid slice"/>'
        b += txt(x, y + th + 26, t, 15, LIGHT["text"], 600) + txt(x + tw, y + th + 26, s, 12, LIGHT["dim"], 400, "end") + txt(x, y + th + 46, "screens/" + f + ".svg", 11, LIGHT["faint"], family=MONO)
    return sheet(W, H, "05 · Screen index", "All frozen screens · vector SVG · 1440 × 900", b)


# ---------------------------------------------------------------- 06 interaction
def flows():
    W, H = 1600, 1060
    P = LIGHT; b = ""

    def box(x, y, w, h, t, s, c=None):
        return (rect(x, y, w, h, P["base"], c or P["line2"], 10, 'filter="url(#lift)"') + txt(x + 16, y + 28, t, 14, P["text"], 600)
                + "".join(txt(x + 16, y + 50 + i * 18, l, 11.5, P["dim"]) for i, l in enumerate(s)))

    def arrow(x1, y1, x2, y2, label="", c=None):
        c = c or P["dim"]; s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="1.6" marker-end="url(#ah)"/>'
        return s + (txt((x1 + x2) / 2 + 6, (y1 + y2) / 2 - 6, label, 11, c, 600) if label else "")
    b += f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="{P["dim"]}"/></marker></defs>'
    b += box(40, 130, 250, 110, "1 · Choose analysis", ["Ribbon button or Ctrl K.", "Data pane switches to the", "analysis's dataset."])
    b += box(340, 130, 270, 110, "2 · Assign variables", ["Drag · click then click ·", "double-click (auto by type).", "✕ or drag back to remove."])
    b += box(340, 300, 270, 92, "Rejected", ["Box shakes 300 ms; toast says", "the type and the rule."], P["bad"])
    b += box(670, 130, 280, 110, "3a · Live result", ["Descriptive and not-qualified", "analyses recompute instantly.", "Blocks tagged by status."])
    b += box(670, 300, 280, 110, "3b · Specification changed", ["Qualified methods: stale bar,", "dimmed blocks, live syntax.", "Ctrl ↵ or ▶ Run."], P["warn"])
    b += box(1010, 300, 250, 110, "Worker run", ["TaskRunner sends the spec to", "the qualified worker; pill", "shows “Running in worker…”."], P["mod"])
    b += box(1310, 220, 250, 92, "Recorded / new result", ["Blocks restored, pill green,", "digest in the footer."], P["ok"])
    b += box(1310, 360, 250, 92, "No result", ["Prototype only: “No recorded", "run”. Restore specification."])
    b += box(1010, 130, 250, 110, "4 · Review checks", ["Toggle assumption checks;", "exploratory ones keep their", "exact RES-619 labels."])
    b += box(1010, 470, 250, 110, "5 · Promote to evidence", ["Qualified runs only.", "Not-qualified methods show", "promotion disabled."])
    b += box(1310, 520, 250, 92, "6 · Add to report", ["Selected blocks go to the", "versioned report."])
    b += arrow(290, 185, 340, 185) + arrow(475, 240, 475, 300, "invalid", P["bad"]) + arrow(610, 185, 670, 185, "valid")
    b += arrow(610, 215, 670, 340, "qualified") + arrow(950, 355, 1010, 355, "Run") + arrow(1260, 340, 1310, 280) + arrow(1260, 380, 1310, 400)
    b += arrow(950, 185, 1010, 185) + arrow(1135, 240, 1135, 300, "") + arrow(1135, 410, 1135, 470) + arrow(1260, 525, 1310, 560)
    # keyboard + 3D + states
    b += rect(40, 640, 740, 380, P["base"], P["line"], 12) + txt(60, 672, "KEYBOARD", 10.5, P["dim"], 700, extra='letter-spacing=".6"')
    keys = [("Ctrl K", "Command palette"), ("Ctrl ↵", "Run the current specification"), ("Esc", "Close palette, popover or drawer"), ("↑ ↓ ↵", "Move and choose in lists and the palette"),
            ("Ctrl 1 · 2 · 3", "Focus Data · Options · Results"), ("F6", "Cycle panes"), ("Space", "Toggle the focused checkbox"), ("Delete", "Remove the focused variable from its box"),
            ("Ctrl C (results)", "Copy the focused table as TSV"), ("Ctrl Shift L", "Toggle light / dark")]
    for i, (k, d) in enumerate(keys):
        b += rect(60, 690 + i * 31, 120, 22, P["alt"], P["line2"], 5) + txt(120, 705 + i * 31, k, 11, P["text"], 600, "middle", MONO) + txt(196, 706 + i * 31, d, 12, P["text"])
    b += rect(820, 640, 740, 380, P["base"], P["line"], 12) + txt(840, 672, "3D TRAJECTORIES · STATES", 10.5, P["dim"], 700, extra='letter-spacing=".6"')
    lines = ["Drag: rotate (yaw, pitch clamped −0.1 … 1.35 rad). Wheel: zoom 0.6–2.2×.", "Presets: Front · Side · 3D, eased over ~250 ms.", "Hover: nearest point within 10 px → “A07 · Post 10m · 36.2 cm (observed)”.",
             "Layers: Observed · Model surface · Athlete lines (toggle chips).", "Axes: occasion · athlete (by baseline) · outcome with unit.", "Native: pyqtgraph.opengl GLViewWidget + GLScatterPlotItem + GLMeshItem.", "",
             "RUN STATE", "up to date (green) → changed (amber, pulsing) → running (blue) → up to date", "", "EMPTY / ERROR STATES", "Waiting for variables: names the boxes still needed.",
             "Too few rows · collinear covariates · identical levels: plain sentence, no stack trace.", "Unavailable option: disabled with N/A chip and a tooltip reason."]
    for i, l in enumerate(lines):
        b += txt(840, 700 + i * 22, l, 10.5 if l.isupper() else 12, P["dim"] if l.isupper() else P["text"], 700 if l.isupper() else 400)
    return sheet(W, H, "06 · Interaction flows and states", "Assignment · validation · stale / run · promotion · keyboard · 3D", b)


if __name__ == "__main__":
    for name, fn in [("01-tokens", tokens), ("02-components", components), ("03-layout", layout), ("04-main-annotated", annotated),
                     ("05-screens", screens), ("06-interactions", flows)]:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
        print("wrote", name)
