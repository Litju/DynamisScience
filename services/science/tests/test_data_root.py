from __future__ import annotations

from pathlib import Path

import pytest

from dynamis_science.data_root import (
    DataRootConfigurationError,
    ROOT,
    data_root,
    paths,
)


def test_data_root_requires_explicit_absolute_private_path(monkeypatch, tmp_path):
    monkeypatch.delenv("DYNAMISSCIENCE_DATA_ROOT", raising=False)
    with pytest.raises(DataRootConfigurationError, match="Set DYNAMISSCIENCE_DATA_ROOT"):
        data_root()

    with pytest.raises(DataRootConfigurationError, match="absolute path"):
        data_root("relative-data")

    with pytest.raises(DataRootConfigurationError, match="outside the repository"):
        data_root(ROOT / "data" / "real")

    file_path = tmp_path / "not-a-directory"
    file_path.write_text("sentinel", encoding="utf-8")
    with pytest.raises(DataRootConfigurationError, match="must be a directory"):
        data_root(file_path)


def test_path_resolution_uses_the_current_environment_or_explicit_root(monkeypatch, tmp_path):
    configured = tmp_path / "configured"
    explicit = tmp_path / "explicit"
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(configured))

    assert data_root() == configured.resolve()
    assert paths(explicit)["root"] == explicit.resolve()
    assert Path(paths()["research"]) == configured.resolve() / "research"
    assert Path(paths()["performance"]) == configured.resolve() / "performance"
