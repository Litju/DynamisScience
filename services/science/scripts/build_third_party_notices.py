"""Collect direct and transitive Python distribution notices for a build."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement


def _runtime_distributions(project_file: Path) -> list[metadata.Distribution]:
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
    pending = [Requirement(item).name for item in project.get("dependencies", [])]
    found: dict[str, metadata.Distribution] = {}
    while pending:
        name = pending.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in found:
            continue
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        found[key] = distribution
        for requirement_text in distribution.requires or []:
            requirement = Requirement(requirement_text)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return sorted(found.values(), key=lambda item: item.metadata["Name"].casefold())


def _license_files(distribution: metadata.Distribution) -> list[tuple[str, str]]:
    files = []
    for relative in distribution.files or []:
        normalized = str(relative).replace("\\", "/")
        name = Path(normalized).name.lower()
        if ".dist-info/licenses/" not in normalized.lower():
            continue
        if not name.startswith(("license", "copying", "notice", "copyright")):
            continue
        if "commercial" in name and distribution.metadata["Name"].casefold().startswith("pyside6"):
            continue
        path = distribution.locate_file(relative)
        try:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if content:
            files.append((normalized, content))
    return files


def build_notices(project_file: Path, output_file: Path) -> int:
    distributions = _runtime_distributions(project_file)
    if not distributions:
        raise RuntimeError("No installed runtime distributions were found.")
    sections = [
        "DynamisScience — Third-party Python runtime notices",
        "Generated from the installed runtime distributions used for this Windows build.",
        "",
    ]
    for distribution in distributions:
        name = distribution.metadata["Name"]
        version = distribution.version
        license_id = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "See upstream distribution metadata"
        )
        sections.extend([f"## {name} {version}", f"Declared license: {license_id}", ""])
        license_files = _license_files(distribution)
        if license_files:
            for relative, content in license_files:
                sections.extend([f"### {relative}", "", content, ""])
        elif len(license_id) > 300:
            sections.extend(["### Distribution license text", "", license_id, ""])
    try:
        bootloader = metadata.distribution("pyinstaller")
    except metadata.PackageNotFoundError as error:
        raise RuntimeError("PyInstaller must be installed to package the desktop app") from error
    bootloader_licenses = [
        (relative, content)
        for relative, content in _license_files(bootloader)
        if Path(relative).name.lower() == "copying.txt"
    ]
    if not bootloader_licenses:
        raise RuntimeError("PyInstaller bootloader license text is unavailable")
    sections.extend(
        [
            "## PyInstaller bootloader",
            "The desktop executable includes the PyInstaller bootloader; its license follows.",
            "",
        ]
    )
    for relative, content in bootloader_licenses:
        sections.extend([f"### {relative}", "", content, ""])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(sections), encoding="utf-8")
    return len(distributions)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1] / "pyproject.toml")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = build_notices(args.project, args.output)
    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise RuntimeError("Third-party notices were not generated.")
    print(f"Collected notices for {count} runtime distributions: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
