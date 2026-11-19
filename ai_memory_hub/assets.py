"""Content-addressed files and separately observed external references."""

import hashlib
import mimetypes
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, ContextManager, NamedTuple, Protocol

from . import SCHEMA
from .model import (
    Conflict, Denied, HubError, Missing, canonical, digest, evidence, external_url, ident, iso_date,
    no_credentials, now, one_of, open_source, revision, strict_json, text,
)
from .store import Store, git_tree, private_directory, record, reparse

SHA256 = re.compile(r"[0-9a-f]{64}")
LINK_STATES = ("available", "missing", "permission_denied", "unreachable")
GIT_TEXT_EXTENSIONS = {".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".py", ".js", ".ts", ".html", ".css"}
GIT_TEXT_LIMIT = 8 * 1024 * 1024


class Staged(NamedTuple):
    path: Path
    sha256: str
    size: int


class BlobStore(Protocol):
    def stage(self, source: Path) -> ContextManager[Staged]: ...
    def stage_stream(self, source: BinaryIO, limit: int) -> ContextManager[Staged]: ...
    def publish(self, staged: Staged) -> None: ...
    def check(self, sha256: str) -> str: ...
    def read_small(self, sha256: str, limit: int) -> bytes: ...
    def open_blob(self, sha256: str) -> BinaryIO: ...


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class LocalVault:
    def __init__(self, root):
        self.directory = root / "blobs"

    def _path(self, sha256):
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            raise HubError("invalid blob SHA-256")
        if os.path.lexists(self.directory) and reparse(self.directory):
            raise Denied("blob directory is outside the instance boundary")
        path = self.directory / sha256
        if os.path.lexists(path) and reparse(path):
            raise Denied("blob must be a regular file under the instance boundary")
        return path

    @contextmanager
    def stage(self, source):
        with open_source(source) as origin:
            before = os.fstat(origin.fileno())
            with self.stage_stream(origin, before.st_size) as staged:
                after = os.fstat(origin.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or staged.size != after.st_size:
                    raise Conflict("asset source changed while reading; retry with a stable copy")
                yield staged

    @contextmanager
    def stage_stream(self, source, limit):
        private_directory(self.directory)
        with tempfile.NamedTemporaryFile(dir=self.directory, prefix=".partial-", delete=False) as stream:
            path = Path(stream.name)
            sha = hashlib.sha256()
            size = 0
            try:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    size += len(chunk)
                    if size > limit:
                        raise Conflict("asset exceeds the authorized size")
                    sha.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                yield Staged(path, sha.hexdigest(), size)
            finally:
                stream.close()
                path.unlink(missing_ok=True)

    def publish(self, staged):
        path = self._path(staged.sha256)
        state = self.check(staged.sha256)
        if state in ("missing", "corrupt"):
            os.replace(staged.path, path)
            if os.name != "nt":
                handle = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(handle)
                finally:
                    os.close(handle)
        elif state != "available":
            raise Denied("blob cannot be published")

    def check(self, sha256):
        try:
            path = self._path(sha256)
            return "available" if file_hash(path) == sha256 else "corrupt"
        except FileNotFoundError:
            return "missing"
        except (PermissionError, Denied):
            return "permission_denied"
        except (IsADirectoryError, NotADirectoryError):
            return "corrupt"
        except OSError:
            return "unreachable"

    def open_blob(self, sha256):
        return self._path(sha256).open('rb')

    def read_small(self, sha256, limit):
        with self._path(sha256).open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise Denied("repository export exceeds the small-file limit")
        if hashlib.sha256(data).hexdigest() != sha256:
            raise Conflict("blob digest mismatch")
        return data


def asset_fields(asset_id, name, project_id=None, session_id=None):
    name = text(name, 255)
    if name.endswith((" ", ".")) or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name):
        raise HubError("asset name must be a portable filename")
    return {
        "id": ident(asset_id),
        "name": name,
        "media_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
        "project_id": ident(project_id) if project_id is not None else None,
        "session_id": ident(session_id) if session_id is not None else None,
    }


def save_asset(store, db, metadata, content, source, base=None, managed_by=None):
    entry_id = metadata["id"]
    evidence(source)
    old = store.get(db, "asset", entry_id)
    previous_owner = old.get("managed_by") if old else None
    if old and previous_owner != managed_by:
        raise Conflict("asset ID belongs to a different writer")
    value = {
        "schema_version": SCHEMA, "kind": "asset", "id": entry_id,
        "source": source, "sensitivity": store.level, "data": {**metadata, **content},
    }
    if managed_by is not None:
        value["managed_by"] = managed_by
    fingerprint = digest(value)
    if base is not None:
        revision(base, 0)
    current = old["revision"] if old else 0
    if managed_by is None and (base or 0) < current:
        replay = store.get(db, "asset", entry_id, (base or 0) + 1)
        if replay and replay["record_digest"] == fingerprint:
            return {"status": "unchanged", "kind": "asset", "id": entry_id, "revision": replay["revision"]}
    if old and old["record_digest"] == fingerprint:
        return {"status": "unchanged", "kind": "asset", "id": entry_id, "revision": current}
    if managed_by is None and (base or 0) != current:
        raise Conflict("asset base revision differs from the current revision")
    return store.append(db, "asset", entry_id, value, fingerprint, old)


def put_file(store, db, blobs, staged, name, source, asset_id=None, project_id=None,
             session_id=None, base=None, managed_by=None):
    fields = asset_fields(asset_id or "asset-" + staged.sha256, name, project_id, session_id)
    content = {
        "storage": "vault", "address": "vault:sha256:" + staged.sha256,
        "sha256": staged.sha256, "size": staged.size,
    }
    result = save_asset(store, db, fields, content, source, base, managed_by)
    blobs.publish(staged)
    return result


def put_link(store, db, url, name, source, asset_id=None, project_id=None, session_id=None,
             base=None, expires_at=None, managed_by=None):
    external_url(url)
    entry_id = asset_id or "link-" + uuid.uuid5(uuid.NAMESPACE_URL, url).hex
    fields = asset_fields(entry_id, name, project_id, session_id)
    content = {
        "storage": "external", "address": url, "sha256": None, "size": None,
        "expires_at": iso_date(expires_at) if expires_at else None,
    }
    return save_asset(store, db, fields, content, source, base, managed_by)


def observe_link(db, entry_id, version, state, source):
    item = Store.get(db, "asset", entry_id, version)
    if item is None:
        raise Missing("asset revision not found")
    if item["data"]["storage"] != "external":
        raise HubError("only external links have observations")
    observation = {"status": one_of(state, LINK_STATES), "source": evidence(source), "observed_at": now()}
    db.execute("INSERT INTO observations VALUES (?,?,?,?)",
               (entry_id, item["revision"], observation["observed_at"], canonical(observation)))
    return observation


def availability(db, blobs, item):
    fields = item["data"]
    if fields["storage"] == "vault":
        return {"status": blobs.check(fields["sha256"]), "basis": "local_sha256"}
    if fields["expires_at"] and iso_date(now()) >= fields["expires_at"]:
        return {"status": "expired", "basis": "declared_expiry"}
    row = db.execute(
        """SELECT content FROM observations WHERE id=? AND revision=?
        ORDER BY rowid DESC LIMIT 1""", (item["id"], item["revision"]),
    ).fetchone()
    if row is None:
        return {"status": "unverified", "basis": "not_probed"}
    return {**strict_json(row["content"]), "basis": "reported_observation"}


def references(db, entry_id):
    rows = db.execute(
        "SELECT * FROM revisions WHERE kind IN ('session','project') ORDER BY kind,id,revision"
    )
    results = []
    for row in rows:
        item = record(row)
        fields = item["data"]
        refs = fields.get("file_refs", []) + fields.get("checkpoint", {}).get("file_refs", [])
        for ref in refs:
            if ref["asset_id"] == entry_id:
                results.append({
                    "kind": item["kind"], "id": item["id"], "revision": item["revision"],
                    "asset_version": ref.get("version"),
                })
    versions = Store.history(db, "asset", entry_id)
    return {
        "references": results,
        "asset_associations": [
            {"version": version["revision"], "project_id": version["data"]["project_id"],
             "session_id": version["data"]["session_id"]}
            for version in versions
        ],
    }


def export_public_text(store, blobs, item, destination):
    if store.level != "public" or item["data"]["storage"] != "vault":
        raise Denied("Git export requires a public instance and a stored file")
    target = Path(destination).expanduser().absolute()
    if not git_tree(target.parent) or not target.parent.is_dir():
        raise HubError("choose an existing destination directory inside a Git working tree")
    for part in (target.parent, *target.parent.parents):
        if reparse(part) or part.name.casefold() == ".git":
            raise Denied("Git export refuses redirected paths and Git metadata")
    if (
        target.suffix.lower() not in GIT_TEXT_EXTENSIONS
        or Path(item["data"]["name"]).suffix.lower() not in GIT_TEXT_EXTENSIONS
        or target.name.startswith(".")
    ):
        raise Denied("Git export supports explicitly approved small UTF-8 text assets")
    data = blobs.read_small(item["data"]["sha256"], GIT_TEXT_LIMIT)
    no_credentials(data.decode("utf-8"))
    if b"\x00" in data:
        raise Denied("Git export refuses binary content")
    with target.open("xb") as stream:
        stream.write(data)
    return {"status": "written", "path": str(target), "sha256": item["data"]["sha256"]}


def retrieve_blob(root, blobs, expected, name):
    directory = root / "retrieved"
    private_directory(directory)
    filename = uuid.uuid4().hex + Path(name).suffix
    temporary = directory / (".incomplete-" + filename)
    try:
        with blobs.open_blob(expected) as origin, temporary.open("xb") as target:
            sha = hashlib.sha256()
            for chunk in iter(lambda: origin.read(1024 * 1024), b""):
                sha.update(chunk)
                target.write(chunk)
            if sha.hexdigest() != expected:
                raise HubError("blob integrity check failed")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, directory / filename)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "retrieved", "path": str(directory / filename), "sha256": expected}
