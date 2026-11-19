"""Prepare and verify an independent Git projection of expressly selected data."""

import difflib
import os
import re
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unicodedata import category, normalize

from . import SCHEMA
from .model import (
    Conflict, Denied, HubError, Missing, canonical, document, ident, no_credentials, one_of, open_source,
    revision, seq, shape, strict_json, text,
)
from .shared_version import export_record
from .store import checked_relative, instance_path, protect_root, reparse
from .transfer import asset_key, checksum, hash_bytes
from .workspace import private_pair

FORMAT = "1.0"
MANIFEST_FORMAT = "2.0"
MANIFEST = "projection.json"
README = b"""# AI Memory Hub Git projection

This directory contains reviewed publication data. The private Workspace, Vault,
raw conversations, machine binding, and stored file bytes remain local.
Verify the manifest and review the exact preview before publishing.
"""
LEGACY_REQUIRED = {"README.md": "static", "inventory.json": "aggregate_metadata"}
LEGACY_OPTIONAL = {"shared-memory.json": "public_reviewed_memory", "asset-refs.json": "public_version_references"}
MODULES = {
    ".github": "Repository configuration. No active workflows are provided.",
    "assets": "Optional approved version references. Original files stay in the Vault.",
    "candidates": "Review proposals in the owner Workspace before sharing accepted records.",
    "collaboration": "Use approved summaries and authorize any separate context transfer.",
    "config": "Runtime bindings, grants and schedules stay in the owner Workspace.",
    "core": "Start with the Agent entry and use published working rules in memory.",
    "docs": "See the Agent entry for this repository's data layout.",
    "examples": "Use synthetic fixtures when checking the owner workflow.",
    "integrations": "Use only integrations and sources the owner has authorized.",
    "knowledge": "Use independently reviewed references when adding knowledge.",
    "life-archive": "Life records and original evidence stay with the owner.",
    "memory": "Read reviewed.json for approved portable summaries, or shared-memory.json for a public snapshot.",
    "projects": "Read index.json for approved project summaries and checkpoints.",
    "schemas": "The installed AI Memory Hub validates the publication format.",
    "scripts": "Owner execution stays local. This projection carries no runnable scripts.",
    "sessions": "Read index.json for approved session indexes and optional L2 checkpoints.",
    "tests": "Validate changes with synthetic inputs.",
    "vendor": "Use the separately distributed AI Memory Hub engine.",
    "workflows": "Review local changes, then publish only the exact approved projection.",
}
AGENTS = ("# Agent entry\n\n"
          "Use only the summaries and indexes in this reviewed Private repository. "
          "Follow the owner's actual permissions to access any original evidence.\n\n"
          "## Modules\n\n" + "".join(f"- [{name}]({name}/README.md)\n" for name in MODULES)).encode("utf-8")
STATIC = {
    "README.md": b"# Personal AI Memory Hub\n\nStart with [the Agent entry](AGENTS.md).\n",
    "AGENTS.md": AGENTS,
    **{f"{name}/README.md": f"# {name}\n\n{description}\n\n[All modules](../AGENTS.md)\n".encode("utf-8")
       for name, description in MODULES.items()},
}
PUBLIC_MEMORY = "memory/shared-memory.json"
PUBLIC_ASSETS = "assets/refs.json"
REVIEWED_PATHS = {"memory": "memory/reviewed.json", "project": "projects/index.json", "session": "sessions/index.json"}
REQUIRED = {**dict.fromkeys(STATIC, "static"), "inventory.json": "aggregate_metadata"}
OPTIONAL = {PUBLIC_MEMORY: "public_reviewed_memory", PUBLIC_ASSETS: "public_version_references",
            **{path: f"private_reviewed_{kind}" for kind, path in REVIEWED_PATHS.items()}}
CLASSES = {**LEGACY_REQUIRED, **LEGACY_OPTIONAL, **REQUIRED, **OPTIONAL, MANIFEST: "manifest"}
DIRECTORIES = frozenset(MODULES)
RECORD_KINDS = ("session", "project", "memory", "asset")
MEMORY_CLASSES = ("fact", "rule", "preference")
MAX_FILE = 512 * 1024
MAX_SELECTIONS = 128
UNSAFE_TEXT = re.compile(
    r"(?ix) (?<![a-z0-9+.-])[a-z][a-z0-9+.-]*:// | (?<!\w)[a-z]:[\\/]"
    r"| \\\\ | (?<![\w./])/(?:[\w.@-]+/)+"
    r"| (?<![\w.+-])[\w.+-]+@[\w.-]+\.[\w-]{2,}"
    r"| (?<!\d)(?:\d[ -]?){9,}\d(?!\d)"
    r"| \b(?:bearer\s|sk-[a-z0-9_]|xox[baprs]-|AIza[a-z0-9_-])"
)


def encoded(value):
    return (canonical(value) + "\n").encode("utf-8")


def safe_text(value):
    value = normalize("NFKC", text(value, 4096))
    no_credentials(value)
    if UNSAFE_TEXT.search(value) or any(category(char) in ("Cc", "Cf") for char in value):
        raise Denied("projection text contains a potential identifier, link, local path or control character")


def count(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise HubError("invalid projection count")


def public_source(entry_id, version):
    return {"provider": "reviewed_projection", "kind": "workspace_artifact",
            "locator": f"projection:public-memory:{entry_id}@{version}"}


def json_value(contents):
    value = strict_json(contents.decode("utf-8"))
    if encoded(value) != contents:
        raise HubError("projection JSON must use canonical UTF-8 encoding")
    return value


def unique_ordered(keys):
    if not keys or len(keys) > MAX_SELECTIONS or keys != sorted(set(keys)):
        raise HubError("projection selections must be non-empty, distinct, sorted and bounded")


def validate_inventory(value):
    shape(value, ("format", "kind", "counts"))
    one_of(value["format"], (FORMAT,))
    one_of(value["kind"], ("aggregate_inventory",))
    shape(value["counts"], RECORD_KINDS)
    for amount in value["counts"].values():
        count(amount)


def validate_memories(value):
    shape(value, ("format", "kind", "scopes"))
    one_of(value["format"], ("1.0",))
    one_of(value["kind"], ("shared_memory",))
    shape(value["scopes"], ("reviewed",))
    ids = []
    for item in seq(value["scopes"]["reviewed"]):
        shape(item, ("kind", "id", "schema_version", "sensitivity", "source", "data", "revision"))
        entry_id, version = ident(item["id"]), revision(item["revision"])
        one_of(item["kind"], ("memory",))
        one_of(item["sensitivity"], ("public",))
        if item["source"] != public_source(entry_id, version):
            raise Denied("projection only permits its scrubbed evidence locator")
        document({key: item[key] for key in item if key != "revision"}, "public", allow_review=True)
        fields = item["data"]
        if fields["status"] != "accepted" or fields.get("classification") not in MEMORY_CLASSES:
            raise Denied("only accepted and classified public memories can be selected")
        for value_to_check in (entry_id, fields["key"], fields["claim"]):
            safe_text(value_to_check)
        ids.append(entry_id)
    unique_ordered(ids)


def validate_assets(value):
    shape(value, ("format", "kind", "refs"))
    one_of(value["format"], (FORMAT,))
    one_of(value["kind"], ("public_asset_references",))
    keys = []
    for item in seq(value["refs"]):
        shape(item, ("id", "version", "storage", "sha256"))
        entry_id = ident(item["id"])
        safe_text(entry_id)
        keys.append((entry_id, revision(item["version"])))
        if one_of(item["storage"], ("vault", "external")) == "vault":
            checksum(item["sha256"])
        elif item["sha256"] is not None:
            raise HubError("external references have no stored content hash")
    unique_ordered(keys)


VALIDATORS = {"inventory.json": validate_inventory,
              "shared-memory.json": validate_memories, PUBLIC_MEMORY: validate_memories,
              "asset-refs.json": validate_assets, PUBLIC_ASSETS: validate_assets}


def validate_payload(files, format_version, review=None):
    required, optional = (LEGACY_REQUIRED, LEGACY_OPTIONAL) if format_version == FORMAT else (REQUIRED, OPTIONAL)
    if required.keys() - files.keys() or files.keys() - (required.keys() | optional.keys()):
        raise Denied("the projection may only contain its approved file classes")
    if any(len(contents) > MAX_FILE for contents in files.values()):
        raise Denied("projection file exceeds the 512 KiB inspection limit")
    fixed = {"README.md": README} if format_version == FORMAT else STATIC
    if any(files[path] != contents for path, contents in fixed.items()):
        raise Denied("projection scaffold must match the built-in neutral templates")
    for name, validate in VALIDATORS.items():
        if name in files:
            validate(json_value(files[name]))
    reviewed = {kind: json_value(files[path]) for kind, path in REVIEWED_PATHS.items() if path in files}
    if bool(reviewed) != (review is not None) or (reviewed and files.keys() & {PUBLIC_MEMORY, PUBLIC_ASSETS}):
        raise Denied("private reviewed data needs exactly one bound review and its own projection")
    if reviewed:
        from .projection_review import validate_sections

        validate_sections(reviewed)


def declared_files(files):
    return [{"path": name, "classification": CLASSES[name], "sha256": hash_bytes(contents)}
            for name, contents in sorted(files.items())]


def read_member(root, name):
    path = checked_relative(root, name)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise Denied("projection files must be regular files without hard links")
    with open_source(path) as source:
        opened = os.fstat(source.fileno())
        if not os.path.samestat(opened, before):
            raise Conflict("a projection file changed while opening it")
        contents = source.read(MAX_FILE + 1)
    if len(contents) > MAX_FILE:
        raise Denied("projection file exceeds the 512 KiB inspection limit")
    return contents


def validate_manifest(contents, expected_digest):
    if expected_digest is not None and hash_bytes(contents) != checksum(expected_digest):
        raise Conflict("projection differs from the approved digest")
    value = json_value(contents)
    shape(value, ("format", "kind", "files"), ("review",))
    version = one_of(value["format"], (FORMAT, MANIFEST_FORMAT))
    one_of(value["kind"], ("git_projection",))
    required, optional = (LEGACY_REQUIRED, LEGACY_OPTIONAL) if version == FORMAT else (REQUIRED, OPTIONAL)
    names = []
    for entry in seq(value["files"]):
        shape(entry, ("path", "classification", "sha256"))
        name = entry["path"]
        if not isinstance(name, str) or name not in required.keys() | optional.keys():
            raise Denied("projection manifest names an unapproved path")
        if entry["classification"] != CLASSES[name]:
            raise Denied("projection classification differs from the fixed allowlist")
        checksum(entry["sha256"])
        names.append(name)
    if not required.keys() <= set(names) or names != sorted(set(names)):
        raise Denied("projection manifest is missing required files or contains duplicates")
    reviewed = set(names) & set(REVIEWED_PATHS.values())
    if bool(reviewed) != ("review" in value) or (reviewed and set(names) & {PUBLIC_MEMORY, PUBLIC_ASSETS}):
        raise Denied("private reviewed data needs its own bound manifest")
    if reviewed:
        from .projection_review import validate_review_binding

        validate_review_binding(value["review"])
    return value


def verify_projection_files(files, expected_digest):
    """Validate a complete projection tree already read into trusted memory."""
    if MANIFEST not in files or files.keys() - CLASSES.keys():
        raise Denied("unexpected or missing projection members")
    if any(type(contents) is not bytes or len(contents) > MAX_FILE for contents in files.values()):
        raise Denied("projection files must be bytes within the 512 KiB inspection limit")
    manifest = validate_manifest(files[MANIFEST], expected_digest)
    payload = {name: contents for name, contents in files.items() if name != MANIFEST}
    validate_payload(payload, manifest["format"], manifest.get("review"))
    if manifest["files"] != declared_files(payload):
        raise Conflict("projection contents do not match the manifest")
    return dict(files)


def projection_members(root):
    names = set()
    for member in root.iterdir():
        if reparse(member):
            raise Denied("projection cannot contain links or reparse points")
        if member.is_dir():
            if member.name not in DIRECTORIES:
                raise Denied("projection contains an unexpected directory")
            children = list(member.iterdir())
            if not children or any(not child.is_file() or reparse(child) for child in children):
                raise Denied("projection directories must contain only approved regular files")
            names.update(f"{member.name}/{child.name}" for child in children)
        else:
            names.add(member.name)
    return names


def read_projection(root, expected_digest=None):
    names = projection_members(root)
    if MANIFEST not in names or names - CLASSES.keys():
        raise Denied("unexpected or missing projection members")
    files = {name: read_member(root, name) for name in names}
    if names != projection_members(root):
        raise Conflict("projection members changed during verification")
    return verify_projection_files(files, expected_digest)


def verify_projection(path, expected_digest):
    """Return a byte snapshot of exactly the independently reviewed projection."""
    return read_projection(instance_path(path), checksum(expected_digest))


def authorize_projection(store, files, target):
    manifest = json_value(files[MANIFEST])
    if manifest["format"] != MANIFEST_FORMAT:
        raise Denied("regenerate the legacy preview as a complete modular projection before publishing")
    if "review" in manifest:
        from .projection_review import authorize_publication

        if store is None:
            raise Denied("reviewed private material requires its approved Vault")
        with store.transaction() as db:
            authorize_publication(store, db, files, manifest["review"], target)
    selections = files.keys() & {PUBLIC_MEMORY, PUBLIC_ASSETS}
    if selections:
        if store is None or store.level != "public":
            raise Denied("public selections must be verified against their public Vault")
        ids = [item["id"] for item in json_value(files[PUBLIC_MEMORY])["scopes"]["reviewed"]] if PUBLIC_MEMORY in files else []
        refs = [(item["id"], item["version"]) for item in json_value(files[PUBLIC_ASSETS])["refs"]] if PUBLIC_ASSETS in files else []
        with store.transaction() as db:
            expected = {
                PUBLIC_MEMORY: encoded(public_memories(store, db, ids)) if ids else None,
                PUBLIC_ASSETS: encoded(public_assets(store, db, refs)) if refs else None,
            }
        if any(files[name] != expected[name] for name in selections):
            raise Conflict("public selection differs from the current approved Vault records")
    return manifest.get("review")


def public_memories(store, db, selected):
    rows = []
    for entry_id in selected:
        item = store.get(db, "memory", entry_id)
        if item is None:
            raise Missing("selected public memory does not exist")
        row = export_record(item)
        row["source"] = public_source(entry_id, item["revision"])
        rows.append(row)
    return {"format": "1.0", "kind": "shared_memory", "scopes": {"reviewed": rows}}


def public_assets(store, db, selected):
    refs = []
    for entry_id, version in selected:
        item = store.get(db, "asset", entry_id, version)
        if item is None:
            raise Missing("selected public asset version does not exist")
        if item["sensitivity"] != "public":
            raise Denied("selected asset is outside the public projection scope")
        refs.append({"id": entry_id, "version": version, "storage": item["data"]["storage"],
                     "sha256": item["data"]["sha256"]})
    return {"format": FORMAT, "kind": "public_asset_references", "refs": refs}


def prepare_payload(store, selected, assets, review_digest=None):
    memory_ids = sorted(ident(entry) for entry in selected)
    asset_versions = sorted(asset_key(entry) for entry in assets)
    if memory_ids or asset_versions:
        if store.level != "public":
            raise Denied("a private or internal Vault can only project aggregate inventory")
    if review_digest is not None and (memory_ids or asset_versions):
        raise Denied("use a separate projection for public and private reviewed records")
    binding = None
    with store.transaction() as db:
        counts = {kind: db.execute("SELECT count(DISTINCT id) FROM revisions WHERE kind=?", (kind,)).fetchone()[0]
                  for kind in RECORD_KINDS}
        files = {**STATIC, "inventory.json":
                 encoded({"format": FORMAT, "kind": "aggregate_inventory", "counts": counts})}
        if memory_ids:
            unique_ordered(memory_ids)
            files[PUBLIC_MEMORY] = encoded(public_memories(store, db, memory_ids))
        if asset_versions:
            unique_ordered(asset_versions)
            files[PUBLIC_ASSETS] = encoded(public_assets(store, db, asset_versions))
        if review_digest is not None:
            from .projection_review import approved_sections

            binding, reviewed = approved_sections(store, db, review_digest)
            files.update(reviewed)
    validate_payload(files, MANIFEST_FORMAT, binding)
    manifest = {"format": MANIFEST_FORMAT, "kind": "git_projection", "files": declared_files(files)}
    if binding is not None:
        manifest["review"] = binding
    return {**files, MANIFEST: encoded(manifest)}


def separated_path(path, workspace, vault):
    root = instance_path(path)
    private_pair(root, workspace)
    private_pair(root, vault)
    return root


def write_projection(root, files):
    if not root.parent.is_dir():
        raise HubError("the projection parent directory must already exist")
    if os.path.lexists(root):
        if not root.is_dir() or read_projection(root) != files:
            raise Conflict("choose a new projection directory for changed content")
        return "unchanged"
    with TemporaryDirectory(dir=root.parent, prefix=".hub-projection-") as staging:
        stage = Path(staging)
        protect_root(stage, create=True)
        for name, contents in sorted(files.items()):
            destination = stage / name
            destination.parent.mkdir(exist_ok=True)
            with destination.open("xb") as output:
                output.write(contents)
                output.flush()
                os.fsync(output.fileno())
        if os.path.lexists(root):
            raise Conflict("the projection path appeared during preparation")
        stage.rename(root)
    return "created"


def differences(previous, current):
    result = []
    for name in sorted(previous.keys() | current.keys()):
        old, new = previous.get(name), current.get(name)
        if old == new:
            continue
        status = "added" if old is None else "removed" if new is None else "changed"
        before = (old or b"").decode("utf-8").splitlines(keepends=True)
        after = (new or b"").decode("utf-8").splitlines(keepends=True)
        change = difflib.unified_diff(before, after, fromfile=f"previous/{name}", tofile=f"current/{name}")
        result.append({"path": name, "status": status, "diff": "".join(change)})
    return result


def build_projection(store, output, *, workspace, selected=(), assets=(), previous=None, review_digest=None):
    """Write a new immutable review snapshot, or verify an unchanged rerun."""
    workspace = instance_path(workspace)
    root = separated_path(output, workspace, store.root)
    baseline = separated_path(previous, workspace, store.root) if previous is not None else None
    if baseline is not None:
        private_pair(root, baseline)
    before = read_projection(baseline) if baseline is not None else {}
    files = prepare_payload(store, selected, assets, review_digest)
    status = write_projection(root, files)
    digest = hash_bytes(files[MANIFEST])
    verified = verify_projection(root, digest)
    return {
        "status": status, "path": str(root), "digest": digest,
        "files": [{**entry, "content": verified[entry["path"]].decode("utf-8")}
                  for entry in declared_files(verified)],
        "changes": differences(before, verified),
    }
