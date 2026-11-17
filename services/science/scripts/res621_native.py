"""Disposable native audit harness. Store is owned, size/time bounded and purged on exit.

Usage: python scripts/res621_native.py <evidence-directory>
The evidence directory retains only screenshots/receipts, never the research store.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dynamis_science.qa_cleanup import allocate_run_root, tree_bytes


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    repository = Path(__file__).resolve().parents[3]
    scratch, marker = allocate_run_root(Path(tempfile.gettempdir())/'res621-development', repository=repository,
        protected_roots=('D:/datasets/DynamisScience',), issue_id='RES-621',
        max_bytes=512*1024**2, min_free_bytes=1024**3)
    os.environ['DYNAMISSCIENCE_DATA_ROOT'] = str(scratch/'private')
    os.environ['MPLCONFIGDIR'] = str(scratch/'mpl')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    peak = 0
    started = time.monotonic()
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from dynamis_science.desktop.main_window import MainWindow
        from dynamis_science.desktop.services import DynamisAppService
        from res621_study import prepare, follow_up
        app = QApplication([])
        service = DynamisAppService()
        case = follow_up(service, prepare(service, scratch), scratch)
        window = MainWindow(service)
        window.resize(1366, 720)
        window.show()
        def opened():
            window._show_study(case['id'], service.get_study_detail(case['id']))
        window.catalogue_loaded.connect(opened)
        def guard():
            nonlocal peak
            peak = max(peak, tree_bytes(scratch))
            if peak > marker['max_bytes'] or time.monotonic()-started > 1800:
                window.close()
        timer = QTimer()
        timer.timeout.connect(guard)
        timer.start(1000)
        # Screenshots are exact QWidget captures of the same real window inspected via Computer Use.
        # F12 gives an operator a reproducible capture, with no extra UI state mutation.
        from PySide6.QtGui import QShortcut, QKeySequence
        counter = [0]
        def capture():
            counter[0] += 1
            window.grab().save(str(out/f'{counter[0]:02d}-native.png'))
        shortcut = QShortcut(QKeySequence('F12'), window)
        shortcut.activated.connect(capture)
        (out/'study-receipt.json').write_text(json.dumps(dict(workspace_id=case['id'],
            data_revisions=case['revisions'], athletes=20, weeks=12, protocols=20,
            runs=[r['id'] for r in case['runs']+case['final_runs']],
            report_version=case['report_version'], historical_report_unchanged=True,
            frozen_comparisons=[case['frozen_series']['id'],case['comparison']['id']],
            store=str(scratch), platform=app.platformName()), indent=2), encoding='utf-8')
        print(f'READY {case["id"]} {scratch}', flush=True)
        app.exec()
        peak = max(peak, tree_bytes(scratch))
    finally:
        # Delete only this allocation after the application has closed all workers.
        resolved = scratch.resolve(strict=True)
        assert resolved.parent == Path(marker['scratch_parent']).resolve()
        assert resolved.name == 'dynamisscience-qa-'+marker['run_id']
        assert not resolved.is_relative_to(repository) and not resolved.is_relative_to(Path('D:/datasets/DynamisScience'))
        shutil.rmtree(resolved)
        (out/'cleanup.json').write_text(json.dumps(dict(scratch=str(scratch), removed=not scratch.exists(),
            peak_bytes=peak, limits='512 MiB / 1800 s', elapsed_seconds=round(time.monotonic()-started, 1)), indent=2))


if __name__ == '__main__':
    main()
