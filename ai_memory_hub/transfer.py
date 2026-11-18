"""Offline, explicitly authorized project transfer across independent Vaults."""

import hashlib
import os
import stat
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from zipfile import BadZipFile, ZIP_STORED, ZipFile

from . import SCHEMA
from .adapters import local_input
from .assets import SHA256, asset_fields, retrieve_blob
from .handoff import build_handoff
from .model import (
    Conflict, Denied, HubError, Missing, canonical, digest, evidence, ident, iso_date,
    no_credentials, one_of, revision, seq, shape, strict_json, text,
)
from .store import checked_relative, private_directory

FORMAT = "2.2"
MAX_FILES = 256
MAX_CONTEXT = 16 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
MAX_BYTES = 1024 * 1024 * 1024
MANIFEST = "manifest.json"
CONTEXT = "handoff.json"
CHUNK = 1024 * 1024


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def checksum(value):
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise HubError("invalid SHA-256")
    return value


def asset_key(value):
    entry_id, separator, edition = value.partition("@")
    if separator != "@" or not edition.isascii() or not edition.isdigit() or len(edition) > 19:
        raise HubError("asset selection must be ID@REV")
    return ident(entry_id), revision(int(edition))


def file_key(ref):
    return ident(ref["id"]), revision(ref["version"]) if ref["version"] is not None else None


def checked_context(context, level):
    fields = ("schema_version", "kind", "project_id", "sensitivity", "created_at", "project",
              "sessions", "timeline", "files", "missing_l2", "recipient_instruction")
    shape(context, fields)
    ident(context["project_id"])
    one_of(context["schema_version"], (SCHEMA,))
    one_of(context["kind"], ("project_handoff",))
    if context["sensitivity"] != level:
        raise Denied("the handoff and recipient Vault must have the same sensitivity")
    iso_date(context["created_at"])
    text(context["recipient_instruction"])
    for missing in seq(context["missing_l2"]):
        ident(missing)
    project = context["project"]
    if project is not None:
        check_scope(project, "project", level)
        if project["id"] != context["project_id"] or not isinstance(project.get("data"), dict):
            raise HubError("project record does not match the handoff")
    for session in seq(context["sessions"]):
        check_scope(session, "session", level)
        if session.get("layer") != "L2" or session.get("project_id") != context["project_id"]:
            raise HubError("session does not match the handoff project or layer")
    for entry in seq(context["timeline"]):
        shape(entry, ("kind", "id", "revision", "created_at", "source", "record_digest"))
        one_of(entry["kind"], ("session", "project"))
        ident(entry["id"])
        revision(entry["revision"])
        evidence(entry["source"])
        iso_date(entry["created_at"])
        checksum(entry["record_digest"])
    pending = [context]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if {"messages", "raw_messages", "raw_text"} & node.keys() or node.get("layer") == "L3":
                raise Denied("raw messages cannot be transferred")
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    no_credentials(canonical(context))
    refs = {}
    for ref in seq(context["files"]):
        if not isinstance(ref, dict) or "id" not in ref or "version" not in ref:
            raise HubError("malformed handoff file reference")
        key = file_key(ref)
        if key in refs:
            raise HubError("duplicate handoff file reference")
        refs[key] = ref
    return refs


def check_scope(record, kind, level):
    if not isinstance(record, dict) or record.get("kind") != kind:
        raise HubError("invalid handoff record")
    if record.get("sensitivity") != level:
        raise Denied("record sensitivity is outside this handoff")
    ident(record.get("id"))
    revision(record.get("revision"))
    evidence(record.get("source"))
    checksum(record.get("record_digest"))


def selected_blobs(manifest, refs):
    """Return unique payload digests after matching every selection to the handoff."""
    items = seq(manifest["assets"])
    if len(items) > MAX_FILES:
        raise HubError("too many attached file versions")
    blobs, seen = {}, set()
    for item in items:
        shape(item, ("id", "version", "sha256", "size"))
        key = ident(item["id"]), revision(item["version"])
        sha = checksum(item["sha256"])
        size = item["size"]
        if type(size) is not int or not 0 <= size <= MAX_BYTES:
            raise HubError("invalid transfer file size")
        ref = refs.get(key)
        observed = ref.get("availability") if ref else None
        if (not ref or ref.get("storage") != "vault" or ref.get("sha256") != sha
                or type(ref.get("size")) is not int or ref["size"] != size or key in seen
                or not isinstance(observed, dict) or observed.get("status") != "available"):
            raise HubError("attached file does not match an available, unique Vault reference")
        asset_fields(key[0], ref.get("name"))
        if sha in blobs and blobs[sha] != size:
            raise HubError("inconsistent sizes for one transfer digest")
        blobs[sha] = size
        seen.add(key)
    if sum(blobs.values()) > MAX_BYTES:
        raise HubError("attached files exceed the transfer size limit")
    return blobs


@contextmanager
def atomic_file(target):
    private_directory(target.parent)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".incomplete-", delete=False) as stream:
        temp = Path(stream.name)
        try:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(temp, target)
        finally:
            stream.close()
            temp.unlink(missing_ok=True)


def write_blob(archive, blobs, sha, size):
    hasher = hashlib.sha256()
    received = 0
    with blobs.open_blob(sha) as source, archive.open("blobs/" + sha, "w", force_zip64=True) as target:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            received += len(chunk)
            if received > size:
                raise Conflict("source bytes changed during transfer")
            hasher.update(chunk)
            target.write(chunk)
    if received != size or hasher.hexdigest() != sha:
        raise Conflict("source bytes failed transfer integrity check")


def pack_transfer(store, blobs, project_id, selections):
    keys = sorted({asset_key(value) for value in selections})
    with store.transaction() as db:
        context = build_handoff(store, db, blobs, project_id)
        refs = checked_context(context, store.level)
        assets = []
        for entry_id, edition in keys:
            ref = refs.get((entry_id, edition))
            if not ref or ref.get("storage") != "vault":
                raise Denied("select an exact stored file revision referenced by this project")
            if ref["availability"]["status"] != "available":
                raise Missing("selected Vault file is no longer available")
            assets.append({"id": entry_id, "version": edition, "sha256": ref["sha256"], "size": ref["size"]})
    context_bytes = canonical(context).encode("utf-8")
    if len(context_bytes) > MAX_CONTEXT:
        raise HubError("handoff context exceeds transfer limit")
    manifest = {
        "format": FORMAT, "sensitivity": store.level, "context_sha256": hash_bytes(context_bytes), "assets": assets,
    }
    selected = selected_blobs(manifest, refs)
    identifier = digest(manifest)
    output = store.root / "outgoing" / (identifier + ".zip")
    with atomic_file(output) as file, ZipFile(file, "w", compression=ZIP_STORED) as archive:
        archive.writestr(MANIFEST, canonical(manifest).encode("utf-8"))
        archive.writestr(CONTEXT, context_bytes)
        for sha, size in selected.items():
            write_blob(archive, blobs, sha, size)
    return {"status": "transfer_ready", "id": identifier, "path": str(output),
            "attached_versions": len(assets), "unique_blobs": len(selected), "network_transfer": "manual"}


def decode_json(contents):
    try:
        return strict_json(contents.decode("utf-8"))
    except (UnicodeError, RecursionError) as exc:
        raise HubError("transfer metadata is not supported UTF-8 JSON") from exc


def metadata(archive, name, limit):
    try:
        member = archive.getinfo(name)
    except KeyError as exc:
        raise HubError("transfer metadata is missing") from exc
    if member.file_size > limit:
        raise HubError("transfer metadata exceeds its limit")
    with archive.open(member) as stream:
        contents = stream.read(limit + 1)
    if len(contents) != member.file_size:
        raise HubError("inconsistent transfer metadata size")
    return contents


def members(archive):
    entries = {}
    if len(archive.infolist()) > MAX_FILES + 2:
        raise HubError("transfer ZIP has too many members")
    for member in archive.infolist():
        name = member.filename
        regular = stat.S_IFMT(member.external_attr >> 16) in (0, stat.S_IFREG)
        if (name != member.orig_filename or name in entries or not regular or member.is_dir() or member.flag_bits & 1
                or member.compress_type != ZIP_STORED):
            raise HubError("transfer ZIP has a duplicate, encrypted, compressed or irregular member")
        if name not in (MANIFEST, CONTEXT):
            if not name.startswith("blobs/"):
                raise HubError("unexpected transfer ZIP member")
            checksum(name.removeprefix("blobs/"))
        entries[name] = member
    return entries


def receive_transfer(store, blobs, path):
    with store.transaction(write=True) as db:
        store.require(db, "handoff")
        path = local_input(path.expanduser().absolute())
        if not path.is_file():
            raise Missing("choose an existing transfer ZIP")
        if path.stat().st_size > MAX_BYTES + MAX_CONTEXT + MAX_MANIFEST + CHUNK:
            raise HubError("transfer ZIP exceeds its size limit")
        try:
            return receive_package(store, blobs, path)
        except (BadZipFile, NotImplementedError) as exc:
            raise HubError("invalid or unsupported transfer ZIP") from exc


def receive_package(store, blobs, path):
    with ZipFile(path) as archive:
        entries = members(archive)
        manifest = decode_json(metadata(archive, MANIFEST, MAX_MANIFEST))
        shape(manifest, ("format", "sensitivity", "context_sha256", "assets"))
        one_of(manifest["format"], (FORMAT,))
        if manifest["sensitivity"] != store.level:
            raise Denied("the sender and recipient Vault must have the same sensitivity")
        context_bytes = metadata(archive, CONTEXT, MAX_CONTEXT)
        if checksum(manifest["context_sha256"]) != hash_bytes(context_bytes):
            raise Conflict("transfer context digest mismatch")
        context = decode_json(context_bytes)
        if canonical(context).encode("utf-8") != context_bytes:
            raise HubError("handoff JSON must use canonical transfer encoding")
        refs = checked_context(context, store.level)
        selected = selected_blobs(manifest, refs)
        expected = {MANIFEST, CONTEXT} | {"blobs/" + sha for sha in selected}
        if set(entries) != expected:
            raise HubError("transfer ZIP members do not match the approved manifest")
        identifier = digest(manifest)
        receipt = store.root / "received" / (identifier + ".json")
        existed = os.path.lexists(receipt)
        if existed:
            load_receipt(store, identifier)
        needs_repair = False
        with ExitStack() as staged_files:
            verified = []
            for sha, size in selected.items():
                member = entries["blobs/" + sha]
                if member.file_size != size:
                    raise Conflict("transfer size mismatch")
                with archive.open(member) as origin:
                    staged = staged_files.enter_context(blobs.stage_stream(origin, size))
                if (staged.sha256, staged.size) != (sha, size):
                    raise Conflict("transfer file digest mismatch")
                needs_repair |= blobs.check(sha) != "available"
                verified.append(staged)
            for staged in verified:
                blobs.publish(staged)
        if not existed:
            with atomic_file(receipt) as file:
                file.write(canonical({"manifest": manifest, "context": context}).encode("utf-8"))
    outcome = "restored" if existed and needs_repair else "unchanged" if existed else "received"
    return {"status": outcome, "id": identifier, "attached_versions": len(manifest["assets"])}


def load_receipt(store, identifier):
    checksum(identifier)
    file = checked_relative(store.root, f"received/{identifier}.json")
    if not file.is_file():
        raise Missing("transfer receipt is unavailable")
    with file.open("rb") as source:
        contents = source.read(MAX_CONTEXT + MAX_MANIFEST + CHUNK)
    receipt = decode_json(contents)
    shape(receipt, ("manifest", "context"))
    manifest, context = receipt["manifest"], receipt["context"]
    shape(manifest, ("format", "sensitivity", "context_sha256", "assets"))
    one_of(manifest["format"], (FORMAT,))
    if (digest(manifest) != identifier or manifest["sensitivity"] != store.level
            or manifest["context_sha256"] != hash_bytes(canonical(context).encode("utf-8"))):
        raise Conflict("stored transfer receipt does not match its digests")
    refs = checked_context(context, store.level)
    selected_blobs(manifest, refs)
    return manifest, context


def inspect_transfer(store, blobs, identifier):
    with store.transaction() as db:
        store.require(db, "handoff")
        manifest, context = load_receipt(store, identifier)
    attached = {(item["id"], item["version"]): item["sha256"] for item in manifest["assets"]}
    for ref in context["files"]:
        if "availability" in ref:
            ref["sender_availability"] = ref.pop("availability")
        sha = attached.get(file_key(ref))
        ref["recipient_status"] = blobs.check(sha) if sha else "not_transferred"
    return {"status": "inspected", "id": identifier, "context": context}


def retrieve_transfer(store, blobs, identifier, selection):
    key = asset_key(selection)
    with store.transaction() as db:
        store.require(db, "handoff")
        manifest, context = load_receipt(store, identifier)
    refs = {file_key(ref): ref for ref in context["files"]}
    for item in manifest["assets"]:
        if (item["id"], item["version"]) == key:
            return retrieve_blob(store.root, blobs, item["sha256"], refs[key]["name"])
    raise Denied("file revision was not transferred to this Vault")
