"""Read-only research history inside the native workbench; never selects a revision."""
from __future__ import annotations

import html
import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import context_timeline, researchstore as store
from .plots import ScientificFigureWidget, run_figure


class ResearchHistoryPanel(QWidget):
    context_requested = Signal(str)
    compose_requested = Signal()

    def __init__(self, service, run_task, parent=None):
        super().__init__(parent)
        self.service, self.run_task = service, run_task
        self.identity = self.subject = None
        self.generation = 0
        layout = QVBoxLayout(self)
        title = QLabel("Research archive")
        title.setObjectName("StudyHeading")
        layout.addWidget(title)
        self.binding = QLabel('Open a workspace to inspect frozen history.')
        self.binding.setWordWrap(True)
        self.binding.setAccessibleName('Frozen history context')
        layout.addWidget(self.binding)
        controls = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItems(['Frozen reports', 'Saved analyses', 'Data revisions', 'Contextual views'])
        self.kind.currentIndexChanged.connect(self.populate)
        self.all_scopes = QCheckBox('Include all athletes and cohort')
        self.all_scopes.toggled.connect(self.populate)
        controls.addWidget(self.kind)
        controls.addWidget(self.all_scopes)
        refresh = QPushButton('Refresh history')
        refresh.clicked.connect(self.reload)
        controls.addWidget(refresh)
        self.export = QPushButton('Export selected frozen report…')
        self.export.clicked.connect(self.export_report)
        controls.addWidget(self.export)
        compose = QPushButton("Write report…")
        compose.setProperty("primary", True)
        compose.clicked.connect(self.compose_requested)
        controls.addWidget(compose)
        self.open_context = QPushButton('Open selected contextual view…')
        self.open_context.clicked.connect(self._open_context)
        self.open_context.hide()
        controls.addWidget(self.open_context)
        layout.addLayout(controls)
        self.picker = QComboBox()
        self.picker.setAccessibleName('Frozen research record')
        self.picker.currentIndexChanged.connect(self.show_record)
        layout.addWidget(self.picker)
        self.tabs = QTabWidget()
        self.preview = QTextBrowser()
        self.preview.setAccessibleName('Frozen research content')
        self.tabs.addTab(self.preview, 'Summary / report')
        self.figure = ScientificFigureWidget()
        self.tabs.addTab(self.figure, 'Figure')
        self.provenance = QTextBrowser()
        self.tabs.addTab(self.provenance, 'Diagnostics and provenance')
        layout.addWidget(self.tabs, 1)
        self.records = {}

    def set_context(self, identity, subject=None):
        if identity and (identity, subject) == (self.identity, self.subject):
            self.reload()
            return
        self.identity, self.subject = identity, subject
        self.generation += 1
        self.records = {}
        self.picker.clear()
        self.preview.clear()
        self.provenance.clear()
        self.export.setEnabled(False)
        self.all_scopes.setVisible(bool(subject))
        if identity:
            self.reload()

    def reload(self):
        if not self.identity:
            return
        self.generation += 1
        token, identity = self.generation, self.identity
        def read():
            return dict(reports=[store.get_report_version(identity, r['version']) for r in store.report_versions(identity)],
                        runs=store.list_runs(identity), revisions=store.data_revisions(identity),
                        context=context_timeline.history(identity))
        def loaded(value):
            if (token, identity) != (self.generation, self.identity):
                return
            self.records = value
            self.populate()
        self.run_task(read, loaded, 'Reading frozen research history')

    def populate(self):
        previous = self.picker.currentData() if hasattr(self, 'picker') else None
        if not hasattr(self, 'picker'):
            return
        self.picker.blockSignals(True)
        self.picker.clear()
        kind = self.kind.currentText()
        subject = self.subject if not self.all_scopes.isChecked() else None
        if kind == 'Frozen reports':
            for record in self.records.get('reports', []):
                sections = record['frozen_content'].get('research_sections', [])
                if subject and not any(s.get('scope', {}).get('subject_id') == subject for s in sections):
                    continue
                scopes = ', '.join(s.get('scope', {}).get('subject_id') or 'cohort' for s in sections)
                self.picker.addItem(f"Report v{record['version']} · {scopes} · frozen", ('report', record))
        elif kind == 'Saved analyses':
            for record in reversed(self.records.get('runs', [])):
                scope = record.get('scope') or {}
                if subject and scope.get('subject_id') != subject:
                    continue
                name = record.get('result', {}).get('method') or record['method_id']
                self.picker.addItem(f"{scope.get('subject_id') or 'Cohort'} · {name} · {record['created_at']}", ('run', record))
        elif kind == 'Contextual views':
            for record in self.records.get('context', []):
                if not subject or subject in json.loads(record['participants']):
                    self.picker.addItem(f"{record['title']} · {record['created_at'][:16]}", ('context', record))
        else:
            for record in reversed(self.records.get('revisions', [])):
                self.picker.addItem(f"Data revision {record['number']} · {record['mode'].lower()}", ('data', record))
        if previous:
            self.picker.setCurrentIndex(max(0, self.picker.findData(previous)))
        self.picker.blockSignals(False)
        self.show_record()

    def show_record(self):
        self.preview.clear()
        self.provenance.clear()
        self.binding.setToolTip("")
        value = self.picker.currentData()
        self.export.setEnabled(bool(value and value[0] == 'report'))
        self.open_context.setVisible(self.kind.currentText() == 'Contextual views')
        self.open_context.setEnabled(bool(value and value[0] == 'context'))
        self.tabs.setTabEnabled(1, bool(value and value[0] == 'run'))
        self.tabs.setCurrentIndex(0)
        self.binding.setText(f"{self.subject or 'Workspace'} · Frozen history · current research context is preserved")
        if not value:
            extra = " Include all athletes and cohort to broaden history." if self.subject and not self.all_scopes.isChecked() else ""
            self.preview.setPlainText(f"No saved records for this selection.{extra}")
            return
        kind, record = value
        self.provenance.setPlainText(json.dumps(record, indent=2, default=str))
        if kind == 'report':
            identity, version, token = self.identity, record['version'], self.generation
            self.binding.setText(f"Frozen report v{version} · read-only")
            self.binding.setToolTip(f"SHA-256 {record['content_hash']}")
            self.run_task(lambda: self.service.render_report_html(identity, version),
                lambda rendered: self.preview.setHtml(rendered) if
                    (token, identity, value) == (self.generation, self.identity, self.picker.currentData()) else None,
                'Opening frozen report')
        elif kind == 'run':
            result = record['result']
            binding = f"{record['id']} · data revision {record.get('data_revision_id')} · frozen result"
            self.binding.setText(binding)
            if record['method_id'] in {'METH-EXPERIMENT-DESC', 'METH-ONSET-EXACT'}:
                from ..experiments import result_html
                if record['method_id'] == 'METH-ONSET-EXACT':
                    from ..randomized_onset import result_html
                self.preview.setHtml(result_html(result))
            else:
                from .method_selector import run_html
                self.preview.setHtml(run_html(record, include_details=False))
            self.figure.show_figure(run_figure(record))
        elif kind == 'context':
            self.binding.setText(f"{record['id']} · {record['revision_id']} · Frozen contextual view")
            self.preview.setPlainText(f"{record['title']}\n\nSaved {record['created_at']}\n"
                                      f"SHA-256 {record['content_hash']}")
        else:
            self.preview.setPlainText(f"Data revision {record['number']} · {record['mode']}\n"
                f"Created {record['created_at']}\nImmutable measurements; inspecting this record does not activate it.\n"
                'Use the workspace History action to explicitly change the active data revision.')

    def _open_context(self):
        selected = self.picker.currentData()
        if selected and selected[0] == 'context':
            self.context_requested.emit(selected[1]['id'])

    def export_report(self):
        value = self.picker.currentData()
        if not value or value[0] != 'report':
            return
        identity, version = self.identity, value[1]['version']
        path, _ = QFileDialog.getSaveFileName(self, 'Export frozen report', f'{identity}-report-v{version}.html', 'HTML report (*.html)')
        if path:
            self.run_task(lambda: self.service.export_report_html(identity, path, version),
                          lambda _: None, 'Exporting frozen report')
