"""Native research roster and version-bound descriptive experiment comparisons."""
from __future__ import annotations

import html
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QScrollArea, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from ..experiment_series import LIMIT, comparability
from .individual_research import _fill, _table, fit_dialog
from .plots import ScientificFigureWidget


def result_label(member):
    run = member['latest_result']
    if not run:
        return 'No saved result'
    result = run['result']
    inference = result.get('inference', {})
    summary = f"{run['id']} · {'current' if member['result_current'] else 'stale'} · {result.get('status', '')}"
    if inference.get('p_value') is not None:
        summary += f" · individual p={inference['p_value']:.4g} · observed difference {inference.get('descriptive_difference')} {result.get('unit', '')}"
    else:
        summary += f" · {result.get('n_observations', 0)} observations · descriptive only"
    return summary


class ExperimentSeriesPanel(QWidget):
    open_experiment = Signal(str)

    def __init__(self, service, run_task, parent=None):
        super().__init__(parent)
        self.service, self.run_task = service, run_task
        self.workspace_id = None
        self.generation = 0
        self.payload = {}
        self.rendered_checks = []
        layout = QVBoxLayout(self)
        note = QLabel(LIMIT + '\nSelect two or more athlete rows with Ctrl or Shift, then save a comparison to retain this revision.')
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        refresh = QPushButton('Refresh experiment roster')
        refresh.clicked.connect(self.reload)
        self.save = QPushButton('Save selected comparison')
        self.save.clicked.connect(self.capture)
        self.history = QComboBox()
        self.history.setAccessibleName('Frozen series comparison history')
        self.history.currentIndexChanged.connect(self.show_history)
        for widget in (refresh, self.save, self.history):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.roster = _table(['Athlete / experiment', 'Protocol / design', 'Outcome / unit',
                              'Visits\nobserved / planned', 'Eligibility', 'Latest result'], 'Experiment series roster')
        self.roster.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.roster.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.roster.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.roster.horizontalHeader().setMinimumSectionSize(60)
        self.roster.setWordWrap(True)
        self.roster.verticalHeader().setDefaultSectionSize(76)
        self.roster.setSortingEnabled(True)
        self.roster.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.roster.itemSelectionChanged.connect(self.preview)
        self.roster.setMaximumHeight(210)
        layout.addWidget(self.roster)
        inspect = QPushButton('&Inspect selected experiment details…')
        inspect.setToolTip('Full values, protocol, eligibility, result and captured provenance for each selected athlete')
        inspect.clicked.connect(self.inspect_selected)
        layout.addWidget(inspect)
        self.binding = QLabel()
        self.binding.setWordWrap(True)
        layout.addWidget(self.binding)
        self.checks = QTextBrowser()
        self.checks.setAccessibleName('Design comparability checks')
        self.checks.setOpenLinks(False)
        self.checks.anchorClicked.connect(self._check_details)
        self.checks.setMaximumHeight(170)
        layout.addWidget(self.checks)
        self.detail = QScrollArea()
        self.detail.setWidgetResizable(True)
        layout.addWidget(self.detail, 1)
        self.setEnabled(False)

    def set_workspace(self, workspace_id):
        self.workspace_id = workspace_id
        self.generation += 1
        self.payload = {}
        self.rendered_checks = []
        self.roster.setRowCount(0)
        self.history.clear()
        self.checks.clear()
        self.binding.clear()
        self._clear_detail()
        self.setEnabled(bool(workspace_id))
        if workspace_id:
            self.reload()

    def _clear_detail(self):
        previous = self.detail.takeWidget()
        if previous:
            previous.deleteLater()

    def reload(self):
        if not self.workspace_id:
            return
        self.generation += 1
        token, identity = self.generation, self.workspace_id
        self.run_task(lambda: self.service.experiment_series(identity),
                      lambda value: self._loaded(value) if (token, identity) == (self.generation, self.workspace_id) else None,
                      'Loading series of individual experiments')

    def _loaded(self, payload):
        self.payload = payload
        self.roster.blockSignals(True)
        self.roster.setSortingEnabled(False)
        _fill(self.roster, [[f"{m['subject_id']} · {m['title']}",
                            f"v{m['protocol']['version']} · {m['protocol']['design_label']}" if m['protocol'] else 'No experimental protocol',
                            f"{m['protocol']['outcome_label']} ({m['protocol']['unit']})" if m['protocol'] else '—',
                            f"{m['observed']} / {m['scheduled']}",
                            m['eligibility']['status'] + ': ' + '; '.join(m['eligibility']['issues']),
                            result_label(m)]
                           for m in payload['roster']['members']])
        for row, member in enumerate(payload['roster']['members']):
            self.roster.item(row, 0).setData(Qt.ItemDataRole.UserRole, member)
        self.roster.setSortingEnabled(True)
        self.roster.blockSignals(False)
        self.history.blockSignals(True)
        self.history.clear()
        self.history.addItem('Live selection · select rows to compare', None)
        for record in reversed(payload['history']):
            self.history.addItem(f"{record['comparison']['captured_at']} · {record['id']}", record)
        self.history.blockSignals(False)
        self.preview()

    def selected(self):
        return [self.roster.item(i.row(), 0).data(Qt.ItemDataRole.UserRole)
                for i in self.roster.selectionModel().selectedRows()] if self.payload else []

    def inspect_selected(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Selected experiment details / provenance')
        layout = QVBoxLayout(dialog)
        view = QTextBrowser()
        view.setPlainText(json.dumps(dict(data_revision_id=self.payload.get('roster', {}).get('data_revision_id'),
                                          members=self.selected()), indent=2))
        layout.addWidget(view)
        fit_dialog(dialog, 850, 650)
        dialog.exec()

    def preview(self):
        if self.history.currentData():
            self.history.setCurrentIndex(0)
        members = self.selected()
        self.save.setEnabled(len(members) >= 2 and len({m['subject_id'] for m in members}) == len(members))
        self.render(dict(members=members, checks=comparability(members) if members else [],
                         data_revision_id=self.payload.get('roster', {}).get('data_revision_id')), 'Live selection')

    def show_history(self):
        record = self.history.currentData()
        if record:
            self.save.setEnabled(False)
            self.render(record['comparison'], f"Frozen {record['id']} · SHA-256 {record['content_hash']}")
        elif self.payload:
            self.preview()

    def capture(self):
        members = self.selected()
        bindings = {m['investigation_id']:m['investigation_version'] for m in members}
        identity, revision = self.workspace_id, self.payload['roster']['data_revision_id']
        token = self.generation
        def saved(record):
            if (token, identity) != (self.generation, self.workspace_id):
                return
            self.payload['history'].append(record)
            self.history.addItem(f"{record['comparison']['captured_at']} · {record['id']}", record)
            self.history.setCurrentIndex(self.history.count()-1)
        self.run_task(lambda: self.service.capture_experiment_series(identity, bindings, revision), saved,
                      'Freezing descriptive comparison')

    def render(self, content, label):
        self._clear_detail()
        self.binding.setText(f"{label} · data revision {content.get('data_revision_id')} · Each plot has independent axes.")
        esc = lambda value: html.escape(str(value))
        self.rendered_checks = content['checks']
        self.checks.setHtml('<br>'.join(f"<b>{esc(c['check'])}: {esc(c['status'])}</b>" for c in content['checks'])
                            + ('<br><a href="details">Inspect definitions, bindings and sufficiency reasons</a>' if content['checks'] else ''))
        holder = QWidget()
        layout = QVBoxLayout(holder)
        columns = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(columns)
        for member in content['members']:
            page = QWidget()
            column = QVBoxLayout(page)
            p = member['protocol']
            label_widget = QLabel(f"{member['subject_id']} · {member['title']} · investigation v{member['investigation_version']}")
            label_widget.setWordWrap(True)
            column.addWidget(label_widget)
            open_button = QPushButton('Open complete participant experiment')
            open_button.setProperty('investigation_id', member['investigation_id'])
            open_button.clicked.connect(lambda _=False, identity=member['investigation_id']: self.open_experiment.emit(identity))
            column.addWidget(open_button)
            details = QTextBrowser()
            details.setAccessibleName(f"{member['subject_id']} captured protocol and result")
            details.setMinimumHeight(180)
            if p:
                allocation = p.get('allocation', {})
                config = allocation.get('configuration', {})
                phases = '<br>'.join(f"{esc(v['kind'])}: {esc(v['label'])} · {v['start']}–{v['end']}" for v in p['periods'])
                details.setHtml(f"<b>{esc(p['question'])}</b><p>Protocol v{p['version']} · {esc(p['design_label'])}<br>"
                    f"{esc(p['outcome_label'])} ({esc(p['unit'])}) · axis {esc(p['axis'])}</p>"
                    f"<p>{phases}</p><p>Assignment: {esc(p['assignment'])}<br>"
                    f"Planned onset: {esc(allocation.get('assigned_start', 'Not applicable'))}<br>"
                    f"Conditions: {esc(config.get('baseline_condition', 'See planned periods'))} → "
                    f"{esc(config.get('intervention_condition', 'See planned periods'))}</p>"
                    f"<p>Eligibility: {esc(member['eligibility']['status'])} · {esc('; '.join(member['eligibility']['issues']))}<br>"
                    f"{esc(result_label(member))}</p>")
            else:
                details.setPlainText('No saved experimental protocol. Open the participant investigation to define one.')
            column.addWidget(details)
            if member['latest_result']:
                diagnostics = QPushButton('Inspect captured result and diagnostics')
                diagnostics.clicked.connect(lambda _=False, m=member: self._diagnostics(m))
                column.addWidget(diagnostics)
            for report in member['reports']:
                button = QPushButton(f"Open historical report v{report['version']}")
                button.clicked.connect(lambda _=False, version=report['version']: self._report(version))
                column.addWidget(button)
            if p:
                figure = ScientificFigureWidget()
                figure.show_figure(series_figure(member))
                figure.setMinimumSize(330, 250)
                column.addWidget(figure)
                table = _table(['Scheduled', 'Actual / date', 'Planned phase', 'Actual condition / exposure',
                                f"Mean ({p['unit']})", 'Status / missing reason'], f"{member['subject_id']} experiment timeline")
                _fill(table, [[r['scheduled_occasion'],
                    f"{r['visit']['occasion']} / {r['visit']['occurred_at']}" if r['visit'] else '—', r['period']['label'],
                    f"{r['visit'].get('actual_condition')} / {r['visit']['exposure']}" if r['visit'] else '—',
                    r['mean'], f"{r['status']} / {r['visit'].get('missing_reason', '') if r['visit'] else ''}"] for r in member['timeline']['rows']])
                table.setMinimumSize(330, 240)
                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                table.verticalHeader().setDefaultSectionSize(58)
                column.addWidget(table)
            columns.addWidget(page)
        self.detail.setWidget(holder)

    def _check_details(self, _url):
        dialog = QDialog(self)
        dialog.setWindowTitle('Captured design comparability definitions')
        layout = QVBoxLayout(dialog)
        view = QTextBrowser()
        view.setPlainText(json.dumps(self.rendered_checks, indent=2))
        layout.addWidget(view)
        fit_dialog(dialog, 900, 700)
        dialog.exec()

    def _diagnostics(self, member):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{member['subject_id']} captured result and diagnostics")
        layout = QVBoxLayout(dialog)
        view = QTextBrowser()
        view.setPlainText(json.dumps(member['latest_result'], indent=2))
        layout.addWidget(view)
        fit_dialog(dialog, 900, 700)
        dialog.exec()

    def _report(self, version):
        identity, token = self.workspace_id, self.generation
        def loaded(markup):
            if (identity, token) != (self.workspace_id, self.generation):
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(f'Frozen report v{version}')
            layout = QVBoxLayout(dialog)
            view = QTextBrowser()
            view.setHtml(markup)
            layout.addWidget(view)
            fit_dialog(dialog, 1000, 750)
            dialog.exec()
        self.run_task(lambda: self.service.render_report_html(identity, version), loaded, 'Opening frozen participant report')


def series_figure(member):
    from matplotlib.figure import Figure

    p = member['protocol']
    figure = Figure(figsize=(5, 3), layout='constrained')
    ax = figure.subplots()
    rows = member['timeline']['rows']
    # Missing observations break the line; actual occasion is never replaced by planned time.
    ax.plot([r['visit']['occasion'] if r['visit'] else r['scheduled_occasion'] for r in rows],
            [r['mean'] if r['mean'] is not None else float('nan') for r in rows], color='#536779')
    for kind, marker in [('BASELINE', 'o'), ('INTERVENTION', '^'), ('COMPARISON', 's'), ('WASHOUT', 'x'), ('FOLLOW_UP', 'D')]:
        observed = [r for r in rows if r['mean'] is not None and r['observed_period'] and r['observed_period']['kind'] == kind]
        if observed:
            ax.scatter([r['visit']['occasion'] for r in observed], [r['mean'] for r in observed], marker=marker, label=kind)
    if p.get('allocation'):
        ax.axvline(p['allocation']['assigned_start'], linestyle='--', color='gray', label='Planned onset')
    ax.set(xlabel=f"Actual {p['axis']} / scheduled if missing", ylabel=f"{p['outcome_label']} ({p['unit']})",
           title=f"{member['subject_id']} · descriptive observations")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7)
    return figure
