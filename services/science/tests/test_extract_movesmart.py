from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from pathlib import Path

import pytest

import dynamis_science.extract_movesmart as movesmart_extractor
from dynamis_science.extract_movesmart import _excluded, _validated_path


@pytest.mark.parametrize(
    "name",
    ["../escape.csv", r"..\escape.csv", "C:/escape.csv", r"\\server\share.csv"],
)
def test_zip_paths_cannot_escape_the_extraction_root(name):
    with pytest.raises(ValueError, match="Unsafe ZIP path"):
        _validated_path(zipfile.ZipInfo(name))


def test_zip_symlinks_are_rejected():
    info = zipfile.ZipInfo("Dataset/link.csv")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="symlink"):
        _validated_path(info)


def test_normal_zip_paths_are_kept_relative():
    assert _validated_path(zipfile.ZipInfo("Dataset/P1/data.csv")).parts == (
        "Dataset",
        "P1",
        "data.csv",
    )


def test_office_lock_document_is_excluded_without_storing_its_name():
    from pathlib import PurePosixPath

    assert _excluded(PurePosixPath("Dataset/Participant/~$redacted.docx"))


def _small_archive(tmp_path: Path, monkeypatch, *, expected_expanded_bytes: int | None = None):
    csv = b"a,b\n1,2\n"
    document = b"unrelated private document"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("Dataset/P1/clean.csv", csv)
        bundle.writestr("Dataset/P1/~$redacted.docx", document)
    archive_bytes = buffer.getvalue()
    archive = tmp_path / "sources" / "zenodo-17376717" / "Dataset.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(archive_bytes)
    expanded_bytes = len(csv) + len(document)
    monkeypatch.setenv("DYNAMISSCIENCE_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(
        movesmart_extractor,
        "ZENODO_SOURCE",
        {
            "files": [{"size_bytes": len(archive_bytes), "md5": hashlib.md5(archive_bytes, usedforsecurity=False).hexdigest()}],
            "archive_inventory": {
                "entries": 2,
                "uncompressed_bytes": expected_expanded_bytes if expected_expanded_bytes is not None else expanded_bytes,
                "csv_files": 1,
            },
        },
    )
    return archive, csv, document


def test_extract_movesmart_uses_bounded_inventory_and_excludes_documents(tmp_path, monkeypatch):
    _, csv, _ = _small_archive(tmp_path, monkeypatch)

    result = movesmart_extractor.extract_movesmart()
    target = tmp_path / "extracted" / "zenodo-17376717" / "Dataset"

    assert result["csv_files"] == 1
    assert result["excluded_personal_documents"] == 1
    assert result["extracted_csv_bytes"] == len(csv)
    assert (target / "P1" / "clean.csv").read_bytes() == csv
    assert not list(target.rglob("*.docx"))


def test_extract_movesmart_rejects_unexpected_expansion_before_writing(tmp_path, monkeypatch):
    _, _, _ = _small_archive(tmp_path, monkeypatch, expected_expanded_bytes=100_000_000)

    with pytest.raises(ValueError, match="Unexpected expanded ZIP size"):
        movesmart_extractor.extract_movesmart()

    assert not (tmp_path / "extracted" / "zenodo-17376717" / "Dataset").exists()
