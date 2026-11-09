"""Interactive native inspector for persisted scientific provenance DAGs."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class LineageDialog(QDialog):
    def __init__(self, graph: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scientific provenance lineage")
        self.resize(1180, 700)
        self.graph = graph
        self.scene = QGraphicsScene(self)
        self.node_items: dict[str, QGraphicsRectItem] = {}
        self.node_labels: list[QGraphicsTextItem] = []
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        layout = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        split.addWidget(self.view)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)

        controls = QHBoxLayout()
        controls.addStretch(1)
        fit = QPushButton("Fit graph")
        fit.clicked.connect(
            lambda: self.view.fitInView(
                self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
            )
        )
        controls.addWidget(fit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        controls.addWidget(buttons)
        layout.addLayout(controls)

        positions = self._positions(nodes, edges)
        for edge in edges:
            source = positions.get(edge.get("source"))
            target = positions.get(edge.get("target"))
            if source is None or target is None:
                continue
            start = QPointF(source.x() + 190, source.y() + 34)
            end = QPointF(target.x(), target.y() + 34)
            line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
            line.setPen(QPen(QColor("#788b99"), 1.6))
            self.scene.addItem(line)
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            wing = 8
            points = QPolygonF(
                [
                    end,
                    QPointF(
                        end.x() - wing * math.cos(angle - 0.45),
                        end.y() - wing * math.sin(angle - 0.45),
                    ),
                    QPointF(
                        end.x() - wing * math.cos(angle + 0.45),
                        end.y() - wing * math.sin(angle + 0.45),
                    ),
                ]
            )
            arrow = QGraphicsPolygonItem(points)
            arrow.setPen(QPen(QColor("#788b99"), 1))
            arrow.setBrush(QBrush(QColor("#788b99")))
            self.scene.addItem(arrow)

        for node in nodes:
            position = positions.get(node["id"], QPointF())
            rect = QGraphicsRectItem(position.x(), position.y(), 190, 68)
            rect.setPen(QPen(QColor("#347f91"), 1.5))
            rect.setBrush(QBrush(QColor("#183b49")))
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setData(0, node)
            self.scene.addItem(rect)
            text = QGraphicsTextItem(
                f"{node.get('kind', 'artifact')}\n{node.get('label') or node.get('id', '')}",
                rect,
            )
            text.setDefaultTextColor(QColor("#edf4f6"))
            text.setTextWidth(174)
            text.setPos(position.x() + 8, position.y() + 7)
            text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.node_labels.append(text)
            self.node_items[node["id"]] = rect

        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-32, -32, 32, 32))
        self.scene.selectionChanged.connect(self._selection_changed)
        if nodes:
            self.node_items[nodes[0]["id"]].setSelected(True)
        else:
            self.detail.setPlainText("No provenance nodes are available for this record.")

    @staticmethod
    def _positions(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, QPointF]:
        node_ids = {node["id"] for node in nodes}
        ranks = {node_id: 0 for node_id in node_ids}
        for _ in range(len(nodes)):
            for edge in edges:
                source, target = edge.get("source"), edge.get("target")
                if source in ranks and target in ranks:
                    ranks[target] = max(ranks[target], ranks[source] + 1)
        level_rows: dict[int, int] = defaultdict(int)
        positions = {}
        for node in nodes:
            rank = ranks[node["id"]]
            row = level_rows[rank]
            level_rows[rank] += 1
            positions[node["id"]] = QPointF(rank * 255, row * 100)
        return positions

    def _selection_changed(self) -> None:
        items = self.scene.selectedItems()
        if not items:
            return
        node = items[0].data(0)
        if node is not None:
            self.detail.setPlainText(
                json.dumps(node, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            )
