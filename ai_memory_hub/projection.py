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
from .store import checked_relative, instance_path, protect_root
from .transfer import asset_key, checksum, hash_bytes
from .workspace import private_pair

FORMAT = "1.0"
MANIFEST = "projection.json"
README = b"""# AI Memory Hub Git projection

This directory contains reviewed publication data. The private Workspace, Vault,
raw conversations, machine binding, and stored file bytes remain local.
Verify the manifest and review the exact preview before publishing.
"""
REQUIRED = {"README.md": "static", "inventory.json": "aggregate_metadata"}
OPTIONAL = {"shared-memory.json": "public_reviewed_memory", "asset-refs.json": "public_version_references"}
CLASSES = {**REQUIRED, **OPTIONAL, MANIFEST: "manifest"}
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


VALIDATORS = {"inventory.json": validate_inventory, "shared-memory.json": validate_memories,
              "asset-refs.json": validate_assets}


def validate_payload(files):
    if set(REQUIRED) - files.keys() or files.keys() - (REQUIRED.keys() | OPTIONAL.keys()):
        raise Denied("the projection may only contain its approved file classes")
    if any(len(contents) > MAX_FILE for contents in files.values()):
        raise Denied("projection file exceeds the 512 KiB inspection limit")
    if files["README.md"] != README:
        raise Denied("the projection README must match the built-in text")
    for name, validate in VALIDATORS.items():
        if name in files:
            validate(json_value(files[name]))


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


def verify_projection_files(files, expected_digest):
    """Validate a complete projection tree already read into trusted memory."""
    if MANIFEST not in files or files.keys() - CLASSES.keys():
        raise Denied("unexpected or missing projection members")
    if any(type(contents) is not bytes or len(contents) > MAX_FILE for contents in files.values()):
        raise Denied("projection files must be bytes within the 512 KiB inspection limit")
    manifest_bytes = files[MANIFEST]
    if expected_digest is not None and hash_bytes(manifest_bytes) != checksum(expected_digest):
        raise Conflict("projection differs from the approved digest")
    manifest = json_value(manifest_bytes)
    shape(manifest, ("format", "kind", "files"))
    one_of(manifest["format"], (FORMAT,))
    one_of(manifest["kind"], ("git_projection",))
    payload = {name: contents for name, contents in files.items() if name != MANIFEST}
    validate_payload(payload)
    if manifest["files"] != declared_files(payload):
        raise Conflict("projection contents do not match the manifest")
    return dict(files)


def read_projection(root, expected_digest=None):
    names = {file.name for file in root.iterdir()}
    if MANIFEST not in names or names - CLASSES.keys():
        raise Denied("unexpected or missing projection members")
    files = {name: read_member(root, name) for name in names}
    if names != {file.name for file in root.iterdir()}:
        raise Conflict("projection members changed during verification")
    return verify_projection_files(files, expected_digest)


def verify_projection(path, expected_digest):
    """Return a byte snapshot of exactly the independently reviewed projection."""
    return read_projection(instance_path(path), checksum(expected_digest))


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


def prepare_payload(store, selected, assets):
    memory_ids = sorted(ident(entry) for entry in selected)
    asset_versions = sorted(asset_key(entry) for entry in assets)
    if memory_ids or asset_versions:
        if store.level != "public":
            raise Denied("a private or internal Vault can only project aggregate inventory")
    with store.transaction() as db:
        counts = {kind: db.execute("SELECT count(DISTINCT id) FROM revisions WHERE kind=?", (kind,)).fetchone()[0]
                  for kind in RECORD_KINDS}
        files = {"README.md": README, "inventory.json":
                 encoded({"format": FORMAT, "kind": "aggregate_inventory", "counts": counts})}
        if memory_ids:
            unique_ordered(memory_ids)
            files["shared-memory.json"] = encoded(public_memories(store, db, memory_ids))
        if asset_versions:
            unique_ordered(asset_versions)
            files["asset-refs.json"] = encoded(public_assets(store, db, asset_versions))
    validate_payload(files)
    manifest = {"format": FORMAT, "kind": "git_projection", "files": declared_files(files)}
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
            with (stage / name).open("xb") as output:
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


def build_projection(store, output, *, workspace, selected=(), assets=(), previous=None):
    """Write a new immutable review snapshot, or verify an unchanged rerun."""
    workspace = instance_path(workspace)
    root = separated_path(output, workspace, store.root)
    baseline = separated_path(previous, workspace, store.root) if previous is not None else None
    if baseline is not None:
        private_pair(root, baseline)
    before = read_projection(baseline) if baseline is not None else {}
    files = prepare_payload(store, selected, assets)
    status = write_projection(root, files)
    digest = hash_bytes(files[MANIFEST])
    verified = verify_projection(root, digest)
    return {
        "status": status, "path": str(root), "digest": digest,
        "files": [{**entry, "content": verified[entry["path"]].decode("utf-8")}
                  for entry in declared_files(verified)],
        "changes": differences(before, verified),
    }
