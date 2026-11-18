"""Check the standalone repository history and build review artifacts."""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ALLOWED = {
    ".gitattributes", ".github/workflows/test.yml", ".gitignore", "LICENSE", "README.md", "SECURITY.md",
    "ai_memory_hub/__init__.py", "ai_memory_hub/__main__.py", "ai_memory_hub/adapters.py",
    "ai_memory_hub/assets.py", "ai_memory_hub/handoff.py", "ai_memory_hub/model.py",
    "ai_memory_hub/store.py", "ai_memory_hub/sync.py",
    "docs/adapters.md", "docs/guide.md", "docs/protocol.md",
    "examples/checklist.txt", "examples/checkpoint-event.json", "examples/memory-hub.json",
    "examples/memory.json", "examples/project.json", "examples/session-delta.json", "examples/session.json",
    "pyproject.toml", "schemas/protocol.schema.json", "scripts/build_review_artifacts.py", "scripts/smoke_release.py",
    "tests/test_hub.py", "tests/test_protocol_schema.py",
}
ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def tree(commit):
    entries = {}
    for item in git("ls-tree", "-rz", commit).split(b"\0"):
        if not item:
            continue
        header, name = item.split(b"\t", 1)
        file = name.decode("utf-8")
        mode, kind, oid = header.split()
        if file not in ALLOWED or mode != b"100644" or kind != b"blob":
            raise ValueError("unapproved history entry: " + file)
        entries[file] = oid.decode("ascii")
    return entries


def build(out):
    dirty = git("status", "--porcelain").strip()
    if dirty:
        raise ValueError("build from a clean standalone checkout")
    commits = git("rev-list", "--all").decode().splitlines()
    roots = git("rev-list", "--all", "--max-parents=0").decode().splitlines()
    if len(roots) != 1:
        raise ValueError("standalone history must have one root")
    head = git("rev-parse", "HEAD").decode().strip()
    if head != git("rev-parse", "refs/heads/main").decode().strip():
        raise ValueError("check out the standalone main branch")
    current = tree(head)
    if set(current) != ALLOWED:
        raise ValueError("release tree differs from the approved file list")
    histories = {oid for commit in commits for oid in tree(commit).values()}
    for oid in histories:
        git("cat-file", "blob", oid).decode("utf-8")
    version = re.search(rb'^VERSION = "(\d+\.\d+\.\d+)"$', git("show", "HEAD:ai_memory_hub/__init__.py"), re.M)[1].decode()
    tags = git("for-each-ref", "--format=%(refname)", "refs/tags").decode().splitlines()
    if any(not re.fullmatch(r"refs/tags/v2\.1\.\d+", tag) for tag in tags):
        raise ValueError("unexpected release tag")
    release_tag = f"refs/tags/v{version}"
    if git("rev-parse", release_tag + "^{commit}").decode().strip() != head:
        raise ValueError("release tag does not match checkout")
    if set(commits) != set(git("rev-list", "refs/heads/main", *tags).decode().splitlines()):
        raise ValueError("extra reachable history outside the review bundle")
    out = out.resolve()
    out.mkdir(exist_ok=True, parents=True)
    prefix = f"ai-memory-hub-v{version}"
    archive, bundle = out / (prefix + ".zip"), out / (prefix + ".bundle")
    git("archive", "--format=zip", f"--prefix={prefix}/", f"--output={archive}", head)
    git("bundle", "create", str(bundle), "refs/heads/main", *tags)
    git("bundle", "verify", str(bundle))
    with zipfile.ZipFile(archive) as packaged:
        names = {x.filename for x in packaged.infolist() if not x.is_dir()}
        if names != {f"{prefix}/{name}" for name in current}:
            raise ValueError("ZIP differs from the checked tree")
        for name, oid in current.items():
            if packaged.read(f"{prefix}/{name}") != git("cat-file", "blob", oid):
                raise ValueError("ZIP content differs from Git")
    artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (archive, bundle)}
    metadata = {
        "commit": head, "root": roots[0], "reachable_commits": len(commits),
        "files": len(current), "history_blobs": len(histories), "tag": f"v{version}", "sha256": artifacts,
    }
    (out / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in artifacts.items()),
                                   encoding="ascii", newline="\n")
    (out / "release-evidence.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
