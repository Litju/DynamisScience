# Third-party licensing for the Windows desktop build

This notice applies to the DynamisScience PyInstaller `--onedir` bundle and
Inno Setup installer. The notice and Qt LGPL text ship beside
`DynamisScience.exe`; per-package license files are retained by the build when
present in the installed distributions.

## Qt for Python

The application uses the PySide6 Community Edition bindings and Qt libraries
under LGPLv3. The onedir bundle keeps Qt as separate DLLs; it does not modify or
statically link Qt. The installer preserves those DLLs as replaceable shared
libraries in the user's application directory. The bundle includes the full
[GNU LGPL version 3 text](licenses/LGPL-3.0.txt), Qt/PySide6 copyright notices,
and a Help → Open-Source Licenses action. See the
[Qt LGPL guidance](https://doc.qt.io/qt-6/lgpl.html) for the library terms and
relinking/installation requirements.

## Python and application libraries

The installer includes this notice and the principal license references for
the bundled runtime dependencies:

| Component | License |
|---|---|
| Python | [Python Software Foundation License](https://docs.python.org/3/license.html) |
| PySide6 / Qt | LGPLv3 (Community Edition) |
| pyqtgraph | [MIT](https://github.com/pyqtgraph/pyqtgraph/blob/main/LICENSE.txt) |
| Matplotlib | [Matplotlib License](https://matplotlib.org/stable/project/license.html) |
| NumPy | [BSD 3-Clause](https://numpy.org/doc/stable/license.html) |
| SciPy | [BSD 3-Clause](https://github.com/scipy/scipy/blob/main/LICENSE.txt) |
| statsmodels | [BSD 3-Clause](https://github.com/statsmodels/statsmodels/blob/main/LICENSE.txt) |
| Polars | [MIT](https://github.com/pola-rs/polars/blob/main/LICENSE) |
| PyArrow | [Apache 2.0](https://github.com/apache/arrow/blob/main/LICENSE.txt) |
| DuckDB | [MIT](https://github.com/duckdb/duckdb/blob/main/LICENSE) |
| Pydantic | [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| openpyxl | [MIT](https://openpyxl.readthedocs.io/en/stable/) |
| PyInstaller bootloader | [GPLv2-or-later with PyInstaller exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) |

The build tooling is not required at runtime. This project does not modify
PySide6, Qt, or third-party scientific libraries. Their copyright notices and
upstream license files are retained in the installer bundle.

## Inno Setup

Inno Setup 6.7.3 is used only to build the Windows installer and is not bundled
into the installed application. Its license permits commercial use subject to
the stated copyright and redistribution conditions; the installer build keeps
the Inno Setup copyright and source attribution in this documentation. The
The compiler is not shipped with the application. See the [official license](https://jrsoftware.org/files/is/license.txt) for the copyright and redistribution conditions.

## Dataset rights and private state

The installer contains the deterministic synthetic `DS-SYNTH-001` fixture for
demonstration and regression workflows. It contains no Mendeley or MoveSmart
research records. Real snapshots, SQLite research records, user-authored
projects, and operational history remain in the separately configured
`DYNAMISSCIENCE_DATA_ROOT`; installing or uninstalling the application must
not modify or remove that directory.
