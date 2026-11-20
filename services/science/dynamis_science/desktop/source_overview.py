"""Source review before the optional measurement table."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .investigation_timeline import heading, wrapping_label

_TABLE_NAMES = {
    "subjects": "Athletes", "cmj_trials": "Jump trials", "sprint_trials": "Sprint trials",
    "force_traces": "Force recordings", "training_load": "Training records", "monitoring": "Monitoring records",
}


class SourceOverview(QWidget):
    import_requested = Signal()
    qc_requested = Signal()
    measurements_requested = Signal()
    exploration_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)
        header = QHBoxLayout()
        title = QLabel("Sources & quality")
        title.setObjectName("StudyHeading")
        header.addWidget(title, 1)
        self.import_button = QPushButton("Add measurements…")
        self.import_button.setProperty("primary", True)
        self.import_button.clicked.connect(self.import_requested)
        header.addWidget(self.import_button)
        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("SourceCard")
        reading = QVBoxLayout(card)
        reading.setContentsMargins(16, 13, 16, 13)
        name = QLabel("Measurements")
        heading(name, 14)
        reading.addWidget(name)
        self.dataset = wrapping_label()
        reading.addWidget(self.dataset)
        self.quality = wrapping_label()
        reading.addWidget(self.quality)
        self.totals = QHBoxLayout()
        reading.addLayout(self.totals)
        actions = QHBoxLayout()
        self.measurements_button = QPushButton("Browse measurement rows…")
        self.measurements_button.clicked.connect(self.measurements_requested)
        self.explore_button = QPushButton("Explore signals…")
        self.explore_button.clicked.connect(self.exploration_requested)
        self.qc_button = QPushButton("Review QC receipts…")
        self.qc_button.clicked.connect(self.qc_requested)
        for action in (self.measurements_button, self.explore_button, self.qc_button):
            actions.addWidget(action)
        actions.addStretch()
        reading.addLayout(actions)
        layout.addWidget(card)

        context_card = QFrame()
        context_card.setObjectName("SourceCard")
        context_layout = QVBoxLayout(context_card)
        context_layout.setContentsMargins(16, 13, 16, 13)
        name = QLabel("Training & wellness")
        heading(name, 14)
        context_layout.addWidget(name)
        self.context_sources = wrapping_label()
        context_layout.addWidget(self.context_sources)
        layout.addWidget(context_card)
        layout.addStretch()
        self.reset()

    def reset(self):
        self.dataset.setText("No measurement dataset selected.")
        self.quality.clear()
        self.measurements_button.setEnabled(False)
        self.explore_button.setEnabled(False)
        self.set_counts({})
        self.show_context_sources([])

    def set_counts(self, counts):
        while self.totals.count():
            widget = self.totals.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        for key, count in sorted(counts.items(), key=lambda pair: (pair[0] != "subjects", pair[0]))[:6]:
            label = _TABLE_NAMES.get(key, key.replace("_", " ").capitalize())
            value = wrapping_label(f"{count:,}  {label.lower()}")
            value.setObjectName("SourceCount")
            self.totals.addWidget(value)
        self.totals.addStretch()

    def show_measurements(self, detail):
        self.dataset.setText(detail.get("label") or "Active measurement dataset")
        self.quality.setText("Checking measurement quality and permissions…")
        tables = {item["name"]: item["rows"] for item in detail.get("tables", [])}
        self.set_counts(tables)
        self.measurements_button.setEnabled(bool(tables))
        self.explore_button.setEnabled(bool(tables))

    def show_quality(self, info):
        source = info.get("source") or {}
        name = source.get("name") or source.get("publisher")
        current_label = info.get("label") or "Active measurement dataset"
        self.dataset.setText(f"{name} · {current_label}" if name and name != current_label else current_label)
        quality = info.get("quality") or {}
        status = str(quality.get("status") or "Not recorded").replace("_", " ").capitalize()
        synthetic = " · Synthetic fixture. No empirical validity." if info.get("synthetic") else ""
        if not synthetic and not info.get("real_data"):
            synthetic = " · Empirical validity unavailable."
        findings = [str(value) for value in quality.get("errors", []) + quality.get("warnings", [])]
        self.quality.setText(f"Quality · {status}{synthetic}" + ("\n" + "\n".join(findings) if findings else ""))

    def show_context_sources(self, receipts):
        latest = {row["source"]["id"]: row for row in receipts}
        lines = []
        for row in latest.values():
            flagged = ", ".join(f"{count} {flag.replace('_', ' ').lower()}" for flag, count in row["qc"].items())
            lines.append(f"{row['source']['name']} · version {row['version']} · {row['row_count']:,} observations" +
                         (f"\n{flagged}" if flagged else ""))
        self.context_sources.setText("\n\n".join(lines) or "No training or wellness source is attached to this data revision.")
