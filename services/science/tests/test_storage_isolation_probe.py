from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from dynamis_science.data_root import DataRootConfigurationError, data_root


def test_pytest_replaces_and_blocks_inherited_operational_storage():
    test_root = data_root()
    assert test_root == Path(os.environ["DYNAMISSCIENCE_TEST_ROOT"]).resolve()
    assert test_root.is_relative_to(Path(tempfile.gettempdir()).resolve())

    protected_roots = json.loads(os.environ["DYNAMISSCIENCE_TEST_PROTECTED_ROOTS"])
    assert all(test_root != Path(item).expanduser().resolve() for item in protected_roots)
    for item in protected_roots:
        with pytest.raises(DataRootConfigurationError):
            data_root(item)
