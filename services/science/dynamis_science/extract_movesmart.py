"""Safely extract the research CSVs from the rights-verified MoveSmart archive."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .data_root import data_root
from .real_sources import ZENODO_SOURCE

def _excluded(path: PurePosixPath) -> bool:
    return path.name.casefold() == ".ds_store" or (
        path.name.startswith("~$") and path.suffix.casefold() == ".docx"
    )


def _validated_path(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename.replace("\\", "/")
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or any(part in {".", ".."} or ":" in part for part in path.parts)
    ):
        raise ValueError(f"Unsafe ZIP path: {info.filename!r}")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"ZIP symlink is not allowed: {info.filename!r}")
    if info.flag_bits & 0x1:
        raise ValueError(f"Encrypted ZIP entry is not allowed: {info.filename!r}")
    return path


def extract_movesmart() -> dict[str, int | str]:
    root = data_root()
    source = ZENODO_SOURCE["files"][0]
    inventory = ZENODO_SOURCE["archive_inventory"]
    archive = root / "sources" / "zenodo-17376717" / "Dataset.zip"
    target = root / "extracted" / "zenodo-17376717" / "Dataset"
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Refusing to replace existing extraction: {target}")

    digest = hashlib.md5(usedforsecurity=False)
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if archive.stat().st_size != source["size_bytes"] or digest.hexdigest() != source["md5"]:
        raise ValueError("MoveSmart archive size or publisher MD5 does not match")

    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) != inventory["entries"]:
            raise ValueError(f"Unexpected ZIP entry count: {len(entries)}")
        expanded_bytes = sum(info.file_size for info in entries)
        if expanded_bytes != inventory["uncompressed_bytes"]:
            raise ValueError(f"Unexpected expanded ZIP size: {expanded_bytes}")

        seen: set[str] = set()
        members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info in entries:
            path = _validated_path(info)
            key = "/".join(path.parts).casefold()
            if key in seen:
                raise ValueError(f"Duplicate ZIP path: {info.filename!r}")
            seen.add(key)
            if info.is_dir() or "__macosx" in {part.casefold() for part in path.parts}:
                continue
            if _excluded(path):
                continue
            if path.suffix.casefold() == ".csv":
                if len(path.parts) < 2 or path.parts[0].casefold() != "dataset":
                    raise ValueError(f"Unexpected CSV location: {info.filename!r}")
                members.append((info, PurePosixPath(*path.parts[1:])))

        if len(members) != inventory["csv_files"]:
            raise ValueError(f"Unexpected filtered CSV count: {len(members)}")

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_root = root / "tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        extracted_bytes = 0
        with tempfile.TemporaryDirectory(prefix="movesmart-", dir=temporary_root) as temp:
            stage = Path(temp) / "Dataset"
            stage.mkdir()
            stage_resolved = stage.resolve()
            for info, relative in members:
                output = stage.joinpath(*relative.parts)
                if not output.resolve().is_relative_to(stage_resolved):
                    raise ValueError(f"ZIP path escapes extraction directory: {info.filename!r}")
                output.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source_file, output.open("xb") as output_file:
                    shutil.copyfileobj(source_file, output_file, 1024 * 1024)
                if output.stat().st_size != info.file_size:
                    raise ValueError(f"Truncated ZIP member: {info.filename!r}")
                extracted_bytes += info.file_size
            stage.rename(target)

    return {
        "archive": str(archive),
        "entries": len(entries),
        "csv_files": len(members),
        "excluded_personal_documents": 1,
        "expanded_bytes": expanded_bytes,
        "extracted_csv_bytes": extracted_bytes,
        "destination": str(target),
    }


if __name__ == "__main__":
    print(json.dumps(extract_movesmart(), indent=2))
