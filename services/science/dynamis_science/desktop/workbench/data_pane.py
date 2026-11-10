"""Data pane of the RES-620 workbench: By athlete / Variables / Rows over the bounded models.

Reads only through the service (get_dataset_detail / read_table_page).  Missing values are
always painted (red dash, dashed ring in sparklines); nothing is blank or imputed.
The research navigator stays reachable in a collapsible "Library" section.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QPointF, QRectF, QSize, QSortFilterProxyModel, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QStackedWidget, QStyle, QStyledItemDelegate, QTableView, QToolButton, QVBoxLayout, QWidget,
)

from .. import theme
from .data_models import (
    MISSING_TEXT, ByAthleteModel, MissingRole, RowsModel, SortRole, VariableRole, VariablesModel,
)
from .spec import CATEGORICAL, IDENTIFIER, NUMERICAL, ORDINAL, STUDY_FOR_TABLE

TrendRole = Qt.ItemDataRole.UserRole + 10  # list[float | None] for the sparkline column
BY_ATHLETE_MAX_ROWS = 5_000  # keeps the synchronous pivot build quick
VIEWS = ("By athlete", "Variables", "Rows")

_BADGE = {NUMERICAL: ("N", "mod"), ORDINAL: ("O", "hyp"), CATEGORICAL: ("C", "warn"), IDENTIFIER: ("ID", "muted")}


def paint_type_badge(painter: QPainter, rect: QRectF, vtype: str, dim: bool = False) -> None:
    """Small rounded type badge (N numerical, O ordinal, C categorical, ID identifier)."""
    letter, hue = _BADGE.get(vtype, ("?", "muted"))
    t = theme.tokens()
    colour = QColor(t.get(f"{hue}_text", t[hue]))
    fill = QColor(t.get(f"{hue}_chip", t["alt"]))
    if dim:
        colour.setAlphaF(0.55)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(t.get(f"{hue}_edge", t["line2"])), 1))
    painter.setBrush(fill)
    painter.drawRoundedRect(rect, 4, 4)
    font = QFont(painter.font())
    font.setPixelSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(colour)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, letter)
    painter.restore()


def _bad() -> QColor:
    return QColor(theme.tokens()["bad"])


class MissingDelegate(QStyledItemDelegate):
    """Paints cells flagged by MissingRole in the missing colour (a red dash for absent values)."""

    def _draw_background(self, painter, option, index):
        opt = type(option)(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        return opt

    def paint(self, painter, option, index):
        if not index.data(MissingRole):
            return super().paint(painter, option, index)
        opt = self._draw_background(painter, option, index)
        painter.save()
        painter.setPen(_bad())
        font = QFont(opt.font)
        font.setBold(True)
        painter.setFont(font)
        align = index.data(Qt.ItemDataRole.TextAlignmentRole)
        flags = Qt.AlignmentFlag(align) if align is not None else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(opt.rect.adjusted(6, 0, -6, 0), int(flags), str(index.data(Qt.ItemDataRole.DisplayRole)))
        painter.restore()


class VariableNameDelegate(MissingDelegate):
    """Variables view, first column: type badge, name, unit in muted text."""

    def paint(self, painter, option, index):
        variable = index.data(VariableRole)
        opt = self._draw_background(painter, option, index)
        t = theme.tokens()
        r = opt.rect
        painter.save()
        paint_type_badge(painter, QRectF(r.left() + 6, r.center().y() - 8, 20, 16), variable.type)
        x = r.left() + 34
        painter.setPen(QColor(t["text"]))
        font = QFont(opt.font)
        font.setBold(True)
        painter.setFont(font)
        name_rect = r.adjusted(34, 0, -4, 0)
        text = painter.fontMetrics().elidedText(variable.name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.drawText(name_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        if variable.unit:
            used = painter.fontMetrics().horizontalAdvance(text) + 6
            painter.setFont(opt.font)
            painter.setPen(QColor(t["dim_text"]))
            if x + used < r.right() - 20:
                painter.drawText(r.adjusted(34 + used, 0, -4, 0),
                                 int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), variable.unit)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 28))
        return size


class SparklineDelegate(MissingDelegate):
    """By athlete trend column: polyline over occasions; a missing occasion is a dashed ring and a gap."""

    def paint(self, painter, option, index):
        values = index.data(TrendRole)
        if values is None:
            return super().paint(painter, option, index)
        opt = self._draw_background(painter, option, index)
        present = [v for v in values if v is not None]
        t = theme.tokens()
        r = opt.rect.adjusted(8, 6, -8, -6)
        if not present or r.width() < 4 or r.height() < 4:
            return
        lo, hi = min(present), max(present)
        span = (hi - lo) or 1.0
        n = len(values)
        pts = []
        for i, v in enumerate(values):
            x = r.left() + (r.width() * i / (n - 1) if n > 1 else r.width() / 2)
            y = r.center().y() if v is None else r.bottom() - r.height() * (v - lo) / span
            pts.append((QPointF(x, y), v is None))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QPen(QColor(t["mod"]), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        for (a, a_missing), (b, b_missing) in zip(pts, pts[1:]):
            if not a_missing and not b_missing:
                painter.setPen(line)
                painter.drawLine(a, b)
        painter.setBrush(QColor(t["mod"]))
        painter.setPen(Qt.PenStyle.NoPen)
        for p, missing in pts:
            if not missing:
                painter.drawEllipse(p, 1.8, 1.8)
        ring = QPen(_bad(), 1.2, Qt.PenStyle.DashLine)
        painter.setPen(ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for p, missing in pts:
            if missing:
                painter.drawEllipse(p, 3.5, 3.5)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(90, 28)


class PivotTrendModel(QAbstractTableModel):
    """Athlete | occasion cells | Δ (last - first) | Trend over a ByAthleteModel; Δ is missing when either end is."""

    def __init__(self, source: ByAthleteModel, parent=None) -> None:
        super().__init__(parent)
        self.source = source
        self._n = source.columnCount()

    @property
    def trend_column(self) -> int:
        return self._n + 2

    def _values(self, row: int) -> list[Any]:
        return [self.source.data(self.source.index(row, c), SortRole) for c in range(self._n)]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self.source.rowCount()

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else self._n + 3

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return section + 1
        if section == 0:
            return "Athlete"
        if section <= self._n:  # the occasion value alone; the column set is the occasion variable
            return str(self.source.headerData(section - 1, Qt.Orientation.Horizontal)).removeprefix(f"{self.source.occasion} ")
        return "Δ" if section == self._n + 1 else "Trend"

    def _delta(self, row: int) -> float | None:
        values = self._values(row)
        if not values or values[0] is None or values[-1] is None or len(values) < 2:
            return None
        if not all(isinstance(v, (int, float)) for v in (values[0], values[-1])):
            return None
        return values[-1] - values[0]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if col == 0:
            name = self.source.headerData(row, Qt.Orientation.Vertical)
            if role in (Qt.ItemDataRole.DisplayRole, SortRole):
                return name
            if role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setBold(True)
                return font
            return None
        if col <= self._n:
            return self.source.data(self.source.index(row, col - 1), role)
        if col == self._n + 1:
            delta = self._delta(row)
            if role == MissingRole:
                return delta is None
            if role == SortRole:
                return delta
            if role == Qt.ItemDataRole.DisplayRole:
                return MISSING_TEXT if delta is None else f"{delta:+.3g}"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return None
        if role == TrendRole:
            return [v if isinstance(v, (int, float)) else None for v in self._values(row)]
        return None


class _SortProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(SortRole)

    def lessThan(self, left, right) -> bool:
        a, b = left.data(SortRole), right.data(SortRole)
        if a is None or b is None:  # missing sorts after every value
            return a is not None and b is None
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class _Collapsible(QFrame):
    """A header toggle over a body widget (the Library section)."""

    def __init__(self, title: str, body: QWidget, expanded: bool, parent=None) -> None:
        super().__init__(parent)
        self.body = body
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.setAccessibleName(f"{title} section")
        self.toggle.toggled.connect(self._toggled)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(body)
        self.toggle.setChecked(expanded)
        self._toggled(expanded)

    def _toggled(self, open_: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)
        self.body.setVisible(open_)

    def set_expanded(self, open_: bool) -> None:
        self.toggle.setChecked(open_)


def _table(delegate: QStyledItemDelegate | None = None) -> QTableView:
    view = QTableView()
    view.setAlternatingRowColors(True)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setShowGrid(False)
    view.verticalHeader().setDefaultSectionSize(28)
    view.verticalHeader().setMinimumWidth(28)
    view.horizontalHeader().setStretchLastSection(True)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    view.setItemDelegate(delegate or MissingDelegate(view))
    return view


class DataPane(QWidget):
    """Table selector, segmented By athlete / Variables / Rows views, and the Library section."""

    variable_selected = Signal(str)
    dataset_changed = Signal(str, str)  # snapshot id, table ("" = nothing open)

    def __init__(self, service: Any, navigator: QWidget | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DataPane")
        self.service = service
        self.snapshot_id = ""
        self.table = ""
        self._detail: dict[str, Any] = {}
        self._variables_model = VariablesModel()
        self._rows_model: RowsModel | None = None
        self._by_athlete_key: tuple | None = None
        self._selected = ""
        self._columns: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.library: _Collapsible | None = None
        if navigator is not None:
            navigator.setMinimumHeight(120)
            navigator.setMaximumHeight(200)
            self.library = _Collapsible("Library", navigator, True)
            layout.addWidget(self.library)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.table_combo = QComboBox()
        self.table_combo.setAccessibleName("Table")
        self.table_combo.setMinimumContentsLength(12)
        self.table_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.table_combo.currentTextChanged.connect(self._table_chosen)
        bar.addWidget(self.table_combo)
        bar.addStretch(1)
        self.segmented = QFrame()
        self.segmented.setObjectName("Segmented")
        seg = QHBoxLayout(self.segmented)
        seg.setContentsMargins(2, 2, 2, 2)
        seg.setSpacing(0)
        self.view_buttons = QButtonGroup(self)
        self._view_button: dict[str, QPushButton] = {}
        for name in VIEWS:
            button = QPushButton(name)
            button.setCheckable(True)
            button.setAccessibleName(f"{name} view")
            button.clicked.connect(lambda _c=False, name=name: self.set_view(name))
            self.view_buttons.addButton(button)
            self._view_button[name] = button
            seg.addWidget(button)
        bar.addWidget(self.segmented)
        layout.addLayout(bar)

        # By athlete: value picker + pivot
        self.value_combo = QComboBox()
        self.value_combo.setAccessibleName("Value shown by athlete")
        self.value_combo.currentIndexChanged.connect(lambda _i: self._build_by_athlete())
        self.athlete_view = _table(SparklineDelegate(self))
        self.athlete_note = QLabel()
        self.athlete_note.setObjectName("PaneContext")
        self.athlete_note.setWordWrap(True)
        athlete_page = QWidget()
        page = QVBoxLayout(athlete_page)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(6)
        value_row = QHBoxLayout()
        value_row.addWidget(QLabel("Value"))
        value_row.addWidget(self.value_combo, 1)
        page.addLayout(value_row)
        page.addWidget(self.athlete_view, 1)
        page.addWidget(self.athlete_note)

        self.variables_view = _table(MissingDelegate(self))
        self.variables_view.setItemDelegateForColumn(0, VariableNameDelegate(self.variables_view))
        self.variables_view.setDragEnabled(True)
        self.variables_view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.variables_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.variables_view.setSortingEnabled(True)
        self.variables_view.verticalHeader().hide()
        self.rows_view = _table()
        self.rows_view.horizontalHeader().setSectionsClickable(True)
        self.rows_view.horizontalHeader().sectionClicked.connect(self._column_clicked)
        self.rows_view.verticalScrollBar().valueChanged.connect(self._maybe_fetch_more)
        self.rows_view.horizontalHeader().setStretchLastSection(False)

        self.empty = QLabel("Open a dataset or study to see its data.")
        self.empty.setObjectName("PaneEmpty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.stack = QStackedWidget()
        for widget in (self.empty, athlete_page, self.variables_view, self.rows_view):
            self.stack.addWidget(widget)
        self._pages = {"By athlete": athlete_page, "Variables": self.variables_view, "Rows": self.rows_view}
        layout.addWidget(self.stack, 1)
        self.footer = QLabel()
        self.footer.setObjectName("PaneContext")
        self.footer.setAccessibleName("Dataset summary")
        layout.addWidget(self.footer)
        self._current_view = "Variables"
        self._set_controls_enabled(False)

    # ------------------------------------------------------------------ public API
    def set_dataset(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        self.snapshot_id, self._detail = snapshot_id, detail
        tables = [t["name"] for t in detail.get("tables", [])]
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        self.table_combo.addItems(tables)
        self.table_combo.blockSignals(False)
        if not tables:
            self.clear()
            return
        # prefer a longitudinal table (subject + occasion), else the first
        preferred = next((t for t in tables if t in STUDY_FOR_TABLE), None) or next(
            (t for t in tables if self._longitudinal(detail, t)), tables[0])
        self.table_combo.setCurrentText(preferred)
        self._load_table(preferred)
        if self.library is not None:
            self.library.set_expanded(False)

    def clear(self) -> None:
        self.snapshot_id = self.table = ""
        self._detail = {}
        self._variables_model = VariablesModel()
        self._rows_model = None
        self._by_athlete_key = None
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        self.table_combo.blockSignals(False)
        self.variables_view.setModel(None)
        self.rows_view.setModel(None)
        self.athlete_view.setModel(None)
        self.footer.setText("")
        self.stack.setCurrentWidget(self.empty)
        self._set_controls_enabled(False)
        self.dataset_changed.emit("", "")

    def variable_types(self) -> dict[str, str]:
        return self._variables_model.variable_types()

    def variables(self):
        return self._variables_model.variables()

    def current_view(self) -> str:
        return self._current_view

    def set_view(self, name: str) -> None:
        if name not in VIEWS:
            raise ValueError(name)
        self._current_view = name
        self._view_button[name].setChecked(True)
        if not self.snapshot_id:
            return
        if name == "By athlete":
            self._build_by_athlete()
        self.stack.setCurrentWidget(self._pages[name])

    def selected_variable(self) -> str:
        return self._selected

    def select_variable(self, name: str) -> None:
        """Select a variable by name in the Variables view (and announce it)."""
        for row, variable in enumerate(self._variables_model.variables()):
            if variable.name == name:
                proxy = self.variables_view.model()
                index = proxy.mapFromSource(self._variables_model.index(row, 0))
                self.variables_view.selectRow(index.row())
                self.variables_view.setCurrentIndex(index)
                return

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _longitudinal(detail: dict[str, Any], table: str) -> bool:
        from .data_models import variables_from_detail

        types = {v.name: v.type for v in variables_from_detail(detail, table)}
        return IDENTIFIER in types.values() and ORDINAL in types.values()

    def _set_controls_enabled(self, on: bool) -> None:
        self.table_combo.setEnabled(on)
        for button in self._view_button.values():
            button.setEnabled(on)

    def _table_chosen(self, name: str) -> None:
        if name and name != self.table and self._detail:
            self._load_table(name)

    def _load_table(self, table: str) -> None:
        self.table = table
        self._by_athlete_key = None
        self._variables_model = VariablesModel.from_service(self.service, self.snapshot_id, table, self)
        proxy = _SortProxy(self)
        proxy.setSourceModel(self._variables_model)
        self.variables_view.setModel(proxy)
        self.variables_view.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)  # natural order
        for col, width in enumerate((190, 76, 46, 40, 56, 66, 90)):
            self.variables_view.setColumnWidth(col, width)
        self.variables_view.selectionModel().currentRowChanged.connect(self._variable_row_changed)
        self._rows_model = RowsModel(self.service, self.snapshot_id, table, self)
        self._rows_model.fetchMore()
        self._columns = self._rows_model.columns
        self.rows_view.setModel(self._rows_model)
        meta = next(t for t in self._detail["tables"] if t["name"] == table)
        self.footer.setText(f"{int(meta['rows']):,} rows  ·  {self.snapshot_id}")
        numeric = [v.name for v in self._variables_model.variables() if v.type == NUMERICAL]
        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        self.value_combo.addItems(numeric)
        self.value_combo.blockSignals(False)
        self._set_controls_enabled(True)
        self._view_button["By athlete"].setEnabled(self._pivot_columns() is not None and bool(numeric))
        view = self._current_view if self._view_button[self._current_view].isEnabled() else "Variables"
        self.set_view(view)
        self.dataset_changed.emit(self.snapshot_id, table)

    def _pivot_columns(self) -> tuple[str, str] | None:
        types = self.variable_types()
        occasion = next((n for n, t in types.items() if t == ORDINAL and n == "occasion"), None)
        subject = "subject_id" if types.get("subject_id") == IDENTIFIER else next(
            (n for n, t in types.items() if t == IDENTIFIER and n.endswith("subject_id")), None)
        return (subject, occasion) if subject and occasion else None

    def _build_by_athlete(self) -> None:
        pivot = self._pivot_columns()
        value = self.value_combo.currentText()
        if pivot is None or not value or not self.snapshot_id:
            return
        key = (self.snapshot_id, self.table, value)
        if key == self._by_athlete_key:
            return
        self._by_athlete_key = key
        source = ByAthleteModel(self.service, self.snapshot_id, self.table, pivot[0], pivot[1], value,
                                self, max_rows=BY_ATHLETE_MAX_ROWS)
        model = PivotTrendModel(source, self)
        proxy = _SortProxy(self)
        proxy.setSourceModel(model)
        self.athlete_view.setModel(proxy)
        self.athlete_view.setSortingEnabled(True)
        self.athlete_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.athlete_view.setItemDelegateForColumn(model.trend_column, SparklineDelegate(self.athlete_view))
        for col in range(model.columnCount()):
            self.athlete_view.setColumnWidth(col, 66 if col == 0 else 58 if col <= model.trend_column - 2 else 56)
        total = int(next(t for t in self._detail["tables"] if t["name"] == self.table)["rows"])
        cells = source.rowCount() * source.columnCount()
        note = f"{source.rowCount()} subjects × {source.columnCount()} occasions"
        if source.truncated:
            note += f"  ·  first {BY_ATHLETE_MAX_ROWS:,} of {total:,} rows only"
        elif total > cells:
            note += f"  ·  {total - cells} rows share a subject and occasion; the last value is shown"
        self.athlete_note.setText(note)

    def _variable_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if current.isValid():
            variable = current.data(VariableRole)
            self._selected = variable.name
            self.variable_selected.emit(variable.name)

    def _column_clicked(self, section: int) -> None:
        if 0 <= section < len(self._columns):
            self._selected = self._columns[section]
            self.variable_selected.emit(self._selected)

    def _maybe_fetch_more(self, value: int) -> None:
        model = self._rows_model
        if model is not None and value >= self.rows_view.verticalScrollBar().maximum() - 4 and model.canFetchMore():
            model.fetchMore()
