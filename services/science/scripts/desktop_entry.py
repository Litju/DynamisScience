"""PyInstaller entry point for the native GUI and its hidden worker mode."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        from dynamis_science.desktop.worker import run_files

        return run_files(sys.argv[2], sys.argv[3])
    from dynamis_science.desktop.__main__ import main as desktop_main

    return desktop_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
