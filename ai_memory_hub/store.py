"""Instance isolation, revision history and transactional import receipts."""

import base64
import contextlib
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

from . import SCHEMA, VERSION
from .model import (
    FEATURES, LEVELS, LISTS, PRESETS, Conflict, Denied, HubError, Missing,
    canonical, digest, document, ident, now, one_of, revision, strict_json,
)

DB_LAYOUT = (
    "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE revisions (
        kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, content TEXT NOT NULL,
        fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (kind, id, revision))""",
    """CREATE TABLE sources (
        id TEXT PRIMARY KEY, adapter TEXT NOT NULL, path TEXT NOT NULL,
        allow_raw INTEGER NOT NULL, grant_id TEXT NOT NULL, granted_at TEXT NOT NULL)""",
    """CREATE TABLE runs (
        id TEXT PRIMARY KEY, feature TEXT NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT, state TEXT NOT NULL, report TEXT)""",
    """CREATE TABLE receipts (
        grant_id TEXT NOT NULL, item TEXT NOT NULL, digest TEXT NOT NULL,
        PRIMARY KEY (grant_id, item))""",
    "CREATE TABLE events (id TEXT PRIMARY KEY, digest TEXT NOT NULL)",
    "CREATE TABLE observations (id TEXT, revision INTEGER, observed_at TEXT, content TEXT)",
)

WINDOWS_ACL = r"""
$ErrorActionPreference = 'Stop'
$path = $env:AI_MEMORY_HUB_ACL_PATH
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = Get-Acl -LiteralPath $path
if ($env:AI_MEMORY_HUB_ACL_CREATE -eq '1') {
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in $acl.GetAccessRules($true,$false,[Security.Principal.SecurityIdentifier])) {
        $acl.RemoveAccessRuleSpecific($rule)
    }
    $acl.SetOwner($sid)
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $path -AclObject $acl
    $acl = Get-Acl -LiteralPath $path
}
$rules = $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])
if (!$acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]) -ne $sid -or
    $rules.Count -ne 1 -or $rules[0].IdentityReference -ne $sid -or
    $rules[0].AccessControlType -ne 'Allow' -or $rules[0].FileSystemRights -ne 'FullControl' -or
    $rules[0].InheritanceFlags -ne ('ContainerInherit,ObjectInherit') -or
    $rules[0].PropagationFlags -ne 'None') { exit 1 }

# Restores or same-volume moves can preserve an unsafe child ACL. Windows users
# can have bypass-traverse rights, so checking the root alone is insufficient.
function Test-VaultChildren($directory) {
    foreach ($child in [IO.Directory]::EnumerateFileSystemEntries($directory)) {
        try {
            $attrs = [IO.File]::GetAttributes($child)
            if ($attrs -band [IO.FileAttributes]::ReparsePoint) { exit 1 }
            $childAcl = if ($attrs -band [IO.FileAttributes]::Directory) {
                [IO.Directory]::GetAccessControl($child)
            } else {
                [IO.File]::GetAccessControl($child)
            }
        } catch {
            $cause = $_.Exception.GetBaseException()
            if ($cause -is [IO.FileNotFoundException] -or $cause -is [IO.DirectoryNotFoundException]) { continue }
            throw
        }
        if (!$childAcl) { exit 1 }
        $childOwner = $childAcl.GetOwner([Security.Principal.SecurityIdentifier])
        if ($childOwner -ne $sid -and $childOwner.Value -ne 'S-1-5-32-544') { exit 1 }
        $childRules = $childAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])
        if ($childRules.Count -ne 1 -or $childRules[0].IdentityReference -ne $sid -or
            $childRules[0].AccessControlType -ne 'Allow' -or $childRules[0].FileSystemRights -ne 'FullControl') { exit 1 }
        if ($attrs -band [IO.FileAttributes]::Directory) {
            if ($childRules[0].InheritanceFlags -ne ('ContainerInherit,ObjectInherit') -or
                $childRules[0].PropagationFlags -ne 'None') { exit 1 }
            if ([IO.Directory]::Exists($child)) { Test-VaultChildren $child }
        }
    }
}
Test-VaultChildren $path
"""


def protect_root(path, create=False):
    if os.name == "nt":
        encoded = base64.b64encode(WINDOWS_ACL.encode("utf-16-le")).decode("ascii")
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        shell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        env = {**os.environ, "AI_MEMORY_HUB_ACL_PATH": str(path), "AI_MEMORY_HUB_ACL_CREATE": str(int(create))}
        env.pop("PSMODULEPATH", None)
        try:
            run = subprocess.run(
                [str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True, env=env, timeout=20, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Denied("could not verify the Windows instance ACL") from exc
        if run.returncode:
            raise Denied("instance requires a Windows ACL restricted to its current owner")
    else:
        info = path.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise Denied("instance must be owned by the current OS user with mode 0700")


def private_directory(path):
    # Modern Windows treats an explicit 0700 specially, adding system and
    # administrator ACEs. New children should inherit the verified root DACL.
    path.mkdir(mode=0o777 if os.name == "nt" else 0o700, exist_ok=True)
    if reparse(path) or not path.is_dir():
        raise Denied("directory is outside the instance boundary")


def reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def checked_relative(root, filename):
    if not isinstance(filename, str) or "\\" in filename or ":" in filename:
        raise Denied("source path must be a relative portable path")
    parts = filename.split("/")
    if any(not part or part in (".", "..") or part.endswith((" ", ".")) for part in parts):
        raise Denied("source path must stay inside its authorized directory")
    path = root
    for part in parts:
        path = path / part
        if reparse(path):
            raise Denied("symbolic links and reparse points are outside the source grant")
    if not path.resolve().is_relative_to(root):
        raise Denied("source path escapes its authorized directory")
    return path


def git_tree(path):
    return any(os.path.lexists(parent / ".git") for parent in (path, *path.parents))


def require_local_path(path):
    if os.name == "nt":
        import ctypes

        if path.drive.startswith("\\\\") or ctypes.windll.kernel32.GetDriveTypeW(
            ctypes.c_wchar_p(path.anchor)
        ) == 4:
            raise Denied("select a local Windows volume")


def instance_path(root):
    original = Path(root).expanduser().absolute()
    require_local_path(original)
    for part in (original, *original.parents):
        if os.path.lexists(part) and reparse(part):
            raise Denied("instance paths must not traverse symbolic links or reparse points")
    path = original.resolve()
    if git_tree(path):
        raise Denied("the instance must live outside Git working trees")
    return path


def document_digest(data):
    return digest({key: value for key, value in data.items() if key != "base_revision"})


def record(row):
    return {
        **strict_json(row["content"]), "revision": row["revision"], "created_at": row["created_at"],
        "record_digest": row["fingerprint"],
    }


class Store:
    def __init__(self, root, initialize=None, switches=None, *, require_fresh=False):
        self.root = instance_path(root)
        if initialize is not None:
            one_of(initialize, LEVELS)
            if switches is None:
                switches = dict(zip(FEATURES, PRESETS["ordinary"]))
            if set(switches) != set(FEATURES) or any(type(value) is not bool for value in switches.values()):
                raise HubError("invalid initial sync policy")
            if not self.root.exists():
                self.root.mkdir(mode=0o700)
                protect_root(self.root, create=True)
            else:
                protect_root(self.root)
        else:
            if not self.root.is_dir():
                raise Missing("instance does not exist; run init")
            protect_root(self.root)
        self.path = self.root / "index.sqlite"
        if os.path.lexists(self.path) and reparse(self.path):
            raise Denied("instance database cannot be a symbolic link")
        if initialize is None and not self.path.is_file():
            raise Missing("instance database does not exist; run init")
        if initialize is not None and not self.path.exists() and any(self.root.iterdir()):
            raise Denied("initialization requires an empty directory")
        try:
            with self.transaction(write=initialize is not None, create=initialize is not None) as db:
                current = db.execute("PRAGMA user_version").fetchone()[0]
                if current == 0 and initialize is not None:
                    if db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]:
                        raise HubError("refusing to initialize an unrelated database")
                    for statement in DB_LAYOUT:
                        db.execute(statement)
                    db.execute("PRAGMA user_version=210")
                    db.executemany("INSERT INTO settings VALUES (?,?)", (
                        ("level", canonical(initialize)), ("schema_version", canonical(SCHEMA)),
                        ("core_version", canonical(VERSION)), ("switches", canonical(switches)),
                    ))
                elif require_fresh:
                    raise Conflict("the Vault was initialized by another process")
                elif current != 210:
                    raise HubError("unsupported database version; use the pinned core or a documented migration")
                if self.setting(db, "schema_version") != SCHEMA:
                    raise HubError("incompatible instance schema")
                self.level = one_of(self.setting(db, "level"), LEVELS)
                if initialize is not None and self.level != initialize:
                    raise Conflict("the existing instance has a different sensitivity boundary")
        except sqlite3.DatabaseError as exc:
            raise HubError("instance database unavailable or invalid") from exc

    @contextlib.contextmanager
    def transaction(self, write=False, create=False):
        uri = self.path.as_uri() + ("?mode=rwc" if create else "?mode=rw")
        db = sqlite3.connect(uri, uri=True, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def setting(db, key):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            raise HubError("incomplete instance settings")
        return strict_json(row["value"])

    def settings(self, feature=None, enabled=None, preset=None):
        with self.transaction(write=feature is not None or preset is not None) as db:
            switches = self.setting(db, "switches")
            if preset is not None:
                switches = dict(zip(FEATURES, PRESETS[one_of(preset, PRESETS)]))
            if feature is not None:
                switches[one_of(feature, FEATURES)] = enabled
            if feature is not None or preset is not None:
                db.execute("UPDATE settings SET value=? WHERE key='switches'", (canonical(switches),))
        return {
            "schema_version": SCHEMA, "core_version": VERSION, "sensitivity": self.level,
            "switches": switches, "weekly_preference": {"day": "SU", "time": "23:00", "timezone": "Asia/Shanghai"},
            "scheduler": "not_verified",
        }

    def require(self, db, feature):
        if not self.setting(db, "switches")[one_of(feature, FEATURES)]:
            raise Denied(f"{feature} is disabled")

    @staticmethod
    def get(db, kind, entry_id, revision=None):
        query = "SELECT * FROM revisions WHERE kind=? AND id=?"
        params = [kind, ident(entry_id)]
        if revision is not None:
            if type(revision) is not int or not 1 <= revision < 2**63:
                raise HubError("invalid revision")
            query += " AND revision=?"
            params.append(revision)
        row = db.execute(query + " ORDER BY revision DESC LIMIT 1", params).fetchone()
        return record(row) if row else None

    @staticmethod
    def latest(db, kind):
        rows = db.execute(
            """SELECT r.* FROM revisions r JOIN (
                SELECT id, max(revision) revision FROM revisions WHERE kind=? GROUP BY id
            ) latest USING (id, revision) WHERE r.kind=? ORDER BY r.id""",
            (kind, kind),
        )
        return [record(row) for row in rows]

    @staticmethod
    def history(db, kind, entry_id):
        rows = db.execute(
            "SELECT * FROM revisions WHERE kind=? AND id=? ORDER BY revision",
            (kind, ident(entry_id)),
        )
        return [record(row) for row in rows]

    @staticmethod
    def session_revisions(db):
        for row in db.execute("SELECT * FROM revisions WHERE kind='session' ORDER BY id, revision"):
            yield record(row)

    def session_view(self, db, item, layer, raw_consent=False):
        if layer != "L3":
            return view_session(item, layer)
        if not raw_consent or self.level not in ("private", "restricted"):
            raise Denied("L3 requires separate read consent within a private or restricted instance")
        rows = db.execute(
            """SELECT * FROM revisions WHERE kind='session' AND id=? AND revision<=?
            ORDER BY revision DESC""", (item["id"], item["revision"]),
        )
        for row in rows:
            raw = record(row)
            if "messages" in raw["data"]:
                result = view_session(item, "L0")
                result.update({
                    "layer": "L3", "source": raw["source"], "messages": raw["data"]["messages"],
                    "raw_revision": raw["revision"], "raw_record_digest": raw["record_digest"],
                    "raw_created_at": raw["created_at"],
                })
                return result
        raise Missing("raw messages are unavailable at the requested session revision")

    @staticmethod
    def append(db, kind, entry_id, content, fingerprint, previous):
        version = revision(1 + (previous["revision"] if previous else 0))
        db.execute(
            "INSERT INTO revisions VALUES (?,?,?,?,?,?)",
            (kind, entry_id, version, canonical(content), fingerprint, now()),
        )
        return {"status": "updated" if previous else "created", "kind": kind, "id": entry_id, "revision": version}

    @staticmethod
    def resolve_refs(db, refs):
        for ref in refs:
            if "version" not in ref:
                asset = Store.get(db, "asset", ref["asset_id"])
                if asset:
                    ref["version"] = asset["revision"]

    def ingest(self, db, data, allow_raw=False, allow_review=False):
        document(data, self.level, allow_raw, allow_review)
        kind, entry_id = data["kind"], data["id"]
        previous = self.get(db, kind, entry_id)
        fingerprint = document_digest(data)
        base = data.get("base_revision", 0)
        current = previous["revision"] if previous else 0
        if base < current:
            replay = self.get(db, kind, entry_id, base + 1)
            if replay and replay["record_digest"] == fingerprint:
                return {"status": "unchanged", "kind": kind, "id": entry_id, "revision": replay["revision"]}
        if base != current:
            raise Conflict("base revision differs from the current revision")
        if kind == "memory" and previous and previous["data"]["status"] != "candidate" and not allow_review:
            raise Denied("a reviewed memory needs a confirmed review transition or a separate candidate ID")
        fields = strict_json(canonical(data["data"]))
        result = {key: data[key] for key in ("kind", "id", "schema_version", "sensitivity", "source")}
        if kind == "session":
            old_fields = previous["data"] if previous else {}
            patch = fields.pop("append", None)
            checkpoint = fields.get("checkpoint")
            origins = previous.get("checkpoint_sources", []) if previous else []
            if patch is not None:
                if not old_fields.get("checkpoint"):
                    raise Conflict("append requires an existing L2 checkpoint")
                checkpoint = strict_json(canonical(old_fields["checkpoint"]))
                self.resolve_refs(db, patch.get("file_refs", []))
                for key, value in patch.items():
                    if key in LISTS:
                        checkpoint[key].extend(value)
                    else:
                        checkpoint[key] = value
            if checkpoint is not None:
                if patch is None:
                    self.resolve_refs(db, checkpoint["file_refs"])
                fields["checkpoint"] = checkpoint
                origins = (origins if patch is not None else []) + [{"revision": current + 1, "source": data["source"]}]
            elif "checkpoint" in old_fields:
                fields["checkpoint"] = old_fields["checkpoint"]
            for key in ("summary", "project_id"):
                if key in old_fields:
                    fields.setdefault(key, old_fields[key])
            result["checkpoint_sources"] = origins
        elif kind == "project":
            self.resolve_refs(db, fields.get("file_refs", []))
        if kind == "memory" and previous and "classification" in previous["data"]:
            fields.setdefault("classification", previous["data"]["classification"])
        result["data"] = fields
        return self.append(db, kind, entry_id, result, fingerprint, previous)


def view_session(item, layer):
    one_of(layer, ("L0", "L1", "L2"))
    fields = item["data"]
    result = {key: value for key, value in item.items() if key not in ("data", "checkpoint_sources")}
    result.update({"layer": layer, "title": fields["title"], "project_id": fields.get("project_id")})
    if layer in ("L1", "L2"):
        result["summary"] = fields.get("summary")
    if layer == "L2":
        result["checkpoint"] = fields.get("checkpoint")
        result["checkpoint_sources"] = item["checkpoint_sources"]
    return result


def memory_review(items):
    review = {"candidates": 0, "duplicates": [], "conflicts": []}
    by_key = {}
    for item in items:
        fields = item["data"]
        if fields["status"] in ("accepted", "candidate"):
            by_key.setdefault(fields["key"].strip().casefold(), []).append(item)
    for group in by_key.values():
        candidates = [item for item in group if item["data"]["status"] == "candidate"]
        review["candidates"] += len(candidates)
        for candidate in candidates:
            for peer in group:
                if candidate["id"] == peer["id"]:
                    continue
                reason = "duplicates" if candidate["data"]["claim"].strip() == peer["data"]["claim"].strip() else "conflicts"
                review[reason].append({"candidate": candidate["id"], "other": peer["id"]})
    return review
