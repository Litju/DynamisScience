"""Options pane of the RES-620 workbench: variable list, role boxes and per-analysis option sections.

The pane never mutates the spec.  It checks `spec.can_accept`, shakes a rejecting role box and emits
`message`; accepted assignments and option edits go out as signals for the controller to apply.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStackedLayout, QStyledItemDelegate, QListView,
    QVBoxLayout, QWidget,
)

from .. import theme
from .data_models import VARIABLE_MIME, Variable, VariableRole, VariablesModel, variables_from_mime
from .data_pane import VariableNameDelegate, _Collapsible, paint_type_badge
from .spec import ROLE_RULES, AnalysisSpec, RoleRule, method_status

_TYPE_WORD = {"numerical": "numeric", "categorical": "categorical", "ordinal": "ordinal", "identifier": "id"}

# kind -> [(section title, [(option key, widget kind, label, config)])]; keys are AnalysisSpec option names.
OPTION_SECTIONS: dict[str, list[tuple[str, list[tuple[str, str, str, dict]]]]] = {
    "mixed_model": [("Model", [
        ("reference_occasion", "int", "Reference occasion", {"min": 1, "max": 99}),
        ("contrast_occasion", "int", "Contrast occasion", {"min": 2, "max": 99}),
        ("alpha", "float", "Alpha", {"min": 0.001, "max": 0.5, "step": 0.01, "decimals": 3}),
        ("excluded_subject_ids", "list", "Exclude subjects", {}),
    ])],
    "reliability": [("Model", [
        ("activity", "text", "Activity", {}),
        ("max_trials", "int", "First k trials", {"min": 2, "max": 8}),
        ("excluded_subject_ids", "list", "Exclude subjects", {}),
    ])],
    "athlete_change": [("Change", [
        ("reference_occasion", "int", "From occasion", {"min": 0, "max": 99, "special": "First"}),
        ("contrast_occasion", "int", "To occasion", {"min": 0, "max": 99, "special": "Last"}),
    ])],
    "ttest": [("Comparison", [
        ("level_1", "level", "Level 1", {}),
        ("level_2", "level", "Level 2", {}),
    ])],
}
# fixed (non-editable) properties of the method, shown so nothing is implied silently
FIXED_INFO = {
    "mixed_model": ("Random effects", "Intercept + occasion slope", "Estimation", "ML (qualified engine)"),
    "reliability": ("Statistic", "ICC(3,1)", "Trials", "First k per subject, acquisition order"),
}


class RoleBox(QListWidget):
    """Small list of assigned variables: accepts drops, Delete removes the selected one."""

    dropped = Signal(list)
    remove_requested = Signal(str)
    focused = Signal()

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self.placeholder = placeholder
        self.setObjectName("RoleBox")
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setItemDelegate(_RoleItemDelegate(self))
        self.setMinimumHeight(34)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(VARIABLE_MIME):
            self._set_hover(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    dragMoveEvent = dragEnterEvent

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)

    def dropEvent(self, event) -> None:
        self._set_hover(False)
        names = variables_from_mime(event.mimeData())
        if names:
            event.acceptProposedAction()
            self.dropped.emit(names)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.currentItem() is not None:
            self.remove_requested.emit(self.currentItem().data(Qt.ItemDataRole.UserRole + 1))
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            self.remove_requested.emit(item.data(Qt.ItemDataRole.UserRole + 1))

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def _set_hover(self, hover: bool) -> None:
        self.setProperty("dropHover", hover)
        theme.repolish(self)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count() == 0:  # placeholder text has no stylesheet equivalent
            painter = QPainter(self.viewport())
            painter.setPen(QColor(theme.tokens()["dim_text"]))
            painter.drawText(self.viewport().rect().adjusted(10, 0, -10, 0),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.placeholder)
            painter.end()


class _RoleItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        opt = type(option)(option)
        self.initStyleOption(opt, index)
        text, opt.text = opt.text, ""
        opt.widget.style().drawControl(opt.widget.style().ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        r = opt.rect
        paint_type_badge(painter, QRectF(r.left() + 4, r.center().y() - 8, 20, 16), index.data(Qt.ItemDataRole.UserRole))
        painter.save()
        painter.setPen(QColor(theme.tokens()["text"]))
        painter.drawText(r.adjusted(30, 0, -22, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        painter.setPen(QColor(theme.tokens()["dim_text"]))
        painter.drawText(r.adjusted(0, 0, -8, 0), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), "✕")
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 26))
        return size


class RoleSlot(QFrame):
    """Caption + RoleBox.  `shake()` plays the short rejection animation."""

    def __init__(self, role: str, rule: RoleRule, parent=None) -> None:
        super().__init__(parent)
        self.role, self.rule = role, rule
        self._shake = 0
        if rule.max == 0:
            placeholder = "Not available in the qualified engine"
        else:
            types = " / ".join(_TYPE_WORD[t] for t in sorted(rule.types))
            placeholder = f"Drop a variable ({types})" if rule.max == 1 else f"Drop variables ({types})"
        self.caption = QLabel(rule.label + (" *" if rule.min else ""))
        self.caption.setObjectName("PaneContext")
        self.caption.setWordWrap(True)
        self.box = RoleBox(placeholder)
        self.box.setAccessibleName(f"{rule.label} role")
        self.box.setToolTip(f"{rule.label}: drop a variable or press Assign; Delete removes the selected one")
        self.box.setFixedHeight(36 if rule.max in (0, 1) else 76)
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(3)
        self._layout.addWidget(self.caption)
        self._layout.addWidget(self.box)
        self._apply_shake(0)
        self._animation = QPropertyAnimation(self, b"shake_offset", self)
        self._animation.setDuration(280)
        self._animation.setKeyValueAt(0, 0)
        for stop, value in ((0.2, -8), (0.4, 8), (0.6, -5), (0.8, 4), (1, 0)):
            self._animation.setKeyValueAt(stop, value)
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)

    def _apply_shake(self, offset: int) -> None:
        self._shake = offset
        self._layout.setContentsMargins(max(offset, 0) + 0, 0, max(-offset, 0) + 0, 0)

    def get_shake(self) -> int:
        return self._shake

    shake_offset = Property(int, get_shake, _apply_shake)

    def shake(self) -> None:
        self._animation.stop()
        self._animation.start()

    @property
    def shaking(self) -> bool:
        return self._animation.state() == QPropertyAnimation.State.Running

    def set_names(self, names: list[str], types: dict[str, str]) -> None:
        self.box.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, types.get(name))
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self.box.addItem(item)

    def names(self) -> list[str]:
        return [self.box.item(i).data(Qt.ItemDataRole.UserRole + 1) for i in range(self.box.count())]


class _VariableList(QListView):
    assign_requested = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.assign_requested.emit()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.assign_requested.emit()


class _AssignedDelegate(VariableNameDelegate):
    """Variable list rows: variables already in a role are dimmed with a dot, as in the design."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.assigned: set[str] = set()

    def paint(self, painter, option, index) -> None:
        variable = index.data(VariableRole)
        if variable.name in self.assigned:
            painter.save()
            painter.setOpacity(0.5)
            super().paint(painter, option, index)
            painter.restore()
            painter.setPen(QColor(theme.tokens()["accent"]))
            painter.setBrush(QColor(theme.tokens()["accent"]))
            r = option.rect
            painter.drawEllipse(r.right() - 12, r.center().y() - 2, 4, 4)
        else:
            super().paint(painter, option, index)


class OptionsPane(QWidget):
    variable_assigned = Signal(str, str)  # role, variable
    variable_removed = Signal(str, str)
    option_changed = Signal(str, object)
    message = Signal(str)  # rejection and status text for the status bar

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OptionsPane")
        self.spec: AnalysisSpec | None = None
        self.slots: dict[str, RoleSlot] = {}
        self.active_role = ""
        self._kind = ""
        self._option_widgets: dict[str, QWidget] = {}
        self._syncing = False

        self.method_line = QLabel()
        self.method_line.setObjectName("PaneContext")
        self.method_line.setAccessibleName("Method qualification")
        self.method_line.setWordWrap(True)

        self.model = VariablesModel()
        self.var_list = _VariableList()
        self.var_list.setModel(self.model)
        self.var_list.setAccessibleName("Variables")
        self.var_list.setDragEnabled(True)
        self.var_list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.var_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.var_list.setUniformItemSizes(True)
        self.var_list.setMinimumWidth(96)
        self.var_list.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.delegate = _AssignedDelegate(self.var_list)
        self.var_list.setItemDelegate(self.delegate)
        self.var_list.assign_requested.connect(self.assign_selected)
        self.assign_button = QPushButton("Assign  ▸")
        self.assign_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.assign_button.setAccessibleName("Assign selected variable to the active role")
        self.assign_button.setToolTip("Assign the selected variable to the active role (Ctrl+Right)")
        self.assign_button.clicked.connect(self.assign_selected)
        QShortcut(QKeySequence("Ctrl+Right"), self, self.assign_selected).setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut)
        left = QVBoxLayout()
        left.setSpacing(4)
        caption = QLabel("Variables")
        caption.setObjectName("PaneContext")
        left.addWidget(caption)
        left.addWidget(self.var_list, 1)
        left.addWidget(self.assign_button)

        self.roles_layout = QVBoxLayout()
        self.roles_layout.setSpacing(8)
        self.roles_layout.addStretch(1)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addLayout(left, 6)
        top.addLayout(self.roles_layout, 5)

        self.issues = QFrame()
        self.issues.setObjectName("StaleBar")
        issues_layout = QVBoxLayout(self.issues)
        issues_layout.setContentsMargins(10, 6, 10, 6)
        self.issues_label = QLabel()
        self.issues_label.setWordWrap(True)
        self.issues_label.setAccessibleName("Validation issues")
        issues_layout.addWidget(self.issues_label)
        self.ready_label = QLabel()
        self.ready_label.setObjectName("PaneContext")
        self.ready_label.setWordWrap(True)

        self.options_layout = QVBoxLayout()
        self.options_layout.setSpacing(4)

        self.placeholder = QLabel("Choose an analysis in the ribbon.")
        self.placeholder.setObjectName("PaneEmpty")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)

        form = QWidget()
        body = QVBoxLayout(form)
        body.setContentsMargins(4, 4, 4, 8)
        body.setSpacing(10)
        body.addWidget(self.method_line)
        body.addLayout(top, 1)
        body.addWidget(self.issues)
        body.addWidget(self.ready_label)
        body.addLayout(self.options_layout)
        body.addStretch(1)
        self.form = form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(form)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self.placeholder)
        stack.addWidget(scroll)
        self._stack = stack
        form.setMinimumHeight(0)

    # ------------------------------------------------------------------ public API
    def set_variables(self, variables: list[Variable]) -> None:
        self.model = VariablesModel(variables)
        self.var_list.setModel(self.model)

    def set_placeholder(self, text: str) -> None:
        self.spec = None
        self._kind = ""
        self.placeholder.setText(text)
        self._stack.setCurrentIndex(0)

    def set_spec(self, spec: AnalysisSpec) -> None:
        if spec.kind not in ROLE_RULES:
            self.set_placeholder(f"{spec.kind} has no assignable variables.")
            return
        self.spec = spec
        self._stack.setCurrentIndex(1)
        if spec.kind != self._kind:
            self._rebuild(spec.kind)
        self._refresh()

    def role_names(self, role: str) -> list[str]:
        return self.slots[role].names()

    def issues_text(self) -> str:
        return self.issues_label.text() if self.issues.isVisible() or self.issues_label.text() else ""

    def assign_selected(self) -> None:
        """Assign the selected variable(s) to the active role (keyboard / button path)."""
        if self.spec is None or not self.active_role:
            return
        for index in self.var_list.selectionModel().selectedIndexes():
            self._assign(self.active_role, index.data(VariableRole).name)

    # ------------------------------------------------------------------ build
    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild(self, kind: str) -> None:
        self._kind = kind
        self.slots.clear()
        self._option_widgets.clear()
        self._clear_layout(self.roles_layout)
        self._clear_layout(self.options_layout)
        for role, rule in ROLE_RULES[kind].items():
            slot = RoleSlot(role, rule)
            slot.box.dropped.connect(lambda names, role=role: [self._assign(role, n) for n in names])
            slot.box.remove_requested.connect(lambda name, role=role: self.variable_removed.emit(role, name))
            slot.box.focused.connect(lambda role=role: self._set_active(role))
            self.slots[role] = slot
            self.roles_layout.addWidget(slot)
        self.roles_layout.addStretch(1)
        self._set_active(next((r for r, rule in ROLE_RULES[kind].items() if rule.max != 0), ""))
        info = FIXED_INFO.get(kind)
        sections = OPTION_SECTIONS.get(kind, [])
        if info or sections:
            for title, fields in sections:
                self.options_layout.addWidget(self._section(title, fields, info if title == sections[0][0] else None))
        else:
            note = QLabel("This analysis has no options beyond the variable roles.")
            note.setObjectName("PaneContext")
            note.setWordWrap(True)
            self.options_layout.addWidget(note)

    def _section(self, title: str, fields, info) -> QWidget:
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(18, 2, 0, 6)
        form.setHorizontalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        if info:
            for key, value in zip(info[0::2], info[1::2]):
                fixed = QLabel(value)
                fixed.setWordWrap(True)
                form.addRow(key, fixed)
        for key, widget_kind, label, cfg in fields:
            widget = self._option_widget(key, widget_kind, cfg)
            widget.setAccessibleName(label)
            self._option_widgets[key] = widget
            form.addRow(label, widget)
        return _Collapsible(title, body, True)

    def _option_widget(self, key: str, kind: str, cfg: dict) -> QWidget:
        if kind == "int":
            w = QSpinBox()
            w.setRange(cfg["min"], cfg["max"])
            if "special" in cfg:
                w.setSpecialValueText(cfg["special"])
            w.valueChanged.connect(lambda v, key=key, w=w, cfg=cfg: self._emit_option(key, None if "special" in cfg and v == w.minimum() else v))
        elif kind == "float":
            w = QDoubleSpinBox()
            w.setDecimals(cfg["decimals"])
            w.setRange(cfg["min"], cfg["max"])
            w.setSingleStep(cfg["step"])
            w.valueChanged.connect(lambda v, key=key: self._emit_option(key, v))
        else:
            w = QLineEdit()
            if kind == "list":
                w.setPlaceholderText("subject ids, comma separated")
                w.editingFinished.connect(lambda key=key, w=w: self._emit_option(
                    key, [p.strip() for p in w.text().split(",") if p.strip()]))
            elif kind == "level":
                w.setPlaceholderText("level value")
                w.editingFinished.connect(lambda key=key, w=w: self._emit_option(key, _level(w.text())))
            else:
                w.editingFinished.connect(lambda key=key, w=w: self._emit_option(key, w.text().strip()))
        return w

    def _emit_option(self, key: str, value: Any) -> None:
        if not self._syncing:
            self.option_changed.emit(key, value)

    # ------------------------------------------------------------------ refresh
    def _set_active(self, role: str) -> None:
        self.active_role = role
        rule = ROLE_RULES.get(self._kind, {}).get(role)
        self.assign_button.setToolTip(f"Assign the selected variable to {rule.label} (Ctrl+Right)" if rule else "")
        self.assign_button.setEnabled(bool(rule))

    def _refresh(self) -> None:
        spec = self.spec
        assert spec is not None
        types = spec.variable_types
        for role, slot in self.slots.items():
            slot.set_names(spec.role(role), types)
        self.delegate.assigned = {n for names in spec.roles.values() for n in names}
        self.var_list.viewport().update()
        st = method_status(spec.kind)
        bits = [st["status"].upper()]
        if st["method_id"]:
            bits.append(f"{st['method_id']} v{st['version']}" + (f" · {st['record']}" if st["record"] else ""))
        elif st["status"] == "descriptive":
            bits.append("live workbench descriptive · no method record · cannot be promoted")
        elif st["status"] == "not qualified":
            bits.append("exploratory only; cannot be promoted")
        self.method_line.setText("  ·  ".join(bits))
        self._syncing = True
        try:
            options = spec.effective_options()
            for key, widget in self._option_widgets.items():
                value = options.get(key)
                if isinstance(widget, QSpinBox):
                    widget.setValue(widget.minimum() if value is None else int(value))
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QLineEdit) and not widget.hasFocus():
                    widget.setText(", ".join(map(str, value)) if isinstance(value, list) else "" if value is None else str(value))
        finally:
            self._syncing = False
        errors = [i["message"] for i in spec.validate() if i["severity"] == "error"]
        self.issues.setVisible(bool(errors))
        self.issues_label.setText("<br>".join(f"⚠ {m}" for m in errors))
        self.ready_label.setVisible(not errors)
        self.ready_label.setText("Ready to run  ·  Ctrl+Enter")

    # ------------------------------------------------------------------ assignment
    def _assign(self, role: str, name: str) -> None:
        spec = self.spec
        if spec is None:
            return
        rule = ROLE_RULES[spec.kind].get(role)
        check = spec
        if rule is not None and rule.max == 1 and spec.role(role) and name not in spec.role(role):
            check = dataclasses.replace(spec, roles={**spec.roles, role: []})  # a single slot replaces its occupant
        problem = check.can_accept(role, name)
        if problem:
            self.message.emit(problem)
            if role in self.slots:
                self.slots[role].shake()
            return
        if name in spec.role(role):
            return
        self.variable_assigned.emit(role, name)


def _level(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    return int(text) if text.lstrip("-").isdigit() else text
