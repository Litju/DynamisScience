from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_test_root: tempfile.TemporaryDirectory[str] | None = None


def pytest_configure(config: pytest.Config) -> None:
    del config
    global _test_root

    try:
        protected = json.loads(os.environ.get("DYNAMISSCIENCE_TEST_PROTECTED_ROOTS", "[]"))
    except ValueError as exc:
        raise pytest.UsageError("DYNAMISSCIENCE_TEST_PROTECTED_ROOTS must be valid JSON") from exc
    if not isinstance(protected, list):
        raise pytest.UsageError("DYNAMISSCIENCE_TEST_PROTECTED_ROOTS must be a JSON list")

    inherited_root = os.environ.get("DYNAMISSCIENCE_DATA_ROOT", "").strip()
    if inherited_root:
        protected.append(inherited_root)
    _test_root = tempfile.TemporaryDirectory(prefix="dynamis-science-pytest-")
    test_root = str(Path(_test_root.name).resolve())
    os.environ["DYNAMISSCIENCE_TEST_SESSION"] = "1"
    os.environ["DYNAMISSCIENCE_TEST_PROTECTED_ROOTS"] = json.dumps(sorted(set(protected)))
    os.environ["DYNAMISSCIENCE_TEST_ROOT"] = test_root
    os.environ["DYNAMISSCIENCE_DATA_ROOT"] = test_root


def pytest_unconfigure(config: pytest.Config) -> None:
    del config
    if _test_root is not None:
        _test_root.cleanup()
