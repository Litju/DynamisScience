"""Design E workbench shell: analysis ribbon, Data · Options · Results panes, syntax bar.

Later gates fill the panes through ``set_data_widget`` / ``set_options_widget`` /
``set_results_widget`` and react to ``analysis_selected``.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QPointF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from .palette import CommandPalette

# (key, ribbon label, group); a separator is drawn where the group changes.
ANALYSES = (
    ("descriptives", "Descriptives", "explore"),
    ("t_tests", "T-Tests", "explore"),
    ("anova", "ANOVA", "explore"),
    ("regression", "Regression", "explore"),
    ("mixed_models", "Mixed Models", "explore"),
    ("reliability", "Reliability", "explore"),
    ("frequencies", "Frequencies", "explore"),
    ("signals", "Signals", "sports"),
    ("athlete_change", "Athlete change", "sports"),
)
PANES = ("data", "options", "results")
PANE_MINIMUM = {"data": 300, "options": 260, "results": 420}
COMPACT_WIDTH = 1100
# v2: earlier builds saved the splitter even when the user never moved it, freezing a first-pass layout
SPLITTER_KEY = "workbench/splitter-v2"

# Line icons on a 20 x 20 grid: polylines, plus ("o", x, y, r) circles and ("r", x, y, w, h) boxes.
_ICONS = {
    "descriptives": [[(3, 3), (3, 17), (17, 17)], ("r", 6, 10, 2, 6), ("r", 10, 6, 2, 10), ("r", 14, 12, 2, 4)],
    "t_tests": [[(2, 15), (6, 7), (9, 12), (12, 5), (17, 15)]],
    "anova": [("r", 3, 7, 3, 10), ("r", 8.5, 4, 3, 13), ("r", 14, 9, 3, 8)],
    "regression": [[(2, 16), (18, 4)], ("o", 5, 11, 1), ("o", 9, 12, 1), ("o", 12, 6, 1), ("o", 15, 9, 1)],
    "mixed_models": [[(3, 9), (17, 3)], [(3, 13), (17, 7)], [(3, 17), (17, 11)]],
    "reliability": [("o", 7, 10, 4.5), ("o", 13, 10, 4.5)],
    "frequencies": [("r", 3, 3, 14, 14), [(3, 8), (17, 8)], [(3, 12.5), (17, 12.5)], [(8, 3), (8, 17)]],
    "signals": [[(2, 11), (6, 11), (8, 4), (11, 16), (13, 9), (18, 9)]],
    "athlete_change": [("o", 10, 6, 3.2), [(4, 18), (4.5, 15), (7, 12.5), (13, 12.5), (15.5, 15), (16, 18)]],
}


def _icon(key: str) -> QIcon:
    icon = QIcon()
    t = theme.tokens()
    for colour, state in ((t["muted"], QIcon.State.Off), (t["accent"], QIcon.State.On)):
        pixmap = QPixmap(48, 48)
        pixmap.setDevicePixelRatio(2.0)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(colour), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.translate(2, 2)
        for shape in _ICONS[key]:
            if isinstance(shape, list):
                path = QPainterPath(QPointF(*shape[0]))
                for point in shape[1:]:
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)
            elif shape[0] == "o":
                painter.drawEllipse(QPointF(shape[1], shape[2]), shape[3], shape[3])
            else:
                painter.drawRoundedRect(*shape[1:], 1, 1)
        painter.end()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
            icon.addPixmap(pixmap, mode, state)
    return icon


class _Pane(QFrame):
    def __init__(self, key: str, title: str) -> None:
        super().__init__()
        self.key = key
        self.setObjectName("WorkbenchPane")
        self.setProperty("focused", False)
        self.setAccessibleName(f"{title} pane")
        self.setMinimumWidth(PANE_MINIMUM[key])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.header = QFrame()
        self.header.setObjectName("PaneHeader")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(14, 0, 10, 0)
        self.header_layout.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("PaneTitle")
        self.header_layout.addWidget(self.title)
        layout.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(8, 8, 8, 8)
        self.body.setSpacing(8)
        layout.addLayout(self.body, 1)
        self.content: QWidget | None = None

    def set_content(self, widget: QWidget, index: int = 0) -> QWidget | None:
        previous = self.content
        if previous is widget:
            return previous
        if previous is not None:
            self.body.removeWidget(previous)
            previous.hide()
            previous.setParent(None)
        self.content = widget
        self.body.insertWidget(index, widget, 1)
        widget.show()
        return previous


class WorkbenchShell(QWidget):
    """Research perspective of the main window (design E 1.0)."""

    analysis_selected = Signal(str)
    theme_changed = Signal(str)

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkbenchShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.settings = settings
        self._compact: bool | None = None
        self._drawer_open = False
        self._sized = False
        self._build_actions()
        self._build_ribbon()
        self._build_panes()
        self._build_status_items()
        self._build_toast()
        self.palette = CommandPalette(self)
        self.palette.add_actions(self.analysis_actions.values(), "Analysis")
        self.palette.add_actions((self.action_run, self.action_add_to_report, self.action_promote, self.action_export), "Results")
        self.palette.add_actions(self.view_actions, "View")
        self._shortcuts()
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self.set_run_state("none")
        self.set_provenance()
        self.restore_state()

    # ------------------------------------------------------------------ build
    def _build_actions(self) -> None:
        self.analysis_group = QActionGroup(self)
        self.analysis_group.setExclusive(True)
        self.analysis_actions: dict[str, QAction] = {}
        for key, label, _group in ANALYSES:
            action = QAction(_icon(key), label, self)
            action.setCheckable(True)
            action.setData(key)
            action.setToolTip(f"{label} analysis")
            action.triggered.connect(lambda _checked=False, key=key: self.select_analysis(key))
            self.analysis_group.addAction(action)
            self.analysis_actions[key] = action
        self.action_run = QAction("Run analysis", self)
        self.action_run.setShortcut(QKeySequence("Ctrl+Return"))
        self.action_run.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.action_add_to_report = QAction("Add to report", self)
        self.action_promote = QAction("Promote to evidence", self)
        self.action_promote.setToolTip("Only qualified methods can be promoted to evidence")
        self.action_export = QAction("Export…", self)
        self.addAction(self.action_run)
        self.view_actions = []
        for index, key in enumerate(PANES):
            action = QAction(f"Focus {key.title()} pane", self)
            action.triggered.connect(lambda _checked=False, index=index: self.focus_pane(index))
            self.view_actions.append(action)
        for name in theme.THEMES:
            action = QAction(f"Switch to {name} theme", self)
            action.triggered.connect(lambda _checked=False, name=name: self.set_theme(name))
            self.view_actions.append(action)

    def _build_ribbon(self) -> None:
        self.ribbon = QToolBar("Analyses", self)
        self.ribbon.setObjectName("WorkbenchRibbon")
        self.ribbon.setAccessibleName("Analysis ribbon")
        self.ribbon.setMovable(False)
        self.ribbon.setFloatable(False)
        self.ribbon.setIconSize(QSize(22, 22))
        self.ribbon.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        group = ANALYSES[0][2]
        for key, label, action_group in ANALYSES:
            if action_group != group:
                self.ribbon.addSeparator()
                group = action_group
            action = self.analysis_actions[key]
            self.ribbon.addAction(action)
            button = self.ribbon.widgetForAction(action)
            button.setAccessibleName(label)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        overflow = self.ribbon.findChild(QToolButton, "qt_toolbar_ext_button")
        if overflow is not None:
            overflow.setAccessibleName("More ribbon commands")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.ribbon.addWidget(spacer)
        self.palette_button = QPushButton("Search commands…      Ctrl K")
        self.palette_button.setObjectName("PaletteLauncher")
        self.palette_button.setAccessibleName("Search commands (Ctrl+K)")
        self.palette_button.clicked.connect(lambda: self.palette.popup())
        self.ribbon.addWidget(self.palette_button)
        self.run_pill = QFrame()
        self.run_pill.setObjectName("RunStatePill")
        pill = QHBoxLayout(self.run_pill)
        pill.setContentsMargins(10, 4, 12, 4)
        pill.setSpacing(7)
        self.run_dot = QLabel()
        self.run_dot.setObjectName("RunStateDot")
        self.run_label = QLabel()
        pill.addWidget(self.run_dot)
        pill.addWidget(self.run_label)
        self.ribbon.addWidget(self.run_pill)
        self.theme_switch = QFrame()
        self.theme_switch.setObjectName("Segmented")
        switch = QHBoxLayout(self.theme_switch)
        switch.setContentsMargins(2, 2, 2, 2)
        switch.setSpacing(0)
        self.theme_buttons = QButtonGroup(self)
        for name in theme.THEMES:
            button = QPushButton(name.title())
            button.setCheckable(True)
            button.setAccessibleName(f"{name.title()} theme")
            button.clicked.connect(lambda _checked=False, name=name: self.set_theme(name))
            self.theme_buttons.addButton(button)
            switch.addWidget(button)
        self.theme_switch_action = self.ribbon.addWidget(self.theme_switch)
        for widget in (self.palette_button, self.run_pill, self.theme_switch):
            widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self._sync_theme_buttons()

    def _build_panes(self) -> None:
        self.panes = {key: _Pane(key, title) for key, title in zip(PANES, ("Data", "Analysis options", "Results"))}
        data, options, results = (self.panes[key] for key in PANES)

        self.context_label = QLabel("Select a project, study or dataset")
        self.context_label.setObjectName("PaneContext")
        self.context_label.setAccessibleName("Open research context")
        self.context_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data.header_layout.addWidget(self.context_label, 1)
        data.set_content(self._empty("Open a dataset or study to see its data."))

        self.method_chip = theme.chip("", "descriptive")
        options.header_layout.addStretch(1)
        options.header_layout.addWidget(self.method_chip)
        options.set_content(self._empty("Choose an analysis in the ribbon."))

        results.header_layout.addStretch(1)
        for action, primary in ((self.action_export, False), (self.action_add_to_report, True)):
            button = QPushButton(action.text())
            button.setAccessibleName(action.text().rstrip("…"))
            button.setProperty("primary", primary)
            button.clicked.connect(action.trigger)
            action.enabledChanged.connect(button.setEnabled)
            results.header_layout.addWidget(button)
        self.stale_bar = QFrame()
        self.stale_bar.setObjectName("StaleBar")
        stale = QHBoxLayout(self.stale_bar)
        stale.setContentsMargins(12, 6, 6, 6)
        stale_label = QLabel("⚠  <b>Specification changed.</b> These results are for the previous specification.")
        stale_label.setTextFormat(Qt.TextFormat.RichText)
        stale_label.setWordWrap(True)
        run = QPushButton("▶ Run  ·  Ctrl ↵")
        run.setProperty("primary", True)
        run.setAccessibleName("Run analysis")
        run.clicked.connect(self.action_run.trigger)
        stale.addWidget(stale_label, 1)
        stale.addWidget(run)
        results.body.addWidget(self.stale_bar)
        results.set_content(self._empty("Results appear here after a run."), 1)
        results.layout().addWidget(self._build_syntax_bar())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("WorkbenchSplitter")
        self.splitter.setAccessibleName("Workbench panes")
        self.splitter.setHandleWidth(8)
        self.splitter.setChildrenCollapsible(False)
        for key in PANES:
            self.splitter.addWidget(self.panes[key])
        self.splitter.setStretchFactor(0, 112)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 115)
        self.splitter.splitterMoved.connect(self._user_resized)
        self.splitter.installEventFilter(self)  # default pane sizes follow the splitter's own resizes

        desk = QWidget()
        desk.setObjectName("WorkbenchDesk")
        desk_layout = QVBoxLayout(desk)
        desk_layout.setContentsMargins(8, 8, 8, 8)
        desk_layout.addWidget(self.splitter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ribbon)
        layout.addWidget(desk, 1)

    def _build_syntax_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("SyntaxBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 6, 10, 6)
        caption = QLabel("SYNTAX")
        caption.setObjectName("SyntaxCaption")
        self.syntax = QPlainTextEdit()
        self.syntax.setObjectName("SyntaxText")
        self.syntax.setAccessibleName("Python syntax equivalent")
        self.syntax.setReadOnly(True)
        self.syntax.setFont(theme.mono_font())
        self.syntax.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.syntax.setFixedHeight(self.syntax.fontMetrics().lineSpacing() * 2 + 12)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setAccessibleName("Copy syntax")
        self.copy_button.clicked.connect(self.copy_syntax)
        layout.addWidget(caption, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.syntax, 1)
        layout.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)
        return bar

    def _build_status_items(self) -> None:
        """Widgets for the host's status bar: application status, then provenance."""
        self.app_status = QLabel("Starting")
        self.app_status.setAccessibleName("Application status")
        self.status_items = QWidget()
        self.status_items.setObjectName("ProvenanceStatus")
        layout = QHBoxLayout(self.status_items)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(6)
        self.source_chip = theme.chip("", "real")
        self.provenance_label = QLabel()
        self.provenance_label.setAccessibleName("Scientific provenance")
        self.provenance_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_method_chip = theme.chip("", "descriptive")
        layout.addWidget(self.source_chip)
        layout.addWidget(self.provenance_label)
        layout.addWidget(self.status_method_chip)

    def _build_toast(self) -> None:
        self.toast = QLabel(self)
        self.toast.setObjectName("Toast")
        self.toast.setAccessibleName("Notification")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

    def _shortcuts(self) -> None:
        for index in range(3):
            QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self, lambda index=index: self.focus_pane(index))
        QShortcut(QKeySequence("F6"), self, self.cycle_panes)
        QShortcut(QKeySequence("Ctrl+K"), self, lambda: self.palette.popup())

    @staticmethod
    def _empty(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PaneEmpty")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    # ------------------------------------------------------------------ public API
    def set_data_widget(self, widget: QWidget) -> QWidget | None:
        return self.panes["data"].set_content(widget)

    def set_options_widget(self, widget: QWidget) -> QWidget | None:
        return self.panes["options"].set_content(widget)

    def set_results_widget(self, widget: QWidget) -> QWidget | None:
        return self.panes["results"].set_content(widget, 1)

    def select_analysis(self, key: str) -> None:
        action = self.analysis_actions[key]
        action.setChecked(True)
        self.panes["options"].title.setText(action.text())
        if self.settings is not None:
            self.settings.setValue("workbench/analysis", key)
        self.analysis_selected.emit(key)

    def current_analysis(self) -> str | None:
        action = self.analysis_group.checkedAction()
        return action.data() if action else None

    def set_context(self, text: str) -> None:
        self.context_label.setText(text)

    def set_status(self, text: str) -> None:
        self.app_status.setText(text)

    def set_provenance(self, source: str = "", run: str = "", digest: str = "", method_status: str = "",
                       provenance: str = "") -> None:
        """Status-bar provenance: source · run · digest, plus provenance and method-status chips.

        ``provenance`` is "real" or "synthetic"; ``method_status`` is a method-axis chip kind
        (e.g. "qualified", "descriptive", "not_qualified"). Promote is enabled only when qualified.
        """
        self.provenance_label.setText("  ·  ".join(part for part in (source, run, digest and f"result digest {digest}") if part))
        self.provenance_label.setToolTip(
            f"Result digest of {run}: first 8 hex digits of the SHA-256 of the run's recorded result. Identical "
            "data and specification give the identical digest on every rerun." if digest else "")
        theme.set_chip(self.source_chip, provenance.upper() if provenance else "", provenance or "real")
        label = method_status.replace("_", " ")
        for widget in (self.status_method_chip, self.method_chip):
            theme.set_chip(widget, label, method_status or "descriptive")
        self.action_promote.setEnabled(method_status == "qualified")

    def set_run_state(self, state: str) -> None:
        """``none`` · ``current`` (up to date) · ``stale`` (specification changed) · ``running``."""
        text = {"none": "No results yet", "current": "Results up to date",
                "stale": "Specification changed", "running": "Running in worker…"}[state]
        self.run_label.setText(text)
        self.run_pill.setAccessibleName(f"Run state: {text}")
        self.run_dot.setProperty("state", state)
        theme.repolish(self.run_dot)
        self.stale_bar.setVisible(state == "stale")

    def set_syntax(self, text: str) -> None:
        self.syntax.setPlainText(text)

    def copy_syntax(self) -> None:
        QApplication.clipboard().setText(self.syntax.toPlainText())
        self.show_toast("Syntax copied")

    def show_toast(self, text: str, milliseconds: int = 2200) -> None:
        self.toast.setText(text)
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2, self.height() - self.toast.height() - 64)
        self.toast.raise_()
        self.toast.show()
        self._toast_timer.start(milliseconds)

    def focus_pane(self, index: int) -> None:
        pane = self.panes[PANES[index]]
        if PANES[index] == "options" and self._compact:
            if pane.isVisible() and self.focused_pane() == "options":
                self._drawer_open = False
                pane.hide()
                return
            self._drawer_open = True
            pane.show()
        target = pane.content if pane.content is not None and pane.content.focusPolicy() != Qt.FocusPolicy.NoFocus else None
        if target is None:
            target = next(
                (w for w in pane.findChildren(QWidget) if w.isVisible() and w.focusPolicy() & Qt.FocusPolicy.TabFocus),
                pane,
            )
        if target is pane:
            pane.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        target.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._mark_focused(pane)

    def cycle_panes(self) -> None:
        current = self.focused_pane()
        visible = [i for i, key in enumerate(PANES) if self.panes[key].isVisible()]
        start = PANES.index(current) if current else -1
        following = [i for i in visible if i > start] or visible
        if following:
            self.focus_pane(following[0])

    def focused_pane(self) -> str | None:
        focus = QApplication.focusWidget()
        if focus is None:
            return None
        return next((key for key, pane in self.panes.items() if focus is pane or pane.isAncestorOf(focus)), None)

    def set_theme(self, name: str) -> None:
        theme.apply_theme(QApplication.instance(), name)
        for key, action in self.analysis_actions.items():
            action.setIcon(_icon(key))
        self._sync_theme_buttons()
        if self.settings is not None:
            self.settings.setValue("workbench/theme", name)
        self.theme_changed.emit(name)

    def set_compact(self, compact: bool) -> None:
        """1366 × 768 at 150 % and smaller: icon-only ribbon, Options becomes a drawer (Ctrl+2)."""
        if compact == self._compact:
            return
        self._compact = compact
        self.ribbon.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly if compact else Qt.ToolButtonStyle.ToolButtonTextUnderIcon
        )
        self.palette_button.setText("Ctrl K" if compact else "Search commands…      Ctrl K")
        self.palette_button.setProperty("compact", compact)
        self.theme_switch_action.setVisible(not compact)  # still in View menu and the palette
        theme.repolish(self.palette_button)
        self.panes["options"].setVisible(not compact or self._drawer_open)

    def save_state(self) -> None:
        if self.settings is None:
            return
        if self._sized:  # only a layout the user chose; otherwise the design defaults apply next time
            self.settings.setValue(SPLITTER_KEY, self.splitter.saveState())
        else:
            self.settings.remove(SPLITTER_KEY)
        self.settings.sync()

    def restore_state(self) -> None:
        if self.settings is None:
            return
        state = self.settings.value(SPLITTER_KEY)
        if isinstance(state, QByteArray) and self.splitter.restoreState(state):
            self._sized = True
        self.panes["options"].show()  # visibility is decided by the layout, not the saved state
        analysis = self.settings.value("workbench/analysis")
        if analysis in self.analysis_actions:
            self.analysis_actions[analysis].setChecked(True)
            self.panes["options"].title.setText(self.analysis_actions[analysis].text())

    # ------------------------------------------------------------------ events
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_compact(self.width() < COMPACT_WIDTH)
        if self.toast.isVisible():
            self.toast.move((self.width() - self.toast.width()) // 2, self.height() - self.toast.height() - 64)

    def _apply_default_sizes(self) -> None:
        """Sheet 03: Data 1.12 fr · Options 320 px (300 below 1400) · Results 1.15 fr, 8 px handles.

        Reapplied on every resize until the user drags a splitter handle (or a saved layout is
        restored), so the first, smaller layout pass no longer freezes narrow panes.
        """
        options = 320 if self.splitter.width() >= 1384 else 300  # window >= 1400
        rest = max(self.splitter.width() - options - 2 * self.splitter.handleWidth(), 0)
        self.splitter.setSizes([round(rest * 112 / 227), options, round(rest * 115 / 227)])

    def _user_resized(self, *_args) -> None:
        self._sized = True

    def eventFilter(self, watched, event) -> bool:
        if watched is self.splitter and event.type() == QEvent.Type.Resize and not self._sized:
            self._apply_default_sizes()
        return super().eventFilter(watched, event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._sync_theme_buttons()

    def _sync_theme_buttons(self) -> None:
        for button in self.theme_buttons.buttons():
            button.setChecked(button.text().lower() == theme.current_theme())

    def _focus_changed(self, _old, _new) -> None:
        key = self.focused_pane()
        self._mark_focused(self.panes[key] if key else None)
        if self._compact and self._drawer_open and key not in (None, "options"):
            self._drawer_open = False
            self.panes["options"].hide()

    def _mark_focused(self, focused: QWidget | None) -> None:
        for pane in self.panes.values():
            if pane.property("focused") != (pane is focused):
                pane.setProperty("focused", pane is focused)
                theme.repolish(pane)
