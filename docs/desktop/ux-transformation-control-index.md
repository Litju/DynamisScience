# Baseline native control and entry index

Static source inventory of 1056 Qt control, chart, dialog, menu, tab, shortcut and accessible-name entries across 27 desktop modules at `2c911f514350e656b064f2efec9951ea65c84075`. The line numbers refer to that source.

Repeated controls built by loops appear once at their construction site. Text filled at runtime is represented by its widget binding when available. This source index complements the observed Windows walkthrough and screen-by-screen UX requirements in [the baseline audit](ux-transformation-inventory.md).

## `__main__.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 113 | `main` | `getExistingDirectory` | root | Choose the private DynamisScience data root |

## `context_source_dialog.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 25 | `SourceRegistration.__init__` | `setWindowTitle` | — | Register a context source |
| 33 | `SourceRegistration.__init__` | `QLineEdit` | — | — |
| 36 | `SourceRegistration.__init__` | `QComboBox` | self.privacy | — |
| 39 | `SourceRegistration.__init__` | `QLineEdit` | self.reviewer | — |
| 43 | `SourceRegistration.__init__` | `QDialogButtonBox` | buttons | — |
| 78 | `ContextSourceDialog.__init__` | `setWindowTitle` | — | Import training and wellness context |
| 81 | `ContextSourceDialog.__init__` | `QLabel` | self.title | Preview suggested mapping |
| 88 | `ContextSourceDialog.__init__` | `QComboBox` | self.sources | — |
| 89 | `ContextSourceDialog.__init__` | `setAccessibleName` | — | Authorized source |
| 91 | `ContextSourceDialog.__init__` | `QPushButton` | register | Register source… |
| 95 | `ContextSourceDialog.__init__` | `QLineEdit` | self.reviewer | — |
| 96 | `ContextSourceDialog.__init__` | `setAccessibleName` | — | Reviewed by |
| 103 | `ContextSourceDialog.__init__` | `QPushButton` | self.column_button | Review column mapping… |
| 107 | `ContextSourceDialog.__init__` | `QScrollArea` | self.identity_scroll | — |
| 111 | `ContextSourceDialog.__init__` | `QTextBrowser` | self.details | — |
| 112 | `ContextSourceDialog.__init__` | `setAccessibleName` | — | Import conflicts, quality and proposed changes |
| 117 | `ContextSourceDialog.__init__` | `QDialogButtonBox` | buttons | — |
| 152 | `ContextSourceDialog.choose_file` | `getOpenFileName` | (filename, _) | Choose training or wellness export |
| 213 | `ContextSourceDialog._identity_fields` | `QComboBox` | picker | — |
| 259 | `ContextSourceDialog._edit_columns` | `QDialog` | dialog | — |
| 260 | `ContextSourceDialog._edit_columns` | `setWindowTitle` | — | Map source columns |
| 263 | `ContextSourceDialog._edit_columns` | `QScrollArea` | scroll | — |
| 269 | `ContextSourceDialog._edit_columns` | `QComboBox` | box | — |
| 283 | `ContextSourceDialog._edit_columns` | `QDialogButtonBox` | buttons | — |
| 373 | `ContextSourceDialog._quarantine` | `getText` | (reason, confirmed) | Quarantine context file |

## `data_workspace.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 61 | `_view` | `QTableView` | view | — |
| 77 | `DataWorkspaceDialog.__init__` | `setWindowTitle` | — | Data workspace |
| 93 | `DataWorkspaceDialog.__init__` | `QSplitter` | split | — |
| 97 | `DataWorkspaceDialog.__init__` | `QLineEdit` | self.search | — |
| 99 | `DataWorkspaceDialog.__init__` | `setAccessibleName` | — | Search datasets |
| 101 | `DataWorkspaceDialog.__init__` | `QListWidget` | self.catalogue | — |
| 102 | `DataWorkspaceDialog.__init__` | `setAccessibleName` | — | Dataset catalogue |
| 108 | `DataWorkspaceDialog.__init__` | `QTabWidget` | self.tabs | — |
| 109 | `DataWorkspaceDialog.__init__` | `addTab` | — | &Data |
| 110 | `DataWorkspaceDialog.__init__` | `addTab` | — | &Columns |
| 111 | `DataWorkspaceDialog.__init__` | `addTab` | — | T&races |
| 112 | `DataWorkspaceDialog.__init__` | `addTab` | — | Co&mpare |
| 113 | `DataWorkspaceDialog.__init__` | `addTab` | — | &Query |
| 114 | `DataWorkspaceDialog.__init__` | `addTab` | — | &Provenance |
| 121 | `DataWorkspaceDialog.__init__` | `addTab` | — | Reconcile follow-up |
| 127 | `DataWorkspaceDialog.__init__` | `QLabel` | self.status | Choose a dataset. |
| 130 | `DataWorkspaceDialog.__init__` | `QPushButton` | self.analyze_button | &Analyze this dataset |
| 134 | `DataWorkspaceDialog.__init__` | `QPushButton` | close | Close |
| 138 | `DataWorkspaceDialog.__init__` | `QPushButton` | other | Open standard importer… |
| 153 | `DataWorkspaceDialog._table_tab` | `QComboBox` | self.table_picker | — |
| 154 | `DataWorkspaceDialog._table_tab` | `setAccessibleName` | — | Table |
| 156 | `DataWorkspaceDialog._table_tab` | `QToolButton` | self.columns_button | — |
| 158 | `DataWorkspaceDialog._table_tab` | `setAccessibleName` | — | Choose visible columns |
| 160 | `DataWorkspaceDialog._table_tab` | `QMenu` | self.columns_menu | — |
| 162 | `DataWorkspaceDialog._table_tab` | `QLabel` | — | Table |
| 167 | `DataWorkspaceDialog._table_tab` | `QComboBox` | — | — |
| 167 | `DataWorkspaceDialog._table_tab` | `QComboBox` | — | — |
| 167 | `DataWorkspaceDialog._table_tab` | `QLineEdit` | — | — |
| 168 | `DataWorkspaceDialog._table_tab` | `setAccessibleName` | — | Filter column |
| 169 | `DataWorkspaceDialog._table_tab` | `setAccessibleName` | — | Filter operator |
| 172 | `DataWorkspaceDialog._table_tab` | `setAccessibleName` | — | Filter value |
| 174 | `DataWorkspaceDialog._table_tab` | `QPushButton` | — | Add &filter |
| 174 | `DataWorkspaceDialog._table_tab` | `QPushButton` | — | Clear filters |
| 183 | `DataWorkspaceDialog._table_tab` | `QLabel` | self.filter_list | — |
| 185 | `DataWorkspaceDialog._table_tab` | `setAccessibleName` | — | Active filters |
| 194 | `DataWorkspaceDialog._table_tab` | `QPushButton` | — | Next ▶ |
| 194 | `DataWorkspaceDialog._table_tab` | `QPushButton` | — | ◀ Previous |
| 195 | `DataWorkspaceDialog._table_tab` | `QLabel` | self.page_label | — |
| 207 | `DataWorkspaceDialog._columns_tab` | `QLabel` | — | Types, units (from the canonical column name), missingness and range. |
| 217 | `DataWorkspaceDialog._signals_tab` | `QLabel` | self.signals_note | This dataset has no sample-level recordings. |
| 224 | `DataWorkspaceDialog._query_tab` | `QLabel` | self.query_hint | Read-only SELECT over this dataset's tables (Polars SQL). No writes, files or scripts. |
| 226 | `DataWorkspaceDialog._query_tab` | `QPlainTextEdit` | self.query_text | — |
| 227 | `DataWorkspaceDialog._query_tab` | `setAccessibleName` | — | SQL query |
| 229 | `DataWorkspaceDialog._query_tab` | `QPushButton` | run | Run &SQL |
| 232 | `DataWorkspaceDialog._query_tab` | `QComboBox` | self.saved_picker | — |
| 233 | `DataWorkspaceDialog._query_tab` | `setAccessibleName` | — | Saved queries |
| 236 | `DataWorkspaceDialog._query_tab` | `QPushButton` | — | Delete |
| 236 | `DataWorkspaceDialog._query_tab` | `QPushButton` | — | Sa&ve query… |
| 239 | `DataWorkspaceDialog._query_tab` | `QLabel` | — | Saved |
| 245 | `DataWorkspaceDialog._query_tab` | `QLabel` | self.query_status | — |
| 261 | `DataWorkspaceDialog._compare_tab` | `QLabel` | self.compare_note | Pick a raw force-time recording to compare derived values with recorded ones. |
| 264 | `DataWorkspaceDialog._compare_tab` | `QComboBox` | self.compare_trial | — |
| 265 | `DataWorkspaceDialog._compare_tab` | `setAccessibleName` | — | Recording to compare |
| 267 | `DataWorkspaceDialog._compare_tab` | `QLabel` | — | Recording |
| 332 | `DataWorkspaceDialog._save_query` | `getText` | (name, ok) | Save query |
| 351 | `DataWorkspaceDialog._inspector_tab` | `QTextBrowser` | self.inspector | — |
| 352 | `DataWorkspaceDialog._inspector_tab` | `setAccessibleName` | — | Rights, QC, exclusions, instruments and lineage |

## `dialogs.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 47 | `ProjectDialog.__init__` | `QLineEdit` | self.title | — |
| 48 | `ProjectDialog.__init__` | `QPlainTextEdit` | self.description | — |
| 49 | `ProjectDialog.__init__` | `QPlainTextEdit` | self.objectives | — |
| 56 | `ProjectDialog.__init__` | `QLabel` | — | Datasets available to this project |
| 66 | `ProjectDialog.__init__` | `QCheckBox` | checkbox | — |
| 70 | `ProjectDialog.__init__` | `QDialogButtonBox` | self.buttons | — |
| 130 | `StudyDialog.__init__` | `QComboBox` | self.project | — |
| 138 | `StudyDialog.__init__` | `QLineEdit` | self.title | — |
| 139 | `StudyDialog.__init__` | `QPlainTextEdit` | self.question | — |
| 143 | `StudyDialog.__init__` | `QLineEdit` | self.population | — |
| 144 | `StudyDialog.__init__` | `QLineEdit` | self.estimand | — |
| 147 | `StudyDialog.__init__` | `QLineEdit` | self.intervention | — |
| 148 | `StudyDialog.__init__` | `QComboBox` | self.dataset | — |
| 160 | `StudyDialog.__init__` | `QComboBox` | self.metric_picker | — |
| 172 | `StudyDialog.__init__` | `QComboBox` | self.design | — |
| 190 | `StudyDialog.__init__` | `QSpinBox` | self.start_week | — |
| 193 | `StudyDialog.__init__` | `QSpinBox` | self.weeks | — |
| 202 | `StudyDialog.__init__` | `QPlainTextEdit` | self.hypotheses | — |
| 208 | `StudyDialog.__init__` | `QDialogButtonBox` | self.buttons | — |
| 275 | `CohortDialog.__init__` | `QLineEdit` | self.name | — |
| 276 | `CohortDialog.__init__` | `QLineEdit` | self.description | — |
| 277 | `CohortDialog.__init__` | `QPlainTextEdit` | self.include_ids | — |
| 280 | `CohortDialog.__init__` | `QPlainTextEdit` | self.exclude_ids | — |
| 283 | `CohortDialog.__init__` | `QPlainTextEdit` | self.rules | — |
| 286 | `CohortDialog.__init__` | `QSpinBox` | self.minimum | — |
| 289 | `CohortDialog.__init__` | `QLineEdit` | self.activity | — |
| 298 | `CohortDialog.__init__` | `QDialogButtonBox` | self.buttons | — |
| 351 | `PlanDialog.__init__` | `QLineEdit` | self.name | — |
| 352 | `PlanDialog.__init__` | `QComboBox` | self.method | — |
| 355 | `PlanDialog.__init__` | `QComboBox` | self.metric_picker | — |
| 362 | `PlanDialog.__init__` | `QComboBox` | self.cohort | — |
| 371 | `PlanDialog.__init__` | `QLineEdit` | self.estimand | — |
| 372 | `PlanDialog.__init__` | `QPlainTextEdit` | self.parameters | — |
| 375 | `PlanDialog.__init__` | `QLineEdit` | self.inclusion | — |
| 376 | `PlanDialog.__init__` | `QLineEdit` | self.missing | — |
| 377 | `PlanDialog.__init__` | `QPlainTextEdit` | self.hypotheses | — |
| 378 | `PlanDialog.__init__` | `QPlainTextEdit` | self.covariates | — |
| 379 | `PlanDialog.__init__` | `QPlainTextEdit` | self.fixed_effects | — |
| 380 | `PlanDialog.__init__` | `QPlainTextEdit` | self.random_effects | — |
| 381 | `PlanDialog.__init__` | `QPlainTextEdit` | self.contrasts | — |
| 382 | `PlanDialog.__init__` | `QPlainTextEdit` | self.exclusions | — |
| 383 | `PlanDialog.__init__` | `QPlainTextEdit` | self.diagnostics | — |
| 384 | `PlanDialog.__init__` | `QPlainTextEdit` | self.planned_models | — |
| 385 | `PlanDialog.__init__` | `QLineEdit` | self.planned_reliability | — |
| 409 | `PlanDialog.__init__` | `QDialogButtonBox` | self.buttons | — |
| 477 | `DatasetAdmissionDialog.__init__` | `setWindowTitle` | — | Admit local dataset |
| 479 | `DatasetAdmissionDialog.__init__` | `QTabWidget` | self.tabs | — |
| 480 | `DatasetAdmissionDialog.__init__` | `addTab` | — | Source rights |
| 481 | `DatasetAdmissionDialog.__init__` | `addTab` | — | Measurement metadata |
| 482 | `DatasetAdmissionDialog.__init__` | `addTab` | — | File and QC |
| 485 | `DatasetAdmissionDialog.__init__` | `QPushButton` | self.review_button | Register source and run QC |
| 487 | `DatasetAdmissionDialog.__init__` | `QPushButton` | self.admit_button | Admit QC-passed snapshot |
| 490 | `DatasetAdmissionDialog.__init__` | `QPushButton` | self.quarantine_button | Record rejected / quarantined result |
| 493 | `DatasetAdmissionDialog.__init__` | `QPushButton` | cancel | Close |
| 500 | `DatasetAdmissionDialog.__init__` | `QTextBrowser` | self.summary | — |
| 508 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.source_name | — |
| 509 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.publisher | — |
| 510 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.dataset_identity | — |
| 511 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.source_version | 1 |
| 512 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.acquisition | Local file |
| 513 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.license | — |
| 514 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.permitted_uses | research |
| 515 | `DatasetAdmissionDialog._source_page` | `QPlainTextEdit` | self.restrictions | — |
| 516 | `DatasetAdmissionDialog._source_page` | `QComboBox` | self.privacy | — |
| 518 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.retention | — |
| 519 | `DatasetAdmissionDialog._source_page` | `QCheckBox` | self.rights_reviewed | I reviewed the publisher's licence/agreement, permitted uses and redistribution terms. |
| 522 | `DatasetAdmissionDialog._source_page` | `QLineEdit` | self.verifier | — |
| 523 | `DatasetAdmissionDialog._source_page` | `QLabel` | — | — |
| 541 | `DatasetAdmissionDialog._measurement_page` | `QComboBox` | self.family | — |
| 544 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.manufacturer | — |
| 545 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.instrument_model | — |
| 546 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.serial | — |
| 547 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.instrument_id_input | — |
| 548 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.protocol_id_input | — |
| 549 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.calibration | UNKNOWN |
| 550 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.protocol_name | — |
| 551 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.protocol_version | 1.0 |
| 552 | `DatasetAdmissionDialog._measurement_page` | `QSpinBox` | self.sampling | — |
| 555 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.mass_unit | kg |
| 556 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.time_unit | s |
| 557 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.distance_unit | cm |
| 564 | `DatasetAdmissionDialog._measurement_page` | `QLineEdit` | self.coordinate_system | — |
| 585 | `DatasetAdmissionDialog._file_page` | `QLineEdit` | self.file_path | — |
| 586 | `DatasetAdmissionDialog._file_page` | `QPushButton` | browse | Browse… |
| 591 | `DatasetAdmissionDialog._file_page` | `QLabel` | — | QC reads local CSV or Parquet and records the source hash, units and exclusions. |
| 595 | `DatasetAdmissionDialog._browse` | `getOpenFileName` | (path, _) | Choose dataset artifact |
| 750 | `AdmissionHistoryDialog.__init__` | `setWindowTitle` | — | Admission and quality history |
| 752 | `AdmissionHistoryDialog.__init__` | `QTabWidget` | tabs | — |
| 753 | `AdmissionHistoryDialog.__init__` | `QTextBrowser` | records_view | — |
| 755 | `AdmissionHistoryDialog.__init__` | `QTextBrowser` | quality_view | — |
| 757 | `AdmissionHistoryDialog.__init__` | `addTab` | — | Admission records |
| 758 | `AdmissionHistoryDialog.__init__` | `addTab` | — | QC and quarantine |
| 760 | `AdmissionHistoryDialog.__init__` | `QDialogButtonBox` | buttons | — |

## `experiment_series.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 55 | `ExperimentSeriesPanel.__init__` | `QLabel` | note | — |
| 59 | `ExperimentSeriesPanel.__init__` | `QPushButton` | refresh | Refresh experiment roster |
| 61 | `ExperimentSeriesPanel.__init__` | `QPushButton` | self.save | Save selected comparison |
| 63 | `ExperimentSeriesPanel.__init__` | `QComboBox` | self.history | — |
| 64 | `ExperimentSeriesPanel.__init__` | `setAccessibleName` | — | Frozen series comparison history |
| 82 | `ExperimentSeriesPanel.__init__` | `QPushButton` | inspect | &Inspect selected experiment details… |
| 86 | `ExperimentSeriesPanel.__init__` | `QLabel` | self.binding | — |
| 89 | `ExperimentSeriesPanel.__init__` | `QTextBrowser` | self.checks | — |
| 90 | `ExperimentSeriesPanel.__init__` | `setAccessibleName` | — | Design comparability checks |
| 95 | `ExperimentSeriesPanel.__init__` | `QScrollArea` | self.detail | — |
| 157 | `ExperimentSeriesPanel.inspect_selected` | `QDialog` | dialog | — |
| 158 | `ExperimentSeriesPanel.inspect_selected` | `setWindowTitle` | — | Selected experiment details / provenance |
| 160 | `ExperimentSeriesPanel.inspect_selected` | `QTextBrowser` | view | — |
| 206 | `ExperimentSeriesPanel.render` | `QSplitter` | columns | — |
| 212 | `ExperimentSeriesPanel.render` | `QLabel` | label_widget | — |
| 215 | `ExperimentSeriesPanel.render` | `QPushButton` | open_button | Open complete participant experiment |
| 219 | `ExperimentSeriesPanel.render` | `QTextBrowser` | details | — |
| 238 | `ExperimentSeriesPanel.render` | `QPushButton` | diagnostics | Inspect captured result and diagnostics |
| 242 | `ExperimentSeriesPanel.render` | `QPushButton` | button | — |
| 246 | `ExperimentSeriesPanel.render` | `ScientificFigureWidget` | figure | — |
| 264 | `ExperimentSeriesPanel._check_details` | `QDialog` | dialog | — |
| 265 | `ExperimentSeriesPanel._check_details` | `setWindowTitle` | — | Captured design comparability definitions |
| 267 | `ExperimentSeriesPanel._check_details` | `QTextBrowser` | view | — |
| 274 | `ExperimentSeriesPanel._diagnostics` | `QDialog` | dialog | — |
| 277 | `ExperimentSeriesPanel._diagnostics` | `QTextBrowser` | view | — |
| 288 | `ExperimentSeriesPanel._report.loaded` | `QDialog` | dialog | — |
| 291 | `ExperimentSeriesPanel._report.loaded` | `QTextBrowser` | view | — |

## `import_review.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 47 | `MappingEditor.__init__` | `setWindowTitle` | — | Edit mapping |
| 50 | `MappingEditor.__init__` | `QLabel` | — | Choose the file column and unit for each target. Units are converted deterministically; nothing is assumed. |
| 53 | `MappingEditor.__init__` | `QComboBox` | self.family | — |
| 59 | `MappingEditor.__init__` | `setAccessibleName` | — | Measurement family to import |
| 61 | `MappingEditor.__init__` | `QLabel` | note | For mixed CMJ and monitoring columns, explicitly choose one family per import. Import the original again for the other family, then link by confirmed participant IDs. Monitoring must have one record per participant and time point; repeated trials are not silently averaged. |
| 70 | `MappingEditor.__init__` | `QComboBox` | — | — |
| 70 | `MappingEditor.__init__` | `QComboBox` | — | — |
| 89 | `MappingEditor.__init__` | `QPushButton` | — | Apply mapping |
| 89 | `MappingEditor.__init__` | `QPushButton` | — | Cancel |
| 129 | `ImportReviewDialog.__init__` | `setWindowTitle` | — | Import data |
| 138 | `ImportReviewDialog.__init__` | `QLabel` | self.heading | Import your data |
| 145 | `ImportReviewDialog.__init__` | `QLabel` | self.path_label | Drag a file here, or choose one from your computer. |
| 148 | `ImportReviewDialog.__init__` | `QPushButton` | — | &Choose file |
| 148 | `ImportReviewDialog.__init__` | `QPushButton` | — | Choose &folder… |
| 158 | `ImportReviewDialog.__init__` | `QLabel` | drop_text | Drop your file here |
| 162 | `ImportReviewDialog.__init__` | `QLabel` | formats | CSV · TSV · Excel · Parquet · Arrow · JSON |
| 169 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Drop zone |
| 170 | `ImportReviewDialog.__init__` | `QLabel` | self.summary | — |
| 173 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Import summary |
| 177 | `ImportReviewDialog.__init__` | `QLabel` | self.stage_label | — |
| 179 | `ImportReviewDialog.__init__` | `QProgressBar` | self.progress | — |
| 181 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Import processing |
| 187 | `ImportReviewDialog.__init__` | `QLabel` | self.question | — |
| 189 | `ImportReviewDialog.__init__` | `QLineEdit` | self.answer | — |
| 190 | `ImportReviewDialog.__init__` | `QComboBox` | self.answer_choice | — |
| 194 | `ImportReviewDialog.__init__` | `QPushButton` | self.continue_button | &Continue |
| 200 | `ImportReviewDialog.__init__` | `QTableWidget` | self.files | — |
| 204 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Files to import |
| 207 | `ImportReviewDialog.__init__` | `QTableWidget` | self.preview | — |
| 208 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Data preview |
| 210 | `ImportReviewDialog.__init__` | `QTableWidget` | self.mapping | — |
| 212 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Mapping decisions |
| 215 | `ImportReviewDialog.__init__` | `QSplitter` | data_page | — |
| 221 | `ImportReviewDialog.__init__` | `QComboBox` | self.privacy | — |
| 225 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Privacy classification |
| 228 | `ImportReviewDialog.__init__` | `QLineEdit` | edit | — |
| 236 | `ImportReviewDialog.__init__` | `QCheckBox` | self.rights | I reviewed the licence, permitted uses and redistribution terms. |
| 237 | `ImportReviewDialog.__init__` | `QLineEdit` | self.reviewer | — |
| 238 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Rights verified by |
| 253 | `ImportReviewDialog.__init__` | `QPushButton` | self.more_button | More ▾ |
| 268 | `ImportReviewDialog.__init__` | `QScrollArea` | scroll | — |
| 272 | `ImportReviewDialog.__init__` | `QTextBrowser` | self.verdict | — |
| 273 | `ImportReviewDialog.__init__` | `setAccessibleName` | — | Detection, QC verdict, warnings and provenance |
| 274 | `ImportReviewDialog.__init__` | `QTabWidget` | self.detail_tabs | — |
| 275 | `ImportReviewDialog.__init__` | `addTab` | — | Source |
| 276 | `ImportReviewDialog.__init__` | `addTab` | — | Data and mapping |
| 277 | `ImportReviewDialog.__init__` | `addTab` | — | QC report |
| 287 | `ImportReviewDialog.__init__` | `QPushButton` | self.qc_button | Run &QC |
| 288 | `ImportReviewDialog.__init__` | `QPushButton` | self.edit_button | &Edit mapping… |
| 289 | `ImportReviewDialog.__init__` | `QPushButton` | self.preset_button | Save &preset… |
| 290 | `ImportReviewDialog.__init__` | `QPushButton` | self.quarantine_button | Qua&rantine |
| 291 | `ImportReviewDialog.__init__` | `QPushButton` | self.admit_button | &Admit |
| 292 | `ImportReviewDialog.__init__` | `QPushButton` | close | Close |
| 305 | `ImportReviewDialog.__init__` | `QPushButton` | self.details_button | View &details / Advanced |
| 308 | `ImportReviewDialog.__init__` | `QPushButton` | self.import_button | &Import |
| 313 | `ImportReviewDialog.__init__` | `QPushButton` | self.open_button | &Open dataset |
| 316 | `ImportReviewDialog.__init__` | `QPushButton` | self.another_button | Import &another |
| 318 | `ImportReviewDialog.__init__` | `QPushButton` | self.retry_button | &Retry |
| 341 | `ImportReviewDialog._choose_file` | `getOpenFileName` | (path, _) | Choose data file |
| 346 | `ImportReviewDialog._choose_folder` | `getExistingDirectory` | path | Choose data folder |
| 907 | `ImportReviewDialog._save_preset` | `getText` | (name, ok) | Save preset |

## `individual_research.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 52 | `_table` | `QTableWidget` | table | — |
| 103 | `RetestReviewDialog.__init__` | `setWindowTitle` | — | Review matched retest evidence |
| 106 | `RetestReviewDialog.__init__` | `QComboBox` | — | — |
| 106 | `RetestReviewDialog.__init__` | `QComboBox` | — | — |
| 109 | `RetestReviewDialog.__init__` | `QLineEdit` | — | — |
| 109 | `RetestReviewDialog.__init__` | `QLineEdit` | — | — |
| 112 | `RetestReviewDialog.__init__` | `QPlainTextEdit` | self.evidence | — |
| 114 | `RetestReviewDialog.__init__` | `QCheckBox` | self.confirm | I confirmed stable retest conditions and matching jump-height methods. |
| 115 | `RetestReviewDialog.__init__` | `setAccessibleName` | — | Confirm stable and applicable retest design |
| 122 | `RetestReviewDialog.__init__` | `QDialogButtonBox` | self.buttons | — |
| 168 | `IndividualResearchPanel.__init__` | `QLabel` | self.header | Open an athlete from the squad to start individual research. |
| 173 | `IndividualResearchPanel.__init__` | `QTabWidget` | self.tabs | — |
| 301 | `IndividualResearchPanel._build_data` | `addTab` | — | Data |
| 308 | `IndividualResearchPanel._build_analysis` | `QLabel` | note | Individual observational analyses describe one participant's measured trajectory. They are not personalized causal estimates, forecasts or injury-risk assessments. |
| 312 | `IndividualResearchPanel._build_analysis` | `QLabel` | inference_note | Randomized-onset inference requires a saved prospective allocation and complete faithful conduct. Phase differences remain descriptive. |
| 315 | `IndividualResearchPanel._build_analysis` | `QComboBox` | self.method_picker | — |
| 316 | `IndividualResearchPanel._build_analysis` | `setAccessibleName` | — | Individual analysis method |
| 319 | `IndividualResearchPanel._build_analysis` | `QComboBox` | self.analysis_protocol | — |
| 320 | `IndividualResearchPanel._build_analysis` | `setAccessibleName` | — | Experimental analysis protocol version |
| 327 | `IndividualResearchPanel._build_analysis` | `QComboBox` | — | — |
| 327 | `IndividualResearchPanel._build_analysis` | `QComboBox` | — | — |
| 333 | `IndividualResearchPanel._build_analysis` | `QPushButton` | self.trust_review | Review matched retest evidence… |
| 335 | `IndividualResearchPanel._build_analysis` | `QPushButton` | self.trust_remove | Remove evidence |
| 341 | `IndividualResearchPanel._build_analysis` | `QLabel` | self.trust_note | — |
| 345 | `IndividualResearchPanel._build_analysis` | `QCheckBox` | self.method_advanced | Show full statistical contract and assumptions |
| 348 | `IndividualResearchPanel._build_analysis` | `QTextBrowser` | self.method_detail | — |
| 350 | `IndividualResearchPanel._build_analysis` | `QPushButton` | self.run_button | Run individual analysis on the active revision |
| 353 | `IndividualResearchPanel._build_analysis` | `addTab` | — | Analysis |
| 441 | `IndividualResearchPanel._build_results` | `QComboBox` | self.run_picker | — |
| 442 | `IndividualResearchPanel._build_results` | `setAccessibleName` | — | Saved individual analyses |
| 446 | `IndividualResearchPanel._build_results` | `QPushButton` | self.export_result | Create report from selected result… |
| 448 | `IndividualResearchPanel._build_results` | `QPushButton` | self.frozen_reports | Open frozen reports and analyses |
| 452 | `IndividualResearchPanel._build_results` | `QPushButton` | self.context_link | Explore training & testing context |
| 456 | `IndividualResearchPanel._build_results` | `QTabWidget` | self.result_tabs | — |
| 457 | `IndividualResearchPanel._build_results` | `QTextBrowser` | self.result_view | — |
| 458 | `IndividualResearchPanel._build_results` | `addTab` | — | Result |
| 459 | `IndividualResearchPanel._build_results` | `QTextBrowser` | self.result_diagnostics | — |
| 462 | `IndividualResearchPanel._build_results` | `addTab` | — | Trajectory |
| 463 | `IndividualResearchPanel._build_results` | `addTab` | — | Diagnostics and provenance |
| 470 | `IndividualResearchPanel._build_results` | `QPushButton` | self.trust_trace | Open matched force trace |
| 473 | `IndividualResearchPanel._build_results` | `QLabel` | self.trust_trace_note | — |
| 477 | `IndividualResearchPanel._build_results` | `addTab` | — | Source trials |
| 480 | `IndividualResearchPanel._build_results` | `addTab` | — | Results |
| 615 | `IndividualResearchPanel._show_run_figure` | `ScientificFigureWidget` | — | — |
| 623 | `IndividualResearchPanel._build_protocol` | `QTabWidget` | self.protocol_sections | — |
| 624 | `IndividualResearchPanel._build_protocol` | `setAccessibleName` | — | Protocol authoring sections |
| 631 | `IndividualResearchPanel._build_protocol` | `QScrollArea` | section_scroll | — |
| 638 | `IndividualResearchPanel._build_protocol` | `QLabel` | self.protocol_note | Choose a design suited to the intervention. Randomized onset draws a future start once and keeps treatment persistent; crossover requires replicated comparator periods. Saved allocations cannot be redrawn. |
| 643 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.protocol_question | — |
| 644 | `IndividualResearchPanel._build_protocol` | `setAccessibleName` | — | Experimental research question |
| 645 | `IndividualResearchPanel._build_protocol` | `QLabel` | self.protocol_outcome | — |
| 646 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.amendment_reason | — |
| 654 | `IndividualResearchPanel._build_protocol` | `QComboBox` | self.design_picker | — |
| 657 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.assignment | — |
| 659 | `IndividualResearchPanel._build_protocol` | `QCheckBox` | self.prespecified | Periods were prespecified before the outcome measurements |
| 660 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.blinding | — |
| 661 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.testing_occasions | — |
| 676 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.onset_starts | — |
| 677 | `IndividualResearchPanel._build_protocol` | `setAccessibleName` | — | Permissible randomized intervention starts |
| 678 | `IndividualResearchPanel._build_protocol` | `QPlainTextEdit` | self.onset_dates | — |
| 681 | `IndividualResearchPanel._build_protocol` | `setAccessibleName` | — | Prespecified measurement timestamps |
| 682 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.onset_baseline | — |
| 683 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.onset_intervention | — |
| 684 | `IndividualResearchPanel._build_protocol` | `QLineEdit` | self.onset_suitability | — |
| 685 | `IndividualResearchPanel._build_protocol` | `QCheckBox` | self.onset_acknowledge | I confirm the scientific assumptions below |
| 686 | `IndividualResearchPanel._build_protocol` | `QLabel` | assumptions | Required: no anticipation/interference; stable measurements; no assignment-dependent co-intervention or missingness. Persistent intervention; immediate-level statistic fixed in advance. Delayed effects may be missed. |
| 704 | `IndividualResearchPanel._build_protocol` | `QPushButton` | add | Add period |
| 706 | `IndividualResearchPanel._build_protocol` | `QPushButton` | remove | Remove period |
| 714 | `IndividualResearchPanel._build_protocol` | `QPlainTextEdit` | self.changes | — |
| 717 | `IndividualResearchPanel._build_protocol` | `QLabel` | conduct_note | Record actual condition, exposure, adherence, deviations and missing visits in Observations (Visits and timeline). These notes preserve legacy tracking metadata; prospective amendments require a reason in Research question. |
| 723 | `IndividualResearchPanel._build_protocol` | `QPushButton` | self.save_protocol_button | Save protocol version |
| 728 | `IndividualResearchPanel._build_protocol` | `QTextBrowser` | self.period_view | — |
| 732 | `IndividualResearchPanel._build_protocol` | `QScrollArea` | scroll | — |
| 735 | `IndividualResearchPanel._build_protocol` | `addTab` | — | Protocol |
| 775 | `IndividualResearchPanel._add_period` | `QComboBox` | kind | — |
| 859 | `IndividualResearchPanel._build_experiment` | `QLabel` | note | Save a prospective experimental protocol in Protocol first. Import later measurements into this same workspace, then link each actual visit here. Planned exposure is never treated as observed exposure. |
| 863 | `IndividualResearchPanel._build_experiment` | `QLabel` | inference_note | Compare the planned timeline with actual condition, timing and measurements before analysis. Descriptive changes do not establish a treatment effect. |
| 866 | `IndividualResearchPanel._build_experiment` | `QComboBox` | self.protocol_history | — |
| 867 | `IndividualResearchPanel._build_experiment` | `setAccessibleName` | — | Experimental protocol history |
| 870 | `IndividualResearchPanel._build_experiment` | `QPushButton` | self.analyze_experiment_button | Analyze this protocol |
| 873 | `IndividualResearchPanel._build_experiment` | `QPushButton` | self.visit_editor_toggle | Record or correct an actual visit… |
| 878 | `IndividualResearchPanel._build_experiment` | `QLabel` | self.conduct_status | — |
| 894 | `IndividualResearchPanel._build_experiment` | `QTextBrowser` | self.experiment_summary | — |
| 896 | `IndividualResearchPanel._build_experiment` | `QCheckBox` | self.conduct_details | Show period summaries and append-only visit history |
| 899 | `IndividualResearchPanel._build_experiment` | `QLabel` | self.visit_review | — |
| 907 | `IndividualResearchPanel._build_experiment` | `QComboBox` | self.visit_schedule | — |
| 908 | `IndividualResearchPanel._build_experiment` | `setAccessibleName` | — | Scheduled experimental measurement |
| 909 | `IndividualResearchPanel._build_experiment` | `QLineEdit` | self.visit_occasion | — |
| 910 | `IndividualResearchPanel._build_experiment` | `setAccessibleName` | — | Actual experimental occasion |
| 912 | `IndividualResearchPanel._build_experiment` | `QLineEdit` | self.visit_time | — |
| 913 | `IndividualResearchPanel._build_experiment` | `QComboBox` | self.visit_revision | — |
| 914 | `IndividualResearchPanel._build_experiment` | `setAccessibleName` | — | Immutable experimental measurement revision |
| 915 | `IndividualResearchPanel._build_experiment` | `QComboBox` | self.visit_status | — |
| 917 | `IndividualResearchPanel._build_experiment` | `QLineEdit` | self.visit_exposure | — |
| 918 | `IndividualResearchPanel._build_experiment` | `QComboBox` | self.visit_condition | — |
| 922 | `IndividualResearchPanel._build_experiment` | `setAccessibleName` | — | Actually recorded experimental condition |
| 923 | `IndividualResearchPanel._build_experiment` | `QLineEdit` | self.visit_adherence | — |
| 925 | `IndividualResearchPanel._build_experiment` | `QLineEdit` | self.visit_missing | — |
| 926 | `IndividualResearchPanel._build_experiment` | `QLineEdit` | self.visit_deviations | — |
| 927 | `IndividualResearchPanel._build_experiment` | `QComboBox` | self.visit_supersedes | — |
| 936 | `IndividualResearchPanel._build_experiment` | `QPushButton` | self.save_visit_button | Record actual visit |
| 950 | `IndividualResearchPanel._build_experiment` | `QScrollArea` | scroll | — |
| 953 | `IndividualResearchPanel._build_experiment` | `addTab` | — | Visits and timeline |
| 1122 | `IndividualResearchPanel._build_scenarios` | `QLabel` | banner | — |
| 1126 | `IndividualResearchPanel._build_scenarios` | `QTextBrowser` | self.scenario_view | — |
| 1129 | `IndividualResearchPanel._build_scenarios` | `QComboBox` | self.scenario_kind | — |
| 1132 | `IndividualResearchPanel._build_scenarios` | `QLineEdit` | self.scenario_title | — |
| 1133 | `IndividualResearchPanel._build_scenarios` | `QComboBox` | self.model_picker | — |
| 1135 | `IndividualResearchPanel._build_scenarios` | `QDoubleSpinBox` | self.horizon_value | — |
| 1138 | `IndividualResearchPanel._build_scenarios` | `QComboBox` | self.horizon_unit | — |
| 1143 | `IndividualResearchPanel._build_scenarios` | `QLineEdit` | self.adverse | — |
| 1145 | `IndividualResearchPanel._build_scenarios` | `QPlainTextEdit` | self.assumptions | — |
| 1159 | `IndividualResearchPanel._build_scenarios` | `QPushButton` | save | Save hypothetical scenario |
| 1162 | `IndividualResearchPanel._build_scenarios` | `QScrollArea` | scroll | — |
| 1165 | `IndividualResearchPanel._build_scenarios` | `addTab` | — | Scenarios |
| 1211 | `IndividualResearchPanel._build_compare` | `QPushButton` | button | Compare observed values |
| 1215 | `IndividualResearchPanel._build_compare` | `QPushButton` | details | Interpretation and limitations… |
| 1222 | `IndividualResearchPanel._build_compare` | `QTextBrowser` | self.compare_notes | — |
| 1224 | `IndividualResearchPanel._build_compare` | `addTab` | — | Compare with cohort |
| 1227 | `IndividualResearchPanel._comparison_details` | `QDialog` | dialog | — |
| 1228 | `IndividualResearchPanel._comparison_details` | `setWindowTitle` | — | Comparison interpretation and limitations |
| 1231 | `IndividualResearchPanel._comparison_details` | `QTextBrowser` | notes | — |
| 1234 | `IndividualResearchPanel._comparison_details` | `QPushButton` | close | Close |

## `investigation_editor.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 41 | `InvestigationEditor.__init__` | `QComboBox` | self.investigations | — |
| 43 | `InvestigationEditor.__init__` | `QPushButton` | self.new_button | New |
| 45 | `InvestigationEditor.__init__` | `QPushButton` | self.fork_button | Fork |
| 47 | `InvestigationEditor.__init__` | `QLabel` | — | Investigation |
| 53 | `InvestigationEditor.__init__` | `QLineEdit` | self.title | — |
| 57 | `InvestigationEditor.__init__` | `QSplitter` | editor | — |
| 58 | `InvestigationEditor.__init__` | `QListWidget` | self.block_list | — |
| 64 | `InvestigationEditor.__init__` | `QLineEdit` | self.block_title | — |
| 66 | `InvestigationEditor.__init__` | `QPlainTextEdit` | self.state | — |
| 69 | `InvestigationEditor.__init__` | `QLabel` | — | Selected block |
| 71 | `InvestigationEditor.__init__` | `QLabel` | — | Block configuration · JSON |
| 79 | `InvestigationEditor.__init__` | `QComboBox` | self.block_type | — |
| 87 | `InvestigationEditor.__init__` | `QPushButton` | self.add_block_button | Add block |
| 89 | `InvestigationEditor.__init__` | `QPushButton` | self.remove_block_button | Remove |
| 91 | `InvestigationEditor.__init__` | `QPushButton` | self.move_up_button | Move up |
| 93 | `InvestigationEditor.__init__` | `QPushButton` | self.move_down_button | Move down |
| 95 | `InvestigationEditor.__init__` | `QPushButton` | self.save_button | Save version |
| 106 | `InvestigationEditor.__init__` | `QLabel` | self.status | Open a persisted study to author its investigation. |

## `investigation_timeline.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 32 | `wrapping_label` | `QLabel` | label | — |
| 50 | `InvestigationChart.__init__` | `setAccessibleName` | — | Investigation timeline. Use the observation selector to inspect points with the keyboard. |
| 158 | `EvidencePanel.__init__` | `QLabel` | title | Observation evidence |
| 161 | `EvidencePanel.__init__` | `QComboBox` | self.picker | — |
| 162 | `EvidencePanel.__init__` | `setAccessibleName` | — | Inspect timeline observation |
| 167 | `EvidencePanel.__init__` | `QTextBrowser` | self.details | — |
| 168 | `EvidencePanel.__init__` | `setAccessibleName` | — | Selected observation evidence |
| 171 | `EvidencePanel.__init__` | `QPushButton` | self.followup | — |
| 174 | `EvidencePanel.__init__` | `QPushButton` | self.provenance_button | Details / Provenance… |
| 266 | `EvidencePanel._open_provenance` | `QDialog` | dialog | — |
| 267 | `EvidencePanel._open_provenance` | `setWindowTitle` | — | Observation details / provenance |
| 269 | `EvidencePanel._open_provenance` | `QTextBrowser` | text | — |
| 272 | `EvidencePanel._open_provenance` | `QDialogButtonBox` | buttons | — |

## `library_dialog.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 29 | `ScientificLibraryDialog.__init__` | `setWindowTitle` | — | Scientific definition library |
| 33 | `ScientificLibraryDialog.__init__` | `QLabel` | — | Read-only definitions used by the workbench. Prototype and unavailable entries are shown with their recorded status and limitations. |
| 38 | `ScientificLibraryDialog.__init__` | `QTabWidget` | self.tabs | — |
| 50 | `ScientificLibraryDialog.__init__` | `QSplitter` | splitter | — |
| 51 | `ScientificLibraryDialog.__init__` | `QTableView` | table | — |
| 59 | `ScientificLibraryDialog.__init__` | `QTextBrowser` | detail | — |
| 78 | `ScientificLibraryDialog.__init__` | `QDialogButtonBox` | buttons | — |

## `lineage_dialog.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 33 | `LineageDialog.__init__` | `setWindowTitle` | — | Scientific provenance lineage |
| 43 | `LineageDialog.__init__` | `QSplitter` | split | — |
| 47 | `LineageDialog.__init__` | `QTextBrowser` | self.detail | — |
| 57 | `LineageDialog.__init__` | `QPushButton` | fit | Fit graph |
| 64 | `LineageDialog.__init__` | `QDialogButtonBox` | buttons | — |

## `main_window.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 109 | `MainWindow.__init__` | `setWindowTitle` | — | DynamisScience |
| 121 | `MainWindow._build_shell` | `QTreeWidget` | self.navigator | — |
| 123 | `MainWindow._build_shell` | `setAccessibleName` | — | Research navigator |
| 125 | `MainWindow._build_shell` | `QDockWidget` | self.navigator_dock | Navigator |
| 127 | `MainWindow._build_shell` | `QStackedWidget` | self.navigator_stack | — |
| 131 | `MainWindow._build_shell` | `QTextBrowser` | self.inspector | — |
| 132 | `MainWindow._build_shell` | `setAccessibleName` | — | Inspector raw detail |
| 133 | `MainWindow._build_shell` | `QDockWidget` | self.inspector_dock | Inspector |
| 135 | `MainWindow._build_shell` | `QStackedWidget` | self.inspector_stack | — |
| 145 | `MainWindow._build_shell` | `QStackedWidget` | self.workspace | — |
| 146 | `MainWindow._build_shell` | `QLabel` | self.welcome | Loading the validated research catalogue… |
| 159 | `MainWindow._build_shell` | `QScrollArea` | results_scroll | — |
| 166 | `MainWindow._build_shell` | `QStackedWidget` | self.results_stack | — |
| 217 | `MainWindow._build_shell` | `QScrollArea` | perspectives_scroll | — |
| 225 | `MainWindow._build_shell` | `QProgressBar` | self.progress | — |
| 228 | `MainWindow._build_shell` | `setAccessibleName` | — | Background task in progress |
| 253 | `MainWindow._build_menu` | `QAction` | action | — |
| 259 | `MainWindow._build_menu` | `QToolBar` | context_bar | Research Context |
| 264 | `MainWindow._build_menu` | `QLabel` | wordmark | DynamisScience |
| 267 | `MainWindow._build_menu` | `QPushButton` | self.investigate_button | Investigate |
| 268 | `MainWindow._build_menu` | `QPushButton` | self.study_button | Study |
| 276 | `MainWindow._build_menu` | `QLabel` | self.location | — |
| 283 | `MainWindow._build_menu` | `QMenu` | self.tools_menu | Study tools |
| 284 | `MainWindow._build_menu` | `QToolButton` | tools_button | — |
| 291 | `MainWindow._build_menu` | `QLabel` | self.context_title | No workspace |
| 292 | `MainWindow._build_menu` | `setAccessibleName` | — | Workspace title and active data revision |
| 295 | `MainWindow._build_menu` | `QComboBox` | self.scope_picker | — |
| 296 | `MainWindow._build_menu` | `setAccessibleName` | — | Research cohort or athlete investigation |
| 302 | `MainWindow._build_menu` | `QComboBox` | self.stage_picker | — |
| 303 | `MainWindow._build_menu` | `setAccessibleName` | — | Research stage |
| 312 | `MainWindow._build_menu` | `QLabel` | self.context_binding | — |
| 313 | `MainWindow._build_menu` | `setAccessibleName` | — | Selected protocol and result binding |
| 322 | `MainWindow._build_menu` | `addMenu` | file_menu | File |
| 323 | `MainWindow._build_menu` | `QAction` | export_action | Export current report… |
| 326 | `MainWindow._build_menu` | `addAction` | combined | Export combined report… |
| 329 | `MainWindow._build_menu` | `QAction` | quit_action | Quit |
| 332 | `MainWindow._build_menu` | `addMenu` | research_menu | Research |
| 333 | `MainWindow._build_menu` | `addAction` | — | Attach an admitted dataset… |
| 334 | `MainWindow._build_menu` | `QAction` | self.action_new_project | New project… |
| 336 | `MainWindow._build_menu` | `QAction` | self.action_new_study | New study… |
| 338 | `MainWindow._build_menu` | `QAction` | self.action_new_monitoring | New monitoring program… |
| 340 | `MainWindow._build_menu` | `QAction` | self.action_edit | Edit selected project / study… |
| 342 | `MainWindow._build_menu` | `QAction` | self.action_workspace | Data workspace… |
| 345 | `MainWindow._build_menu` | `QAction` | self.action_import | Import data… |
| 348 | `MainWindow._build_menu` | `QAction` | self.action_admit | Admit local dataset (manual)… |
| 350 | `MainWindow._build_menu` | `QAction` | self.action_admission_history | Admission and quarantine history… |
| 352 | `MainWindow._build_menu` | `QAction` | self.action_archive | Archive selected project / study |
| 354 | `MainWindow._build_menu` | `QAction` | self.action_restore | Restore selected project / study |
| 356 | `MainWindow._build_menu` | `QAction` | self.action_transition | Transition selected study state… |
| 358 | `MainWindow._build_menu` | `QAction` | self.action_study_history | Study / project history… |
| 360 | `MainWindow._build_menu` | `QAction` | self.action_report_history | Report version history… |
| 362 | `MainWindow._build_menu` | `QAction` | self.action_compare_report_versions | Compare frozen report versions… |
| 364 | `MainWindow._build_menu` | `QAction` | self.action_scientific_library | Scientific definition library… |
| 384 | `MainWindow._build_menu` | `addMenu` | cohort_menu | Cohort |
| 394 | `MainWindow._build_menu` | `addMenu` | plan_menu | Analysis plan |
| 404 | `MainWindow._build_menu` | `addMenu` | tools_menu | System |
| 405 | `MainWindow._build_menu` | `QAction` | self.action_verify_database | Verify research database integrity |
| 407 | `MainWindow._build_menu` | `QAction` | self.action_backup_database | Create verified database backup |
| 409 | `MainWindow._build_menu` | `QAction` | self.action_restore_database | Rehearse restore from backup… |
| 411 | `MainWindow._build_menu` | `QAction` | self.action_run_qualification | Run independent real-data qualification |
| 420 | `MainWindow._build_menu` | `addMenu` | analyses_menu | Analyses |
| 422 | `MainWindow._build_menu` | `addMenu` | results_menu | Results |
| 431 | `MainWindow._build_menu` | `addMenu` | view_menu | View |
| 436 | `MainWindow._build_menu` | `QAction` | action | — |
| 442 | `MainWindow._build_menu` | `QAction` | self.action_study_record | Study record |
| 447 | `MainWindow._build_menu` | `addMenu` | advanced | Advanced |
| 453 | `MainWindow._build_menu` | `addMenu` | perspective_menu | Perspective |
| 454 | `MainWindow._build_menu` | `QAction` | self.action_research_perspective | Research workbench |
| 461 | `MainWindow._build_menu` | `addMenu` | help_menu | Help |
| 462 | `MainWindow._build_menu` | `QAction` | about | About DynamisScience |
| 471 | `MainWindow._build_menu` | `QAction` | licenses_action | Open-source licenses… |
| 483 | `MainWindow._build_menu` | `addAction` | — | Research context details… |
| 510 | `MainWindow._ensure_performance` | `QToolBar` | self.performance_toolbar | Performance OS |
| 514 | `MainWindow._ensure_performance` | `QScrollArea` | header_scroll | — |
| 537 | `MainWindow._open_third_party_licenses` | `QDialog` | dialog | — |
| 538 | `MainWindow._open_third_party_licenses` | `setWindowTitle` | — | Open-source licenses |
| 540 | `MainWindow._open_third_party_licenses` | `QTextBrowser` | browser | — |
| 547 | `MainWindow._open_third_party_licenses` | `QPushButton` | close | Close |
| 592 | `MainWindow._rehearse_research_restore` | `getOpenFileName` | (target, _) | Choose a verified database backup |
| 718 | `MainWindow._start_follow_up` | `getText` | (title, accepted) | Start follow-up |
| 739 | `MainWindow._show_research_mode` | `setWindowTitle` | — | Inspector |
| 849 | `MainWindow._analysis_selected` | `setAccessibleName` | — | Signal inspection |
| 942 | `MainWindow._export_results` | `getSaveFileName` | (path, selected) | Export figures |
| 1002 | `MainWindow._show_athlete_inspector` | `setWindowTitle` | — | ATHLETE 360 |
| 1008 | `MainWindow._show_daily_context` | `setWindowTitle` | — | DAILY CONTEXT |
| 1057 | `MainWindow.run_task.failed` | `QMessageBox` | box | — |
| 1058 | `MainWindow.run_task.failed` | `setWindowTitle` | — | Record changed |
| 1350 | `MainWindow._inspect_research_context` | `QDialog` | dialog | — |
| 1351 | `MainWindow._inspect_research_context` | `setWindowTitle` | — | Research context / provenance |
| 1353 | `MainWindow._inspect_research_context` | `QTextBrowser` | view | — |
| 1451 | `MainWindow._open_individual_tool` | `getItem` | (choice, ok) | Open investigation |
| 1455 | `MainWindow._open_individual_tool` | `getText` | (title, ok) | Start an investigation |
| 1477 | `MainWindow._show_individual_tool` | `QDialog` | dialog | — |
| 1487 | `MainWindow._show_individual_tool` | `QDialogButtonBox` | buttons | — |
| 1678 | `MainWindow._export_combined_report` | `getSaveFileName` | (path, _) | Export combined report |
| 1685 | `MainWindow._new_workspace` | `getText` | (title, accepted) | Create research workspace |
| 1697 | `MainWindow._choose_workspace` | `getItem` | (label, accepted) | Open research workspace |
| 1717 | `MainWindow._select_admitted_workspace_data` | `getItem` | (label, accepted) | Select data |
| 1726 | `MainWindow._attach_workspace_dataset` | `getItem` | (choice, accepted) | Attach data |
| 1758 | `MainWindow._workspace_history.show` | `QDialog` | dialog | — |
| 1759 | `MainWindow._workspace_history.show` | `setWindowTitle` | — | Workspace history |
| 1763 | `MainWindow._workspace_history.show` | `QComboBox` | picker | — |
| 1764 | `MainWindow._workspace_history.show` | `setAccessibleName` | — | Workspace history selection |
| 1776 | `MainWindow._workspace_history.show` | `QTextBrowser` | detail | — |
| 1777 | `MainWindow._workspace_history.show` | `setAccessibleName` | — | Workspace history detail or frozen report |
| 1779 | `MainWindow._workspace_history.show` | `QPushButton` | select | Open selected revision or analysis |
| 1797 | `MainWindow._workspace_history.show.open_revision` | `getSaveFileName` | (path, _) | Export frozen report |
| 2003 | `MainWindow._fork_cohort` | `getText` | (name, accepted) | Fork cohort |
| 2074 | `MainWindow._fork_plan` | `getText` | (name, accepted) | Fork analysis plan |
| 2084 | `MainWindow._history_dialog` | `QDialog` | dialog | — |
| 2087 | `MainWindow._history_dialog` | `QTextBrowser` | browser | — |
| 2090 | `MainWindow._history_dialog` | `QPushButton` | close | Close |
| 2219 | `MainWindow._transition_current_study` | `getItem` | (target, accepted) | Study state |
| 2288 | `MainWindow._show_report_version_comparison` | `QDialog` | dialog | — |
| 2289 | `MainWindow._show_report_version_comparison` | `setWindowTitle` | — | Compare frozen report versions |
| 2292 | `MainWindow._show_report_version_comparison` | `QComboBox` | left_version | — |
| 2293 | `MainWindow._show_report_version_comparison` | `QComboBox` | right_version | — |
| 2300 | `MainWindow._show_report_version_comparison` | `QLabel` | — | compared with |
| 2303 | `MainWindow._show_report_version_comparison` | `QTextBrowser` | comparison | — |
| 2365 | `ResearchWorkbench.__init__` | `QTabWidget` | self.tabs | — |
| 2391 | `ResearchWorkbench.__init__` | `addTab` | — | Series of experiments |
| 2395 | `ResearchWorkbench.__init__` | `addTab` | — | Frozen history |
| 2435 | `ResearchWorkbench._build_overview` | `QPushButton` | edit | Edit study… |
| 2439 | `ResearchWorkbench._build_overview` | `QPushButton` | cohorts | Review cohort membership… |
| 2442 | `ResearchWorkbench._build_overview` | `QPushButton` | details | Details / Provenance… |
| 2447 | `ResearchWorkbench._build_overview` | `QTextBrowser` | self.overview | — |
| 2452 | `ResearchWorkbench._show_setup_details` | `QDialog` | dialog | — |
| 2453 | `ResearchWorkbench._show_setup_details` | `setWindowTitle` | — | Study details / provenance |
| 2455 | `ResearchWorkbench._show_setup_details` | `QTextBrowser` | browser | — |
| 2458 | `ResearchWorkbench._show_setup_details` | `QDialogButtonBox` | buttons | — |
| 2484 | `ResearchWorkbench._build_dataset` | `QStackedWidget` | self.source_stack | — |
| 2494 | `ResearchWorkbench._build_dataset` | `QPushButton` | back | Back to sources |
| 2497 | `ResearchWorkbench._build_dataset` | `QLabel` | self.source_detail_title | — |
| 2501 | `ResearchWorkbench._build_dataset` | `QLabel` | self.data_summary | Inspect measurements and source quality before analysis. |
| 2504 | `ResearchWorkbench._build_dataset` | `QTabWidget` | self.dataset_tabs | — |
| 2509 | `ResearchWorkbench._build_dataset` | `QComboBox` | self.table_picker | — |
| 2511 | `ResearchWorkbench._build_dataset` | `QLabel` | — | Measurement type |
| 2513 | `ResearchWorkbench._build_dataset` | `QCheckBox` | self.preview_metadata | Show technical columns |
| 2516 | `ResearchWorkbench._build_dataset` | `QPushButton` | details | Row &details / provenance… |
| 2520 | `ResearchWorkbench._build_dataset` | `QTableView` | self.table | — |
| 2529 | `ResearchWorkbench._build_dataset` | `QLabel` | self.table_status | Select a study or dataset to inspect bounded Parquet pages. |
| 2531 | `ResearchWorkbench._build_dataset` | `addTab` | — | Parquet preview |
| 2536 | `ResearchWorkbench._build_dataset` | `QComboBox` | self.cohort_picker | — |
| 2537 | `ResearchWorkbench._build_dataset` | `QPushButton` | resolve_button | Resolve cohort |
| 2539 | `ResearchWorkbench._build_dataset` | `QLabel` | — | Saved cohort |
| 2543 | `ResearchWorkbench._build_dataset` | `QLabel` | self.cohort_summary | Open a study to resolve its cohort. |
| 2545 | `ResearchWorkbench._build_dataset` | `QTableView` | self.cohort_table | — |
| 2550 | `ResearchWorkbench._build_dataset` | `addTab` | — | Cohort resolution |
| 2602 | `ResearchWorkbench._build_exploration` | `QComboBox` | self.metric_picker | — |
| 2603 | `ResearchWorkbench._build_exploration` | `QComboBox` | self.reference_picker | — |
| 2605 | `ResearchWorkbench._build_exploration` | `QPushButton` | explore_button | Explore longitudinal signal |
| 2607 | `ResearchWorkbench._build_exploration` | `QLabel` | — | Metric |
| 2612 | `ResearchWorkbench._build_exploration` | `ScientificFigureWidget` | self.exploration_plot | — |
| 2614 | `ResearchWorkbench._build_exploration` | `QPushButton` | export_exploration | Export Matplotlib figure… |
| 2618 | `ResearchWorkbench._build_exploration` | `QComboBox` | self.trial_picker | — |
| 2619 | `ResearchWorkbench._build_exploration` | `QPushButton` | signal_button | Load selected signal |
| 2621 | `ResearchWorkbench._build_exploration` | `QLabel` | — | Force / IMU trial |
| 2625 | `ResearchWorkbench._build_exploration` | `PlotWidget` | self.signal_plot | — |
| 2635 | `ResearchWorkbench._build_analysis` | `QTabWidget` | self.analysis_tabs | — |
| 2639 | `ResearchWorkbench._build_analysis` | `QComboBox` | self.method_picker | — |
| 2640 | `ResearchWorkbench._build_analysis` | `QComboBox` | self.analysis_metric_picker | — |
| 2644 | `ResearchWorkbench._build_analysis` | `QPlainTextEdit` | self.parameters | — |
| 2647 | `ResearchWorkbench._build_analysis` | `QPushButton` | execute_button | Run analysis |
| 2650 | `ResearchWorkbench._build_analysis` | `QPushButton` | self.show_figure_button | Show Matplotlib figure |
| 2653 | `ResearchWorkbench._build_analysis` | `QPushButton` | export_run | Export figure… |
| 2657 | `ResearchWorkbench._build_analysis` | `QCheckBox` | advanced_parameters | Advanced parameters |
| 2665 | `ResearchWorkbench._build_analysis` | `QTextBrowser` | self.method_details | — |
| 2666 | `ResearchWorkbench._build_analysis` | `setAccessibleName` | — | Scientific method contract and eligibility |
| 2673 | `ResearchWorkbench._build_analysis` | `QTabWidget` | results | — |
| 2675 | `ResearchWorkbench._build_analysis` | `QTextBrowser` | self.run_output | — |
| 2678 | `ResearchWorkbench._build_analysis` | `QLabel` | — | Run an analysis to create a scientific figure. |
| 2679 | `ResearchWorkbench._build_analysis` | `addTab` | — | Result |
| 2680 | `ResearchWorkbench._build_analysis` | `addTab` | — | Figure |
| 2681 | `ResearchWorkbench._build_analysis` | `QTextBrowser` | self.run_provenance | — |
| 2682 | `ResearchWorkbench._build_analysis` | `addTab` | — | Diagnostics and provenance |
| 2684 | `ResearchWorkbench._build_analysis` | `addTab` | — | Analysis run |
| 2688 | `ResearchWorkbench._build_analysis` | `addTab` | — | Investigation |
| 2695 | `ResearchWorkbench._build_evidence` | `QPushButton` | promote_button | Promote completed run to evidence |
| 2697 | `ResearchWorkbench._build_evidence` | `QPushButton` | cite_button | Cite promoted evidence |
| 2699 | `ResearchWorkbench._build_evidence` | `QPushButton` | uncite_button | Remove current citation |
| 2701 | `ResearchWorkbench._build_evidence` | `QPushButton` | freeze_button | Freeze report version |
| 2703 | `ResearchWorkbench._build_evidence` | `QPushButton` | lineage_button | Show provenance lineage |
| 2705 | `ResearchWorkbench._build_evidence` | `QPushButton` | export_button | Export versioned HTML report… |
| 2710 | `ResearchWorkbench._build_evidence` | `QTextBrowser` | self.evidence_output | — |
| 2714 | `ResearchWorkbench._build_evidence` | `QLineEdit` | self.report_title | — |
| 2715 | `ResearchWorkbench._build_evidence` | `QPlainTextEdit` | self.report_summary | — |
| 2717 | `ResearchWorkbench._build_evidence` | `QPlainTextEdit` | self.report_conclusion | — |
| 2719 | `ResearchWorkbench._build_evidence` | `QPlainTextEdit` | self.report_recommendations | — |
| 2726 | `ResearchWorkbench._build_evidence` | `QPushButton` | self.save_report_button | Save report draft |
| 2729 | `ResearchWorkbench._build_evidence` | `QTextBrowser` | self.report_preview | — |
| 3031 | `ResearchWorkbench._preview_details` | `QDialog` | dialog | — |
| 3032 | `ResearchWorkbench._preview_details` | `setWindowTitle` | — | Measurement row details / provenance |
| 3034 | `ResearchWorkbench._preview_details` | `QTextBrowser` | view | — |
| 3332 | `ResearchWorkbench._show_run_figure` | `ScientificFigureWidget` | self.run_plot | — |
| 3518 | `ResearchWorkbench.export_report` | `getSaveFileName` | (path, _) | Export scientific report |
| 3531 | `ResearchWorkbench.export_report` | `getSaveFileName` | (path, _) | Export scientific report |

## `performance_workbench.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 49 | `_record_view` | `QTableView` | view | — |
| 65 | `SessionDialog.__init__` | `setWindowTitle` | — | Log training session |
| 66 | `SessionDialog.__init__` | `QDateEdit` | self.date | — |
| 68 | `SessionDialog.__init__` | `QLineEdit` | self.session_type | Field |
| 69 | `SessionDialog.__init__` | `QDoubleSpinBox` | self.duration | — |
| 72 | `SessionDialog.__init__` | `QDoubleSpinBox` | self.rpe | — |
| 75 | `SessionDialog.__init__` | `QSpinBox` | self.attendance | — |
| 78 | `SessionDialog.__init__` | `QLineEdit` | self.notes | — |
| 89 | `SessionDialog.__init__` | `QDialogButtonBox` | buttons | — |
| 112 | `PlanDialog.__init__` | `setWindowTitle` | — | Edit microcycle |
| 119 | `PlanDialog.__init__` | `QSpinBox` | self.week | — |
| 122 | `PlanDialog.__init__` | `QLineEdit` | self.focus | — |
| 123 | `PlanDialog.__init__` | `QLineEdit` | self.testing | — |
| 124 | `PlanDialog.__init__` | `QTableWidget` | self.sessions | — |
| 134 | `PlanDialog.__init__` | `QPushButton` | add | Add session |
| 135 | `PlanDialog.__init__` | `QPushButton` | remove | Remove selected |
| 144 | `PlanDialog.__init__` | `QDialogButtonBox` | buttons | — |
| 193 | `ReportDialog.__init__` | `setWindowTitle` | — | Compose practitioner report |
| 194 | `ReportDialog.__init__` | `QComboBox` | self.audience | — |
| 197 | `ReportDialog.__init__` | `QComboBox` | self.athlete | — |
| 200 | `ReportDialog.__init__` | `QLineEdit` | self.role | Head of Performance |
| 205 | `ReportDialog.__init__` | `QDialogButtonBox` | buttons | — |
| 230 | `PerformanceHeader.__init__` | `QToolButton` | self.menu_button | — |
| 238 | `PerformanceHeader.__init__` | `QLabel` | name | Dynamis Performance OS |
| 240 | `PerformanceHeader.__init__` | `QLabel` | descriptor | SPORTS SCIENCE |
| 246 | `PerformanceHeader.__init__` | `QLabel` | self.club | Northside FC |
| 248 | `PerformanceHeader.__init__` | `QLabel` | self.squad | U21 |
| 252 | `PerformanceHeader.__init__` | `QLabel` | slash | / |
| 255 | `PerformanceHeader.__init__` | `QLabel` | mode | Performance |
| 258 | `PerformanceHeader.__init__` | `QLabel` | self.season | 2026/27 · WEEK 16 · BUILD |
| 262 | `PerformanceHeader.__init__` | `QLineEdit` | self.search | — |
| 272 | `PerformanceHeader.__init__` | `QLabel` | role | ROLE |
| 275 | `PerformanceHeader.__init__` | `QLabel` | self.role | Head of Performance |
| 278 | `PerformanceHeader.__init__` | `QLabel` | self.avatar | HP |
| 283 | `PerformanceHeader.set_menu_actions` | `QMenu` | menu | — |
| 315 | `PerformanceRail.__init__` | `QLabel` | crest | NFC |
| 319 | `PerformanceRail.__init__` | `QLabel` | self.club_name | Northside FC |
| 321 | `PerformanceRail.__init__` | `QLabel` | self.squad_summary | U21 · 28 athletes |
| 332 | `PerformanceRail.__init__` | `QLabel` | label | — |
| 336 | `PerformanceRail.__init__` | `QPushButton` | button | — |
| 342 | `PerformanceRail.__init__` | `QLabel` | title | — |
| 346 | `PerformanceRail.__init__` | `QLabel` | tag_label | — |
| 359 | `PerformanceRail.__init__` | `QLabel` | footer_heading | SQUAD AVAILABILITY |
| 362 | `PerformanceRail.__init__` | `QLabel` | self.availability | 28 / 28 active |
| 373 | `PerformanceRail.__init__` | `QLabel` | self.availability_note | No injury table admitted. Roster status only. |
| 417 | `PerformanceContextPanel.__init__` | `QStackedWidget` | self.views | — |
| 436 | `PerformanceContextPanel.__init__` | `QLabel` | self.readiness_legend | — |
| 438 | `PerformanceContextPanel.__init__` | `QLabel` | self.quality | Waiting for the synthetic fixture summary. |
| 440 | `PerformanceContextPanel.__init__` | `QLabel` | self.injury | Injury module unavailable · no injury or exposure table admitted. |
| 442 | `PerformanceContextPanel.__init__` | `QLabel` | self.movement | Movement scope is a bounded segment, not full-match distance. |
| 463 | `PerformanceContextPanel.__init__` | `QLabel` | footer | Synthetic fixture · DS-SYNTH-001 · no real athletes or measurements |
| 472 | `PerformanceContextPanel.__init__` | `QLabel` | self.athlete_identity | ATHLETE 360 |
| 474 | `PerformanceContextPanel.__init__` | `QLabel` | self.athlete_position | Select an athlete from the squad command queue. |
| 490 | `PerformanceContextPanel.__init__` | `QLabel` | caption | — |
| 492 | `PerformanceContextPanel.__init__` | `QLabel` | value | — |
| 499 | `PerformanceContextPanel.__init__` | `QLabel` | self.athlete_baseline | — |
| 503 | `PerformanceContextPanel.__init__` | `QLabel` | self.athlete_notes | — |
| 507 | `PerformanceContextPanel.__init__` | `QLabel` | self.athlete_limitations | Availability is roster-only. Individual change is descriptive, with no causal attribution. |
| 515 | `PerformanceContextPanel.__init__` | `QPushButton` | back | Daily context |
| 517 | `PerformanceContextPanel.__init__` | `QPushButton` | full_profile | Open full profile → |
| 528 | `PerformanceContextPanel._add_heading` | `QLabel` | heading | — |
| 539 | `PerformanceContextPanel.update_today` | `QLabel` | check | — |
| 541 | `PerformanceContextPanel.update_today` | `QLabel` | title | — |
| 543 | `PerformanceContextPanel.update_today` | `QLabel` | status | — |
| 636 | `PerformanceWorkbench.__init__` | `QTabWidget` | self.tabs | — |
| 689 | `PerformanceWorkbench._heading` | `QLabel` | label | — |
| 702 | `PerformanceWorkbench._module` | `QLabel` | title_label | — |
| 706 | `PerformanceWorkbench._module` | `QLabel` | detail | — |
| 724 | `PerformanceWorkbench._pulse_cell` | `QLabel` | label | — |
| 726 | `PerformanceWorkbench._pulse_cell` | `QLabel` | value | — |
| 730 | `PerformanceWorkbench._pulse_cell` | `QLabel` | detail | — |
| 744 | `PerformanceWorkbench._build_today` | `QLabel` | self.today_kicker | SQUAD COMMAND · LOADING FIXTURE |
| 746 | `PerformanceWorkbench._build_today` | `QLabel` | title | Squad command |
| 748 | `PerformanceWorkbench._build_today` | `QLabel` | self.today_summary | Who needs attention, what changed, and what should happen next? |
| 755 | `PerformanceWorkbench._build_today` | `QPushButton` | plan_button | Open week plan |
| 757 | `PerformanceWorkbench._build_today` | `QPushButton` | session_button | ＋  Log session |
| 803 | `PerformanceWorkbench._build_today` | `QPushButton` | athlete_button | Open selected Athlete 360 → |
| 811 | `PerformanceWorkbench._build_today` | `PlotWidget` | self.today_load_plot | — |
| 817 | `PerformanceWorkbench._build_today` | `QLabel` | self.today_load_caption | Descriptive reference; not an injury predictor. |
| 823 | `PerformanceWorkbench._build_today` | `PlotWidget` | self.today_force_plot | — |
| 843 | `PerformanceWorkbench._build_today` | `QLabel` | heading | — |
| 845 | `PerformanceWorkbench._build_today` | `QLabel` | value | — |
| 855 | `PerformanceWorkbench._build_today` | `QLabel` | self.today_research_title | Loading linked study… |
| 857 | `PerformanceWorkbench._build_today` | `QLabel` | self.today_research_body | — |
| 860 | `PerformanceWorkbench._build_today` | `QLabel` | self.today_decision | — |
| 863 | `PerformanceWorkbench._build_today` | `QPushButton` | open_research | Open research → |
| 866 | `PerformanceWorkbench._build_today` | `QPushButton` | movement_button | Open bounded movement segment → |
| 869 | `PerformanceWorkbench._build_today` | `QLabel` | research_caption | LINKED STUDY · SYNTHETIC |
| 884 | `PerformanceWorkbench._build_athlete` | `QComboBox` | self.athlete_picker | — |
| 886 | `PerformanceWorkbench._build_athlete` | `QLabel` | — | Athlete |
| 888 | `PerformanceWorkbench._build_athlete` | `QPushButton` | note_button | Add practitioner note… |
| 891 | `PerformanceWorkbench._build_athlete` | `QPushButton` | back_to_today | Today |
| 895 | `PerformanceWorkbench._build_athlete` | `QSplitter` | split | — |
| 896 | `PerformanceWorkbench._build_athlete` | `QTextBrowser` | self.athlete_detail | — |
| 900 | `PerformanceWorkbench._build_athlete` | `PlotWidget` | self.athlete_trend | Observed CMJ trend · cm · weeks 1–16 |
| 903 | `PerformanceWorkbench._build_athlete` | `PlotWidget` | self.force_trace | Force–time trace · synthetic fixture |
| 911 | `PerformanceWorkbench._build_athlete` | `QLabel` | self.athlete_note | Notes are practitioner-entered operational records, not clinical records. |
| 917 | `PerformanceWorkbench._build_plan` | `QLabel` | self.plan_summary | Loading periodization… |
| 922 | `PerformanceWorkbench._build_plan` | `PlotWidget` | self.plan_chart | Observed squad training impulse · AU · 16 weeks |
| 927 | `PerformanceWorkbench._build_plan` | `QPushButton` | edit | Edit next microcycle… |
| 929 | `PerformanceWorkbench._build_plan` | `QPushButton` | publish | Publish next microcycle |
| 939 | `PerformanceWorkbench._build_monitor` | `QLabel` | self.monitor_summary | Loading weekly monitoring data… |
| 942 | `PerformanceWorkbench._build_monitor` | `QSplitter` | split | — |
| 948 | `PerformanceWorkbench._build_monitor` | `QPushButton` | button | Log training session… |
| 952 | `PerformanceWorkbench._build_monitor` | `QPushButton` | match_button | Open match & pose segment |
| 961 | `PerformanceWorkbench._build_test` | `QLabel` | self.test_summary | Loading testing windows… |
| 966 | `PerformanceWorkbench._build_test` | `QComboBox` | self.trial_picker | — |
| 969 | `PerformanceWorkbench._build_test` | `PlotWidget` | self.test_trace | CMJ force–time signal · decimated per plate |
| 973 | `PerformanceWorkbench._build_test` | `QPushButton` | action | Run and append reliability assessment |
| 981 | `PerformanceWorkbench._build_match` | `QComboBox` | self.match_player | — |
| 985 | `PerformanceWorkbench._build_match` | `QLabel` | — | Player |
| 987 | `PerformanceWorkbench._build_match` | `QSlider` | self.frame_slider | — |
| 991 | `PerformanceWorkbench._build_match` | `QLabel` | — | Frame |
| 993 | `PerformanceWorkbench._build_match` | `QLabel` | self.frame_label | 90.0 s |
| 995 | `PerformanceWorkbench._build_match` | `QPushButton` | back_to_monitor | Back to Monitor |
| 1000 | `PerformanceWorkbench._build_match` | `PlotWidget` | self.match_field | Field path · 105 × 68 m |
| 1004 | `PerformanceWorkbench._build_match` | `PlotWidget` | self.pose_plot | Sagittal pose · x–z · metres |
| 1011 | `PerformanceWorkbench._build_match` | `QLabel` | self.match_status | Pose confidence and segment-only scope will appear here. |
| 1023 | `PerformanceWorkbench._build_research` | `QTextBrowser` | self.research_summary | — |
| 1027 | `PerformanceWorkbench._build_research` | `QSplitter` | tables | — |
| 1031 | `PerformanceWorkbench._build_research` | `QPushButton` | button | Open linked research study |
| 1038 | `PerformanceWorkbench._build_report` | `QSplitter` | split | — |
| 1041 | `PerformanceWorkbench._build_report` | `QTextBrowser` | self.report_preview | — |
| 1047 | `PerformanceWorkbench._build_report` | `QPushButton` | create | Compose report… |
| 1049 | `PerformanceWorkbench._build_report` | `QPushButton` | freeze | Freeze selected report |
| 1051 | `PerformanceWorkbench._build_report` | `QPushButton` | export | Export HTML… |
| 1605 | `PerformanceWorkbench._export_report` | `getSaveFileName` | (path, _) | Export practitioner report |

## `reconciliation_review.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 20 | `_label` | `QLabel` | label | — |
| 28 | `_table` | `QTableWidget` | table | — |
| 69 | `_buttons` | `QDialogButtonBox` | buttons | — |
| 80 | `IdentityEditor.__init__` | `setWindowTitle` | — | Map athletes and sessions |
| 86 | `IdentityEditor.__init__` | `QScrollArea` | scroll | — |
| 95 | `IdentityEditor.__init__` | `QComboBox` | picker | — |
| 122 | `ContextEditor.__init__` | `setWindowTitle` | — | Confirm source context |
| 131 | `ContextEditor.__init__` | `QLineEdit` | field | — |
| 142 | `ContextEditor.__init__` | `QLineEdit` | field | — |
| 148 | `ContextEditor.__init__` | `QPushButton` | reference | Use IDs from reference |
| 174 | `ReconciliationReview.__init__` | `QPushButton` | self.choose | Choose follow-up file… |
| 176 | `ReconciliationReview.__init__` | `QComboBox` | self.history | — |
| 177 | `ReconciliationReview.__init__` | `setAccessibleName` | — | Reconciliation proposal and decision history |
| 181 | `ReconciliationReview.__init__` | `QPushButton` | refresh | Refresh |
| 190 | `ReconciliationReview.__init__` | `setAccessibleName` | — | Reconciliation status |
| 192 | `ReconciliationReview.__init__` | `setAccessibleName` | — | Source rights, protocol, instrument and QC |
| 196 | `ReconciliationReview.__init__` | `QTabWidget` | self.tables | — |
| 210 | `ReconciliationReview.__init__` | `QPushButton` | self.mapping | Edit column mapping… |
| 212 | `ReconciliationReview.__init__` | `QPushButton` | self.identity | Map identities… |
| 214 | `ReconciliationReview.__init__` | `QPushButton` | self.declare | Confirm source context… |
| 222 | `ReconciliationReview.__init__` | `QLineEdit` | self.reviewer | — |
| 223 | `ReconciliationReview.__init__` | `setAccessibleName` | — | Decision reviewer |
| 227 | `ReconciliationReview.__init__` | `QLineEdit` | self.reason | — |
| 228 | `ReconciliationReview.__init__` | `setAccessibleName` | — | Reason for reconciliation decision |
| 231 | `ReconciliationReview.__init__` | `QPushButton` | self.approve | &Approve |
| 232 | `ReconciliationReview.__init__` | `QPushButton` | self.reject | &Reject |
| 233 | `ReconciliationReview.__init__` | `QPushButton` | self.quarantine | &Quarantine |
| 234 | `ReconciliationReview.__init__` | `QPushButton` | self.analyze | Open revision in Analysis |
| 253 | `ReconciliationReview._choose` | `getOpenFileName` | (path, _) | Choose follow-up file |

## `research_history.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 27 | `ResearchHistoryPanel.__init__` | `QLabel` | self.binding | Open a workspace to inspect frozen history. |
| 29 | `ResearchHistoryPanel.__init__` | `setAccessibleName` | — | Frozen history context |
| 32 | `ResearchHistoryPanel.__init__` | `QComboBox` | self.kind | — |
| 35 | `ResearchHistoryPanel.__init__` | `QCheckBox` | self.all_scopes | Include all athletes and cohort |
| 39 | `ResearchHistoryPanel.__init__` | `QPushButton` | refresh | Refresh history |
| 42 | `ResearchHistoryPanel.__init__` | `QPushButton` | self.export | Export selected frozen report… |
| 45 | `ResearchHistoryPanel.__init__` | `QPushButton` | compose | Write report… |
| 48 | `ResearchHistoryPanel.__init__` | `QPushButton` | self.open_context | Open selected contextual view… |
| 53 | `ResearchHistoryPanel.__init__` | `QComboBox` | self.picker | — |
| 54 | `ResearchHistoryPanel.__init__` | `setAccessibleName` | — | Frozen research record |
| 57 | `ResearchHistoryPanel.__init__` | `QTabWidget` | self.tabs | — |
| 58 | `ResearchHistoryPanel.__init__` | `QTextBrowser` | self.preview | — |
| 59 | `ResearchHistoryPanel.__init__` | `setAccessibleName` | — | Frozen research content |
| 60 | `ResearchHistoryPanel.__init__` | `addTab` | — | Summary / report |
| 61 | `ResearchHistoryPanel.__init__` | `ScientificFigureWidget` | self.figure | — |
| 62 | `ResearchHistoryPanel.__init__` | `addTab` | — | Figure |
| 63 | `ResearchHistoryPanel.__init__` | `QTextBrowser` | self.provenance | — |
| 64 | `ResearchHistoryPanel.__init__` | `addTab` | — | Diagnostics and provenance |
| 184 | `ResearchHistoryPanel.export_report` | `getSaveFileName` | (path, _) | Export frozen report |

## `source_overview.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 26 | `SourceOverview.__init__` | `QLabel` | title | Sources & quality |
| 29 | `SourceOverview.__init__` | `QPushButton` | self.import_button | Add measurements… |
| 39 | `SourceOverview.__init__` | `QLabel` | name | Measurements |
| 49 | `SourceOverview.__init__` | `QPushButton` | self.measurements_button | Browse measurement rows… |
| 51 | `SourceOverview.__init__` | `QPushButton` | self.explore_button | Explore signals… |
| 53 | `SourceOverview.__init__` | `QPushButton` | self.qc_button | Review QC receipts… |
| 65 | `SourceOverview.__init__` | `QLabel` | name | Training & wellness |

## `squad_view.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 115 | `SquadBoard.__init__` | `QLabel` | self.title | Open a workspace with data to see the squad. |
| 117 | `SquadBoard.__init__` | `QComboBox` | self.group_picker | — |
| 118 | `SquadBoard.__init__` | `setAccessibleName` | — | Group athletes by |
| 120 | `SquadBoard.__init__` | `QComboBox` | self.metric_picker | — |
| 121 | `SquadBoard.__init__` | `setAccessibleName` | — | Metric shown on tiles |
| 123 | `SquadBoard.__init__` | `QPushButton` | self.rules_button | Flag rules… |
| 125 | `SquadBoard.__init__` | `QPushButton` | self.simulate_button | Hypothetical scenarios… |
| 130 | `SquadBoard.__init__` | `QLineEdit` | self.search | — |
| 132 | `SquadBoard.__init__` | `setAccessibleName` | — | Search participants |
| 135 | `SquadBoard.__init__` | `QLabel` | — | Show |
| 137 | `SquadBoard.__init__` | `QLabel` | — | Group by |
| 142 | `SquadBoard.__init__` | `QLabel` | self.note | — |
| 146 | `SquadBoard.__init__` | `QScrollArea` | self.scroll | — |
| 197 | `SquadBoard._loaded` | `QLabel` | header | — |
| 237 | `RulesDialog.__init__` | `setWindowTitle` | — | Flag rules |
| 242 | `RulesDialog.__init__` | `QListWidget` | self.list | — |
| 243 | `RulesDialog.__init__` | `setAccessibleName` | — | Flag rules |
| 245 | `RulesDialog.__init__` | `QPushButton` | — | Delete rule |
| 245 | `RulesDialog.__init__` | `QPushButton` | — | New rule |
| 254 | `RulesDialog.__init__` | `QLineEdit` | — | — |
| 254 | `RulesDialog.__init__` | `QLineEdit` | — | — |
| 256 | `RulesDialog.__init__` | `QComboBox` | — | — |
| 256 | `RulesDialog.__init__` | `QComboBox` | — | — |
| 273 | `RulesDialog.__init__` | `QLabel` | self.condition_note | Record windows count valid session means, not days. Thresholds are researcher-defined and are not validated risk limits. |
| 277 | `RulesDialog.__init__` | `QPushButton` | — | Add condition |
| 277 | `RulesDialog.__init__` | `QPushButton` | — | Remove condition |
| 284 | `RulesDialog.__init__` | `QLabel` | self.error | — |
| 287 | `RulesDialog.__init__` | `QDialogButtonBox` | buttons | — |
| 318 | `RulesDialog._add_condition` | `QComboBox` | picker | — |
| 391 | `SimulationDialog.__init__` | `QTabWidget` | self.tabs | — |
| 393 | `SimulationDialog.__init__` | `QScrollArea` | setup_scroll | — |
| 397 | `SimulationDialog.__init__` | `addTab` | — | Assumptions |
| 398 | `SimulationDialog.__init__` | `addTab` | — | Results |
| 401 | `SimulationDialog.__init__` | `QLabel` | banner | &lt;b&gt;HYPOTHETICAL · NOT QUALIFIED&lt;/b&gt; · Save researcher-defined assumptions. Numerical forecasts are unavailable pending RES-619/RES-590 qualification. Definitions are not evidence. |
| 406 | `SimulationDialog.__init__` | `QLineEdit` | self.name | Scenario |
| 407 | `SimulationDialog.__init__` | `QSpinBox` | self.steps | — |
| 410 | `SimulationDialog.__init__` | `QComboBox` | self.outcome | — |
| 417 | `SimulationDialog.__init__` | `QDoubleSpinBox` | box | — |
| 424 | `SimulationDialog.__init__` | `QLabel` | — | — |
| 431 | `SimulationDialog.__init__` | `QLabel` | — | Drivers: how each metric changes per step and the outcome % change you assume per 1% driver change |
| 437 | `SimulationDialog.__init__` | `QPushButton` | — | Add driver |
| 437 | `SimulationDialog.__init__` | `QPushButton` | — | Remove driver |
| 440 | `SimulationDialog.__init__` | `QPushButton` | — | Save scenario |
| 440 | `SimulationDialog.__init__` | `QPushButton` | — | Validate definition |
| 453 | `SimulationDialog.__init__` | `QLabel` | self.summary | — |
| 460 | `SimulationDialog._add_driver` | `QComboBox` | picker | — |
| 511 | `AthletePage.__init__` | `QPushButton` | back | ← Squad |
| 513 | `AthletePage.__init__` | `QLabel` | self.header | — |
| 515 | `AthletePage.__init__` | `QPushButton` | self.simulate_button | Scenarios… |
| 521 | `AthletePage.__init__` | `QTabWidget` | self.research_tabs | — |
| 524 | `AthletePage.__init__` | `addTab` | — | Longitudinal measurements |
| 525 | `AthletePage.__init__` | `addTab` | — | Scientific investigations |
| 531 | `AthletePage.__init__` | `QTextBrowser` | self.flags | — |
| 534 | `AthletePage.__init__` | `ScientificFigureWidget` | self.figure | — |
| 540 | `AthletePage.__init__` | `QLabel` | — | Investigations |
| 541 | `AthletePage.__init__` | `QComboBox` | self.branch_picker | — |
| 542 | `AthletePage.__init__` | `setAccessibleName` | — | Individual research branches |
| 544 | `AthletePage.__init__` | `QPushButton` | new_branch | New investigation… |
| 567 | `AthletePage.set_athlete` | `QLabel` | card | — |
| 610 | `AthletePage.new_branch` | `getText` | (title, accepted) | New branch |
| 645 | `EventsFeed.__init__` | `QLabel` | self.title | Open a workspace with data to see its events. |
| 646 | `EventsFeed.__init__` | `QComboBox` | self.filter | — |
| 647 | `EventsFeed.__init__` | `setAccessibleName` | — | Filter events |
| 651 | `EventsFeed.__init__` | `QPushButton` | refresh | Refresh |
| 657 | `EventsFeed.__init__` | `QScrollArea` | self.scroll | — |
| 690 | `EventsFeed._card` | `QLabel` | text | — |
| 695 | `EventsFeed._card` | `QPushButton` | open_button | Open athlete |
| 699 | `EventsFeed._card` | `QPushButton` | follow | — |
| 715 | `EventsFeed._render` | `QLabel` | — | &lt;b&gt;Needs attention&lt;/b&gt; · your concern rules fired and there is no follow-up branch yet |
| 718 | `EventsFeed._render` | `QLabel` | — | &lt;b&gt;Timeline&lt;/b&gt; |
| 722 | `EventsFeed._render` | `QLabel` | — | Nothing here yet. |

## `study_home.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 37 | `StudyInstrument.__init__` | `setAccessibleName` | — | Rotatable study map |
| 199 | `StudyHome.__init__` | `QLabel` | self.title | Open a study |
| 205 | `StudyHome.__init__` | `QLabel` | self.summary | — |
| 213 | `StudyHome.__init__` | `StudyInstrument` | self.instrument | — |
| 220 | `StudyHome.__init__` | `QPushButton` | button | — |
| 231 | `StudyHome.__init__` | `QPushButton` | self.open_button | Open study… |
| 232 | `StudyHome.__init__` | `QPushButton` | self.new_button | New study… |
| 233 | `StudyHome.__init__` | `QPushButton` | self.import_button | Add measurements… |

## `theme.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 123 | `chip` | `QLabel` | label | — |

## `training_context.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 44 | `TrainingContextPanel.__init__` | `QComboBox` | self.scope | — |
| 45 | `TrainingContextPanel.__init__` | `setAccessibleName` | — | Athlete or cohort |
| 49 | `TrainingContextPanel.__init__` | `QLabel` | self.mode | — |
| 51 | `TrainingContextPanel.__init__` | `setAccessibleName` | — | Investigation mode and data revision |
| 53 | `TrainingContextPanel.__init__` | `QLabel` | self.pinned_scope | — |
| 55 | `TrainingContextPanel.__init__` | `QComboBox` | self.first | — |
| 56 | `TrainingContextPanel.__init__` | `QComboBox` | self.second | — |
| 64 | `TrainingContextPanel.__init__` | `QLabel` | — | Assessments |
| 66 | `TrainingContextPanel.__init__` | `QLabel` | — | → |
| 68 | `TrainingContextPanel.__init__` | `QLabel` | self.pinned_dates | — |
| 69 | `TrainingContextPanel.__init__` | `QPushButton` | self.add_source | Import context… |
| 71 | `TrainingContextPanel.__init__` | `QPushButton` | self.open_view | Frozen history… |
| 73 | `TrainingContextPanel.__init__` | `QPushButton` | self.live_view | Return to live |
| 82 | `TrainingContextPanel.__init__` | `QLabel` | self.finding | — |
| 90 | `TrainingContextPanel.__init__` | `QPushButton` | self.compare_button | Compare assessments |
| 101 | `TrainingContextPanel.__init__` | `QLabel` | title | Training and testing timeline |
| 105 | `TrainingContextPanel.__init__` | `QLabel` | — | ◆ Assessment    ▲ Modified    × Missing or unusable |
| 107 | `TrainingContextPanel.__init__` | `InvestigationChart` | self.chart | — |
| 109 | `TrainingContextPanel.__init__` | `PlotWidget` | self.values_chart | — |
| 110 | `TrainingContextPanel.__init__` | `setAccessibleName` | — | Dated values for the selected athlete |
| 125 | `TrainingContextPanel.__init__` | `QPushButton` | self.research_actions | Research actions |
| 126 | `TrainingContextPanel.__init__` | `QMenu` | research | — |
| 132 | `TrainingContextPanel.__init__` | `QPushButton` | self.configure | Timeline options |
| 133 | `TrainingContextPanel.__init__` | `QMenu` | options | — |
| 134 | `TrainingContextPanel.__init__` | `addAction` | self.configure_action | Timeline settings… |
| 135 | `TrainingContextPanel.__init__` | `QPushButton` | self.save_view | Freeze current view… |
| 138 | `TrainingContextPanel.__init__` | `addAction` | self.freeze_action | Freeze current view… |
| 139 | `TrainingContextPanel.__init__` | `addAction` | self.method_details | Comparison details… |
| 146 | `TrainingContextPanel.__init__` | `QDialog` | self.settings_dialog | — |
| 147 | `TrainingContextPanel.__init__` | `setWindowTitle` | — | Timeline settings |
| 149 | `TrainingContextPanel.__init__` | `QComboBox` | self.kind | — |
| 153 | `TrainingContextPanel.__init__` | `QComboBox` | self.outcome | — |
| 154 | `TrainingContextPanel.__init__` | `QComboBox` | self.source_version | — |
| 155 | `TrainingContextPanel.__init__` | `QComboBox` | self.plots | — |
| 156 | `TrainingContextPanel.__init__` | `QLineEdit` | self.date_from | — |
| 157 | `TrainingContextPanel.__init__` | `QLineEdit` | self.date_to | — |
| 158 | `TrainingContextPanel.__init__` | `QLineEdit` | self.week_one | — |
| 159 | `TrainingContextPanel.__init__` | `QLineEdit` | self.offset | +00:00 |
| 170 | `TrainingContextPanel.__init__` | `QDialogButtonBox` | buttons | — |
| 649 | `TrainingContextPanel._comparison_details` | `QDialog` | dialog | — |
| 650 | `TrainingContextPanel._comparison_details` | `setWindowTitle` | — | Comparison details and limitations |
| 652 | `TrainingContextPanel._comparison_details` | `QTextBrowser` | text | — |
| 663 | `TrainingContextPanel._comparison_details` | `QDialogButtonBox` | buttons | — |
| 672 | `TrainingContextPanel._freeze` | `getText` | (title, confirmed) | Freeze investigation |
| 696 | `TrainingContextPanel._open.choose` | `getItem` | (selected, confirmed) | Frozen investigations |

## `workbench/data_pane.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 282 | `_Collapsible.__init__` | `QToolButton` | self.toggle | — |
| 306 | `_table` | `QTableView` | view | — |
| 352 | `DataPane.__init__` | `QComboBox` | self.table_combo | — |
| 353 | `DataPane.__init__` | `setAccessibleName` | — | Table |
| 367 | `DataPane.__init__` | `QPushButton` | button | — |
| 378 | `DataPane.__init__` | `QComboBox` | self.value_combo | — |
| 379 | `DataPane.__init__` | `setAccessibleName` | — | Value shown by athlete |
| 382 | `DataPane.__init__` | `setAccessibleName` | — | By athlete table |
| 383 | `DataPane.__init__` | `QLabel` | self.athlete_note | — |
| 391 | `DataPane.__init__` | `QLabel` | — | Value |
| 406 | `DataPane.__init__` | `setAccessibleName` | — | Rows table |
| 407 | `DataPane.__init__` | `setAccessibleName` | — | Variables table |
| 413 | `DataPane.__init__` | `QLabel` | self.empty | Open a dataset or study to see its data. |
| 417 | `DataPane.__init__` | `QStackedWidget` | self.stack | — |
| 422 | `DataPane.__init__` | `QLabel` | self.footer | — |
| 424 | `DataPane.__init__` | `setAccessibleName` | — | Dataset summary |

## `workbench/interactive.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 126 | `_label` | `QLabel` | label | — |
| 164 | `TrajectoryPlot.__init__` | `PlotWidget` | self.plot | — |
| 165 | `TrajectoryPlot.__init__` | `setAccessibleName` | — | Trajectory plot |
| 383 | `Trajectory3D.__init__` | `QPushButton` | button | — |
| 393 | `Trajectory3D.__init__` | `QLabel` | — | Depth |
| 394 | `Trajectory3D.__init__` | `QComboBox` | self.depth_combo | — |
| 395 | `Trajectory3D.__init__` | `setAccessibleName` | — | Depth axis |
| 402 | `Trajectory3D.__init__` | `QPushButton` | button | — |
| 407 | `Trajectory3D.__init__` | `QPushButton` | reset | Reset |
| 431 | `Trajectory3D.__init__` | `setAccessibleName` | — | 3D trajectories view |

## `workbench/options_pane.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 167 | `RoleSlot.__init__` | `QLabel` | self.caption | — |
| 267 | `OptionsPane.__init__` | `QLabel` | self.method_line | — |
| 269 | `OptionsPane.__init__` | `setAccessibleName` | — | Method qualification |
| 275 | `OptionsPane.__init__` | `setAccessibleName` | — | Variables |
| 285 | `OptionsPane.__init__` | `QPushButton` | self.assign_button | Assign  ▸ |
| 287 | `OptionsPane.__init__` | `setAccessibleName` | — | Assign selected variable to the active role |
| 290 | `OptionsPane.__init__` | `QShortcut` | — | — |
| 294 | `OptionsPane.__init__` | `QLabel` | caption | Variables |
| 312 | `OptionsPane.__init__` | `QLabel` | self.issues_label | — |
| 314 | `OptionsPane.__init__` | `setAccessibleName` | — | Validation issues |
| 316 | `OptionsPane.__init__` | `QLabel` | self.ready_label | — |
| 323 | `OptionsPane.__init__` | `QLabel` | self.placeholder | Choose an analysis in the ribbon. |
| 339 | `OptionsPane.__init__` | `QScrollArea` | scroll | — |
| 416 | `OptionsPane._rebuild` | `QLabel` | note | This analysis has no options beyond the variable roles. |
| 436 | `OptionsPane._section` | `QLabel` | fixed | — |
| 452 | `OptionsPane._option_widget` | `QCheckBox` | w | — |
| 455 | `OptionsPane._option_widget` | `QSpinBox` | w | — |
| 461 | `OptionsPane._option_widget` | `QDoubleSpinBox` | w | — |
| 467 | `OptionsPane._option_widget` | `QLineEdit` | w | — |

## `workbench/palette.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 43 | `CommandPalette.__init__` | `setAccessibleName` | — | Command palette |
| 47 | `CommandPalette.__init__` | `QLineEdit` | self.input | — |
| 49 | `CommandPalette.__init__` | `setAccessibleName` | — | Search commands |
| 55 | `CommandPalette.__init__` | `QListView` | self.list | — |
| 57 | `CommandPalette.__init__` | `setAccessibleName` | — | Matching commands |
| 62 | `CommandPalette.__init__` | `QLabel` | hint | ↑ ↓ move  ·  ↵ run  ·  Esc close |

## `workbench/results.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 118 | `_label` | `QLabel` | label | — |
| 213 | `ResultBlock.set_footer` | `QPushButton` | self.promote_button | Promote to evidence |
| 255 | `ResultsDocument.__init__` | `setAccessibleName` | — | Results document |
| 333 | `ResultsDocument.show_unavailable` | `ResultBlock` | block | — |
| 372 | `ResultsDocument.set_trajectory_mode` | `Trajectory3D` | self.trajectory_3d | — |
| 485 | `ResultsDocument._mixed_model` | `ResultBlock` | block | Linear Mixed Model |
| 540 | `ResultsDocument._mixed_model` | `ResultBlock` | figure_block | Estimated change by occasion |
| 552 | `ResultsDocument._mixed_model` | `ResultBlock` | checks | Assumption checks |
| 585 | `ResultsDocument._trajectories` | `ResultBlock` | block | Trajectories |
| 595 | `ResultsDocument._trajectories` | `QPushButton` | button | — |
| 605 | `ResultsDocument._trajectories` | `QStackedWidget` | block.trajectory_stack | — |
| 607 | `ResultsDocument._trajectories` | `TrajectoryPlot` | self.trajectory_plot | — |
| 633 | `ResultsDocument._reliability` | `ResultBlock` | block | Reliability |
| 681 | `ResultsDocument._reliability` | `ResultBlock` | figure_block | ICC and trial-to-trial variation |
| 690 | `ResultsDocument._generic` | `ResultBlock` | block | — |

## `workbench/shell.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 105 | `_Pane.__init__` | `QLabel` | self.title | — |
| 164 | `WorkbenchShell._build_actions` | `QAction` | action | — |
| 172 | `WorkbenchShell._build_actions` | `QAction` | self.action_run | Run analysis |
| 175 | `WorkbenchShell._build_actions` | `QAction` | self.action_add_to_report | Add to report |
| 176 | `WorkbenchShell._build_actions` | `QAction` | self.action_promote | Promote to evidence |
| 178 | `WorkbenchShell._build_actions` | `QAction` | self.action_export | Export… |
| 182 | `WorkbenchShell._build_actions` | `QAction` | action | — |
| 186 | `WorkbenchShell._build_actions` | `QAction` | action | — |
| 191 | `WorkbenchShell._build_ribbon` | `QToolBar` | self.ribbon | Analyses |
| 193 | `WorkbenchShell._build_ribbon` | `setAccessibleName` | — | Analysis ribbon |
| 210 | `WorkbenchShell._build_ribbon` | `setAccessibleName` | — | More ribbon commands |
| 214 | `WorkbenchShell._build_ribbon` | `QPushButton` | self.palette_button | Search commands…      Ctrl K |
| 216 | `WorkbenchShell._build_ribbon` | `setAccessibleName` | — | Search commands (Ctrl+K) |
| 224 | `WorkbenchShell._build_ribbon` | `QLabel` | self.run_dot | — |
| 226 | `WorkbenchShell._build_ribbon` | `QLabel` | self.run_label | — |
| 237 | `WorkbenchShell._build_ribbon` | `QPushButton` | button | — |
| 252 | `WorkbenchShell._build_panes` | `QLabel` | self.context_label | Select a project, study or dataset |
| 254 | `WorkbenchShell._build_panes` | `setAccessibleName` | — | Open research context |
| 265 | `WorkbenchShell._build_panes` | `QPushButton` | self.run_button | Run |
| 266 | `WorkbenchShell._build_panes` | `setAccessibleName` | — | Run analysis |
| 271 | `WorkbenchShell._build_panes` | `QPushButton` | button | — |
| 281 | `WorkbenchShell._build_panes` | `QLabel` | stale_label | ⚠  &lt;b&gt;Specification changed.&lt;/b&gt; These results are for the previous specification. |
| 284 | `WorkbenchShell._build_panes` | `QPushButton` | run | ▶ Run  ·  Ctrl ↵ |
| 286 | `WorkbenchShell._build_panes` | `setAccessibleName` | — | Run analysis |
| 294 | `WorkbenchShell._build_panes` | `QSplitter` | self.splitter | — |
| 296 | `WorkbenchShell._build_panes` | `setAccessibleName` | — | Workbench panes |
| 323 | `WorkbenchShell._build_syntax_bar` | `QLabel` | caption | SYNTAX |
| 325 | `WorkbenchShell._build_syntax_bar` | `QPlainTextEdit` | self.syntax | — |
| 327 | `WorkbenchShell._build_syntax_bar` | `setAccessibleName` | — | Python syntax equivalent |
| 333 | `WorkbenchShell._build_syntax_bar` | `QPushButton` | self.copy_button | Copy |
| 334 | `WorkbenchShell._build_syntax_bar` | `setAccessibleName` | — | Copy syntax |
| 353 | `WorkbenchShell._build_status_items` | `QLabel` | self.app_status | Starting |
| 354 | `WorkbenchShell._build_status_items` | `setAccessibleName` | — | Application status |
| 361 | `WorkbenchShell._build_status_items` | `QLabel` | self.provenance_label | — |
| 362 | `WorkbenchShell._build_status_items` | `setAccessibleName` | — | Scientific provenance |
| 370 | `WorkbenchShell._build_toast` | `QLabel` | self.toast | — |
| 372 | `WorkbenchShell._build_toast` | `setAccessibleName` | — | Notification |
| 380 | `WorkbenchShell._shortcuts` | `QShortcut` | — | — |
| 381 | `WorkbenchShell._shortcuts` | `QShortcut` | — | — |
| 382 | `WorkbenchShell._shortcuts` | `QShortcut` | — | — |
| 386 | `WorkbenchShell._empty` | `QLabel` | label | — |

## `workbench/signals_view.py`

| Line | Scope | Qt control or entry | Binding | Literal text |
| ---: | --- | --- | --- | --- |
| 66 | `SignalsView.__init__` | `QSplitter` | splitter | — |
| 73 | `SignalsView.__init__` | `QComboBox` | self.subject_filter | — |
| 74 | `SignalsView.__init__` | `setAccessibleName` | — | Filter trials by athlete |
| 75 | `SignalsView.__init__` | `QComboBox` | self.activity_filter | — |
| 76 | `SignalsView.__init__` | `setAccessibleName` | — | Filter trials by activity |
| 81 | `SignalsView.__init__` | `QListWidget` | self.trial_list | — |
| 82 | `SignalsView.__init__` | `setAccessibleName` | — | Signal trials |
| 85 | `SignalsView.__init__` | `QLabel` | self.count_label | — |
| 94 | `SignalsView.__init__` | `QLabel` | self.title | Choose a trial |
| 100 | `SignalsView.__init__` | `QLabel` | — | Channels |
| 103 | `SignalsView.__init__` | `QCheckBox` | self.reference_box | Recorded baseline / peak |
| 107 | `SignalsView.__init__` | `QPushButton` | reset | Reset zoom |
| 111 | `SignalsView.__init__` | `PlotWidget` | self.plot | — |
| 112 | `SignalsView.__init__` | `setAccessibleName` | — | Signal waveform |
| 115 | `SignalsView.__init__` | `QLabel` | self.detail | — |
| 196 | `SignalsView._channels` | `QCheckBox` | box | — |
