"""Native Qt authoring and dataset-admission dialogs."""

from __future__ import annotations

import json
import getpass
import uuid
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .services import DynamisAppService


class ProjectDialog(QDialog):
    def __init__(
        self,
        datasets: list[dict[str, Any]],
        project: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Edit project" if project else "New project")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(project.get("title", "") if project else "")
        self.description = QPlainTextEdit(project.get("description", "") if project else "")
        self.objectives = QPlainTextEdit(
            "\n".join(project.get("objectives", [])) if project else ""
        )
        form.addRow("Title", self.title)
        form.addRow("Description", self.description)
        form.addRow("Objectives (one per line)", self.objectives)
        layout.addLayout(form)
        layout.addWidget(QLabel("Datasets available to this project"))
        self.dataset_checks: list[tuple[QCheckBox, str]] = []
        selected = set(project.get("dataset_snapshot_ids", [])) if project else set()
        for dataset in datasets:
            label = f"{dataset.get('label') or dataset['id']} · {dataset['id']}"
            source = dataset.get("source", {})
            license_info = source.get("license", {})
            license_id = license_info.get("id") if isinstance(license_info, dict) else license_info
            if license_id:
                label += f" · {license_id}"
            checkbox = QCheckBox(label)
            checkbox.setChecked(dataset["id"] in selected)
            layout.addWidget(checkbox)
            self.dataset_checks.append((checkbox, dataset["id"]))
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def payload(self) -> dict[str, Any]:
        result = {
            "title": self.title.text().strip(),
            "description": self.description.toPlainText().strip(),
            "objectives": [
                line.strip()
                for line in self.objectives.toPlainText().splitlines()
                if line.strip()
            ],
            "dataset_snapshot_ids": [
                snapshot_id for checkbox, snapshot_id in self.dataset_checks if checkbox.isChecked()
            ],
        }
        if self.project:
            result["base_version"] = self.project["version"]
        return result

    def accept(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Project", "A project title is required.")
            return
        super().accept()


class StudyDialog(QDialog):
    DESIGNS = (
        ("OBSERVATIONAL_LONGITUDINAL", "Observational longitudinal"),
        ("REPEATED_MEASURES", "Repeated measures"),
        ("MEASUREMENT_REPEATED_TRIALS", "Repeated-trial measurement"),
        ("DESCRIPTIVE", "Descriptive"),
    )

    def __init__(
        self,
        projects: list[dict[str, Any]],
        datasets: list[dict[str, Any]],
        project_id: str | None = None,
        detail: dict[str, Any] | None = None,
        monitoring: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.projects = projects
        self.datasets = datasets
        self.detail = detail
        self.monitoring = monitoring
        study = (detail or {}).get("study", {})
        self.setWindowTitle(
            ("Edit " if detail else "New ")
            + ("monitoring program" if monitoring else "research study")
        )
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.project = QComboBox()
        for project in projects:
            self.project.addItem(project["title"], project["id"])
        project_id = project_id or study.get("project_id")
        project_index = self.project.findData(project_id)
        if project_index >= 0:
            self.project.setCurrentIndex(project_index)
        self.project.setEnabled(detail is None)
        self.title = QLineEdit(study.get("title", "") if detail else "")
        self.question = QPlainTextEdit(
            (detail or {}).get("question", {}).get("statement", "")
            or study.get("research_question", "")
        )
        self.population = QLineEdit(study.get("population", "") if detail else "")
        self.estimand = QLineEdit(
            (detail or {}).get("question", {}).get("estimand", "")
        )
        self.intervention = QLineEdit(study.get("intervention", "") if detail else "")
        self.dataset = QComboBox()
        for dataset in datasets:
            self.dataset.addItem(
                f"{dataset.get('label') or dataset['id']} · {dataset['id']}",
                dataset["id"],
            )
        snapshot_id = study.get("dataset_snapshot_id")
        if snapshot_id:
            index = self.dataset.findData(snapshot_id)
            if index >= 0:
                self.dataset.setCurrentIndex(index)
        self.dataset.setEnabled(detail is None)
        self.metric_picker = QComboBox()
        self.dataset.currentIndexChanged.connect(self._load_metrics)
        self._load_metrics()
        outcomes = (study.get("outcomes") or {}).get("primary", [])
        metric_id = outcomes[0].get("id") if outcomes else None
        if metric_id is None and detail:
            metric_id = (detail.get("plan") or {}).get("outcome_metric_id")
        if metric_id:
            index = self.metric_picker.findData(metric_id)
            if index >= 0:
                self.metric_picker.setCurrentIndex(index)
        self.metric_picker.setEnabled(detail is None)
        self.design = QComboBox()
        for value, label in self.DESIGNS:
            self.design.addItem(label, value)
        design_index = self.design.findData(study.get("design"))
        if design_index >= 0:
            self.design.setCurrentIndex(design_index)
        self.design.setEnabled(detail is None)
        form.addRow("Project", self.project)
        form.addRow("Title", self.title)
        form.addRow("Research question", self.question)
        form.addRow("Dataset snapshot", self.dataset)
        form.addRow("Primary metric", self.metric_picker)
        if not monitoring:
            form.addRow("Design", self.design)
            form.addRow("Population", self.population)
            form.addRow("Estimand", self.estimand)
            form.addRow("Intervention / exposure", self.intervention)
        else:
            self.start_week = QSpinBox()
            self.start_week.setRange(1, 520)
            self.start_week.setValue(int(study.get("start_week", 5)))
            self.weeks = QSpinBox()
            self.weeks.setRange(1, 104)
            schedule = (detail or {}).get("schedule", {})
            start_week = int(schedule.get("start_week", study.get("start_week", 5)))
            end_week = int(study.get("end_week", start_week + 11))
            self.start_week.setValue(start_week)
            self.weeks.setValue(int(schedule.get("weeks", max(1, end_week - start_week + 1))))
            form.addRow("Start week", self.start_week)
            form.addRow("Duration (weeks)", self.weeks)
        self.hypotheses = QPlainTextEdit(
            "\n".join(item.get("statement", "") for item in (detail or {}).get("hypotheses", []))
        )
        if not monitoring:
            form.addRow("Hypotheses (one per line)", self.hypotheses)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_metrics(self) -> None:
        dataset_id = self.dataset.currentData()
        dataset = next((item for item in self.datasets if item["id"] == dataset_id), {})
        current_id = self.metric_picker.currentData() if hasattr(self, "metric_picker") else None
        self.metric_picker.clear()
        for metric in dataset.get("metrics", []):
            self.metric_picker.addItem(
                f"{metric['label']} ({metric.get('unit', '')})", metric["id"]
            )
        index = self.metric_picker.findData(current_id)
        if index >= 0:
            self.metric_picker.setCurrentIndex(index)

    def payload(self) -> dict[str, Any]:
        result = {
            "project_id": self.project.currentData(),
            "title": self.title.text().strip(),
            "research_question": self.question.toPlainText().strip(),
            "dataset_snapshot_id": self.dataset.currentData(),
            "primary_metric_id": self.metric_picker.currentData(),
        }
        if self.monitoring:
            result.update(start_week=self.start_week.value(), weeks=self.weeks.value())
        else:
            result.update(
                design=self.design.currentData(),
                population=self.population.text().strip(),
                estimand=self.estimand.text().strip(),
                intervention=self.intervention.text().strip(),
                hypotheses=[
                    line.strip()
                    for line in self.hypotheses.toPlainText().splitlines()
                    if line.strip()
                ],
            )
        if self.detail:
            result["base_version"] = self.detail["study"]["version"]
        return result

    def accept(self) -> None:
        if not self.title.text().strip() or not self.dataset.currentData() or not self.metric_picker.currentData():
            QMessageBox.warning(self, "Research object", "A title, admitted snapshot and registered metric are required.")
            return
        if not self.monitoring and not self.question.toPlainText().strip():
            QMessageBox.warning(self, "Research study", "A research question is required.")
            return
        super().accept()


class CohortDialog(QDialog):
    def __init__(
        self,
        cohort: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cohort = cohort
        self.setWindowTitle("Edit cohort" if cohort else "New cohort")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit((cohort or {}).get("name", "All eligible participants"))
        self.description = QLineEdit((cohort or {}).get("description", ""))
        self.include_ids = QPlainTextEdit(
            "\n".join((cohort or {}).get("include_subject_ids", []))
        )
        self.exclude_ids = QPlainTextEdit(
            "\n".join((cohort or {}).get("exclude_subject_ids", []))
        )
        self.rules = QPlainTextEdit(
            json.dumps((cohort or {}).get("rules", []), indent=2, ensure_ascii=False)
        )
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 1_000_000)
        self.minimum.setValue(int((cohort or {}).get("min_metric_observations", 1)))
        self.activity = QLineEdit((cohort or {}).get("activity", "") or "")
        form.addRow("Name", self.name)
        form.addRow("Description", self.description)
        form.addRow("Include subject IDs (blank = all)", self.include_ids)
        form.addRow("Exclude subject IDs", self.exclude_ids)
        form.addRow("Minimum valid observations", self.minimum)
        form.addRow("Activity filter (optional)", self.activity)
        form.addRow("Subject rules (JSON list)", self.rules)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def payload(self) -> dict[str, Any]:
        try:
            rules = json.loads(self.rules.toPlainText() or "[]")
        except json.JSONDecodeError as error:
            raise ValueError(f"Subject rules must be valid JSON: {error}") from error
        if not isinstance(rules, list):
            raise ValueError("Subject rules must be a JSON list")
        result = {
            "name": self.name.text().strip(),
            "description": self.description.text().strip(),
            "include_subject_ids": _parse_ids(self.include_ids.toPlainText()),
            "exclude_subject_ids": _parse_ids(self.exclude_ids.toPlainText()),
            "rules": rules,
            "min_metric_observations": self.minimum.value(),
            "activity": self.activity.text().strip() or None,
        }
        if self.cohort:
            result["base_version"] = self.cohort["version"]
        return result

    def accept(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Cohort", "A cohort name is required.")
            return
        try:
            self.payload()
        except ValueError as error:
            QMessageBox.warning(self, "Cohort rules", str(error))
            return
        super().accept()


class PlanDialog(QDialog):
    def __init__(
        self,
        methods: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
        cohorts: list[dict[str, Any]],
        plan: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Edit analysis plan" if plan else "New analysis plan")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit((plan or {}).get("name", ""))
        self.method = QComboBox()
        for method in methods:
            self.method.addItem(method["name"], method["id"])
        self.metric_picker = QComboBox()
        for metric in metrics:
            self.metric_picker.addItem(f"{metric['label']} ({metric.get('unit', '')})", metric["id"])
        for combo, key in ((self.method, "method_id"), (self.metric_picker, "outcome_metric_id")):
            index = combo.findData((plan or {}).get(key))
            if index >= 0:
                combo.setCurrentIndex(index)
        self.cohort = QComboBox()
        for cohort in cohorts:
            self.cohort.addItem(
                f"{cohort.get('name', cohort['id'])} · {cohort.get('status', 'DRAFT')} · v{cohort.get('version', 1)}",
                cohort["id"],
            )
        cohort_index = self.cohort.findData((plan or {}).get("cohort_id"))
        if cohort_index >= 0:
            self.cohort.setCurrentIndex(cohort_index)
        self.estimand = QLineEdit((plan or {}).get("primary_estimand", ""))
        self.parameters = QPlainTextEdit(
            json.dumps((plan or {}).get("parameters", {}), indent=2, ensure_ascii=False)
        )
        self.inclusion = QLineEdit((plan or {}).get("inclusion_criteria", ""))
        self.missing = QLineEdit((plan or {}).get("missing_data", ""))
        self.hypotheses = QPlainTextEdit(_lines((plan or {}).get("hypotheses", [])))
        self.covariates = QPlainTextEdit(_lines((plan or {}).get("covariates", [])))
        self.fixed_effects = QPlainTextEdit(_lines((plan or {}).get("fixed_effects", [])))
        self.random_effects = QPlainTextEdit(_lines((plan or {}).get("random_effects", [])))
        self.contrasts = QPlainTextEdit(_lines((plan or {}).get("contrasts", [])))
        self.exclusions = QPlainTextEdit(_lines((plan or {}).get("exclusion_criteria", [])))
        self.diagnostics = QPlainTextEdit(_lines((plan or {}).get("diagnostics", [])))
        self.planned_models = QPlainTextEdit(_lines((plan or {}).get("planned_models", [])))
        self.planned_reliability = QLineEdit((plan or {}).get("planned_reliability", ""))
        for editor in (
            self.hypotheses, self.covariates, self.fixed_effects, self.random_effects,
            self.contrasts, self.exclusions, self.diagnostics, self.planned_models,
        ):
            editor.setMaximumHeight(56)
        form.addRow("Name", self.name)
        form.addRow("Qualified method", self.method)
        form.addRow("Outcome metric", self.metric_picker)
        form.addRow("Resolved cohort", self.cohort)
        form.addRow("Primary estimand", self.estimand)
        form.addRow("Parameters (JSON object)", self.parameters)
        form.addRow("Inclusion criteria", self.inclusion)
        form.addRow("Missing data handling", self.missing)
        form.addRow("Hypotheses (one per line)", self.hypotheses)
        form.addRow("Covariates (one per line)", self.covariates)
        form.addRow("Fixed effects (one per line)", self.fixed_effects)
        form.addRow("Random effects (one per line)", self.random_effects)
        form.addRow("Planned contrasts (one per line)", self.contrasts)
        form.addRow("Exclusion criteria (one per line)", self.exclusions)
        form.addRow("Diagnostics (one per line)", self.diagnostics)
        form.addRow("Planned models (one per line)", self.planned_models)
        form.addRow("Planned reliability", self.planned_reliability)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def payload(self) -> dict[str, Any]:
        try:
            parameters = json.loads(self.parameters.toPlainText() or "{}")
        except json.JSONDecodeError as error:
            raise ValueError(f"Plan parameters must be valid JSON: {error}") from error
        if not isinstance(parameters, dict):
            raise ValueError("Plan parameters must be a JSON object")
        result = {
            "name": self.name.text().strip(),
            "method_id": self.method.currentData(),
            "outcome_metric_id": self.metric_picker.currentData(),
            "cohort_id": self.cohort.currentData(),
            "primary_estimand": self.estimand.text().strip(),
            "parameters": parameters,
            "inclusion_criteria": self.inclusion.text().strip(),
            "missing_data": self.missing.text().strip(),
            "hypotheses": _parse_ids(self.hypotheses.toPlainText()),
            "covariates": _parse_ids(self.covariates.toPlainText()),
            "fixed_effects": _parse_ids(self.fixed_effects.toPlainText()),
            "random_effects": _parse_ids(self.random_effects.toPlainText()),
            "contrasts": _parse_ids(self.contrasts.toPlainText()),
            "exclusion_criteria": _parse_ids(self.exclusions.toPlainText()),
            "diagnostics": _parse_ids(self.diagnostics.toPlainText()),
            "planned_models": _parse_ids(self.planned_models.toPlainText()),
            "planned_reliability": self.planned_reliability.text().strip(),
        }
        if self.plan:
            result["base_version"] = self.plan["version"]
        return result

    def accept(self) -> None:
        if not self.name.text().strip() or not self.method.currentData() or not self.metric_picker.currentData():
            QMessageBox.warning(self, "Analysis plan", "A name, registered method and outcome metric are required.")
            return
        try:
            self.payload()
        except ValueError as error:
            QMessageBox.warning(self, "Analysis plan", str(error))
            return
        super().accept()


class DatasetAdmissionDialog(QDialog):
    """Gather a source manifest, rights review, local file and QC metadata."""

    def __init__(
        self,
        service: DynamisAppService,
        run_task: Callable[[Callable[[], Any], Callable[[Any], None], str], None],
        on_admitted: Callable[[dict[str, Any]], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.run_task = run_task
        self.on_admitted = on_admitted
        self.source_id = f"SRC-LOCAL-{uuid.uuid4().hex[:8].upper()}"
        self.instrument_id = f"INST-LOCAL-{uuid.uuid4().hex[:8].upper()}"
        self.protocol_id = f"PROT-LOCAL-{uuid.uuid4().hex[:8].upper()}"
        self.source_artifact: dict[str, Any] | None = None
        self.quality: dict[str, Any] | None = None
        self.setWindowTitle("Admit local dataset")
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._source_page(), "Source rights")
        self.tabs.addTab(self._measurement_page(), "Measurement metadata")
        self.tabs.addTab(self._file_page(), "File and QC")
        layout.addWidget(self.tabs)
        footer = QHBoxLayout()
        self.review_button = QPushButton("Register source and run QC")
        self.review_button.clicked.connect(self._review)
        self.admit_button = QPushButton("Admit QC-passed snapshot")
        self.admit_button.setEnabled(False)
        self.admit_button.clicked.connect(self._admit)
        self.quarantine_button = QPushButton("Record rejected / quarantined result")
        self.quarantine_button.setEnabled(False)
        self.quarantine_button.clicked.connect(self._record_quarantine)
        cancel = QPushButton("Close")
        cancel.clicked.connect(self.reject)
        footer.addWidget(self.review_button)
        footer.addWidget(self.admit_button)
        footer.addWidget(self.quarantine_button)
        footer.addWidget(cancel)
        layout.addLayout(footer)
        self.summary = QTextBrowser()
        self.summary.setMinimumHeight(100)
        self.summary.setMaximumHeight(160)
        layout.addWidget(self.summary)

    def _source_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.source_name = QLineEdit()
        self.publisher = QLineEdit()
        self.dataset_identity = QLineEdit()
        self.source_version = QLineEdit("1")
        self.acquisition = QLineEdit("Local file")
        self.license = QLineEdit()
        self.permitted_uses = QLineEdit("research")
        self.restrictions = QPlainTextEdit()
        self.privacy = QComboBox()
        self.privacy.addItems(["DEIDENTIFIED", "PSEUDONYMOUS", "IDENTIFIABLE", "NOT_APPLICABLE", "TEST_FIXTURE"])
        self.retention = QLineEdit()
        self.rights_reviewed = QCheckBox(
            "I reviewed the publisher's licence/agreement, permitted uses and redistribution terms."
        )
        self.verifier = QLineEdit(getpass.getuser())
        form.addRow("Source ID", QLabel(self.source_id))
        form.addRow("Source name", self.source_name)
        form.addRow("Publisher", self.publisher)
        form.addRow("Dataset identity / DOI", self.dataset_identity)
        form.addRow("Version", self.source_version)
        form.addRow("Acquisition method", self.acquisition)
        form.addRow("Licence or agreement", self.license)
        form.addRow("Permitted uses (comma separated)", self.permitted_uses)
        form.addRow("Redistribution restrictions", self.restrictions)
        form.addRow("Privacy classification", self.privacy)
        form.addRow("Retention limitations", self.retention)
        form.addRow("Rights verified by", self.verifier)
        form.addRow(self.rights_reviewed)
        return page

    def _measurement_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.family = QComboBox()
        self.family.addItem("CMJ force-platform scalars", "CMJ_FORCE_PLATFORM")
        self.family.addItem("Sprint timing", "SPRINT_TIMING")
        self.manufacturer = QLineEdit()
        self.instrument_model = QLineEdit()
        self.serial = QLineEdit()
        self.calibration = QLineEdit("UNKNOWN")
        self.protocol_name = QLineEdit()
        self.protocol_version = QLineEdit("1.0")
        self.sampling = QSpinBox()
        self.sampling.setRange(1, 100000)
        self.sampling.setValue(1000)
        self.mass_unit = QLineEdit("kg")
        self.time_unit = QLineEdit("s")
        self.distance_unit = QLineEdit("m")
        self.coordinate_system = QLineEdit()
        form.addRow("Measurement family", self.family)
        form.addRow("Instrument ID", QLabel(self.instrument_id))
        form.addRow("Manufacturer", self.manufacturer)
        form.addRow("Model", self.instrument_model)
        form.addRow("Serial number", self.serial)
        form.addRow("Calibration status", self.calibration)
        form.addRow("Protocol ID", QLabel(self.protocol_id))
        form.addRow("Protocol name", self.protocol_name)
        form.addRow("Protocol version", self.protocol_version)
        form.addRow("Sampling rate (Hz)", self.sampling)
        form.addRow("Mass unit", self.mass_unit)
        form.addRow("Time unit", self.time_unit)
        form.addRow("Distance unit", self.distance_unit)
        form.addRow("Coordinate convention (sprint)", self.coordinate_system)
        return page

    def _file_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        self.file_path = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        controls.addWidget(self.file_path, 1)
        controls.addWidget(browse)
        layout.addLayout(controls)
        layout.addWidget(QLabel("QC reads local CSV or Parquet and records the source hash, units and exclusions."))
        return page

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose dataset artifact", "", "Data tables (*.csv *.parquet *.pq)"
        )
        if path:
            self.file_path.setText(path)

    def _payloads(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        file_path = Path(self.file_path.text().strip()).expanduser()
        if not file_path.is_file():
            raise ValueError("Choose an existing local CSV or Parquet file.")
        if file_path.suffix.lower() not in {".csv", ".parquet", ".pq"}:
            raise ValueError("Only CSV and Parquet dataset artifacts are supported by this admission dialog.")
        source = {
            "id": self.source_id,
            "name": self.source_name.text().strip(),
            "publisher": self.publisher.text().strip(),
            "dataset_identity": self.dataset_identity.text().strip(),
            "version": self.source_version.text().strip(),
            "acquisition_method": self.acquisition.text().strip(),
            "license_or_agreement": self.license.text().strip(),
            "permitted_uses": _parse_ids(self.permitted_uses.text()),
            "redistribution_restrictions": self.restrictions.toPlainText().strip(),
            "privacy_status": self.privacy.currentText(),
            "retention_limitations": self.retention.text().strip(),
            "derived_data_publishable": False,
            "rights_status": "FIXTURE_ONLY" if self.privacy.currentText() == "TEST_FIXTURE" else "UNVERIFIED",
        }
        instrument = {
            "id": self.instrument_id,
            "measurement_family": self.family.currentData(),
            "manufacturer": self.manufacturer.text().strip(),
            "model": self.instrument_model.text().strip(),
            "serial_number": self.serial.text().strip(),
            "calibration_status": self.calibration.text().strip() or "UNKNOWN",
        }
        protocol = {
            "id": self.protocol_id,
            "measurement_family": self.family.currentData(),
            "name": self.protocol_name.text().strip(),
            "version": self.protocol_version.text().strip(),
            "sampling_hz": self.sampling.value(),
            "units": {
                "body_mass": self.mass_unit.text().strip(),
                "time": self.time_unit.text().strip(),
                "distance": self.distance_unit.text().strip(),
            },
            "coordinate_convention": self.coordinate_system.text().strip() or "NOT_SPECIFIED",
        }
        metadata = {
            "units": protocol["units"],
            "instrument_default": self.instrument_id,
            "protocol_default": self.protocol_id,
        }
        if self.coordinate_system.text().strip():
            metadata["coordinate_system"] = self.coordinate_system.text().strip()
        return source, instrument, protocol, {"path": str(file_path.resolve()), "family": self.family.currentData(), "metadata": metadata}

    def _review(self) -> None:
        if not self.rights_reviewed.isChecked():
            QMessageBox.warning(self, "Source rights", "Review the source rights before registration and verification.")
            self.tabs.setCurrentIndex(0)
            return
        try:
            source, instrument, protocol, file = self._payloads()
        except ValueError as error:
            QMessageBox.warning(self, "Dataset admission", str(error))
            self.tabs.setCurrentIndex(2)
            return
        verifier = self.verifier.text().strip()
        if not verifier:
            QMessageBox.warning(self, "Source rights", "Record who verified the source rights.")
            self.tabs.setCurrentIndex(0)
            return

        def register_ingest_validate() -> dict[str, Any]:
            self.service.register_admission_source(source)
            rights = self.service.verify_source_rights(source["id"], verifier)
            if rights["rights_status"] not in {"VERIFIED", "FIXTURE_ONLY"}:
                raise ValueError(f"Source rights remain unverified: {rights['problems']}")
            self.service.register_admission_instrument(instrument)
            self.service.register_admission_protocol(protocol)
            artifact = self.service.ingest_local_source_file(source["id"], file["path"])
            quality = self.service.validate_source_artifact(artifact["id"], file["family"], file["metadata"])
            return {"source": source, "rights": rights, "instrument": instrument, "protocol": protocol, "artifact": artifact, "quality": quality, "family": file["family"], "metadata": file["metadata"]}

        self.review_button.setEnabled(False)
        self.run_task(register_ingest_validate, self._reviewed, "Registering source and running quality control")

    def _reviewed(self, result: dict[str, Any]) -> None:
        self.review_button.setEnabled(False)
        self.source_artifact = result["artifact"]
        self.quality = result["quality"]
        self.measurement_family = result["family"]
        self.measurement_metadata = result["metadata"]
        self.tabs.setEnabled(False)
        status = self.quality["status"]
        self.summary.setPlainText(self._quality_summary())
        eligible = status in {"ADMITTED", "ADMITTED_WITH_WARNINGS"}
        self.admit_button.setEnabled(eligible)
        self.quarantine_button.setEnabled(not eligible)

    def _admit(self) -> None:
        if not self.source_artifact or not self.quality:
            return
        family = self.measurement_family
        metadata = self.measurement_metadata
        artifact_id = self.source_artifact["id"]
        self.run_task(
            lambda: self.service.admit_source_artifact(artifact_id, family, metadata),
            self._admission_recorded,
            "Admitting validated dataset snapshot",
        )

    def _record_quarantine(self) -> None:
        if not self.source_artifact or not self.quality:
            return
        family = self.measurement_family
        metadata = self.measurement_metadata
        artifact_id = self.source_artifact["id"]
        self.run_task(
            lambda: self.service.admit_source_artifact(artifact_id, family, metadata),
            self._admission_recorded,
            "Recording rejected or quarantined quality result",
        )

    def _admission_recorded(self, record: dict[str, Any]) -> None:
        self.admit_button.setEnabled(False)
        self.quarantine_button.setEnabled(False)
        self.summary.setPlainText(self._quality_summary() + f"\n\nAdmission record: {record['id']}")
        self.on_admitted(record)
        if record.get("dataset_snapshot_id"):
            self.accept()

    def _quality_summary(self) -> str:
        quality = self.quality or {}
        lines = [f"QC decision: {quality.get('status', 'unknown')}"]
        counts = quality.get("counts", {})
        if counts:
            lines.append("  ·  ".join(f"{name}: {value}" for name, value in counts.items()))
        for key, label in (("errors", "Errors"), ("warnings", "Warnings"),
                           ("rejected_record_ids", "Rejected records"),
                           ("quarantined_record_ids", "Quarantined records")):
            values = quality.get(key, [])
            if values:
                lines.append(f"{label}: " + "; ".join(map(str, values)))
        if not quality.get("errors") and not quality.get("warnings"):
            lines.append("No QC errors or warnings.")
        return "\n".join(lines)


class AdmissionHistoryDialog(QDialog):
    def __init__(self, records: list[dict[str, Any]], quality: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Admission and quality history")
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        records_view = QTextBrowser()
        records_view.setPlainText(json.dumps(records, indent=2, ensure_ascii=False, default=str))
        quality_view = QTextBrowser()
        quality_view.setPlainText(json.dumps(quality, indent=2, ensure_ascii=False, default=str))
        tabs.addTab(records_view, "Admission records")
        tabs.addTab(quality_view, "QC and quarantine")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def _parse_ids(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


def _lines(values: Any) -> str:
    result = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            value = value.get("statement") or value.get("id") or ""
        if str(value).strip():
            result.append(str(value).strip())
    return "\n".join(result)
