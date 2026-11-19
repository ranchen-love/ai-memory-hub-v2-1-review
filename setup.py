"""Bundle the single, explicit workspace template list into installed packages."""

import json
from pathlib import Path, PurePosixPath

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

ROOT = Path(__file__).resolve().parent


def template_files():
    data = json.loads((ROOT / "ai_memory_hub/workspace-files.json").read_text(encoding="utf-8"))
    entries = data["files"] + data["demo"]
    for entry in entries:
        if (not isinstance(entry, str) or ":" in entry or "\\" in entry
                or any(part in ("", ".", "..") for part in entry.split("/"))):
            raise ValueError("invalid workspace resource path")
    if len(entries) != len(set(entries)):
        raise ValueError("duplicate workspace resource path")
    return entries


class BundleWorkspace(build_py):
    def run(self):
        paths = template_files()
        approved_files = {PurePosixPath(path) for path in paths}
        approved_dirs = {parent for path in approved_files for parent in path.parents}
        target = Path(self.build_lib).resolve() / "ai_memory_hub" / "_workspace"
        if target.resolve() != target:
            raise ValueError("use a clean workspace build destination")
        for item in target.rglob("*"):
            relative = PurePosixPath(item.relative_to(target).as_posix())
            allowed = approved_dirs if item.is_dir() else approved_files
            if item.resolve() != item or relative not in allowed:
                raise ValueError("stale workspace files; build from a fresh checkout or extracted source")
        super().run()
        for name in paths:
            source = ROOT / name
            if not source.is_file() or source.resolve() != source:
                raise ValueError("workspace input must be a regular source file")
            path = target / name
            self.mkpath(str(path.parent))
            self.copy_file(str(source), str(path))


class WorkspaceSdist(sdist):
    def add_defaults(self):
        super().add_defaults()
        self.filelist.extend(template_files())


setup(cmdclass={"build_py": BundleWorkspace, "sdist": WorkspaceSdist})
