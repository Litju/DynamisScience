"""Native Qt palette matching the approved Dynamis Performance OS system."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(application: QApplication) -> None:
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 9))
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#0a1016"),
        (QPalette.ColorRole.WindowText, "#e3edf2"),
        (QPalette.ColorRole.Base, "#101922"),
        (QPalette.ColorRole.AlternateBase, "#0d171f"),
        (QPalette.ColorRole.ToolTipBase, "#15212b"),
        (QPalette.ColorRole.ToolTipText, "#e3edf2"),
        (QPalette.ColorRole.Text, "#e3edf2"),
        (QPalette.ColorRole.Button, "#101922"),
        (QPalette.ColorRole.ButtonText, "#e3edf2"),
        (QPalette.ColorRole.Highlight, "#273c47"),
        (QPalette.ColorRole.HighlightedText, "#f1f6f8"),
        (QPalette.ColorRole.Link, "#5fd4e8"),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#566873"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#566873"))
    application.setPalette(palette)
    application.setStyleSheet(
        """
        QMainWindow, QDialog { background: #0a1016; color: #e3edf2; }
        QWidget { color: #e3edf2; selection-background-color: #273c47; }
        QMenuBar { background: #071016; color: #b2c0c9; border-bottom: 1px solid #23333e; padding: 2px 6px; }
        QMenuBar::item { padding: 4px 8px; background: transparent; }
        QMenuBar::item:selected, QMenu::item:selected { background: #15212b; color: #f1f6f8; }
        QMenu { background: #101922; border: 1px solid #304552; padding: 4px; }
        QMenu::item { padding: 5px 22px 5px 8px; }
        QToolBar { background: #071016; border: 0; spacing: 6px; padding: 0 12px; }
        QToolBar::separator { background: #23333e; width: 1px; margin: 6px; }
        QDockWidget { color: #b2c0c9; font-size: 9px; }
        QDockWidget::title { background: #0a151b; padding: 7px 10px; border-bottom: 1px solid #23333e; }
        QWidget#ResearchHeader { background: #0d171f; border-bottom: 1px solid #23333e; min-height: 38px; }
        QToolBar#PerformanceToolbar { background: #071016; border-bottom: 1px solid #23333e; min-height: 48px; max-height: 48px; padding: 0; }
        QWidget#PerformanceHeader { background: #071016; }
        QToolButton#PerformanceBrandMark { min-width: 23px; max-width: 23px; min-height: 23px; max-height: 23px; padding: 0; border: 1px solid rgba(200,243,107,130); border-radius: 3px; color: #c8f36b; background: rgba(200,243,107,24); font-family: Consolas; font-size: 11px; }
        QLabel#PerformanceBrandName { color: #e3edf2; font-size: 11px; font-weight: 600; }
        QLabel#PerformanceBrandDescriptor, QLabel#PerformanceRoleLabel { color: #566873; font-family: Consolas; font-size: 7px; letter-spacing: 1px; }
        QLabel#PerformanceClub { color: #e3edf2; font-size: 9px; font-weight: 500; }
        QLabel#PerformanceMuted, QLabel#PerformanceRole { color: #7f919d; font-size: 9px; }
        QLabel#PerformanceSeason { color: #5fd4e8; border: 1px solid rgba(95,212,232,70); padding: 4px 7px; font-family: Consolas; font-size: 8px; }
        QLineEdit#PerformanceSearch { background: #101922; border: 1px solid #23333e; color: #7f919d; min-height: 23px; padding: 2px 8px; font-size: 9px; }
        QLabel#PerformanceAvatar { min-width: 25px; max-width: 25px; min-height: 25px; max-height: 25px; qproperty-alignment: AlignCenter; border: 1px solid #304552; border-radius: 12px; background: #1a2a35; color: #b2c0c9; font-family: Consolas; font-size: 8px; }
        QWidget#PerformanceRail { background: #0a151b; border-right: 1px solid #23333e; }
        QLabel#PerformanceCrest { min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; qproperty-alignment: AlignCenter; border: 1px solid #304552; border-radius: 3px; background: #101922; color: #c8f36b; font-family: Consolas; font-size: 9px; }
        QLabel#PerformanceRailClub { color: #e3edf2; font-size: 9px; font-weight: 600; }
        QLabel#PerformanceRailMeta, QLabel#PerformanceRailNote { color: #566873; font-size: 8px; }
        QLabel#PerformanceRailGroup { color: #566873; font-family: Consolas; font-size: 7px; letter-spacing: 1px; padding: 3px 6px; }
        QPushButton#PerformanceRailItem { text-align: left; padding: 4px 6px; min-height: 22px; border: 0; border-left: 2px solid transparent; background: transparent; color: #b2c0c9; }
        QPushButton#PerformanceRailItem:hover { background: #101922; color: #e3edf2; }
        QPushButton#PerformanceRailItem:checked { background: #15212b; border-left-color: #c8f36b; color: #e3edf2; }
        QLabel#PerformanceRailItemName { color: inherit; font-size: 9px; }
        QLabel#PerformanceRailTag { color: #566873; font-family: Consolas; font-size: 7px; }
        QFrame#PerformanceSquadFooter { border-top: 1px solid #23333e; background: transparent; }
        QLabel#PerformanceAvailability { color: #c8f36b; font-family: Consolas; font-size: 17px; }
        QFrame#PerformanceAvailabilitySegment { background: #c8f36b; border: 0; }
        QWidget#PerformanceContextPanel { background: #0a151b; }
        QLabel#PerformanceContextHeading { color: #566873; font-family: Consolas; font-size: 7px; letter-spacing: 1px; padding: 9px 0 5px; }
        QLabel#PerformanceChecklistLabel { color: #b2c0c9; font-size: 8px; }
        QLabel#PerformanceChecklistStatus { color: #c8f36b; font-family: Consolas; font-size: 7px; }
        QLabel#PerformanceChecklistDone { color: #c8f36b; font-size: 9px; }
        QLabel#PerformanceContextMuted, QLabel#PerformanceContextFooter { color: #566873; font-size: 7px; }
        QLabel#PerformanceContextMono { color: #7f919d; font-family: Consolas; font-size: 8px; line-height: 1.35; padding: 2px 0 8px; }
        QLabel#PerformanceCalloutWarning { color: #ef6b63; background: rgba(239,107,99,12); border: 1px solid rgba(239,107,99,75); padding: 6px; font-size: 8px; margin-top: 6px; }
        QLabel#PerformanceCalloutInfo { color: #5fd4e8; background: rgba(95,212,232,10); border: 1px solid rgba(95,212,232,65); padding: 6px; font-size: 8px; margin-top: 6px; }
        QWidget#PerformancePage { background: #0a1016; }
        QFrame#PerformancePulse { background: #101922; border: 1px solid #23333e; }
        QFrame#PerformancePulseCell { background: transparent; border-right: 1px solid #23333e; }
        QFrame#PerformanceMiniMetric { background: #0d171f; border: 1px solid #23333e; }
        QLabel#PerformanceMiniMetricValue { color: #e3edf2; font-family: Consolas; font-size: 9px; }
        QLabel#PerformanceMetricLabel { color: #566873; font-family: Consolas; font-size: 7px; letter-spacing: .5px; }
        QLabel#PerformanceMetricValue { color: #e3edf2; font-family: Consolas; font-size: 18px; }
        QLabel#PerformanceMetricNote { color: #7f919d; font-size: 7px; }
        QFrame#PerformanceModule { background: #101922; border: 1px solid #23333e; }
        QLabel#PerformanceModuleTitle { color: #e3edf2; font-size: 9px; font-weight: 600; }
        QLabel#PerformanceModuleNote { color: #566873; font-family: Consolas; font-size: 7px; }
        QLabel#PerformanceKicker { color: #c8f36b; font-family: Consolas; font-size: 7px; letter-spacing: 1px; }
        QLabel#PerformancePageTitle { color: #f1f6f8; font-size: 21px; font-weight: 600; }
        QLabel#PerformancePageDescription { color: #7f919d; font-size: 8px; }
        QLabel#PerformanceResearchTitle { color: #e3edf2; font-size: 10px; font-weight: 600; }
        QLabel#PerformanceDecisionCard { color: #b2c0c9; background: #0d171f; border: 1px solid #23333e; padding: 6px; font-size: 8px; }
        QLabel#PerformanceAthleteIdentity { color: #c8f36b; font-family: Consolas; font-size: 14px; font-weight: 600; }
        QPushButton#PerformancePrimaryButton { background: #c8f36b; color: #0c1510; border-color: #c8f36b; font-weight: 600; }
        QPushButton#PerformancePrimaryButton:hover { background: #dcff8f; border-color: #dcff8f; }
        QPushButton#PerformanceLinkButton { border: 0; background: transparent; color: #5fd4e8; text-align: left; padding: 2px 0; min-height: 16px; }
        QPushButton#PerformanceLinkButton:hover { color: #9ae7f2; }
        QTreeWidget, QListWidget, QTableView, QTextBrowser, QPlainTextEdit, QLineEdit,
        QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTableWidget {
            background: #101922; color: #e3edf2; border: 1px solid #23333e;
            selection-background-color: #20333e; selection-color: #f1f6f8;
        }
        QTreeWidget, QListWidget { background: #0a151b; border: 0; outline: 0; }
        QTreeWidget::item, QListWidget::item { min-height: 27px; padding: 2px 5px; }
        QTreeWidget::item:selected, QListWidget::item:selected { background: #15212b; border-left: 2px solid #c8f36b; }
        QHeaderView::section { background: #101922; color: #7f919d; border: 0; border-bottom: 1px solid #23333e; padding: 6px 8px; font-size: 8px; }
        QTableView { gridline-color: #23333e; alternate-background-color: #0d171f; border: 1px solid #23333e; }
        QTableView#PerformanceAttentionTable { font-size: 8px; }
        QTableView::item { padding: 3px 6px; border-bottom: 1px solid rgba(35, 51, 62, 150); }
        QPushButton { background: #101922; color: #e3edf2; border: 1px solid #304552; border-radius: 3px; padding: 5px 9px; min-height: 20px; }
        QPushButton:hover { background: #15212b; border-color: #456071; }
        QPushButton:pressed { background: #1a2a35; }
        QPushButton:focus { border-color: #c8f36b; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit { padding: 4px 6px; min-height: 21px; }
        QComboBox::drop-down { border: 0; width: 18px; }
        QTabWidget::pane { border: 1px solid #23333e; background: #0a1016; }
        QTabBar::tab { background: #0d171f; color: #7f919d; border: 1px solid #23333e; padding: 6px 10px; margin-right: 2px; }
        QTabBar::tab:selected { background: #15212b; color: #e3edf2; border-bottom: 2px solid #c8f36b; }
        QProgressBar { background: #101922; border: 1px solid #23333e; border-radius: 2px; text-align: center; }
        QProgressBar::chunk { background: #c8f36b; }
        QStatusBar { background: #071016; color: #7f919d; border-top: 1px solid #23333e; }
        QSplitter::handle { background: #23333e; }
        QScrollBar:vertical, QScrollBar:horizontal { background: #0a1016; width: 10px; height: 10px; margin: 0; }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #304552; border-radius: 4px; min-height: 20px; }
        QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        """
    )
