"""Study destinations arranged around an interactive native 3D instrument."""

from math import cos, pi, sin

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QRadialGradient, QVector3D
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

DESTINATIONS = (
    ("people", "People", "Athletes, groups and follow-ups"),
    ("sources", "Sources & quality", "Imports, permissions and data checks"),
    ("design", "Study setup", "Research question, plan and cohort"),
    ("series", "Compare experiments", "Individual results across athletes"),
    ("archive", "Reports & archive", "Reports, saved analyses and revisions"),
    ("methods", "Study analysis", "Run and review study-level methods"),
)
_COLORS = ("#b28b51", "#809b83", "#d39677", "#c4a477", "#b98180", "#8eaaab")
_NODES = (
    QVector3D(-.78, .45, .4), QVector3D(-.28, -.8, .54), QVector3D(.63, -.56, .52),
    QVector3D(.87, .35, .27), QVector3D(.16, .89, .41), QVector3D(-.14, .04, 1),
)
_ANGLES = tuple(i * pi / 48 for i in range(97))
_RINGS = (
    tuple(QVector3D(cos(a), sin(a), 0) for a in _ANGLES),
    tuple(QVector3D(cos(a), .46 * sin(a), .888 * sin(a)) for a in _ANGLES),
    tuple(QVector3D(.36 * cos(a), sin(a), .933 * cos(a)) for a in _ANGLES),
)


class StudyInstrument(QWidget):
    opened = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(260, 250)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Rotatable study map")
        self.setAccessibleDescription("Arrow keys rotate the map. Tab moves to the study destinations.")
        self.setMouseTracking(True)
        self._anchor = None
        self._moved = False
        self._highlight = -1
        self.reset_view()

    def sizeHint(self):
        return QSize(520, 390)

    def reset_view(self):
        self._yaw, self._pitch = -.25, .19
        self.update()

    def highlight(self, index):
        if self._highlight != index:
            self._highlight = index
            self.update()

    def _rotate(self, point):
        cx, sx = cos(self._yaw), sin(self._yaw)
        cy, sy = cos(self._pitch), sin(self._pitch)
        x, z = point.x() * cx + point.z() * sx, point.z() * cx - point.x() * sx
        return QVector3D(x, point.y() * cy - z * sy, point.y() * sy + z * cy)

    def _project(self, point):
        point = self._rotate(point)
        radius = min(self.width() * .37, self.height() * .36)
        distance = 3.6 / (3.6 - point.z())
        at = QPointF(self.width() * .5 + point.x() * radius * distance,
                     self.height() * .5 - point.y() * radius * distance)
        return at, point.z()

    def _node_at(self, position):
        options = []
        for index, vertex in enumerate(_NODES):
            point, depth = self._project(vertex * 1.17)
            if (point - position).manhattanLength() < 24:
                options.append((depth, index))
        return max(options)[1] if options else -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._anchor = event.position()
            self._moved = False
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()

    def mouseMoveEvent(self, event):
        if self._anchor is not None:
            delta = event.position() - self._anchor
            self._moved |= delta.manhattanLength() >= 3
            if self._moved:
                self._yaw += delta.x() * .011
                self._pitch = max(-1.35, min(1.35, self._pitch + delta.y() * .011))
                self._anchor = event.position()
                self.update()
            return
        index = self._node_at(event.position())
        self.highlight(index)
        self.setToolTip(DESTINATIONS[index][1] if index >= 0 else "Drag to rotate the study map")
        shape = Qt.CursorShape.PointingHandCursor if index >= 0 else Qt.CursorShape.OpenHandCursor
        self.setCursor(QCursor(shape))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._anchor is None:
            return
        index = self._node_at(event.position())
        if not self._moved and index >= 0:
            self.opened.emit(DESTINATIONS[index][0])
        self._anchor = None
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

    def leaveEvent(self, event):
        self.highlight(-1)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        arrows = {Qt.Key.Key_Left: (-.11, 0), Qt.Key.Key_Right: (.11, 0),
                  Qt.Key.Key_Up: (0, -.11), Qt.Key.Key_Down: (0, .11)}
        if event.key() in arrows:
            x, y = arrows[event.key()]
            self._yaw += x
            self._pitch = max(-1.35, min(1.35, self._pitch + y))
            self.update()
        elif event.key() == Qt.Key.Key_Home:
            self.reset_view()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        centre = bounds.center()
        field = QRadialGradient(centre, max(self.width(), self.height()) * .62, centre - QPointF(32, 62))
        field.setColorAt(0, QColor("#394345"))
        field.setColorAt(.55, QColor("#263237"))
        field.setColorAt(1, QColor("#152226"))
        painter.setPen(QPen(QColor("#546065"), 1))
        painter.setBrush(field)
        painter.drawRoundedRect(bounds, 14, 14)
        extent = min(self.width(), self.height()) * .43
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#556168"), .6, Qt.PenStyle.DotLine))
        painter.drawEllipse(centre, extent, extent)
        painter.drawLine(QPointF(16, centre.y()), QPointF(self.width() - 16, centre.y()))
        painter.drawLine(QPointF(centre.x(), 16), QPointF(centre.x(), self.height() - 16))

        segments = []
        for ring in _RINGS:
            points = [self._project(vertex) for vertex in ring]
            segments.extend((min(a[1], b[1]), a[0], b[0]) for a, b in zip(points, points[1:]))
        painter.setPen(Qt.PenStyle.NoPen)
        globe = QRadialGradient(centre, extent * .26, centre - QPointF(extent * .08, extent * .1))
        for stop, color in ((0, "#fbdf9e"), (.37, "#cfaa63"), (.8, "#8b7043"), (1, "#453d30")):
            globe.setColorAt(stop, QColor(color))
        for back in (True, False):
            for depth, first, second in segments:
                if (depth < 0) == back:
                    painter.setPen(QPen(QColor("#77705f" if back else "#b99d68"), 1.1 if back else 1.8))
                    painter.drawLine(first, second)
            if back:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(globe)
                painter.drawEllipse(centre, extent * .26, extent * .26)
        nodes = sorted(((*self._project(vertex * 1.17), i) for i, vertex in enumerate(_NODES)), key=lambda item: item[1])
        for point, depth, index in nodes:
            size = 8 + depth * 2
            selected = self._highlight == index
            if selected:
                painter.setPen(QPen(QColor("#f6e4bb"), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(point, size + 5, size + 5)
            light = QColor(_COLORS[index])
            point_fill = QRadialGradient(point - QPointF(3, 4), size * 1.7)
            point_fill.setColorAt(0, light.lighter(145))
            point_fill.setColorAt(1, light.darker(200))
            painter.setPen(QPen(light, 1))
            painter.setBrush(point_fill)
            painter.drawEllipse(point, size, size)
        painter.setPen(QColor("#e3d3b5"))
        painter.setFont(QFont("Segoe UI", 10))
        text = DESTINATIONS[self._highlight][1] if self._highlight >= 0 else "Drag to rotate"
        painter.drawText(bounds.adjusted(16, 0, -16, -14), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, text)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#f4cf92"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bounds.adjusted(2, 2, -2, -2), 12, 12)


class StudyHome(QWidget):
    destination = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("StudyHome")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 14)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        self.title = QLabel("Open a study")
        self.title.setObjectName("StudyHeading")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        heading.addWidget(self.title, 1)
        layout.addLayout(heading)
        self.summary = QLabel()
        self.summary.setObjectName("StudySummary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.body = QWidget()
        split = QHBoxLayout(self.body)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(22)
        self.instrument = StudyInstrument()
        self.instrument.opened.connect(self.destination)
        split.addWidget(self.instrument, 4)
        links = QVBoxLayout()
        links.setSpacing(6)
        self.buttons = {}
        for key, title, description in DESTINATIONS:
            button = QPushButton(title.replace('&', '&&'))
            button.setObjectName("StudyDestination")
            button.setAccessibleDescription(description)
            button.setToolTip(description)
            button.clicked.connect(lambda _checked=False, key=key: self.destination.emit(key))
            button.installEventFilter(self)
            self.buttons[key] = button
            links.addWidget(button, 1)
        split.addLayout(links, 3)
        layout.addWidget(self.body, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open study…")
        self.new_button = QPushButton("New study…")
        self.import_button = QPushButton("Add measurements…")
        self.import_button.setProperty("primary", True)
        for button in (self.open_button, self.new_button, self.import_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.set_study({})

    def eventFilter(self, widget, event):
        if widget in self.buttons.values():
            if event.type() in (QEvent.Type.Enter, QEvent.Type.FocusIn):
                self.instrument.highlight(list(self.buttons.values()).index(widget))
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.FocusOut):
                self.instrument.highlight(-1)
        return super().eventFilter(widget, event)

    def set_study(self, detail):
        active = bool(detail.get("workspace"))
        revision = detail.get("active_data_revision_id")
        study = detail.get("study", {})
        self.title.setText(study.get("title") if active else "Research studies")
        self.summary.setText("Choose a study to open its athletes and research." if not active else
                             "A study needs measurements before athlete comparisons are available." if not revision else "")
        self.summary.setVisible(bool(self.summary.text()))
        self.body.setVisible(active)
        self.open_button.setVisible(not active)
        self.new_button.setVisible(not active)
        self.import_button.setVisible(active and not revision)
        for key in ("people", "series", "methods"):
            self.buttons[key].setEnabled(bool(revision))
