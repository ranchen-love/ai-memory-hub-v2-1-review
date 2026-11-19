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
    "docs/i18n/README.zh-CN.md", "docs/i18n/README.ja.md",
    "docs/i18n/README.ko.md", "docs/i18n/README.es.md",
    "docs/i18n/README.fr.md", "docs/i18n/README.de.md",
    "docs/i18n/README.pt-BR.md", "docs/i18n/README.ru.md",
    "ai_memory_hub/__init__.py", "ai_memory_hub/__main__.py", "ai_memory_hub/adapters.py",
    "ai_memory_hub/assets.py", "ai_memory_hub/handoff.py", "ai_memory_hub/model.py",
    "ai_memory_hub/store.py", "ai_memory_hub/sync.py", "ai_memory_hub/transfer.py",
    "docs/adapters.md", "docs/guide.md", "docs/protocol.md", "docs/deployment.md",
    "examples/checklist.txt", "examples/checkpoint-event.json", "examples/memory-hub.json",
    "examples/memory.json", "examples/project.json", "examples/session-delta.json", "examples/session.json",
    "pyproject.toml", "schemas/protocol.schema.json", "schemas/transfer.schema.json", "scripts/build_review_artifacts.py", "scripts/smoke_release.py",
    "scripts/smoke_v22.py", "scripts/check_readme_i18n.py",
    "tests/test_deployment.py", "tests/test_hub.py", "tests/test_protocol_schema.py",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md",
    "ai_memory_hub/life.py", "ai_memory_hub/workspace-files.json", "ai_memory_hub/workspace.py",
    "assets/README.md", "assets/manifest.json", "candidates/README.md",
    "collaboration/agent-roles.md", "collaboration/handoff-protocol.md", "collaboration/verification.md",
    "collaboration/workflows.md", "config/README.md", "config/sync-defaults.json",
    "config/workspace.gitignore", "core/INDEX.md", "core/boundaries.md",
    "core/communication.md", "core/hard-rules.md", "core/identity.md",
    "core/preferences.md", "docs/readme-sync.md", "docs/workspace-parity.md",
    "docs/workspace.md", "integrations/README.md", "integrations/capabilities.md",
    "integrations/memory-bootstrap.md", "knowledge/README.md", "knowledge/TOPIC.md",
    "life-archive/README.md", "life-archive/health/README.md", "life-archive/health/synthetic.json",
    "life-archive/profile.json", "life-archive/taxonomy.md", "life-archive/timeline.json",
    "memory/README.md", "memory/changelog.md", "memory/decisions.md",
    "memory/facts.yaml", "memory/pending-review.md", "projects/README.md",
    "projects/TEMPLATE.md", "schemas/health-summary.schema.json", "schemas/life-archive.schema.json",
    "schemas/memory-candidate.schema.json", "schemas/workspace-index.schema.json", "scripts/smoke_workspace.py",
    "sessions/README.md", "sessions/index.json", "setup.py",
    "tests/test_workspace.py", "vendor/README.md", "workflows/data-quality.md",
    "workflows/development.md", "workflows/document-writing.md", "workflows/hybrid-sync.md",
    "workflows/memory-lifecycle.md", "workflows/project-handoff.md", "workflows/research.md",
    "ai_memory_hub/candidates.py", "ai_memory_hub/shared_version.py",
    "life-archive/field-registry.json", "schemas/life-fields.schema.json", "schemas/shared-memory.schema.json",
    "tests/test_candidate_lifecycle.py", "tests/test_life_registry.py", "tests/test_shared_version.py",
}
LEGACY_ALLOWED = {
    "README.zh-CN.md", "README.ja.md", "README.ko.md", "README.es.md",
    "README.fr.md", "README.de.md", "README.pt-BR.md", "README.ru.md",
}
ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def tree(commit, approved):
    entries = {}
    for item in git("ls-tree", "-rz", commit).split(b"\0"):
        if not item:
            continue
        header, name = item.split(b"\t", 1)
        file = name.decode("utf-8")
        mode, kind, oid = header.split()
        if file not in approved or mode != b"100644" or kind != b"blob":
            raise ValueError("unapproved history entry: " + file)
        entries[file] = oid.decode("ascii")
    return entries


def build(out, candidate=False):
    dirty = git("status", "--porcelain").strip()
    if dirty:
        raise ValueError("build from a clean standalone checkout")
    commits = git("rev-list", "--all").decode().splitlines()
    roots = git("rev-list", "--all", "--max-parents=0").decode().splitlines()
    if len(roots) != 1:
        raise ValueError("standalone history must have one root")
    head = git("rev-parse", "HEAD").decode().strip()
    ref = git("symbolic-ref", "HEAD").decode().strip()
    if not ref.startswith("refs/heads/") or (not candidate and ref != "refs/heads/main"):
        raise ValueError("check out the standalone branch")
    current = tree(head, ALLOWED)
    if set(current) != ALLOWED:
        raise ValueError("release tree differs from the approved file list")
    histories = {oid for commit in commits for oid in tree(commit, ALLOWED | LEGACY_ALLOWED).values()}
    for oid in histories:
        git("cat-file", "blob", oid).decode("utf-8")
    version = re.search(rb'^VERSION = "(\d+\.\d+\.\d+)"$', git("show", "HEAD:ai_memory_hub/__init__.py"), re.M)[1].decode()
    tags = git("for-each-ref", "--format=%(refname)", "refs/tags").decode().splitlines()
    if any(not re.fullmatch(r"refs/tags/v2\.\d+\.\d+", tag) for tag in tags):
        raise ValueError("unexpected release tag")
    release_tag = f"refs/tags/v{version}"
    if not candidate and git("rev-parse", release_tag + "^{commit}").decode().strip() != head:
        raise ValueError("release tag does not match checkout")
    if set(commits) != set(git("rev-list", ref, *tags).decode().splitlines()):
        raise ValueError("extra reachable history outside the review bundle")
    out = out.resolve()
    out.mkdir(exist_ok=True, parents=True)
    prefix = f"ai-memory-hub-v{version}" + ("-review" if candidate else "")
    archive, bundle = out / (prefix + ".zip"), out / (prefix + ".bundle")
    git("archive", "--format=zip", f"--prefix={prefix}/", f"--output={archive}", head)
    git("bundle", "create", str(bundle), ref, *tags)
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
        "files": len(current), "history_blobs": len(histories), "tag": None if candidate else f"v{version}",
        "candidate": candidate, "ref": ref, "sha256": artifacts,
    }
    (out / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in artifacts.items()),
                                   encoding="ascii", newline="\n")
    (out / "release-evidence.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", action="store_true", help="package the checked-out branch without a release tag")
    args = parser.parse_args()
    build(args.output, args.candidate)
