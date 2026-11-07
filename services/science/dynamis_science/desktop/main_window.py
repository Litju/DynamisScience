"""Qt Widgets shell and five-workspace native research journey."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import ParquetPreviewTableModel
from .services import DynamisAppService
from .tasks import TaskRunner


class MainWindow(QMainWindow):
    catalogue_loaded = Signal()

    def __init__(self, service: DynamisAppService) -> None:
        super().__init__()
        self.service = service
        self.runner = TaskRunner(self)
        self._close_after_tasks = False
        self.runner.idle.connect(self._close_if_idle)
        self.current_study_id: str | None = None
        self.current_study: dict[str, Any] = {}
        self.current_snapshot_id: str | None = None
        self.setWindowTitle("DynamisScience")
        self.resize(1420, 900)
        self._build_shell()
        self._load()

    def _build_shell(self) -> None:
        self.navigator = QTreeWidget()
        self.navigator.setHeaderHidden(True)
        self.navigator.itemClicked.connect(self._navigation_activated)
        self.navigator_dock = QDockWidget("Research navigator", self)
        self.navigator_dock.setObjectName("ResearchNavigator")
        self.navigator_dock.setWidget(self.navigator)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.navigator_dock)

        self.inspector = QTextBrowser()
        self.inspector_dock = QDockWidget("Inspector", self)
        self.inspector_dock.setObjectName("Inspector")
        self.inspector_dock.setWidget(self.inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)

        central = QWidget()
        layout = QVBoxLayout(central)
        header = QHBoxLayout()
        brand = QLabel("DYNAMISSCIENCE  /  RESEARCH WORKSTATION")
        brand.setStyleSheet("font-weight: 700; letter-spacing: 1px")
        self.context = QLabel("Select a project, study or dataset")
        self.provenance = QLabel("")
        self.provenance.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(brand)
        header.addStretch(1)
        header.addWidget(self.context)
        header.addWidget(self.provenance)
        layout.addLayout(header)

        self.workspace = QStackedWidget()
        self.welcome = QLabel("Loading the validated research catalogue…")
        self.welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.workspace.addWidget(self.welcome)
        self.research = ResearchWorkbench(self)
        self.workspace.addWidget(self.research)
        layout.addWidget(self.workspace, 1)
        self.setCentralWidget(central)

        self.status_text = QLabel("Starting")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setRange(0, 0)
        self.statusBar().addWidget(self.status_text, 1)
        self.statusBar().addPermanentWidget(self.progress)
        self._build_menu()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        export_action = QAction("Export current report…", self)
        export_action.triggered.connect(self.research.export_report)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.navigator_dock.toggleViewAction())
        view_menu.addAction(self.inspector_dock.toggleViewAction())
        help_menu = self.menuBar().addMenu("Help")
        about = QAction("About DynamisScience", self)
        about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                "About DynamisScience",
                "Native Qt Widgets scientific workstation. Scientific results are computed by the qualified Python domain modules.",
            )
        )
        help_menu.addAction(about)

    def _load(self) -> None:
        self.run_task(self.service.ensure_initialized, self._load_catalogue, "Validating private data root")

    def closeEvent(self, event) -> None:
        if self.runner.active:
            choice = QMessageBox.question(
                self,
                "Research task in progress",
                "A background task is still running. Wait for it to finish before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self._close_after_tasks = True
                self.setEnabled(False)
                self.status_text.setText("Finishing the active research task before closing…")
            event.ignore()
            return
        event.accept()

    def _close_if_idle(self) -> None:
        if self._close_after_tasks:
            self.close()

    def run_task(self, operation, on_result, label: str = "Working") -> None:
        self.status_text.setText(label)
        self.progress.setVisible(True)

        def succeeded(value: Any) -> None:
            self.progress.setVisible(False)
            self.status_text.setText("Ready")
            on_result(value)

        def failed(error: Exception) -> None:
            self.progress.setVisible(False)
            self.status_text.setText("Operation failed")
            QMessageBox.warning(self, "DynamisScience", f"{type(error).__name__}: {error}")

        self.runner.submit(operation, succeeded, failed)

    def _load_catalogue(self, environment: dict[str, Any]) -> None:
        self.inspector.setPlainText(
            f"Data root: {environment['data_root']}\n"
            f"Research database: {environment['database']}\n"
            f"Admitted real snapshots: {environment['real_snapshot_count']}"
        )
        self.run_task(self._catalogue, self._populate_navigation, "Loading projects and studies")

    def _catalogue(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        return self.service.list_projects(), self.service.list_all_studies(), self.service.list_datasets()

    def _populate_navigation(self, values) -> None:
        projects, studies, datasets = values
        self.navigator.clear()
        project_root = QTreeWidgetItem(["Projects"])
        project_root.setData(0, Qt.ItemDataRole.UserRole, {"type": "projects"})
        self.navigator.addTopLevelItem(project_root)
        for project in projects:
            item = QTreeWidgetItem([project.get("title", project["id"])])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "project", "id": project["id"]})
            project_root.addChild(item)
        study_root = QTreeWidgetItem(["Studies and monitoring"])
        study_root.setData(0, Qt.ItemDataRole.UserRole, {"type": "studies"})
        self.navigator.addTopLevelItem(study_root)
        for study in studies:
            item = QTreeWidgetItem([study.get("title", study["id"])])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "study", "id": study["id"]})
            study_root.addChild(item)
        data_root = QTreeWidgetItem(["Datasets"])
        data_root.setData(0, Qt.ItemDataRole.UserRole, {"type": "datasets"})
        self.navigator.addTopLevelItem(data_root)
        for dataset in datasets:
            item = QTreeWidgetItem([dataset.get("label") or dataset["id"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "dataset", "id": dataset["id"]})
            data_root.addChild(item)
        self.navigator.expandAll()
        self.workspace.setCurrentWidget(self.welcome)
        self.welcome.setText(
            f"Ready  ·  {len(projects)} projects  ·  {len(studies)} studies  ·  {len(datasets)} datasets"
        )
        self.status_text.setText("Ready")
        self.catalogue_loaded.emit()

    def _navigation_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        target = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if target.get("type") == "study":
            study_id = target["id"]
            self.run_task(
                lambda: self.service.get_study_detail(study_id),
                lambda detail: self._show_study(study_id, detail),
                "Opening study",
            )
        elif target.get("type") == "dataset":
            snapshot_id = target["id"]
            self.run_task(
                lambda: self.service.get_dataset_detail(snapshot_id),
                lambda detail: self._show_dataset(snapshot_id, detail),
                "Opening dataset",
            )
        elif target.get("type") in {"projects", "datasets", "studies"}:
            self.workspace.setCurrentWidget(self.welcome)
            self.welcome.setText(item.text(0))

    def _show_study(self, study_id: str, detail: dict[str, Any]) -> None:
        self.current_study_id = study_id
        self.current_study = detail
        snapshot = detail.get("snapshot", {})
        self.current_snapshot_id = snapshot.get("id") or detail.get("study", {}).get("dataset_snapshot_id")
        source = snapshot.get("source", {})
        license_info = source.get("license", {})
        license_id = license_info.get("id") if isinstance(license_info, dict) else license_info
        classification = source.get("privacy", {}).get("classification") if isinstance(source.get("privacy"), dict) else None
        if detail.get("real_data") or snapshot.get("real_data"):
            parts = ["REAL DATA", str(license_id or "rights recorded in source manifest")]
            if classification:
                parts.append(str(classification))
            badge = "  ·  ".join(parts)
        else:
            badge = "SYNTHETIC FIXTURE · DS-SYNTH-001 · NO EMPIRICAL CLAIMS"
        self.context.setText(detail.get("study", {}).get("title") or study_id)
        self.provenance.setText(badge)
        self.research.set_study(study_id, detail)
        self.workspace.setCurrentWidget(self.research)

    def _show_dataset(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        self.current_study_id = None
        self.current_study = {}
        self.current_snapshot_id = snapshot_id
        self.context.setText(detail.get("label") or snapshot_id)
        source = detail.get("source", {})
        license_info = source.get("license", {})
        license_id = license_info.get("id") if isinstance(license_info, dict) else license_info
        self.provenance.setText(
            "REAL DATA" if detail.get("real_data") else "SYNTHETIC FIXTURE · DS-SYNTH-001"
        )
        if license_id:
            self.provenance.setText(f"{self.provenance.text()}  ·  {license_id}")
        self.inspector.setPlainText(json.dumps(detail, indent=2, ensure_ascii=False, default=str))
        self.research.select_dataset(snapshot_id, detail)
        self.workspace.setCurrentWidget(self.research)
        self.research.tabs.setCurrentIndex(1)


class ResearchWorkbench(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window = window
        self.service = window.service
        self.latest_run: dict[str, Any] | None = None
        self.latest_evidence_id: str | None = None
        self.report_version: int | None = None
        self.report_generation = 0
        self.exploration_result: dict[str, Any] | None = None
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self._builders = [
            self._build_overview,
            self._build_dataset,
            self._build_exploration,
            self._build_analysis,
            self._build_evidence,
        ]
        self._built_tabs: set[int] = set()
        for label in (
            "Overview & Protocol",
            "Dataset & Cohort",
            "Exploration & Signals",
            "Analysis Plan & Runs",
            "Evidence & Report",
        ):
            self.tabs.addTab(QWidget(), label)
        self.tabs.currentChanged.connect(self._ensure_tab)
        self._ensure_tab(0)

    def _ensure_tab(self, index: int) -> None:
        if index < 0 or index in self._built_tabs:
            return
        self._builders[index]()
        self._built_tabs.add(index)

    def _build_overview(self) -> None:
        page = self.tabs.widget(0)
        layout = QVBoxLayout(page)
        self.overview = QTextBrowser()
        layout.addWidget(self.overview)

    def _build_dataset(self) -> None:
        page = self.tabs.widget(1)
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.table_picker = QComboBox()
        self.table_picker.currentIndexChanged.connect(self._table_changed)
        controls.addWidget(QLabel("Snapshot table"))
        controls.addWidget(self.table_picker, 1)
        layout.addLayout(controls)
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table_model = ParquetPreviewTableModel(self.service, self.window.runner)
        self.table.setModel(self.table_model)
        self.table.verticalHeader().setDefaultSectionSize(23)
        layout.addWidget(self.table, 1)
        self.table_status = QLabel("Select a study or dataset to inspect bounded Parquet pages.")
        layout.addWidget(self.table_status)

    def _build_exploration(self) -> None:
        import pyqtgraph as pg

        from .plots import ScientificFigureWidget

        self.pg = pg
        page = self.tabs.widget(2)
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.metric_picker = QComboBox()
        self.reference_picker = QComboBox()
        self.reference_picker.addItems(["RAW", "CHANGE", "PERCENT"])
        explore_button = QPushButton("Explore longitudinal signal")
        explore_button.clicked.connect(self._explore)
        controls.addWidget(QLabel("Metric"))
        controls.addWidget(self.metric_picker, 1)
        controls.addWidget(self.reference_picker)
        controls.addWidget(explore_button)
        layout.addLayout(controls)
        self.exploration_plot = ScientificFigureWidget()
        layout.addWidget(self.exploration_plot, 3)
        export_exploration = QPushButton("Export Matplotlib figure…")
        export_exploration.clicked.connect(self._export_exploration)
        layout.addWidget(export_exploration)
        signal_controls = QHBoxLayout()
        self.trial_picker = QComboBox()
        signal_button = QPushButton("Load selected signal")
        signal_button.clicked.connect(self._load_signal)
        signal_controls.addWidget(QLabel("Force / IMU trial"))
        signal_controls.addWidget(self.trial_picker, 1)
        signal_controls.addWidget(signal_button)
        layout.addLayout(signal_controls)
        self.signal_plot = pg.PlotWidget()
        self.signal_plot.showGrid(x=True, y=True, alpha=0.25)
        self.signal_plot.setLabel("bottom", "Time", units="s")
        self.signal_plot.setLabel("left", "Signal")
        self.signal_plot.addLegend()
        layout.addWidget(self.signal_plot, 2)

    def _build_analysis(self) -> None:
        page = self.tabs.widget(3)
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.method_picker = QComboBox()
        self.analysis_metric_picker = QComboBox()
        self.parameters = QPlainTextEdit()
        self.parameters.setMaximumHeight(75)
        self.parameters.setPlaceholderText('{"activity":"Walking","max_trials":8}')
        execute_button = QPushButton("Run analysis")
        self.execute_button = execute_button
        execute_button.clicked.connect(self._execute)
        self.show_figure_button = QPushButton("Show Matplotlib figure")
        self.show_figure_button.setEnabled(False)
        self.show_figure_button.clicked.connect(self._show_run_figure)
        export_run = QPushButton("Export figure…")
        export_run.clicked.connect(self._export_run_figure)
        controls.addWidget(self.method_picker, 2)
        controls.addWidget(self.analysis_metric_picker, 2)
        controls.addWidget(self.parameters, 3)
        controls.addWidget(execute_button)
        controls.addWidget(self.show_figure_button)
        controls.addWidget(export_run)
        layout.addLayout(controls)
        results = QSplitter(Qt.Orientation.Horizontal)
        self.run_output = QTextBrowser()
        self.run_plot_holder = QWidget()
        holder_layout = QVBoxLayout(self.run_plot_holder)
        holder_layout.addWidget(QLabel("Run an analysis to create a scientific figure."))
        results.addWidget(self.run_output)
        results.addWidget(self.run_plot_holder)
        layout.addWidget(results, 1)

    def _build_evidence(self) -> None:
        page = self.tabs.widget(4)
        layout = QVBoxLayout(page)
        buttons = QHBoxLayout()
        promote_button = QPushButton("Promote completed run to evidence")
        promote_button.clicked.connect(self._promote)
        cite_button = QPushButton("Cite promoted evidence")
        cite_button.clicked.connect(self._cite_latest)
        freeze_button = QPushButton("Freeze report version")
        freeze_button.clicked.connect(self._freeze_report)
        lineage_button = QPushButton("Show provenance lineage")
        lineage_button.clicked.connect(self._lineage)
        export_button = QPushButton("Export versioned HTML report…")
        export_button.clicked.connect(self.export_report)
        buttons.addWidget(promote_button)
        buttons.addWidget(cite_button)
        buttons.addWidget(lineage_button)
        buttons.addWidget(freeze_button)
        buttons.addWidget(export_button)
        layout.addLayout(buttons)
        self.evidence_output = QTextBrowser()
        self.evidence_output.setMinimumHeight(130)
        layout.addWidget(self.evidence_output, 1)
        self.report_preview = QTextBrowser()
        layout.addWidget(self.report_preview, 2)

    def set_study(self, study_id: str, detail: dict[str, Any]) -> None:
        for index in range(1, len(self._builders)):
            self._ensure_tab(index)
        self.study_id = study_id
        self.detail = detail
        self.snapshot_id = detail.get("snapshot", {}).get("id") or detail.get("study", {}).get("dataset_snapshot_id")
        self.window.inspector.setPlainText(
            json.dumps(
                {
                    "study": detail.get("study"),
                    "question": detail.get("question") or detail.get("research_question"),
                    "plan": detail.get("plan"),
                    "cohort": detail.get("cohort"),
                    "data_health": detail.get("data_health"),
                    "source": detail.get("snapshot", {}).get("source"),
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        summary = {
            "study": detail.get("study"),
            "question": detail.get("question") or detail.get("research_question"),
            "hypotheses": detail.get("hypotheses", []),
            "protocols": detail.get("protocols", []),
            "plan": detail.get("plan"),
            "data_health": detail.get("data_health"),
            "source_manifest": detail.get("snapshot", {}).get("source", {}),
        }
        self.overview.setPlainText(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        self.latest_run = None
        self.latest_evidence_id = None
        self.report_version = None
        self.exploration_result = None
        self.method_picker.clear()
        self.metric_picker.clear()
        self.analysis_metric_picker.clear()
        self.execute_button.setEnabled(study_id != "STUDY-001")
        if study_id == "STUDY-001":
            self.run_output.setPlainText(
                "The synthetic regression fixture is available for inspection and signal QA. "
                "Persisted research runs are created from an authored project and study."
            )
        self._load_dataset(self.snapshot_id)
        self._load_controls()
        self._load_runs_and_report()

    def select_dataset(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        self._ensure_tab(1)
        self.study_id = None
        self.detail = {"snapshot": detail}
        self.snapshot_id = snapshot_id
        self.latest_run = None
        self.latest_evidence_id = None
        self.report_version = None
        self.exploration_result = None
        self.method_picker.clear()
        self.metric_picker.clear()
        self.analysis_metric_picker.clear()
        self.execute_button.setEnabled(False)
        self._load_dataset(snapshot_id, detail)
        self.window.inspector.setPlainText(json.dumps(detail, indent=2, ensure_ascii=False, default=str))

    def _load_dataset(self, snapshot_id: str | None, detail: dict[str, Any] | None = None) -> None:
        if not snapshot_id:
            return
        self.window.run_task(
            lambda: detail or self.service.get_dataset_detail(snapshot_id),
            lambda value: self._dataset_loaded(snapshot_id, value),
            "Reading Parquet metadata",
        )

    def _dataset_loaded(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        if snapshot_id != self.snapshot_id:
            return
        self.dataset_detail = detail
        self.table_picker.blockSignals(True)
        self.table_picker.clear()
        for table in detail.get("tables", []):
            self.table_picker.addItem(table["name"], table)
        self.table_picker.blockSignals(False)
        if self.table_picker.count():
            self._table_changed(0)
        else:
            self.table_status.setText("This snapshot has no tabular data available for preview.")
        if getattr(self, "study_id", None):
            self._load_signal_trials(snapshot_id)

    def _table_changed(self, index: int) -> None:
        if index < 0:
            return
        table = self.table_picker.currentData()
        if not table:
            return
        self.table_status.setText(
            f"{table['rows']:,} rows · showing pages of at most 500 rows · {len(table.get('columns', []))} columns"
        )
        self.table_model.set_table(
            self.snapshot_id,
            table["name"],
            int(table["rows"]),
            [column["name"] for column in table.get("columns", [])],
        )

    def _load_controls(self) -> None:
        if not getattr(self, "snapshot_id", None):
            return
        snapshot_id = self.snapshot_id
        self.window.run_task(
            lambda: (
                self.service.list_methods(snapshot_id),
                self.service.list_metrics(snapshot_id),
            ),
            lambda values: self._controls_loaded(snapshot_id, values),
            "Loading methods and metric definitions",
        )

    def _controls_loaded(self, snapshot_id: str, values) -> None:
        if snapshot_id != self.snapshot_id:
            return
        if getattr(self, "study_id", None) == "STUDY-001":
            self.method_picker.clear()
            self.analysis_metric_picker.clear()
            return
        methods, metrics = values
        self.method_picker.clear()
        for method in methods:
            qualification = method.get("qualification", {}).get("status", "")
            self.method_picker.addItem(f"{method['id']} · {method['name']} · {qualification}", method["id"])
        self.metric_picker.clear()
        self.analysis_metric_picker.clear()
        for metric in metrics:
            label = f"{metric['label']} ({metric.get('unit', '')})"
            self.metric_picker.addItem(label, metric["id"])
            self.analysis_metric_picker.addItem(label, metric["id"])

    def _load_signal_trials(self, snapshot_id: str) -> None:
        self.window.run_task(
            lambda: self.service.list_signal_trials(snapshot_id),
            lambda trials: self._trials_loaded(snapshot_id, trials),
            "Loading trial catalogue",
        )

    def _trials_loaded(self, snapshot_id: str, trials: list[dict[str, Any]]) -> None:
        if snapshot_id != self.snapshot_id or not getattr(self, "study_id", None):
            return
        self.trial_picker.clear()
        for trial in trials:
            trial_id = trial.get("trial_id", trial.get("id", ""))
            activity = trial.get("activity", "")
            self.trial_picker.addItem(f"{trial_id}  ·  {activity}", trial_id)

    def _explore(self) -> None:
        if not getattr(self, "study_id", None) or self.metric_picker.count() == 0:
            return
        study_id = self.study_id
        snapshot_id = self.snapshot_id
        metric = self.metric_picker.currentData()
        reference = self.reference_picker.currentText()
        self.window.run_task(
            lambda: self.service.explore_longitudinal(study_id, metric, reference=reference),
            lambda result: self._exploration_completed(study_id, snapshot_id, result),
            "Computing longitudinal summaries",
        )

    def _exploration_completed(
        self, study_id: str, snapshot_id: str, result: dict[str, Any]
    ) -> None:
        if study_id != self.study_id or snapshot_id != self.snapshot_id:
            return
        self.exploration_result = result
        self.exploration_context = {"study_id": study_id, "snapshot_id": snapshot_id}
        self.exploration_plot.show_figure(self._exploration_figure(result, self.exploration_context))

    def _exploration_figure(self, result: dict[str, Any], context: dict[str, str]):
        from .plots import longitudinal_figure

        metric = result.get("metric", {}).get("metric_id")
        return longitudinal_figure(
            result,
            {
                "study_id": context["study_id"],
                "snapshot_id": context["snapshot_id"],
                "metric_id": metric,
                "cohort_id": result.get("cohort", {}).get("id"),
                "source": result.get("provenance", {}),
            },
        )

    def _figure_target(self, title: str, filename: str) -> tuple[str, int] | None:
        filters = "PNG image (*.png);;PDF document (*.pdf);;SVG image (*.svg)"
        path, selected_filter = QFileDialog.getSaveFileName(self, title, filename, filters)
        if not path:
            return None
        extension = {"PNG image (*.png)": ".png", "PDF document (*.pdf)": ".pdf", "SVG image (*.svg)": ".svg"}[selected_filter]
        if not path.lower().endswith((".png", ".pdf", ".svg")):
            path += extension
        dpi, accepted = QInputDialog.getInt(self, "Figure resolution", "Export resolution (DPI)", 300, 72, 1200, 24)
        return (path, dpi) if accepted else None

    def _export_exploration(self) -> None:
        if not self.exploration_result:
            QMessageBox.information(self, "Figure export", "Create an exploration figure first.")
            return
        target = self._figure_target("Export scientific figure", f"{self.study_id}-exploration.png")
        if target is None:
            return
        path, dpi = target
        result = self.exploration_result
        context = self.exploration_context

        def write_figure():
            from .plots import export_figure

            return export_figure(self._exploration_figure(result, context), path, dpi)

        self.window.run_task(
            write_figure,
            lambda output: self.window.statusBar().showMessage(f"Figure exported: {output}", 8000),
            "Exporting Matplotlib figure",
        )

    def _export_run_figure(self) -> None:
        if not self.latest_run:
            QMessageBox.information(self, "Figure export", "Run an analysis before exporting its figure.")
            return
        run = self.latest_run
        target = self._figure_target("Export analysis figure", f"{run['id']}.png")
        if target is None:
            return
        path, dpi = target

        def write_figure():
            from .plots import export_figure, run_figure

            return export_figure(run_figure(run), path, dpi)

        self.window.run_task(
            write_figure,
            lambda output: self.window.statusBar().showMessage(f"Figure exported: {output}", 8000),
            "Exporting analysis figure",
        )

    def _load_signal(self) -> None:
        if self.trial_picker.count() == 0:
            return
        trial_id = self.trial_picker.currentData()
        snapshot_id = self.snapshot_id

        def render(result: dict[str, Any]) -> None:
            self.signal_plot.clear()
            for index, series in enumerate(result["series"]):
                rows = series["rows"]
                x_column = series["time_column"]
                y_column = series["value_column"]
                self.signal_plot.plot(
                    [row[x_column] for row in rows],
                    [row[y_column] for row in rows],
                    pen=self.pg.mkPen("#176b87" if index == 0 else "#c07139", width=1.5),
                    name=series["label"],
                )
            if result["series"]:
                self.signal_plot.setLabel("bottom", result["series"][0]["time_column"].replace("_", " "))
                self.signal_plot.setLabel("left", result["series"][0]["value_column"].replace("_", " "))
                self.table_status.setText(
                    f"Signal {trial_id} · {result['sample_count']:,} plotted samples from {result['source_rows']:,} source rows"
                )

        self.window.run_task(
            lambda: self.service.get_signal_waveform(snapshot_id, trial_id),
            render,
            "Reading selected force signal",
        )

    def _execute(self) -> None:
        if not getattr(self, "study_id", None):
            QMessageBox.information(self, "Analysis", "Open a persisted research study to create an immutable run.")
            return
        if not self.method_picker.currentData() or not self.analysis_metric_picker.currentData():
            QMessageBox.information(self, "Analysis", "Select a registered method and metric first.")
            return
        try:
            parameters = json.loads(self.parameters.toPlainText() or "{}")
            if not isinstance(parameters, dict):
                raise ValueError("Analysis parameters must be a JSON object")
        except (json.JSONDecodeError, ValueError) as error:
            QMessageBox.warning(self, "Analysis parameters", str(error))
            return
        study_id = self.study_id
        payload = {
            "method_id": self.method_picker.currentData(),
            "outcome_metric_id": self.analysis_metric_picker.currentData(),
            "parameters": parameters,
        }
        self.window.run_task(
            lambda: self.service.execute_analysis_isolated(study_id, payload),
            lambda run: self._run_completed(study_id, run),
            "Running qualified scientific analysis",
        )

    def _run_completed(self, study_id: str, run: dict[str, Any]) -> None:
        if study_id != self.study_id:
            return
        self.latest_run = run
        self.latest_evidence_id = None
        self.show_figure_button.setEnabled(True)
        self.run_output.setPlainText(
            json.dumps(
                {key: run.get(key) for key in ("id", "method_id", "status", "result", "diagnostics", "result_digest", "reproducibility_key")},
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        self.window.current_study_id = self.study_id
        self.window.inspector.setPlainText(
            json.dumps(run.get("diagnostics", {}), indent=2, ensure_ascii=False, default=str)
        )
        self._load_runs_and_report()

    def _show_run_figure(self) -> None:
        if not self.latest_run:
            return
        from .plots import ScientificFigureWidget, run_figure

        if not hasattr(self, "run_plot"):
            self.run_plot = ScientificFigureWidget()
            placeholder = self.run_plot_holder.layout().takeAt(0).widget()
            if placeholder is not None:
                placeholder.deleteLater()
            self.run_plot_holder.layout().addWidget(self.run_plot)
        self.run_plot.show_figure(run_figure(self.latest_run))

    def _promote(self) -> None:
        if not self.latest_run:
            QMessageBox.information(self, "Evidence", "Run a completed analysis before promoting evidence.")
            return
        run_id = self.latest_run["id"]
        study_id = self.latest_run["study_id"]
        self.window.run_task(
            lambda: self.service.promote_run_to_evidence(run_id),
            lambda value: self._evidence_promoted(study_id, value),
            "Promoting immutable evidence",
        )

    def _evidence_promoted(self, study_id: str, value: dict[str, Any]) -> None:
        if study_id != self.study_id:
            return
        self.evidence_output.setPlainText(json.dumps(value, indent=2, ensure_ascii=False, default=str))
        artifact = value.get("evidence_artifact") or {}
        artifact_id = artifact.get("id") or self.latest_run.get("id")
        self.latest_evidence_id = artifact.get("id")
        self.window.run_task(
            lambda: self.service.get_lineage_graph(artifact_id),
            lambda graph: self._show_lineage(graph) if study_id == self.study_id else None,
            "Loading evidence provenance",
        )
        self._load_runs_and_report()

    def _cite_latest(self) -> None:
        if not self.latest_evidence_id or not getattr(self, "study_id", None):
            QMessageBox.information(self, "Report citation", "Promote a completed run to evidence first.")
            return
        study_id = self.study_id
        artifact_id = self.latest_evidence_id
        self.window.run_task(
            lambda: self.service.cite_report_artifact(study_id, artifact_id),
            lambda result: self._report_cited(study_id, result),
            "Adding evidence citation to report",
        )

    def _report_cited(self, study_id: str, result: dict[str, Any]) -> None:
        if study_id != self.study_id:
            return
        self.evidence_output.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        self.report_version = None
        self._load_runs_and_report()

    def _freeze_report(self) -> None:
        if not getattr(self, "study_id", None) or not self.study_id.startswith(("STUDY-U-", "PROG-U-")):
            QMessageBox.information(self, "Report version", "Versioned report freezing is available for persisted research studies.")
            return
        study_id = self.study_id
        self.window.run_task(
            lambda: self.service.freeze_report(study_id),
            lambda result: self._report_frozen(study_id, result),
            "Freezing immutable report version",
        )

    def _report_frozen(self, study_id: str, result: dict[str, Any]) -> None:
        if study_id != self.study_id:
            return
        self.report_generation += 1
        self.report_version = result["version"]
        self.evidence_output.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        version = self.report_version
        generation = self.report_generation
        self.window.run_task(
            lambda: self.service.render_report_html(study_id, version),
            lambda html: self.report_preview.setHtml(html)
            if study_id == self.study_id and generation == self.report_generation
            else None,
            "Rendering frozen report version",
        )

    def _lineage(self) -> None:
        if not self.latest_run:
            QMessageBox.information(self, "Lineage", "Select or create an analysis run first.")
            return
        run_id = self.latest_run["id"]
        study_id = self.latest_run["study_id"]
        self.window.run_task(
            lambda: self.service.get_lineage_graph(run_id),
            lambda graph: self._show_lineage(graph) if study_id == self.study_id else None,
            "Loading run lineage",
        )

    def _show_lineage(self, graph: dict[str, Any]) -> None:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        self.evidence_output.setPlainText(
            f"Lineage graph · {len(nodes)} nodes · {len(edges)} edges\n\n"
            + "\n".join(f"{item.get('kind', '')}  {item.get('id', '')}  {item.get('label', '')}" for item in nodes)
        )

    def _load_runs_and_report(self) -> None:
        if not getattr(self, "study_id", None):
            return
        study_id = self.study_id
        self.report_generation += 1
        generation = self.report_generation
        self.window.run_task(
            lambda: (self.service.get_report(study_id), self.service.get_study_detail(study_id)),
            lambda values: self._report_loaded(study_id, generation, values),
            "Loading evidence and report",
        )

    def _report_loaded(self, study_id: str, generation: int, values) -> None:
        if study_id != self.study_id or generation != self.report_generation:
            return
        report, detail = values
        self.report_version = report.get("version") if report.get("status") == "FROZEN" else None
        self.evidence_output.setPlainText(
            json.dumps(
                {"evidence": detail.get("evidence", []), "report": report},
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        if study_id.startswith(("STUDY-U-", "PROG-U-")):
            self.window.run_task(
                lambda: self.service.render_report_html(study_id),
                lambda html: self.report_preview.setHtml(html)
                if study_id == self.study_id and generation == self.report_generation
                else None,
                "Rendering versioned report preview",
            )

    def export_report(self) -> None:
        if not getattr(self, "study_id", None) or not self.study_id.startswith(("STUDY-U-", "PROG-U-")):
            QMessageBox.information(self, "Report export", "Versioned report export is available for persisted research studies.")
            return
        if self.report_version is None:
            QMessageBox.information(self, "Report export", "Freeze the current report before exporting a version.")
            return
        study_id = self.study_id
        version = self.report_version
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export scientific report",
            f"{study_id}-report-v{version}.html",
            "HTML report (*.html)",
        )
        if not path:
            return
        self.window.run_task(
            lambda: self.service.export_report_html(study_id, path, version),
            lambda output: self.window.statusBar().showMessage(f"Report exported: {output}", 8000),
            "Exporting versioned scientific report",
        )
