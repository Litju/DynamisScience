"""Design E "Analysis Workbench" tokens, palettes and the one generated stylesheet.

Light "Paper & Ink" and dark "Warm graphite" tokens are copied from the frozen
specification (docs/desktop/res620-design/build_svgs.py). Marks and borders use the
frozen tokens as-is; text that sits on a surface uses the ``*_text`` variants, which are
the same hues moved toward the ink colour only as far as WCAG AA (4.5:1) requires.
"""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QWidget

SANS = "Segoe UI Variable Text"
MONO = "Cascadia Mono"
SPACING = (2, 4, 6, 8, 10, 12, 14, 16, 22)
RADII = {"kbd": 4, "control": 6, "slot": 8, "pane": 10, "chip": 9}

LIGHT = dict(desk="#E7E3DC", window="#F6F4F0", base="#FFFFFF", alt="#FAF8F5", chrome="#EFECE6", dock="#F2EFEA",
             line="#E2DDD4", line2="#CFC8BC", hover="#ECE8E1", text="#1B1D20", muted="#464B52", dim="#6D7178",
             faint="#A0A2A6", accent="#1F6B5A", accent_tint="#E3EFEB", obs="#2B2E33", mod="#2F59B0", hyp="#B7791F",
             real="#2B5F6E", synth="#7A4E9C", ok="#2E7D4F", warn="#A15C07", bad="#B42318")
DARK = dict(desk="#0B0C0E", window="#15171A", base="#1C1F23", alt="#191B1F", chrome="#121416", dock="#17191C",
            line="#2A2E33", line2="#383D44", hover="#24282D", text="#E7E4DE", muted="#C2BEB7", dim="#96928B",
            faint="#66635E", accent="#6DB39C", accent_tint="#1F2E29", obs="#D8D4CD", mod="#8DA9EA", hyp="#D9A55B",
            real="#7FB3C0", synth="#B79AD6", ok="#79C29A", warn="#D9A55B", bad="#E5867A")

# Surfaces that carry text in the workbench (the desk itself never carries text).
TEXT_SURFACES = ("window", "base", "alt", "chrome", "dock", "hover", "accent_tint")
HUES = ("accent", "obs", "mod", "hyp", "real", "synth", "ok", "warn", "bad", "muted")

# Chips: four separate axes, never blended (spec rule 1 and 2).
CHIP_AXES = {
    "claim": ("obs", "mod", "hyp"),
    "provenance": ("real", "synthetic"),
    "method": ("qualified", "conditional", "descriptive", "exploratory", "not_qualified", "review",
               "unavailable", "superseded"),
    "record": ("frozen", "draft", "illustrative"),
}
# kind -> (hue token, style)
_CHIP_STYLE = {
    "obs": ("obs", "fill"), "mod": ("mod", "fill"), "hyp": ("hyp", "hatch"),
    "real": ("real", "outline"), "synthetic": ("synth", "outline"),
    "qualified": ("ok", "fill"), "conditional": ("ok", "fill"), "descriptive": ("muted", "fill"),
    "exploratory": ("warn", "dash"), "not_qualified": ("warn", "dash"), "review": ("warn", "dash"),
    "unavailable": ("dim", "dot"), "superseded": ("bad", "strike"),
    "frozen": ("text", "outline"), "draft": ("dim", "dashclear"), "illustrative": ("dim", "dot"),
}

_current = "light"


def mix(a: str, b: str, t: float) -> str:
    """Blend ``t`` of colour ``a`` into ``b`` (same formula as build_svgs.mix)."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(ca, cb))


def contrast_ratio(a: str, b: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, bl = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def ensure_contrast(colour: str, backgrounds: list[str], toward: str, target: float = 4.5) -> str:
    step = 0.0
    result = colour
    while min(contrast_ratio(result, bg) for bg in backgrounds) < target and step < 1:
        step += 0.02
        result = mix(toward, colour, step)
    return result


def _derive(frozen: dict[str, str], dark: bool) -> dict[str, str]:
    t = dict(frozen)
    t["dark"] = "1" if dark else ""
    t["on_accent"] = t["window"] if dark else "#FFFFFF"
    t["accent_hover"] = mix(t["accent"], t["text"], 0.85)
    surfaces = [t[k] for k in TEXT_SURFACES]
    t["dim_text"] = ensure_contrast(t["dim"], surfaces, t["text"])
    t["hatch"] = mix(t["hyp"], t["base"], 0.4 if dark else 0.35)
    for hue in HUES:
        t[f"{hue}_chip"] = mix(t[hue], t["base"], 0.14 if dark else 0.11)
        t[f"{hue}_edge"] = mix(t[hue], t["base"], 0.45)
        extra = [t[f"{hue}_chip"]] + ([t["hatch"]] if hue == "hyp" else [])
        t[f"{hue}_text"] = ensure_contrast(t[hue], surfaces + extra, t["text"])
    t["text_text"] = t["text"]
    return t


THEMES = {"light": _derive(LIGHT, False), "dark": _derive(DARK, True)}


def tokens(name: str | None = None) -> dict[str, str]:
    return THEMES[name or _current]


def current_theme() -> str:
    return _current


def text_pairs(name: str) -> list[tuple[str, str, str, str]]:
    """(foreground token, background token, fg, bg) for every text/surface pairing the stylesheet uses."""
    t = THEMES[name]
    pairs = [(fg, bg, t[fg], t[bg]) for fg in ("text", "muted", "dim_text", "accent_text") for bg in TEXT_SURFACES]
    pairs.append(("on_accent", "accent", t["on_accent"], t["accent"]))
    for kind, (hue, style) in _CHIP_STYLE.items():
        fg = f"{hue}_text" if hue not in ("text", "dim") else ("text" if hue == "text" else "dim_text")
        bg = {"fill": f"{hue}_chip", "hatch": "hatch"}.get(style, "base")
        pairs.append((f"chip:{kind}", bg, t[fg], t[bg]))
    return pairs


def chip(text: str, kind: str, parent: QWidget | None = None) -> QLabel:
    """A claim / provenance / method / record chip; styling comes from the stylesheet."""
    label = QLabel(text.upper(), parent)
    label.setObjectName("Chip")
    set_chip(label, text, kind)
    return label


def set_chip(label: QLabel, text: str, kind: str) -> None:
    if kind not in _CHIP_STYLE:
        raise ValueError(f"Unknown chip kind {kind!r}")
    axis = next(name for name, kinds in CHIP_AXES.items() if kind in kinds)
    label.setText(text.upper())
    label.setProperty("chip", kind)
    label.setAccessibleName(f"{axis}: {text}")
    label.setVisible(bool(text))
    repolish(label)


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def build_palette(t: dict[str, str]) -> QPalette:
    palette = QPalette()
    roles = QPalette.ColorRole
    for role, key in (
        (roles.Window, "window"), (roles.WindowText, "text"), (roles.Base, "base"),
        (roles.AlternateBase, "alt"), (roles.ToolTipBase, "text"), (roles.ToolTipText, "base"),
        (roles.Text, "text"), (roles.Button, "base"), (roles.ButtonText, "text"),
        (roles.Highlight, "accent_tint"), (roles.HighlightedText, "text"), (roles.Link, "accent_text"),
        (roles.PlaceholderText, "dim_text"), (roles.Light, "base"), (roles.Midlight, "line"),
        (roles.Mid, "line2"), (roles.Dark, "line2"), (roles.Shadow, "line2"), (roles.BrightText, "bad_text"),
    ):
        palette.setColor(role, QColor(t[key]))
    for role in (roles.Text, roles.ButtonText, roles.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t["faint"]))
    return palette


_CHIP_CSS = {
    "fill": "background: $bg; border: 1px solid $bg;",
    "hatch": ("background: qlineargradient(spread:repeat, x1:0, y1:0, x2:0.06, y2:0.3, stop:0 $base, "
              "stop:0.5 $base, stop:0.51 $hatch, stop:1 $hatch); border: 1px solid $edge;"),
    "outline": "background: $base; border: 1px solid $edge;",
    "dash": "background: $base; border: 1px dashed $edge;",
    "dot": "background: $base; border: 1px dotted $line2;",
    "dashclear": "background: transparent; border: 1px dashed $line2;",
    "strike": "background: $base; border: 1px solid $base; text-decoration: line-through;",
}


def _chip_rules(t: dict[str, str]) -> str:
    rules = []
    for kind, (hue, style) in _CHIP_STYLE.items():
        fg = t["dim_text"] if hue == "dim" else t["text"] if hue == "text" else t[f"{hue}_text"]
        body = Template(_CHIP_CSS[style]).substitute(
            bg=t.get(f"{hue}_chip", t["base"]), base=t["base"], hatch=t["hatch"],
            edge=t.get(f"{hue}_edge", t["line2"]), line2=t["line2"],
        )
        rules.append(f'QLabel#Chip[chip="{kind}"] {{ color: {fg}; {body} }}')
    return "\n".join(rules)


_STYLESHEET = Template(
    """
QMainWindow, QDialog { background: $window; color: $text; }
QWidget { color: $text; selection-background-color: $accent_tint; selection-color: $text; }
QToolTip { background: $text; color: $base; border: 0; padding: 4px 6px; }
QMenuBar { background: $chrome; color: $text; border-bottom: 1px solid $line; padding: 1px 6px; }
QMenuBar::item { padding: 4px 9px; background: transparent; border-radius: 4px; }
QMenuBar::item:selected, QMenu::item:selected { background: $hover; color: $text; }
QMenu { background: $base; border: 1px solid $line2; padding: 4px; }
QMenu::item { padding: 5px 22px 5px 10px; border-radius: 4px; }
QMenu::item:disabled { color: $faint; }
QMenu::separator { height: 1px; background: $line; margin: 4px 6px; }
QToolBar { background: $chrome; border: 0; spacing: 6px; padding: 0 12px; }
QToolBar::separator { background: $line; width: 1px; margin: 8px 6px; }
QDockWidget { color: $muted; }
QDockWidget::title { background: $dock; padding: 7px 10px; border-bottom: 1px solid $line; }
QStatusBar { background: $chrome; color: $dim_text; border-top: 1px solid $line; min-height: 24px; }
QStatusBar::item { border: 0; }
QStatusBar QLabel { color: $dim_text; padding: 0 6px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: $line; }

/* ---- generic controls ---- */
QTreeWidget, QTreeView, QListWidget, QListView, QTableView, QTextBrowser, QPlainTextEdit, QTextEdit, QLineEdit,
QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTableWidget {
    background: $base; color: $text; border: 1px solid $line; border-radius: 6px;
    selection-background-color: $accent_tint; selection-color: $text;
}
QTreeWidget, QTreeView, QListWidget { outline: 0; }
QTreeWidget::item, QListWidget::item { min-height: 24px; padding: 1px 4px; border-radius: 4px; }
QTreeWidget::item:hover, QListWidget::item:hover { background: $hover; }
QTreeWidget::item:selected, QListWidget::item:selected { background: $accent_tint; color: $text; }
QHeaderView::section { background: $base; color: $text; border: 0; border-bottom: 1px solid $line2;
    padding: 6px 8px; font-weight: 600; }
QTableView { gridline-color: $line; alternate-background-color: $alt; }
QTableView::item { padding: 3px 6px; }
QTableView QTableCornerButton::section { background: $base; border: 0; }
QPushButton { background: $base; color: $text; border: 1px solid $line2; border-radius: 6px;
    padding: 5px 12px; min-height: 20px; }
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $line; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: $accent; }
QPushButton:disabled { color: $faint; border-color: $line; }
QPushButton[primary="true"] { background: $accent; color: $on_accent; border-color: $accent; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[primary="true"]:disabled { background: $line; border-color: $line; color: $faint; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit { padding: 4px 8px; min-height: 21px; border-color: $line2; }
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView { background: $base; border: 1px solid $line2; }
QTabWidget::pane { border: 1px solid $line; background: $window; border-radius: 6px; top: -1px; }
QTabBar::tab { background: transparent; color: $dim_text; border: 0; border-bottom: 2px solid transparent;
    padding: 6px 10px; margin-right: 2px; }
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected { color: $text; border-bottom-color: $accent; }
QProgressBar { background: $base; border: 1px solid $line; border-radius: 3px; text-align: center; max-height: 10px; }
QProgressBar::chunk { background: $accent; }
QScrollBar:vertical, QScrollBar:horizontal { background: transparent; width: 10px; height: 10px; margin: 0; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: $line2; border-radius: 4px; min-height: 20px; min-width: 20px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QGroupBox { border: 0; border-top: 1px solid $line; margin-top: 14px; padding-top: 6px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 0; padding: 0 4px 0 0; }

/* ---- workbench shell ---- */
QWidget#WorkbenchShell, QWidget#WorkbenchDesk { background: $desk; }
QToolBar#WorkbenchRibbon { background: $window; border: 0; border-bottom: 1px solid $line; padding: 4px 10px; spacing: 2px; }
QToolBar#WorkbenchRibbon QToolButton { color: $muted; background: transparent; border: 1px solid transparent;
    border-radius: 8px; padding: 4px 6px; min-width: 56px; font-size: 12px; }
QToolBar#WorkbenchRibbon QToolButton:hover { background: $base; color: $text; }
QToolBar#WorkbenchRibbon QToolButton:checked { background: $base; color: $text; border-color: $line2; }
QToolBar#WorkbenchRibbon QToolButton:disabled { color: $faint; }
QToolBar#WorkbenchRibbon QToolButton:focus { border-color: $accent; }
QPushButton#PaletteLauncher { background: $base; color: $dim_text; border: 1px solid $line2; border-radius: 8px;
    text-align: left; padding: 5px 10px; min-width: 180px; }
QPushButton#PaletteLauncher[compact="true"] { min-width: 0; }
QFrame#RunStatePill { background: $base; border: 1px solid $line; border-radius: 14px; }
QFrame#RunStatePill QLabel { color: $dim_text; padding: 0; font-size: 12px; }
QLabel#RunStateDot { min-width: 8px; max-width: 8px; min-height: 8px; max-height: 8px; border-radius: 4px; background: $faint; padding: 0; }
QLabel#RunStateDot[state="current"] { background: $ok; }
QLabel#RunStateDot[state="stale"] { background: $warn; }
QLabel#RunStateDot[state="running"] { background: $mod; }
QFrame#Segmented { background: $alt; border: 1px solid $line2; border-radius: 7px; }
QFrame#Segmented QPushButton { background: transparent; border: 1px solid transparent; border-radius: 5px;
    color: $dim_text; padding: 3px 10px; min-height: 16px; }
QFrame#Segmented QPushButton:checked { background: $base; color: $text; border-color: $line; }
QListWidget#RoleBox { background: $base; border: 1px solid $line2; border-radius: 6px; outline: 0; }
QListWidget#RoleBox:focus { border: 1.5px solid $accent; }
QListWidget#RoleBox[dropHover="true"] { border: 1.5px dashed $accent; background: $accent_tint; }
QListWidget#RoleBox::item { min-height: 0; padding: 0; border-radius: 4px; }
QListWidget#RoleBox::item:selected { background: $accent_tint; }

/* ---- results document ---- */
QWidget#ResultsCanvas { background: $window; }
QFrame#ResultBlock { background: $base; border: 1px solid $line; border-radius: 10px; }
QLabel#BlockTitle { color: $text; font-size: 16px; font-weight: 600; }
QLabel#BlockSubtitle { color: $muted; font-family: "$mono"; font-size: 12px; }
QLabel#BlockHeading { color: $text; font-size: 13px; font-weight: 600; padding-top: 4px; }
QLabel#BlockText { color: $text; }
QLabel#BlockNote { color: $dim_text; font-style: italic; font-size: 12px; }
QFrame#BlockFooter { border: 0; border-top: 1px dashed $line2; }
QLabel#FooterText { color: $dim_text; font-size: 11px; }
QPushButton#PromoteButton { background: transparent; border: 0; color: $accent_text; padding: 2px 4px; }
QPushButton#PromoteButton:hover { text-decoration: underline; }
QPushButton#PromoteButton:disabled { color: $faint; }
QFrame#SupersededBar { background: $bad_chip; border: 1px solid $bad_edge; border-radius: 8px; }
QFrame#SupersededBar QLabel { color: $text; }
QFrame#WorkbenchPane { background: $window; border: 1px solid $line; border-radius: 10px; }
QFrame#WorkbenchPane[focused="true"] { border-color: $accent; }
QFrame#PaneHeader { background: $base; border: 0; border-bottom: 1px solid $line;
    border-top-left-radius: 10px; border-top-right-radius: 10px; min-height: 42px; max-height: 42px; }
QLabel#PaneTitle { font-size: 13px; font-weight: 600; color: $text; }
QLabel#PaneContext { color: $dim_text; }
QLabel#PaneEmpty { color: $dim_text; padding: 24px; }
QFrame#StaleBar { background: $warn_chip; border: 1px solid $warn_edge; border-radius: 8px; }
QFrame#StaleBar QLabel { color: $text; }
QFrame#SyntaxBar { background: $chrome; border: 0; border-top: 1px solid $line;
    border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; }
QLabel#SyntaxCaption { color: $dim_text; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QPlainTextEdit#SyntaxText { background: transparent; border: 0; color: $text; font-family: "$mono"; font-size: 12px; }
QLabel#Toast { background: $text; color: $base; border-radius: 8px; padding: 10px 16px; }
QLabel#Chip { font-size: 10px; font-weight: 700; border-radius: 9px; padding: 1px 7px; min-height: 15px; max-height: 17px; }
QDialog#CommandPalette { background: $base; border: 1px solid $line2; border-radius: 10px; }
QLineEdit#PaletteInput { border: 0; border-bottom: 1px solid $line; border-radius: 0; font-size: 15px; padding: 10px 14px; background: $base; }
QListView#PaletteList { border: 0; background: $base; padding: 6px; outline: 0; }
QListView#PaletteList::item { padding: 7px 10px; border-radius: 6px; }
QListView#PaletteList::item:selected { background: $accent_tint; color: $text; }
QLabel#PaletteHint { color: $dim_text; font-family: "$mono"; font-size: 11px; padding: 6px 12px; border-top: 1px solid $line; }

/* ---- Performance OS, restyled onto the same tokens ---- */
QToolBar#PerformanceToolbar { background: $chrome; border-bottom: 1px solid $line; min-height: 48px; max-height: 48px; padding: 0; }
QWidget#PerformanceHeader { background: $chrome; }
QToolButton#PerformanceBrandMark { min-width: 23px; max-width: 23px; min-height: 23px; max-height: 23px; padding: 0;
    border: 1px solid $accent_edge; border-radius: 4px; color: $accent_text; background: $accent_chip; font-family: "$mono"; font-size: 11px; }
QLabel#PerformanceBrandName { color: $text; font-size: 11px; font-weight: 600; }
QLabel#PerformanceBrandDescriptor, QLabel#PerformanceRoleLabel { color: $dim_text; font-family: "$mono"; font-size: 7px; letter-spacing: 1px; }
QLabel#PerformanceClub { color: $text; font-size: 9px; font-weight: 600; }
QLabel#PerformanceMuted, QLabel#PerformanceRole { color: $dim_text; font-size: 9px; }
QLabel#PerformanceSeason { color: $accent_text; border: 1px solid $accent_edge; border-radius: 4px; padding: 3px 7px; font-family: "$mono"; font-size: 8px; }
QLineEdit#PerformanceSearch { min-height: 23px; padding: 2px 8px; }
QLabel#PerformanceAvatar { min-width: 25px; max-width: 25px; min-height: 25px; max-height: 25px; qproperty-alignment: AlignCenter;
    border: 1px solid $line2; border-radius: 12px; background: $hover; color: $muted; font-family: "$mono"; font-size: 8px; }
QWidget#PerformanceRail { background: $dock; border-right: 1px solid $line; }
QLabel#PerformanceCrest { min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; qproperty-alignment: AlignCenter;
    border: 1px solid $line2; border-radius: 6px; background: $base; color: $accent_text; font-family: "$mono"; font-size: 9px; }
QLabel#PerformanceRailClub { color: $text; font-size: 9px; font-weight: 600; }
QLabel#PerformanceRailMeta, QLabel#PerformanceRailNote { color: $dim_text; font-size: 8px; }
QLabel#PerformanceRailGroup { color: $dim_text; font-family: "$mono"; font-size: 7px; letter-spacing: 1px; padding: 3px 6px; }
QPushButton#PerformanceRailItem { text-align: left; padding: 4px 6px; min-height: 22px; border: 0; border-radius: 6px;
    border-left: 2px solid transparent; background: transparent; color: $muted; }
QPushButton#PerformanceRailItem:hover { background: $hover; color: $text; }
QPushButton#PerformanceRailItem:checked { background: $accent_tint; border-left-color: $accent; color: $text; }
QLabel#PerformanceRailItemName { font-size: 9px; }
QLabel#PerformanceRailTag { color: $dim_text; font-family: "$mono"; font-size: 7px; }
QFrame#PerformanceSquadFooter { border-top: 1px solid $line; background: transparent; }
QLabel#PerformanceAvailability { color: $accent_text; font-family: "$mono"; font-size: 17px; }
QFrame#PerformanceAvailabilitySegment { background: $accent; border: 0; }
QFrame#PerformanceReadinessSegment { border: 0; background: $line2; }
QFrame#PerformanceReadinessSegment[band="0"] { background: $bad; }
QFrame#PerformanceReadinessSegment[band="1"] { background: $warn; }
QFrame#PerformanceReadinessSegment[band="2"] { background: $mod; }
QFrame#PerformanceReadinessSegment[band="3"] { background: $ok; }
QWidget#PerformanceContextPanel { background: $dock; }
QLabel#PerformanceContextHeading { color: $dim_text; font-family: "$mono"; font-size: 7px; letter-spacing: 1px; padding: 9px 0 5px; }
QLabel#PerformanceChecklistLabel { color: $muted; font-size: 8px; }
QLabel#PerformanceChecklistStatus, QLabel#PerformanceChecklistDone { color: $ok_text; font-family: "$mono"; font-size: 7px; }
QLabel#PerformanceContextMuted, QLabel#PerformanceContextFooter { color: $dim_text; font-size: 7px; }
QLabel#PerformanceContextMono { color: $dim_text; font-family: "$mono"; font-size: 8px; padding: 2px 0 8px; }
QLabel#PerformanceCalloutWarning { color: $bad_text; background: $bad_chip; border: 1px solid $bad_edge; border-radius: 6px; padding: 6px; font-size: 8px; margin-top: 6px; }
QLabel#PerformanceCalloutInfo { color: $mod_text; background: $mod_chip; border: 1px solid $mod_edge; border-radius: 6px; padding: 6px; font-size: 8px; margin-top: 6px; }
QWidget#PerformancePage { background: $window; }
QFrame#PerformancePulse { background: $base; border: 1px solid $line; border-radius: 10px; }
QFrame#PerformancePulseCell { background: transparent; border: 0; border-right: 1px solid $line; }
QFrame#PerformanceMiniMetric { background: $alt; border: 1px solid $line; border-radius: 6px; }
QLabel#PerformanceMiniMetricValue { color: $text; font-family: "$mono"; font-size: 9px; }
QLabel#PerformanceMetricLabel { color: $dim_text; font-family: "$mono"; font-size: 7px; letter-spacing: .5px; }
QLabel#PerformanceMetricValue { color: $text; font-family: "$mono"; font-size: 18px; }
QLabel#PerformanceMetricNote { color: $dim_text; font-size: 7px; }
QFrame#PerformanceModule { background: $base; border: 1px solid $line; border-radius: 10px; }
QLabel#PerformanceModuleTitle { color: $text; font-size: 9px; font-weight: 600; }
QLabel#PerformanceModuleNote { color: $dim_text; font-family: "$mono"; font-size: 7px; }
QLabel#PerformanceKicker { color: $accent_text; font-family: "$mono"; font-size: 7px; letter-spacing: 1px; }
QLabel#PerformancePageTitle { color: $text; font-size: 21px; font-weight: 600; }
QLabel#PerformancePageDescription { color: $dim_text; font-size: 8px; }
QLabel#PerformanceResearchTitle { color: $text; font-size: 10px; font-weight: 600; }
QLabel#PerformanceDecisionCard { color: $muted; background: $alt; border: 1px solid $line; border-radius: 6px; padding: 6px; font-size: 8px; }
QLabel#PerformanceAthleteIdentity { color: $accent_text; font-family: "$mono"; font-size: 14px; font-weight: 600; }
QPushButton#PerformancePrimaryButton { background: $accent; color: $on_accent; border-color: $accent; font-weight: 600; }
QPushButton#PerformancePrimaryButton:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#PerformanceLinkButton { border: 0; background: transparent; color: $accent_text; text-align: left; padding: 2px 0; min-height: 16px; }
QPushButton#PerformanceLinkButton:hover { color: $text; }
QTableView#PerformanceAttentionTable { font-size: 8px; }
QTableView#PerformanceAttentionTable QHeaderView::section { font-size: 8px; padding: 4px 3px; }
QTextBrowser#PerformanceReportPreview { background: $base; color: $text; }
"""
)


def build_stylesheet(t: dict[str, str]) -> str:
    return _STYLESHEET.substitute(t, mono=MONO) + _chip_rules(t)


def ui_font() -> QFont:
    font = QFont()
    font.setFamilies([SANS, "Segoe UI"])
    font.setPointSizeF(9.5)
    return font


def mono_font() -> QFont:
    font = QFont()
    font.setFamilies([MONO, "Consolas"])
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSizeF(9)
    return font


def apply_theme(application: QApplication, name: str | None = None) -> None:
    global _current
    name = name if name in THEMES else _current
    _current = name
    application.setStyle("Fusion")
    application.setFont(ui_font())
    t = THEMES[name]
    application.setPalette(build_palette(t))
    application.setStyleSheet(build_stylesheet(t))
