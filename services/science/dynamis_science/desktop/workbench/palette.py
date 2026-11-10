"""Command palette (Ctrl+K): a frameless dialog that filters registered QActions."""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMenuBar,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

_ACTION = Qt.ItemDataRole.UserRole + 1
_CATEGORY = Qt.ItemDataRole.UserRole + 2


class _CategoryDelegate(QStyledItemDelegate):
    """Draws the command's category right-aligned in the dim ink."""

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        category = index.data(_CATEGORY)
        if category:
            painter.save()
            painter.setPen(option.palette.placeholderText().color())
            rect = option.rect.adjusted(0, 0, -12, 0)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, category)
            painter.restore()


class CommandPalette(QDialog):
    """Only enabled, visible actions are offered; Enter runs, Esc closes."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("CommandPalette")
        self.setAccessibleName("Command palette")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._commands: list[tuple[QAction, str]] = []
        self.input = QLineEdit()
        self.input.setObjectName("PaletteInput")
        self.input.setAccessibleName("Search commands")
        self.input.setPlaceholderText("Type a command…")
        self.model = QStandardItemModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list = QListView()
        self.list.setObjectName("PaletteList")
        self.list.setAccessibleName("Matching commands")
        self.list.setModel(self.proxy)
        self.list.setItemDelegate(_CategoryDelegate(self.list))
        self.list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hint = QLabel("↑ ↓ move  ·  ↵ run  ·  Esc close")
        hint.setObjectName("PaletteHint")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self.input)
        layout.addWidget(self.list, 1)
        layout.addWidget(hint)
        self.input.textChanged.connect(self._filter)
        self.input.returnPressed.connect(self._run_current)
        self.list.clicked.connect(lambda index: self._run(index))

    def add_action(self, action: QAction, category: str) -> None:
        if action.isSeparator() or action.menu() is not None or not action.text():
            return
        if all(existing is not action for existing, _ in self._commands):
            self._commands.append((action, category))

    def add_actions(self, actions, category: str) -> None:
        for action in actions:
            self.add_action(action, category)

    def add_menu(self, menu: QMenu | QMenuBar, category: str = "") -> None:
        for action in menu.actions():
            submenu = action.menu()
            if submenu is not None:
                self.add_menu(submenu, " ▸ ".join(filter(None, (category, action.text().replace("&", "")))))
            else:
                self.add_action(action, category)

    def commands(self) -> list[str]:
        """Texts of the commands currently on offer (for tests and the accessibility tree)."""
        return [self.proxy.index(row, 0).data() for row in range(self.proxy.rowCount())]

    def popup(self) -> None:
        self.model.clear()
        for action, category in self._commands:
            if action.isEnabled() and action.isVisible():
                item = QStandardItem(action.text().replace("&", "").rstrip("…").strip())
                item.setData(action, _ACTION)
                item.setData(category, _CATEGORY)
                item.setToolTip(action.toolTip())
                self.model.appendRow(item)
        self.input.clear()
        self._filter("")
        host = self.parentWidget().window()
        width = min(560, max(360, host.width() - 80))
        rows = min(self.proxy.rowCount(), 9)
        self.resize(width, 90 + rows * 34)
        top_left = host.mapToGlobal(host.rect().topLeft())
        self.move(top_left.x() + (host.width() - width) // 2, top_left.y() + min(110, host.height() // 6))
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())
        if self.proxy.rowCount():
            self.list.setCurrentIndex(self.proxy.index(0, 0))

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.proxy.rowCount():
            step = 1 if key == Qt.Key.Key_Down else -1
            row = (self.list.currentIndex().row() + step) % self.proxy.rowCount()
            self.list.setCurrentIndex(self.proxy.index(row, 0))
            return
        super().keyPressEvent(event)

    def _run_current(self) -> None:
        self._run(self.list.currentIndex())

    def _run(self, index) -> None:
        if not index.isValid():
            return
        action = index.data(_ACTION)
        self.accept()
        action.trigger()
