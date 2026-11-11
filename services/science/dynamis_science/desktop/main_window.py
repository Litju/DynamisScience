"""Qt Widgets shell and five-workspace native research journey."""

from __future__ import annotations

import json
import logging
import sys
import difflib
from typing import Any

from PySide6.QtCore import QEvent, QSettings, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolBar,
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

from .models import ParquetPreviewTableModel, RecordTableModel
from .dialogs import (
    AdmissionHistoryDialog,
    CohortDialog,
    DatasetAdmissionDialog,
    PlanDialog,
    ProjectDialog,
    StudyDialog,
)
from .investigation_editor import InvestigationEditor
from .library_dialog import ScientificLibraryDialog
from .lineage_dialog import LineageDialog
from .performance_navigation import PERFORMANCE_PAGE_KEYS, PERFORMANCE_PAGE_NAMES
from ..researchstore import ResearchConflict
from .services import DynamisAppService
from .import_review import ImportReviewDialog
from .tasks import TaskRunner
from .theme import apply_theme
from .workbench.controller import WorkbenchController
from .workbench.data_pane import DataPane
from .workbench.options_pane import OptionsPane
from .workbench.results import DESCRIPTIVE_KINDS, ENGINE_KINDS, ResultsDocument, run_analysis
from .workbench.shell import COMPACT_WIDTH, WorkbenchShell


class MainWindow(QMainWindow):
    catalogue_loaded = Signal()

    def __init__(self, service: DynamisAppService) -> None:
        super().__init__()
        self.service = service
        # Layout and theme are per data root, so tests and separate data roots never share UI state.
        self.settings = QSettings(
            str(service.root / "desktop" / "workbench.ini"), QSettings.Format.IniFormat
        )
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, self.settings.value("workbench/theme", "light"))
        self.runner = TaskRunner(self)
        self._close_after_tasks = False
        self.runner.idle.connect(self._close_if_idle)
        self.current_study_id: str | None = None
        self.current_study: dict[str, Any] = {}
        self.current_snapshot_id: str | None = None
        self.current_target: dict[str, str] | None = None
        self.current_project: dict[str, Any] | None = None
        self.setWindowTitle("DynamisScience")
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(min(1420, available.width() - 32), min(900, available.height() - 64))
        else:
            self.resize(1420, 900)
        self._build_shell()
        self.workbench.set_compact(self.width() < COMPACT_WIDTH)
        self._load()

    def _build_shell(self) -> None:
        self.navigator = QTreeWidget()
        self.navigator.setHeaderHidden(True)
        self.navigator.setAccessibleName("Research navigator")
        self.navigator.itemClicked.connect(self._navigation_activated)
        self.navigator_dock = QDockWidget("Navigator", self)
        self.navigator_dock.setObjectName("ResearchNavigator")
        self.navigator_stack = QStackedWidget(self.navigator_dock)
        self.navigator_dock.setWidget(self.navigator_stack)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.navigator_dock)

        self.inspector = QTextBrowser()
        self.inspector.setAccessibleName("Inspector raw detail")
        self.inspector_dock = QDockWidget("Inspector", self)
        self.inspector_dock.setObjectName("Inspector")
        self.inspector_stack = QStackedWidget(self.inspector_dock)
        self.inspector_stack.addWidget(self.inspector)
        self.inspector_dock.setWidget(self.inspector_stack)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)

        # Research perspective: design E workbench. Data and Options are the native panes (the research
        # navigator lives in the Data pane's Library section); Results still hosts the study workspace.
        self.workbench = WorkbenchShell(self.settings, self)
        self.context = self.workbench.context_label
        self.provenance = self.workbench.provenance_label
        self.workspace = QStackedWidget()
        self.welcome = QLabel("Loading the validated research catalogue…")
        self.welcome.setObjectName("PaneEmpty")
        self.welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome.setWordWrap(True)
        self.workspace.addWidget(self.welcome)
        self.research = ResearchWorkbench(self)
        self.workspace.addWidget(self.research)
        self.data_pane = DataPane(self.service, self.navigator)
        self.options_pane = OptionsPane()
        self.workbench.set_data_widget(self.data_pane)
        self.workbench.set_options_widget(self.options_pane)
        self.controller = WorkbenchController(self.workbench, self.data_pane, self.options_pane, self)
        self.controller.run_requested.connect(self._run_spec)
        results_scroll = QScrollArea()
        results_scroll.setObjectName("WorkbenchResultsScroll")
        results_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        results_scroll.setWidgetResizable(True)
        results_scroll.setWidget(self.workspace)
        # The workbench result document is the primary Results view; the study record is under View.
        self.results_doc = ResultsDocument(self.service)
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self.results_doc)
        self.results_stack.addWidget(results_scroll)
        self.workbench.set_results_widget(self.results_stack)
        self.controller.spec_changed.connect(self._spec_changed)
        self.workbench.action_promote.triggered.connect(self.results_doc.promote)
        self.workbench.action_add_to_report.triggered.connect(lambda: self.results_doc.add_to_report())
        self.workbench.action_export.triggered.connect(lambda: self._export_results())
        self.results_doc.evidence_promoted.connect(self._evidence_promoted)
        self.results_doc.report_cited.connect(self._report_cited)
        self.results_doc.action_failed.connect(self.workbench.show_toast)
        # linked athlete selection: Data pane By athlete <-> trajectory views
        self.results_doc.athlete_selected.connect(self.data_pane.select_athlete)
        self.data_pane.athlete_selected.connect(self.results_doc.select_athlete)
        self.signals_view = None  # SignalsView, created when the Signals key is first chosen
        self.workbench.analysis_selected.connect(self._analysis_selected)
        self.data_pane.dataset_changed.connect(
            lambda *_: self._analysis_selected(self.workbench.current_analysis() or ""))
        self._sync_result_actions()
        self.perspectives = QStackedWidget()
        self.perspectives.addWidget(self.workbench)
        self.performance = None
        self.performance_header = None
        self.performance_rail = None
        self.performance_toolbar = None
        screen = self.screen()
        available = screen.availableGeometry() if screen is not None else None
        # shortcut: compact layout follows the startup screen, reevaluate when supporting live monitor changes
        if available is not None and (available.width() < 1100 or available.height() < 650):
            perspectives_scroll = QScrollArea()
            perspectives_scroll.setWidgetResizable(True)
            perspectives_scroll.setWidget(self.perspectives)
            self.setCentralWidget(perspectives_scroll)
        else:
            self.setCentralWidget(self.perspectives)

        self.status_text = self.workbench.app_status
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("Background task in progress")
        self.statusBar().addWidget(self.status_text, 1)
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.workbench.status_items)
        self._perspective = ""
        self._build_menu()
        self._show_research_mode()
        self.navigator.setFocus()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        export_action = QAction("Export current report…", self)
        export_action.triggered.connect(self.research.export_report)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        research_menu = self.menuBar().addMenu("Research")
        self.action_new_project = QAction("New project…", self)
        self.action_new_project.triggered.connect(self._new_project)
        self.action_new_study = QAction("New study…", self)
        self.action_new_study.triggered.connect(lambda: self._new_research_object(False))
        self.action_new_monitoring = QAction("New monitoring program…", self)
        self.action_new_monitoring.triggered.connect(lambda: self._new_research_object(True))
        self.action_edit = QAction("Edit selected project / study…", self)
        self.action_edit.triggered.connect(self._edit_current)
        self.action_import = QAction("Import data…", self)
        self.action_import.setShortcut("Ctrl+I")
        self.action_import.triggered.connect(self._open_import)
        self.action_admit = QAction("Admit local dataset (manual)…", self)
        self.action_admit.triggered.connect(self._open_admission)
        self.action_admission_history = QAction("Admission and quarantine history…", self)
        self.action_admission_history.triggered.connect(self._open_admission_history)
        self.action_archive = QAction("Archive selected project / study", self)
        self.action_archive.triggered.connect(self._archive_current)
        self.action_restore = QAction("Restore selected project / study", self)
        self.action_restore.triggered.connect(self._restore_current)
        self.action_transition = QAction("Transition selected study state…", self)
        self.action_transition.triggered.connect(self._transition_current_study)
        self.action_study_history = QAction("Study / project history…", self)
        self.action_study_history.triggered.connect(self._object_history)
        self.action_report_history = QAction("Report version history…", self)
        self.action_report_history.triggered.connect(self._report_history)
        self.action_compare_report_versions = QAction("Compare frozen report versions…", self)
        self.action_compare_report_versions.triggered.connect(self._compare_report_versions)
        self.action_scientific_library = QAction("Scientific definition library…", self)
        self.action_scientific_library.triggered.connect(self._open_scientific_library)
        for action in (
            self.action_new_project,
            self.action_new_study,
            self.action_new_monitoring,
            self.action_edit,
            self.action_import,
            self.action_admit,
            self.action_admission_history,
            self.action_archive,
            self.action_restore,
            self.action_transition,
            self.action_study_history,
            self.action_report_history,
            self.action_compare_report_versions,
            self.action_scientific_library,
        ):
            research_menu.addAction(action)
        cohort_menu = research_menu.addMenu("Cohort")
        for label, callback in (
            ("New cohort…", self._new_cohort),
            ("Edit current cohort…", self._edit_cohort),
            ("Freeze current cohort", self._freeze_cohort),
            ("Fork current cohort…", self._fork_cohort),
            ("Cohort history…", self._cohort_history),
        ):
            action = cohort_menu.addAction(label)
            action.triggered.connect(callback)
        plan_menu = research_menu.addMenu("Analysis plan")
        for label, callback in (
            ("New plan…", self._new_plan),
            ("Edit current plan…", self._edit_plan),
            ("Freeze current plan", self._freeze_plan),
            ("Fork current plan…", self._fork_plan),
            ("Plan history…", self._plan_history),
        ):
            action = plan_menu.addAction(label)
            action.triggered.connect(callback)
        tools_menu = self.menuBar().addMenu("Tools")
        self.action_verify_database = QAction("Verify research database integrity", self)
        self.action_verify_database.triggered.connect(self._verify_research_database)
        self.action_backup_database = QAction("Create verified database backup", self)
        self.action_backup_database.triggered.connect(self._backup_research_database)
        self.action_restore_database = QAction("Rehearse restore from backup…", self)
        self.action_restore_database.triggered.connect(self._rehearse_research_restore)
        self.action_run_qualification = QAction("Run independent real-data qualification", self)
        self.action_run_qualification.triggered.connect(self._run_independent_qualification)
        for action in (
            self.action_verify_database,
            self.action_backup_database,
            self.action_restore_database,
            self.action_run_qualification,
        ):
            tools_menu.addAction(action)
        analyses_menu = self.menuBar().addMenu("Analyses")
        analyses_menu.addActions(list(self.workbench.analysis_actions.values()))
        results_menu = self.menuBar().addMenu("Results")
        results_menu.addActions(
            [
                self.workbench.action_run,
                self.workbench.action_add_to_report,
                self.workbench.action_promote,
                self.workbench.action_export,
            ]
        )
        view_menu = self.menuBar().addMenu("View")
        view_menu.addActions(self.workbench.view_actions)
        view_menu.addSeparator()
        self.trajectory_actions = {}
        for mode in ("2D", "3D"):
            action = QAction(f"Show {mode} trajectories", self)
            action.setToolTip(f"Mixed-model results: {mode} trajectories of the observed values and fitted mean")
            action.triggered.connect(lambda _checked=False, mode=mode: self._show_trajectories(mode))
            view_menu.addAction(action)
            self.trajectory_actions[mode] = action
        view_menu.addSeparator()
        self.action_study_record = QAction("Study record", self)
        self.action_study_record.setCheckable(True)
        self.action_study_record.setToolTip("Overview, dataset, exploration, analysis plan and evidence of the open study")
        self.action_study_record.toggled.connect(self._set_record_view)
        view_menu.addAction(self.action_study_record)
        advanced = view_menu.addMenu("Advanced")
        inspector_toggle = self.inspector_dock.toggleViewAction()
        inspector_toggle.setText("Inspector raw detail")
        advanced.addAction(inspector_toggle)
        # Perspectives: the research workbench and the practitioner Performance OS (its own layout,
        # not the three-pane workbench). The Performance header menu repeats these menus.
        perspective_menu = self.menuBar().addMenu("Perspective")
        self.action_research_perspective = QAction("Research workbench", self)
        self.action_research_perspective.triggered.connect(self._show_research_mode)
        perspective_menu.addAction(self.action_research_perspective)
        perspective_menu.addSeparator()
        for key, name in zip(PERFORMANCE_PAGE_KEYS, PERFORMANCE_PAGE_NAMES):
            action = perspective_menu.addAction(f"Performance OS · {name}")
            action.triggered.connect(lambda _checked=False, key=key: self.show_performance_page(key))
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
        licenses_action = QAction("Open-source licenses…", self)
        licenses_action.triggered.connect(self._open_third_party_licenses)
        help_menu.addAction(licenses_action)
        for menu_action in self.menuBar().actions():
            if menu_action.menu() not in (analyses_menu, results_menu, view_menu):
                self.workbench.palette.add_menu(menu_action.menu(), menu_action.text())
        self.workbench.palette.add_action(inspector_toggle, "View")
        self.workbench.palette.add_action(self.action_study_record, "View")
        for action in self.trajectory_actions.values():
            self.workbench.palette.add_action(action, "View")

    def _ensure_performance(self) -> None:
        if self.performance is not None:
            return
        from .performance_workbench import (
            PerformanceHeader,
            PerformanceRail,
            PerformanceWorkbench,
        )

        self.performance = PerformanceWorkbench(self)
        self.performance.open_research_study.connect(self._open_research_study)
        self.performance.athlete_inspected.connect(self._show_athlete_inspector)
        self.performance.context_panel.back_to_daily.connect(self._show_daily_context)
        self.performance.context_panel.open_full_athlete.connect(self._open_full_athlete_profile)
        self.inspector_stack.addWidget(self.performance.context_panel)
        self.perspectives.addWidget(self.performance)
        self.performance_header = PerformanceHeader(self)
        self.performance_header.search_requested.connect(self._search_performance)
        self.performance_header.set_menu_actions(self.menuBar().actions())
        self.performance_rail = PerformanceRail(self)
        self.performance_rail.page_selected.connect(self.show_performance_page)
        self.navigator_stack.addWidget(self.performance_rail)
        self.performance_toolbar = QToolBar("Performance OS", self)
        self.performance_toolbar.setObjectName("PerformanceToolbar")
        self.performance_toolbar.setMovable(False)
        self.performance_toolbar.setFloatable(False)
        header_scroll = QScrollArea()
        header_scroll.setWidgetResizable(True)
        header_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header_scroll.setWidget(self.performance_header)
        header_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # The toolbar is 48 px (theme); a taller scroll area was clipped and cut "SPORTS SCIENCE" off.
        # shortcut: in a window narrower than the header the horizontal scroll bar overlays its bottom edge.
        header_scroll.setFixedHeight(self.performance_header.minimumHeight())  # its fixed 48 px, not the 29 px hint
        self.performance_toolbar.addWidget(header_scroll)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.performance_toolbar)
        self.performance_toolbar.hide()

    def _open_third_party_licenses(self) -> None:
        if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
            notice = Path(sys._MEIPASS) / "THIRD_PARTY_LICENSES.md"
            distribution_notices = Path(sys._MEIPASS) / "THIRD_PARTY_NOTICES.txt"
        else:
            doc_root = Path(__file__).resolve().parents[4] / "docs" / "desktop"
            notice = doc_root / "THIRD_PARTY_LICENSES.md"
            distribution_notices = doc_root / "licenses" / "THIRD_PARTY_NOTICES.txt"
        if not notice.is_file():
            QMessageBox.warning(self, "Open-source licenses", "The bundled third-party notice is unavailable.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Open-source licenses")
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(False)
        content = notice.read_text(encoding="utf-8")
        if distribution_notices.is_file():
            content += "\n\n" + distribution_notices.read_text(encoding="utf-8")
        browser.setMarkdown(content)
        layout.addWidget(browser)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.resize(760, 600)
        dialog.exec()

    def _verify_research_database(self) -> None:
        def show_report(report: dict[str, Any]) -> None:
            QMessageBox.information(
                self,
                "Research database integrity",
                f"Integrity: {', '.join(report['integrity_check'])}\n"
                f"Foreign-key violations: {report['foreign_key_violations']}\n"
                f"Projects: {report['record_counts']['projects']} · "
                f"Studies: {report['record_counts']['studies']} · "
                f"Runs: {report['record_counts']['runs']} · "
                f"Evidence: {report['record_counts']['evidence']}\n"
                f"SHA-256: {report['logical_sha256']}",
            )

        self.run_task(
            self.service.verify_research_database,
            show_report,
            "Checking SQLite integrity and provenance records",
        )

    def _backup_research_database(self) -> None:
        def show_backup(result: dict[str, Any]) -> None:
            QMessageBox.information(
                self,
                "Research database backup",
                f"Verified online backup created:\n{result['path']}\n\n"
                f"Projects: {result['backup']['record_counts']['projects']} · "
                f"Studies: {result['backup']['record_counts']['studies']} · "
                f"Runs: {result['backup']['record_counts']['runs']} · "
                f"Evidence: {result['backup']['record_counts']['evidence']}",
            )

        self.run_task(
            self.service.backup_research_database,
            show_backup,
            "Creating and verifying an online SQLite backup",
        )

    def _rehearse_research_restore(self) -> None:
        target, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a verified database backup",
            str(self.service.root / "backups"),
            "SQLite backups (*.sqlite3 *.db)",
        )
        if not target:
            return

        def show_restore(result: dict[str, Any]) -> None:
            counts = result["application_reopen"]["record_counts"]
            QMessageBox.information(
                self,
                "Restore rehearsal completed",
                "The backup was restored into an isolated private copy and reopened successfully. "
                "The current data root was left untouched.\n\n"
                f"Rehearsal copy:\n{result['restore_root']}\n\n"
                f"Projects: {counts['projects']} · Studies: {counts['studies']} · "
                f"Runs: {counts['runs']} · Evidence: {counts['evidence']}",
            )

        self.run_task(
            lambda: self.service.rehearse_research_restore(target),
            show_restore,
            "Restoring the backup to a separate root and reopening it",
        )

    def _run_independent_qualification(self) -> None:
        self.run_task(
            self.service.run_independent_qualification,
            self._show_qualification_results,
            "Running independent real-data method qualification",
        )

    def _show_qualification_results(self, records: list[dict[str, Any]]) -> None:
        if not records:
            QMessageBox.information(
                self,
                "Independent method qualification",
                "No admitted real-data snapshots are available to qualify.",
            )
            return
        lines = []
        for record in records:
            outcome = record.get("pass_fail") or record.get("status", "UNKNOWN")
            reason = record.get("reason")
            lines.append(
                f"{record['id']} · {record.get('status', 'UNKNOWN')} · {outcome}"
                + (f"\n  {reason}" if reason else "")
            )
        QMessageBox.information(
            self,
            "Independent method qualification",
            "\n\n".join(lines)
            + f"\n\nRecords were saved under:\n{self.service.root / 'qualification'}",
        )

    def _show_performance_mode(self) -> None:
        self._ensure_performance()
        self.menuBar().hide()
        self.performance_toolbar.show()
        # the toolbar layout keeps the generic QToolBar margins (12 px) until a StyleChange; they clip the header
        QApplication.sendEvent(self.performance_toolbar, QEvent(QEvent.Type.StyleChange))
        if self._perspective != "performance":
            self._perspective = "performance"
            self.navigator_dock.show()
            self.inspector_dock.show()
        self.navigator_stack.setCurrentWidget(self.performance_rail)
        self.navigator_dock.setTitleBarWidget(QWidget())
        self.navigator_dock.setMinimumWidth(196)
        self.navigator_dock.setMaximumWidth(232)
        self.inspector_dock.setWindowTitle(
            "ATHLETE 360"
            if self.performance.context_panel.current_athlete
            and self.performance.context_panel.views.currentWidget()
            == self.performance.context_panel.athlete_view
            else "DAILY CONTEXT"
        )
        self.inspector_stack.setCurrentWidget(self.performance.context_panel)
        self.inspector_dock.setMinimumWidth(280)
        self.inspector_dock.setMaximumWidth(340)
        self.resizeDocks(
            [self.navigator_dock, self.inspector_dock], [204, 300], Qt.Orientation.Horizontal
        )
        if not getattr(self, "_performance_context_loaded", False):
            self._performance_context_loaded = True
            self.run_task(
                lambda: self.service.performance_page_data("context")["context"],
                self._performance_context_loaded_from_service,
                "Loading squad and season context",
            )

    def _performance_context_loaded_from_service(self, context: dict[str, Any]) -> None:
        self.performance_header.set_context(context)
        self.performance_rail.set_context(context)

    def _show_research_mode(self) -> None:
        self.menuBar().show()
        if self.performance_toolbar is not None:
            self.performance_toolbar.hide()
        self.perspectives.setCurrentWidget(self.workbench)
        if self._perspective != "research":
            # The navigator lives in the Data pane; raw inspector detail is behind View > Advanced.
            self._perspective = "research"
            self.navigator_dock.hide()
            self.inspector_dock.hide()
        self.inspector_dock.setWindowTitle("Inspector")
        self.inspector_stack.setCurrentWidget(self.inspector)
        self.inspector_dock.setMinimumWidth(0)
        self.inspector_dock.setMaximumWidth(16777215)
        self.controller.refresh_provenance()

    def _run_spec(self, spec) -> None:
        """Results gate: run through the isolated worker, render in the result document, record the hash."""
        self._set_record_view(False)
        self.results_doc.clear()
        self._sync_result_actions()
        if spec.kind in DESCRIPTIVE_KINDS:
            self._run_descriptive(spec)
            return
        study_id = spec.study_id

        def finish(run: dict[str, Any] | None) -> None:
            self.progress.setVisible(False)
            self.status_text.setText("Ready")
            if spec.kind in ENGINE_KINDS and self.current_study_id != study_id:
                return  # the study changed while the run was in flight; never show it against another study
            if run is None:  # kind without a qualified engine: stated, never promotable
                self.results_doc.show_unavailable(spec)
                self.controller.set_last_run_hash(spec.spec_hash())
            else:
                self.results_doc.show_run(run, spec)
                self.research._run_completed(study_id, run)
                self.controller.set_last_run_hash(spec.spec_hash(), run.get("id", ""),
                                                  str(run.get("result_digest", ""))[:8])
                self._load_observed(run, spec)
            self._spec_changed(self.controller.current_spec())

        def failed(error: Exception) -> None:
            self.progress.setVisible(False)
            self.status_text.setText("Operation failed")
            self.controller.mark_run_failed()
            self.workbench.show_toast(f"{type(error).__name__}: {error}")

        self.status_text.setText("Running qualified scientific analysis (cannot be cancelled; the window stays usable)")
        self.progress.setVisible(True)
        run_analysis(self.service, study_id, spec, self.runner, finish, failed)

    def _run_descriptive(self, spec) -> None:
        """Descriptives, Frequencies, Athlete change: observed summaries of the snapshot rows (pandas),
        shown as descriptive blocks. No engine run, never promotable."""
        from .workbench import descriptive

        snapshot, table = spec.snapshot_id, spec.table
        provenance = {"source": "synthetic" if self.data_pane._detail.get("synthetic") else "real",
                      "snapshot_id": snapshot, "table": table}
        units = {v.name: v.unit for v in self.data_pane.variables() if v.unit}
        types = dict(spec.variable_types)
        subject = "subject_id" if types.get("subject_id") == "identifier" else None
        options = spec.effective_options()

        def build(frame) -> list:
            if spec.kind == "descriptives":
                factors = spec.role("factors")
                return [descriptive.DescriptivesBlock(frame, spec.role("outcome"), factors[0] if factors else None,
                                                      subject, provenance, units, options)]
            if spec.kind == "frequencies":
                return [descriptive.FrequenciesBlock(frame, spec.role("factors"), provenance)]
            outcome, athlete, occasion = spec.role("outcome")[0], spec.role("subject")[0], spec.role("occasion")[0]
            levels = sorted(frame[occasion].dropna().unique())
            first = options["reference_occasion"] if options["reference_occasion"] is not None else levels[0]
            last = options["contrast_occasion"] if options["contrast_occasion"] is not None else levels[-1]
            return [descriptive.AthleteChangeBlock(frame, outcome, athlete, occasion, first, last, provenance,
                                                   unit=units.get(outcome, ""))]

        def finish(frame) -> None:
            self.progress.setVisible(False)
            self.status_text.setText("Ready")
            if (self.data_pane.snapshot_id, self.data_pane.table) != (snapshot, table):
                return  # the dataset changed while the rows were loading
            try:
                self.results_doc.show_blocks(lambda: build(frame), spec, descriptive.DESCRIPTIVE_STATE)
            except (KeyError, IndexError, ValueError, TypeError) as error:
                failed(error)
                return
            self.controller.set_last_run_hash(spec.spec_hash())
            block = self.results_doc.blocks[0]
            # the syntax bar shows what was computed for the visible result (rule 6)
            self.workbench.set_syntax("# DESCRIPTIVE: no inference; not promoted as a modeled claim.\n" + block.syntax)
            self._spec_changed(self.controller.current_spec())

        def failed(error: Exception) -> None:
            self.progress.setVisible(False)
            self.status_text.setText("Operation failed")
            self.controller.mark_run_failed()
            self.workbench.show_toast(f"{type(error).__name__}: {error}")

        self.status_text.setText("Summarising observed rows")
        self.progress.setVisible(True)
        self.runner.submit(lambda: descriptive.load_table(self.service, snapshot, table), finish, failed)

    def _analysis_selected(self, key: str) -> None:
        """Signals shows the trial viewer in the Results pane; every other key the result document."""
        if key != "signals":
            if self.signals_view is not None and self.results_stack.currentWidget() is self.signals_view:
                self.results_stack.setCurrentWidget(self.results_doc)
            return
        from .workbench.signals_view import SignalsView

        if self.signals_view is None:
            self.signals_view = SignalsView(self.service, lambda fn, done: self.run_task(fn, done, "Loading signals"))
            self.signals_view.setAccessibleName("Signal inspection")
            self.signals_view.trial_selected.connect(lambda trial_id: self.workbench.set_syntax(
                "# OBSERVED signal, min/max-decimated for display; no analysis\n"
                f"DynamisAppService().get_signal_waveform({self.signals_view.snapshot_id!r}, {trial_id!r}, 2500)"))
            self.results_stack.addWidget(self.signals_view)
        self.action_study_record.setChecked(False)  # before switching: it resets the stack to the document
        self.results_stack.setCurrentWidget(self.signals_view)
        snapshot = self.data_pane.snapshot_id
        tables = {t["name"] for t in (self.data_pane._detail or {}).get("tables", [])}
        if snapshot and "signal_trials" in tables:
            if snapshot != self.signals_view.snapshot_id:
                self.signals_view.set_snapshot(snapshot)
        elif snapshot:
            self.workbench.show_toast("Signals needs a dataset with signal trials (e.g. the MoveSmart study)")

    def _show_trajectories(self, mode: str) -> None:
        if self.results_doc.trajectory_plot is None:
            self.workbench.show_toast("Run a mixed model to see its trajectories")
            return
        self._set_record_view(False)
        self.results_doc.set_trajectory_mode(mode)
        block = next(b for b in self.results_doc.blocks if getattr(b, "trajectory_stack", None))
        self.results_doc.ensureWidgetVisible(block, 0, 0)

    def _load_observed(self, run: dict[str, Any], spec) -> None:
        """Add the observed layer (snapshot rows) to a mixed-model trajectory figure, and the
        interactive 2D / 3D trajectories (explore_longitudinal of the run's outcome)."""
        if spec.kind != "mixed_model" or not run.get("snapshot_id"):
            return
        snapshot_id, table = run["snapshot_id"], spec.table
        study_id, metric = run.get("study_id") or spec.study_id, spec.outcome_metric_id()
        excluded = list(spec.effective_options().get("excluded_subject_ids") or [])

        def read() -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            rows: list[dict[str, Any]] = []
            while True:
                page = self.service.read_table_page(snapshot_id, table, len(rows), 500)
                rows += page["rows"]
                if not page["rows"] or len(rows) >= int(page["total_rows"]):
                    break
            try:
                explore = self.service.explore_longitudinal(study_id, metric, excluded) if metric else None
            except Exception:  # noqa: BLE001 - the interactive views are optional; the run stands alone
                explore = None
            return rows, explore

        def show(loaded) -> None:
            rows, explore = loaded
            if self.results_doc.run is run:  # still the visible result
                stale = self.results_doc.stale
                self.results_doc.selected_athlete = self.data_pane.selected_athlete()
                self.results_doc.show_run(run, self.results_doc.spec, rows, explore)
                self.results_doc.mark_stale(stale)
                self._sync_result_actions()

        self.runner.submit(read, show, lambda _error: None)  # the observed layer is optional

    def _spec_changed(self, spec) -> None:
        self.results_doc.check_spec(spec)
        self._sync_result_actions()

    def _sync_result_actions(self) -> None:
        doc = self.results_doc
        self.workbench.action_promote.setEnabled(doc.promotable)
        self.workbench.action_add_to_report.setEnabled(doc.promotable)
        self.workbench.action_export.setEnabled(bool(doc.run))

    def _set_record_view(self, record: bool) -> None:
        self.results_stack.setCurrentIndex(1 if record else 0)
        if self.action_study_record.isChecked() != record:
            self.action_study_record.setChecked(record)

    def _reset_results(self, record: bool = False) -> None:
        """Dataset or study switch: no result, spec or run state outlives its data."""
        self.results_doc.clear()
        self.controller.reset()
        self._sync_result_actions()
        self._set_record_view(record)

    def _export_results(self, path: str | None = None) -> None:
        if path is None:
            path, selected = QFileDialog.getSaveFileName(
                self, "Export figures", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
            if not path:
                return
            if not path.lower().endswith((".png", ".pdf", ".svg")):
                path += "." + selected.split("*.")[1].rstrip(")")
        try:
            written = self.results_doc.export(path)
        except (ValueError, OSError) as error:
            self.workbench.show_toast(str(error))
            return
        self.workbench.show_toast(f"Exported {len(written)} figure(s)")

    def _evidence_promoted(self, outcome: dict[str, Any]) -> None:
        run = self.results_doc.run or {}
        self.research._evidence_promoted(run.get("study_id", ""), outcome)
        self.workbench.show_toast("Promoted to evidence")

    def _report_cited(self, result: dict[str, Any]) -> None:
        run = self.results_doc.run or {}
        self.research._report_cited(run.get("study_id", ""), result)

    def show_performance_page(self, page: str) -> None:
        self._ensure_performance()
        self._show_performance_mode()
        page_alias = {"athlete": "today", "match": "monitor"}
        if page in page_alias:
            self.performance_rail.set_current(page_alias[page])
        else:
            self.performance_rail.set_current(page)
        self.current_target = {"type": "performance", "page": page}
        title = {"athlete": "Athlete 360", "match": "Match & Pose"}.get(
            page, self.performance.page_names[self.performance.page_keys.index(page)]
        )
        self.context.setText(title)
        self.workbench.set_provenance("DS-SYNTH-001 · NO REAL DATA", provenance="synthetic")  # until research mode returns
        self.perspectives.setCurrentWidget(self.performance)
        self.performance.select_page(page)

    def _search_performance(self, query: str) -> None:
        if not query:
            return
        self.run_task(
            lambda: self.service.performance_athlete(query),
            self._show_performance_athlete,
            f"Searching athlete records · {query}",
        )

    def _show_performance_athlete(self, detail: dict[str, Any]) -> None:
        self.show_performance_page("athlete")
        athlete_id = detail["subject"]["display_id"]
        index = self.performance.athlete_picker.findText(athlete_id)
        if index < 0:
            self.performance.athlete_picker.addItem(athlete_id)
            index = self.performance.athlete_picker.findText(athlete_id)
        self.performance.athlete_picker.setCurrentIndex(index)
        self.performance._athlete_loaded(detail)

    def _show_athlete_inspector(self, detail: dict[str, Any]) -> None:
        self.performance.context_panel.show_athlete(detail)
        self.inspector_dock.setWindowTitle("ATHLETE 360")
        self.inspector_dock.show()
        self.inspector_dock.raise_()

    def _show_daily_context(self) -> None:
        self.performance.context_panel.show_daily()
        self.inspector_dock.setWindowTitle("DAILY CONTEXT")

    def _open_full_athlete_profile(self, athlete_id: str) -> None:
        self.show_performance_page("athlete")
        index = self.performance.athlete_picker.findText(athlete_id)
        if index >= 0:
            self.performance.athlete_picker.setCurrentIndex(index)

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
        self.workbench.save_state()
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
            logging.getLogger("dynamis_science.desktop").error(
                "Background task failed: %s (%s)", label, type(error).__name__
            )
            if isinstance(error, ResearchConflict):
                box = QMessageBox(self)
                box.setWindowTitle("Record changed")
                box.setIcon(QMessageBox.Icon.Warning)
                box.setText(str(error))
                reload = box.addButton("Reload latest record", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Dismiss", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() is reload and self.current_target:
                    self.refresh_catalogue(self.current_target)
                return
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

    def _populate_navigation(self, values, select: dict[str, str] | None = None) -> None:
        projects, studies, datasets = values
        self.projects, self.studies, self.datasets = projects, studies, datasets
        self.projects = projects
        self.studies = studies
        self.datasets = datasets
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
        performance_root = QTreeWidgetItem(["Performance OS · synthetic fixture"])
        performance_root.setData(0, Qt.ItemDataRole.UserRole, {"type": "performance_root"})
        self.navigator.addTopLevelItem(performance_root)
        for page, label in zip(PERFORMANCE_PAGE_KEYS, PERFORMANCE_PAGE_NAMES):
            item = QTreeWidgetItem([label])
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {"type": "performance", "page": page},
            )
            performance_root.addChild(item)
        self.navigator.expandAll()
        self.workspace.setCurrentWidget(self.welcome)
        self.welcome.setText(
            f"Ready  ·  {len(projects)} projects  ·  {len(studies)} studies  ·  {len(datasets)} datasets"
        )
        self.status_text.setText("Ready")
        self.catalogue_loaded.emit()
        if select:
            self._select_catalogue_target(select)

    def refresh_catalogue(self, select: dict[str, str] | None = None) -> None:
        self.run_task(
            self._catalogue,
            lambda values: self._populate_navigation(values, select),
            "Refreshing research catalogue",
        )

    def _select_catalogue_target(self, target: dict[str, str]) -> None:
        for root_index in range(self.navigator.topLevelItemCount()):
            root = self.navigator.topLevelItem(root_index)
            for child_index in range(root.childCount()):
                child = root.child(child_index)
                if child.data(0, Qt.ItemDataRole.UserRole) == target:
                    self.navigator.setCurrentItem(child)
                    self._navigation_activated(child, 0)
                    return

    def _navigation_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        target = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if target.get("type") == "performance":
            self.show_performance_page(target["page"])
            return
        if target.get("type") == "performance_root":
            self.show_performance_page("today")
            return
        if target.get("type") == "project":
            project_id = target["id"]
            self.run_task(
                lambda: self.service.get_project(project_id),
                lambda project: self._show_project(project_id, project),
                "Opening project",
            )
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
            self._show_research_mode()
            self.current_target = None
            self.current_project = None
            self.current_study_id = None
            self.current_study = {}
            self._reset_results(record=True)
            self.controller.set_source("")
            self.data_pane.clear()
            self.workspace.setCurrentWidget(self.welcome)
            self.welcome.setText(item.text(0))

    def _open_research_study(self, study_id: str) -> None:
        study_parent = self.navigator.topLevelItem(1)
        for index in range(study_parent.childCount()):
            item = study_parent.child(index)
            target = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if target.get("id") == study_id:
                self.navigator.setCurrentItem(item)
                self._navigation_activated(item, 0)
                return
        QMessageBox.information(self, "Research link", f"Linked study {study_id} is not in the current catalogue.")

    def _show_project(self, project_id: str, project: dict[str, Any]) -> None:
        self._show_research_mode()
        self.current_target = {"type": "project", "id": project_id}
        self.current_project = project
        self.current_study_id = None
        self.current_study = {}
        self.current_snapshot_id = None
        self.context.setText(project.get("title", project_id))
        self._reset_results(record=True)
        self.controller.set_source("RESEARCH PROJECT")
        self.data_pane.clear()
        self.research.select_project(project)
        self.workspace.setCurrentWidget(self.research)
        self.research.tabs.setCurrentIndex(0)

    def _show_study(self, study_id: str, detail: dict[str, Any]) -> None:
        self._show_research_mode()
        self.current_target = {"type": "study", "id": study_id}
        self.current_project = detail.get("project")
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
        elif snapshot.get("synthetic") and snapshot.get("id") == "DS-SYNTH-001":
            badge = "SYNTHETIC FIXTURE · DS-SYNTH-001 · NO EMPIRICAL CLAIMS"
        elif snapshot.get("admitted_source"):
            badge = "FIXTURE-ONLY ADMISSION · " + "  ·  ".join(
                str(value) for value in (snapshot.get("id"), license_id, classification) if value
            )
        else:
            badge = f"SYNTHETIC FIXTURE · {snapshot.get('id', 'unknown snapshot')}"
        self.context.setText(detail.get("study", {}).get("title") or study_id)
        self._reset_results()
        real = bool(detail.get("real_data") or snapshot.get("real_data"))
        self.controller.set_source(badge, "real" if real else "synthetic", study_id)
        snapshot_id = self.current_snapshot_id
        if snapshot_id:
            self.run_task(
                lambda: self.service.get_dataset_detail(snapshot_id),
                lambda dataset: self.data_pane.set_dataset(snapshot_id, dataset)
                if self.current_snapshot_id == snapshot_id else None,
                "Reading dataset",
            )
        else:
            self.data_pane.clear()
        self.research.set_study(study_id, detail)
        self.workspace.setCurrentWidget(self.research)

    def _show_dataset(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        self._show_research_mode()
        self.current_target = {"type": "dataset", "id": snapshot_id}
        self.current_study_id = None
        self.current_study = {}
        self.current_project = None
        self.current_snapshot_id = snapshot_id
        self.context.setText(detail.get("label") or snapshot_id)
        source = detail.get("source", {})
        license_info = source.get("license", {})
        license_id = license_info.get("id") if isinstance(license_info, dict) else license_info
        if detail.get("real_data"):
            badge = "REAL DATA"
        elif detail.get("admitted_source"):
            badge = f"FIXTURE-ONLY ADMISSION · {snapshot_id}"
        else:
            badge = f"SYNTHETIC FIXTURE · {snapshot_id}"
        if license_id:
            badge = f"{badge}  ·  {license_id}"
        self._reset_results(record=True)
        self.controller.set_source(badge, "real" if detail.get("real_data") else "synthetic")
        self.data_pane.set_dataset(snapshot_id, detail)
        self.inspector.setPlainText(json.dumps(detail, indent=2, ensure_ascii=False, default=str))
        self.research.select_dataset(snapshot_id, detail)
        self.workspace.setCurrentWidget(self.research)
        self.research.tabs.setCurrentIndex(1)
        self.research.dataset_tabs.setCurrentIndex(0)

    def _new_project(self) -> None:
        datasets = getattr(self, "datasets", [])
        dialog = ProjectDialog(datasets, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        self.run_task(
            lambda: self.service.create_project(payload),
            lambda project: self.refresh_catalogue({"type": "project", "id": project["id"]}),
            "Creating research project",
        )

    def _new_research_object(self, monitoring: bool) -> None:
        projects = [item for item in getattr(self, "projects", []) if item.get("status") != "ARCHIVED"]
        if not projects:
            QMessageBox.information(self, "Research object", "Create an active project first.")
            return
        project_id = None
        if self.current_target and self.current_target.get("type") == "project":
            project_id = self.current_target["id"]
        elif self.current_target and self.current_target.get("type") == "study":
            project_id = (self.current_study.get("study") or {}).get("project_id")
        dialog = StudyDialog(projects, getattr(self, "datasets", []), project_id, monitoring=monitoring, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        project_id = payload.pop("project_id")
        operation = (
            (lambda: self.service.create_monitoring_program(project_id, payload))
            if monitoring
            else (lambda: self.service.create_study(project_id, payload))
        )

        def opened(detail: dict[str, Any]) -> None:
            entity = detail.get("study", {})
            self.refresh_catalogue({"type": "study", "id": entity["id"]})

        self.run_task(operation, opened, "Creating monitoring program" if monitoring else "Creating study")

    def _edit_current(self) -> None:
        if not self.current_target:
            QMessageBox.information(self, "Edit", "Select a project or authored study first.")
            return
        if self.current_target["type"] == "project" and self.current_project:
            dialog = ProjectDialog(getattr(self, "datasets", []), self.current_project, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            project_id = self.current_project["id"]
            payload = dialog.payload()
            self.run_task(
                lambda: self.service.update_project(project_id, payload),
                lambda _project: self.refresh_catalogue({"type": "project", "id": project_id}),
                "Saving project changes",
            )
            return
        if self.current_target["type"] != "study" or not self.current_study_id:
            QMessageBox.information(self, "Edit", "Datasets are immutable; edit project or study metadata instead.")
            return
        if not self.current_study_id.startswith(("STUDY-U-", "PROG-U-")):
            QMessageBox.information(self, "Edit", "Admitted reference studies are read-only. Create an authored study to work with this dataset.")
            return
        detail = self.current_study
        study = detail.get("study", {})
        monitoring = detail.get("kind") == "MONITORING" or study.get("kind") == "MONITORING"
        dialog = StudyDialog(
            [item for item in self.projects if item.get("status") != "ARCHIVED"],
            self.datasets,
            detail=detail,
            monitoring=monitoring,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        study_id = self.current_study_id
        self.run_task(
            lambda: self.service.update_study(study_id, payload, payload.get("base_version")),
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            "Saving research object changes",
        )

    def _authored_study_id(self) -> str | None:
        study_id = self.current_study_id
        if study_id and study_id.startswith(("STUDY-U-", "PROG-U-")):
            return study_id
        QMessageBox.information(self, "Research authoring", "Open an authored research study or monitoring program first.")
        return None

    def _create_cohort(self, study_id: str, cohort: dict[str, Any] | None = None) -> None:
        dialog = CohortDialog(cohort, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        if cohort:
            cohort_id = cohort["id"]
            operation = lambda: self.service.update_cohort(cohort_id, payload)
            label = "Saving cohort version"
        else:
            operation = lambda: self.service.create_cohort(study_id, payload)
            label = "Creating cohort"
        self.run_task(
            operation,
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            label,
        )

    def _new_cohort(self) -> None:
        study_id = self._authored_study_id()
        if study_id:
            self._create_cohort(study_id)

    def _edit_cohort(self) -> None:
        study_id = self._authored_study_id()
        if not study_id:
            return
        self.run_task(
            lambda: self.service.list_cohorts(study_id),
            lambda cohorts: self._choose_cohort_to_edit(study_id, cohorts),
            "Loading cohort versions",
        )

    def _choose_cohort_to_edit(self, study_id: str, cohorts: list[dict[str, Any]]) -> None:
        cohort = next((item for item in reversed(cohorts) if item.get("status") == "DRAFT"), None)
        if cohort is None and cohorts:
            QMessageBox.information(self, "Cohort", "The current cohort is frozen. Fork it to make changes.")
            return
        if cohort is None:
            QMessageBox.information(self, "Cohort", "This study has no saved cohort.")
            return
        self._create_cohort(study_id, cohort)

    def _freeze_cohort(self) -> None:
        study_id = self._authored_study_id()
        cohort_id = (self.current_study.get("cohort") or {}).get("id")
        if not study_id or not cohort_id:
            return
        self.run_task(
            lambda: self.service.freeze_cohort(cohort_id),
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            "Freezing cohort membership",
        )

    def _fork_cohort(self) -> None:
        study_id = self._authored_study_id()
        cohort_id = (self.current_study.get("cohort") or {}).get("id")
        if not study_id or not cohort_id:
            return
        name, accepted = QInputDialog.getText(self, "Fork cohort", "Name for the new draft cohort")
        if not accepted:
            return
        self.run_task(
            lambda: self.service.fork_cohort(cohort_id, name.strip() or None),
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            "Forking cohort version",
        )

    def _open_plan_dialog(self, study_id: str, plan: dict[str, Any] | None, values) -> None:
        methods, metrics, cohorts = values
        dialog = PlanDialog(methods, metrics, cohorts, plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        if plan:
            operation = lambda: self.service.update_plan(plan["id"], payload)
            label = "Saving analysis plan version"
        else:
            operation = lambda: self.service.create_plan(study_id, payload)
            label = "Creating analysis plan"
        self.run_task(
            operation,
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            label,
        )

    def _plan_options(self, study_id: str, plan: dict[str, Any] | None = None) -> None:
        snapshot_id = self.current_study.get("snapshot", {}).get("id")
        self.run_task(
            lambda: (
                self.service.list_methods(snapshot_id),
                self.service.list_metrics(snapshot_id),
                self.service.list_cohorts(study_id),
            ),
            lambda values: self._open_plan_dialog(study_id, plan, values),
            "Loading registered analysis methods",
        )

    def _new_plan(self) -> None:
        study_id = self._authored_study_id()
        if study_id:
            self._plan_options(study_id)

    def _edit_plan(self) -> None:
        study_id = self._authored_study_id()
        if not study_id:
            return
        plans = self.service.list_plans(study_id)
        plan = next((item for item in reversed(plans) if item.get("status") == "DRAFT"), None)
        if plan is None:
            QMessageBox.information(self, "Analysis plan", "The current plan is frozen. Fork it to make changes.")
            return
        self._plan_options(study_id, plan)

    def _freeze_plan(self) -> None:
        study_id = self._authored_study_id()
        plan_id = (self.current_study.get("plan") or {}).get("id")
        if not study_id or not plan_id:
            return
        self.run_task(
            lambda: self.service.freeze_plan(plan_id),
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            "Freezing analysis plan",
        )

    def _fork_plan(self) -> None:
        study_id = self._authored_study_id()
        plan_id = (self.current_study.get("plan") or {}).get("id")
        if not study_id or not plan_id:
            return
        name, accepted = QInputDialog.getText(self, "Fork analysis plan", "Name for the new draft plan")
        if not accepted:
            return
        self.run_task(
            lambda: self.service.fork_plan(plan_id, name.strip() or None),
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            "Forking analysis plan version",
        )

    def _history_dialog(self, title: str, records: list[dict[str, Any]]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setPlainText(json.dumps(records, indent=2, ensure_ascii=False, default=str))
        layout.addWidget(browser)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.resize(850, 600)
        dialog.exec()

    def _cohort_history(self) -> None:
        cohort_id = (self.current_study.get("cohort") or {}).get("id")
        if cohort_id:
            self.run_task(
                lambda: self.service.cohort_history(cohort_id),
                lambda records: self._history_dialog("Cohort version history", records),
                "Loading cohort history",
            )

    def _plan_history(self) -> None:
        plan_id = (self.current_study.get("plan") or {}).get("id")
        if plan_id:
            self.run_task(
                lambda: self.service.plan_history(plan_id),
                lambda records: self._history_dialog("Analysis plan history", records),
                "Loading plan history",
            )

    def _open_import(self) -> None:
        ImportReviewDialog(self.service, self.run_task, self._admission_saved, self).exec()

    def _open_admission(self) -> None:
        dialog = DatasetAdmissionDialog(
            self.service,
            self.run_task,
            self._admission_saved,
            self,
        )
        dialog.exec()

    def _admission_saved(self, record: dict[str, Any]) -> None:
        snapshot_id = record.get("dataset_snapshot_id")
        self.statusBar().showMessage(
            f"Admission recorded: {snapshot_id or record.get('status', 'QC result')}", 8000
        )
        target = {"type": "dataset", "id": snapshot_id} if snapshot_id else None
        self.refresh_catalogue(target)

    def _archive_current(self) -> None:
        if not self.current_target:
            return
        target = self.current_target.copy()
        if target["type"] == "project":
            operation = lambda: self.service.archive_project(target["id"], True)
        elif target["type"] == "study" and target["id"].startswith(("STUDY-U-", "PROG-U-")):
            operation = lambda: self.service.transition_study(target["id"], "ARCHIVED")
        else:
            QMessageBox.information(self, "Archive", "Only authored projects and studies can be archived.")
            return
        self.run_task(operation, lambda _value: self.refresh_catalogue(), "Archiving research record")

    def _restore_current(self) -> None:
        if not self.current_target:
            return
        target = self.current_target.copy()
        if target["type"] == "project":
            operation = lambda: self.service.archive_project(target["id"], False)
        elif target["type"] == "study" and target["id"].startswith(("STUDY-U-", "PROG-U-")):
            prior = self.current_study.get("study", {}).get("state_before_archive", "DRAFT")
            operation = lambda: self.service.transition_study(target["id"], prior)
        else:
            QMessageBox.information(self, "Restore", "Only archived authored records can be restored.")
            return
        self.run_task(
            operation,
            lambda _value: self.refresh_catalogue(target),
            "Restoring research record",
        )

    def _transition_current_study(self) -> None:
        study_id = self._authored_study_id()
        if not study_id:
            return
        allowed = self.current_study.get("allowed_transitions", [])
        if not allowed:
            QMessageBox.information(self, "Study state", "No state transition is available from the current state.")
            return
        target, accepted = QInputDialog.getItem(
            self, "Study state", "Transition to", allowed, 0, False
        )
        if not accepted:
            return
        self.run_task(
            lambda: self.service.transition_study(study_id, target),
            lambda _result: self.refresh_catalogue({"type": "study", "id": study_id}),
            "Recording study state transition",
        )

    def _object_history(self) -> None:
        if not self.current_target:
            return
        target = self.current_target.copy()
        if target["type"] == "project":
            operation = lambda: self.service.project_history(target["id"])
            title = "Project version history"
        elif target["type"] == "study" and target["id"].startswith(("STUDY-U-", "PROG-U-")):
            operation = lambda: self.service.study_history(target["id"])
            title = "Study version history"
        else:
            QMessageBox.information(self, "History", "Version history is available for authored projects and studies.")
            return
        self.run_task(operation, lambda records: self._history_dialog(title, records), "Loading version history")

    def _report_history(self) -> None:
        study_id = self._authored_study_id()
        if study_id:
            self.run_task(
                lambda: self.service.report_versions(study_id),
                lambda records: self._history_dialog("Frozen report versions", records),
                "Loading report versions",
            )

    def _compare_report_versions(self) -> None:
        study_id = self._authored_study_id()
        if not study_id:
            QMessageBox.information(
                self, "Report comparison", "Open an authored research study first."
            )
            return

        def load_versions() -> list[dict[str, Any]]:
            versions = self.service.report_versions(study_id)
            return [
                self.service.get_report_version(study_id, int(item["version"]))
                for item in reversed(versions)
            ]

        self.run_task(
            load_versions,
            self._show_report_version_comparison,
            "Loading frozen report versions",
        )

    def _open_scientific_library(self) -> None:
        self.run_task(
            self.service.scientific_library,
            lambda library: ScientificLibraryDialog(library, self).exec(),
            "Loading scientific metric, protocol and method definitions",
        )

    def _show_report_version_comparison(self, versions: list[dict[str, Any]]) -> None:
        if len(versions) < 2:
            QMessageBox.information(
                self, "Report comparison", "Freeze at least two report versions to compare them."
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Compare frozen report versions")
        layout = QVBoxLayout(dialog)
        selectors = QHBoxLayout()
        left_version = QComboBox()
        right_version = QComboBox()
        for report in versions:
            label = f"v{report['version']} · {report.get('frozen_at', report.get('updated_at', ''))}"
            left_version.addItem(label, report["version"])
            right_version.addItem(label, report["version"])
        right_version.setCurrentIndex(right_version.count() - 1)
        selectors.addWidget(left_version)
        selectors.addWidget(QLabel("compared with"))
        selectors.addWidget(right_version)
        layout.addLayout(selectors)
        comparison = QTextBrowser()
        comparison.setOpenExternalLinks(False)
        layout.addWidget(comparison, 1)
        documents = {
            int(report["version"]): json.dumps(
                {
                    key: report.get(key)
                    for key in (
                        "title",
                        "summary",
                        "conclusion",
                        "recommendations",
                        "narrative_note",
                        "frozen_content",
                    )
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ).splitlines()
            for report in versions
        }

        def render_diff() -> None:
            first = int(left_version.currentData())
            second = int(right_version.currentData())
            html = difflib.HtmlDiff(wrapcolumn=100).make_file(
                documents[first],
                documents[second],
                fromdesc=f"Version {first}",
                todesc=f"Version {second}",
            )
            comparison.setHtml(html)

        left_version.currentIndexChanged.connect(render_diff)
        right_version.currentIndexChanged.connect(render_diff)
        render_diff()
        dialog.resize(1100, 720)
        dialog.exec()

    def _open_admission_history(self) -> None:
        self.run_task(
            lambda: (self.service.list_admission_records(), self.service.list_admission_quality()),
            lambda values: AdmissionHistoryDialog(values[0], values[1], self).exec(),
            "Loading admission and QC history",
        )


class ResearchWorkbench(QWidget):
    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window = window
        self.service = window.service
        self.latest_run: dict[str, Any] | None = None
        self.latest_evidence_id: str | None = None
        self.report_version: int | None = None
        self.report_document_version: int | None = None
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
        self.dataset_tabs = QTabWidget()
        preview_page = QWidget()
        preview_layout = QVBoxLayout(preview_page)
        controls = QHBoxLayout()
        self.table_picker = QComboBox()
        self.table_picker.currentIndexChanged.connect(self._table_changed)
        controls.addWidget(QLabel("Snapshot table"))
        controls.addWidget(self.table_picker, 1)
        preview_layout.addLayout(controls)
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table_model = ParquetPreviewTableModel(self.service, self.window.runner)
        self.table.setModel(self.table_model)
        self.table.verticalHeader().setDefaultSectionSize(23)
        preview_layout.addWidget(self.table, 1)
        self.table_status = QLabel("Select a study or dataset to inspect bounded Parquet pages.")
        preview_layout.addWidget(self.table_status)
        self.dataset_tabs.addTab(preview_page, "Parquet preview")

        cohort_page = QWidget()
        cohort_layout = QVBoxLayout(cohort_page)
        cohort_controls = QHBoxLayout()
        self.cohort_picker = QComboBox()
        resolve_button = QPushButton("Resolve cohort")
        resolve_button.clicked.connect(self._resolve_selected_cohort)
        cohort_controls.addWidget(QLabel("Saved cohort"))
        cohort_controls.addWidget(self.cohort_picker, 1)
        cohort_controls.addWidget(resolve_button)
        cohort_layout.addLayout(cohort_controls)
        self.cohort_summary = QLabel("Open a study to resolve its cohort.")
        cohort_layout.addWidget(self.cohort_summary)
        self.cohort_table = QTableView()
        self.cohort_table_model = RecordTableModel()
        self.cohort_table.setModel(self.cohort_table_model)
        self.cohort_table.setAlternatingRowColors(True)
        cohort_layout.addWidget(self.cohort_table, 1)
        self.dataset_tabs.addTab(cohort_page, "Cohort resolution")
        layout.addWidget(self.dataset_tabs)

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
        self.analysis_tabs = QTabWidget()
        run_page = QWidget()
        run_layout = QVBoxLayout(run_page)
        controls = QGridLayout()
        self.method_picker = QComboBox()
        self.analysis_metric_picker = QComboBox()
        for picker in (self.method_picker, self.analysis_metric_picker):
            picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            picker.setMinimumContentsLength(16)
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
        controls.addWidget(self.method_picker, 0, 0, 1, 2)
        controls.addWidget(self.analysis_metric_picker, 0, 2)
        controls.addWidget(self.parameters, 1, 0, 1, 3)
        controls.addWidget(execute_button, 2, 0)
        controls.addWidget(self.show_figure_button, 2, 1)
        controls.addWidget(export_run, 2, 2)
        run_layout.addLayout(controls)
        results = QTabWidget()
        self.run_result_tabs = results
        self.run_output = QTextBrowser()
        self.run_plot_holder = QWidget()
        holder_layout = QVBoxLayout(self.run_plot_holder)
        holder_layout.addWidget(QLabel("Run an analysis to create a scientific figure."))
        results.addTab(self.run_output, "Result")
        results.addTab(self.run_plot_holder, "Figure")
        run_layout.addWidget(results, 1)
        self.analysis_tabs.addTab(run_page, "Analysis run")
        self.investigation_editor = InvestigationEditor(
            self.service, self.window.run_task, self
        )
        self.analysis_tabs.addTab(self.investigation_editor, "Investigation")
        layout.addWidget(self.analysis_tabs)

    def _build_evidence(self) -> None:
        page = self.tabs.widget(4)
        layout = QVBoxLayout(page)
        buttons = QGridLayout()
        promote_button = QPushButton("Promote completed run to evidence")
        promote_button.clicked.connect(self._promote)
        cite_button = QPushButton("Cite promoted evidence")
        cite_button.clicked.connect(self._cite_latest)
        uncite_button = QPushButton("Remove current citation")
        uncite_button.clicked.connect(self._uncite_latest)
        freeze_button = QPushButton("Freeze report version")
        freeze_button.clicked.connect(self._freeze_report)
        lineage_button = QPushButton("Show provenance lineage")
        lineage_button.clicked.connect(self._lineage)
        export_button = QPushButton("Export versioned HTML report…")
        export_button.clicked.connect(self.export_report)
        for index, button in enumerate((promote_button, cite_button, uncite_button, lineage_button, freeze_button, export_button)):
            buttons.addWidget(button, index // 2, index % 2)
        layout.addLayout(buttons)
        self.evidence_output = QTextBrowser()
        self.evidence_output.setMinimumHeight(130)
        layout.addWidget(self.evidence_output, 1)
        narrative = QFormLayout()
        self.report_title = QLineEdit()
        self.report_summary = QPlainTextEdit()
        self.report_summary.setMaximumHeight(55)
        self.report_conclusion = QPlainTextEdit()
        self.report_conclusion.setMaximumHeight(55)
        self.report_recommendations = QPlainTextEdit()
        self.report_recommendations.setMaximumHeight(55)
        narrative.addRow("Report title", self.report_title)
        narrative.addRow("Summary", self.report_summary)
        narrative.addRow("Conclusion", self.report_conclusion)
        narrative.addRow("Recommendations", self.report_recommendations)
        layout.addLayout(narrative)
        self.save_report_button = QPushButton("Save report draft")
        self.save_report_button.clicked.connect(self._save_report_draft)
        layout.addWidget(self.save_report_button)
        self.report_preview = QTextBrowser()
        layout.addWidget(self.report_preview, 2)

    def set_study(self, study_id: str, detail: dict[str, Any]) -> None:
        for index in range(1, len(self._builders)):
            self._ensure_tab(index)
        self._clear_study_views()
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
        self.report_document_version = None
        self.exploration_result = None
        self.investigation_editor.set_study(study_id)
        self.method_picker.clear()
        self.metric_picker.clear()
        self.analysis_metric_picker.clear()
        self.execute_button.setEnabled(study_id != "STUDY-001")
        self.save_report_button.setEnabled(False)
        if study_id == "STUDY-001":
            self.run_output.setPlainText(
                "The synthetic regression fixture is available for inspection and signal QA. "
                "Persisted research runs are created from an authored project and study."
            )
        self._load_dataset(self.snapshot_id)
        self._load_cohorts(study_id)
        self._load_controls()
        self._load_runs_and_report()

    def select_project(self, project: dict[str, Any]) -> None:
        self._ensure_tab(0)
        self._clear_study_views()
        self.study_id = None
        self.detail = {}
        self.snapshot_id = None
        self.latest_run = None
        self.latest_evidence_id = None
        self.report_version = None
        self.report_document_version = None
        self.exploration_result = None
        if hasattr(self, "execute_button"):
            self.execute_button.setEnabled(False)
        if hasattr(self, "save_report_button"):
            self.save_report_button.setEnabled(False)
        self.overview.setPlainText(json.dumps(project, indent=2, ensure_ascii=False, default=str))

    def select_dataset(self, snapshot_id: str, detail: dict[str, Any]) -> None:
        for index in range(1, len(self._builders)):  # method_picker etc. live in later lazy tabs
            self._ensure_tab(index)
        self._clear_study_views()
        self.study_id = None
        self.detail = {"snapshot": detail}
        self.snapshot_id = snapshot_id
        self.latest_run = None
        self.latest_evidence_id = None
        self.report_version = None
        self.report_document_version = None
        self.exploration_result = None
        self.method_picker.clear()
        self.metric_picker.clear()
        self.analysis_metric_picker.clear()
        if hasattr(self, "execute_button"):
            self.execute_button.setEnabled(False)
        if hasattr(self, "save_report_button"):
            self.save_report_button.setEnabled(False)
        self._load_dataset(snapshot_id, detail)
        self.dataset_tabs.setCurrentIndex(0)
        self.window.inspector.setPlainText(json.dumps(detail, indent=2, ensure_ascii=False, default=str))

    def _clear_study_views(self) -> None:
        if hasattr(self, "table_model"):
            self.table_picker.blockSignals(True)
            self.table_picker.clear()
            self.table_picker.blockSignals(False)
            self.table_model.set_table("", "", 0, [])
            self.table_status.setText("Loading dataset metadata…")
            self.cohort_picker.clear()
            self.cohort_table_model.set_rows([])
            self.cohort_summary.setText("Open a study to resolve its cohort.")
        if hasattr(self, "run_output"):
            self.run_output.clear()
            self.parameters.clear()
            self.show_figure_button.setEnabled(False)
            self.run_result_tabs.setCurrentIndex(0)
        if hasattr(self, "run_plot"):
            self.run_plot.figure.clear()
            self.run_plot.canvas.draw_idle()
        if hasattr(self, "exploration_plot"):
            self.exploration_plot.figure.clear()
            self.exploration_plot.canvas.draw_idle()
            self.signal_plot.clear()
            self.trial_picker.clear()
        if hasattr(self, "evidence_output"):
            self.evidence_output.clear()
            self.report_preview.clear()
            self.report_title.clear()
            self.report_summary.clear()
            self.report_conclusion.clear()
            self.report_recommendations.clear()

    def _load_dataset(self, snapshot_id: str | None, detail: dict[str, Any] | None = None) -> None:
        if not snapshot_id:
            return
        self.window.run_task(
            lambda: detail or self.service.get_dataset_detail(snapshot_id),
            lambda value: self._dataset_loaded(snapshot_id, value),
            "Reading Parquet metadata",
        )

    def _load_cohorts(self, study_id: str) -> None:
        self.window.run_task(
            lambda: self.service.list_cohorts(study_id),
            lambda cohorts: self._cohorts_loaded(study_id, cohorts),
            "Loading cohort versions",
        )

    def _cohorts_loaded(self, study_id: str, cohorts: list[dict[str, Any]]) -> None:
        if study_id != getattr(self, "study_id", None):
            return
        self.cohort_picker.clear()
        for cohort in cohorts:
            self.cohort_picker.addItem(
                f"{cohort.get('name', cohort['id'])} · {cohort.get('status', 'DRAFT')} · v{cohort.get('version', 1)}",
                cohort["id"],
            )
        if not cohorts and study_id in {"STUDY-REAL-001", "STUDY-REAL-002", "STUDY-001"}:
            self.cohort_picker.addItem("Admitted study cohort", None)
        if not self.cohort_picker.count():
            self.cohort_summary.setText("No cohort is saved for this study.")

    def _resolve_selected_cohort(self) -> None:
        if not getattr(self, "study_id", None):
            self.cohort_summary.setText("Open a study to resolve a cohort.")
            return
        study_id = self.study_id
        cohort_id = self.cohort_picker.currentData()
        self.window.run_task(
            lambda: self.service.resolve_cohort(study_id, cohort_id=cohort_id),
            lambda result: self._cohort_resolved(study_id, result),
            "Resolving cohort membership and quality",
        )

    def _cohort_resolved(self, study_id: str, result: dict[str, Any]) -> None:
        if study_id != self.study_id:
            return
        cohort = result.get("cohort", {})
        self.cohort_summary.setText(
            f"{cohort.get('name', cohort.get('id', 'Cohort'))} · {cohort.get('status', 'DRAFT')} · "
            f"{result.get('n', 0):,} included · "
            f"{len(result.get('excluded_subjects', [])):,} excluded · "
            f"{result.get('snapshot_id', self.snapshot_id)}"
        )
        self.cohort_table_model.set_rows(result.get("athletes", []))
        self.window.inspector.setPlainText(
            json.dumps(
                {
                    "cohort": cohort,
                    "trial_quality": result.get("trial_quality"),
                    "exclusion_criteria": result.get("exclusion_criteria"),
                    "snapshot_id": result.get("snapshot_id"),
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
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
                {key: run.get(key) for key in ("id", "method_id", "method_version", "method_status", "status", "result", "diagnostics", "result_digest", "reproducibility_key")},
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
        self.run_result_tabs.setCurrentWidget(self.run_plot_holder)

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
        self.latest_evidence_id = artifact.get("id")
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
        if result.get("version") is not None:
            self.report_document_version = result["version"]
        self.report_version = None
        self._load_runs_and_report()

    def _uncite_latest(self) -> None:
        if not self.latest_evidence_id or not getattr(self, "study_id", None):
            QMessageBox.information(self, "Report citation", "Promote a completed run to evidence first.")
            return
        study_id = self.study_id
        artifact_id = self.latest_evidence_id
        self.window.run_task(
            lambda: self.service.uncite_report_artifact(study_id, artifact_id),
            lambda result: self._report_cited(study_id, result),
            "Removing report citation",
        )

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
        self.lineage_dialog = LineageDialog(graph, self.window)
        self.lineage_dialog.exec()

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
        self.report_document_version = int(report.get("version", 1))
        self.report_version = report.get("version") if report.get("status") == "FROZEN" else None
        self.report_title.setText(report.get("title", ""))
        self.report_summary.setPlainText(report.get("summary", ""))
        self.report_conclusion.setPlainText(report.get("conclusion", ""))
        self.report_recommendations.setPlainText(report.get("recommendations", ""))
        self.save_report_button.setEnabled(study_id.startswith(("STUDY-U-", "PROG-U-")))
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

    def _save_report_draft(self) -> None:
        study_id = getattr(self, "study_id", None)
        if not study_id or not study_id.startswith(("STUDY-U-", "PROG-U-")):
            return
        payload = {
            "title": self.report_title.text().strip(),
            "summary": self.report_summary.toPlainText(),
            "conclusion": self.report_conclusion.toPlainText(),
            "recommendations": self.report_recommendations.toPlainText(),
        }
        base_version = self.report_document_version

        def saved(report: dict[str, Any]) -> None:
            if study_id != self.study_id:
                return
            self.report_document_version = report["version"]
            self.report_version = None
            self._load_runs_and_report()

        self.window.run_task(
            lambda: self.service.update_report(study_id, payload, base_version),
            saved,
            "Saving report draft",
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
