"""Explicitly granted sources. Importers never authenticate to providers."""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import zipfile
from typing import Iterator, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from . import SCHEMA
from .model import Denied, HubError, Missing, ident, now, one_of, read_json, seq, shape, strict_json, text
from .store import checked_relative, reparse, require_local_path


@dataclass(frozen=True)
class Capabilities:
    read: bool
    export: bool
    files: bool
    write: bool
    automatic_trigger: bool
    scheduled_execution: bool


@dataclass(frozen=True)
class Item:
    key: str
    kind: str
    value: dict


class Adapter(Protocol):
    capabilities: Capabilities

    def items(self, root: Path, level: str, allow_raw: bool) -> Iterator[Item]: ...


MANIFEST = "memory-hub.json"
CHATGPT_SHARD = re.compile(r"conversations(?:[-_]\d+)?\.json")
MAX_SHARD = 128 * 1024 * 1024
MAX_EXPORT = 512 * 1024 * 1024


def local_input(path):
    require_local_path(path)
    for part in (path, *path.parents):
        if reparse(part):
            raise Denied("authorized source must not traverse symbolic links or reparse points")
    return path


def manifest_item(value):
    shape(value, ("key", "kind"), ("path", "name", "project_id", "session_id", "origin", "url", "expires_at", "asset_id"))
    key = ident(value["key"])
    kind = one_of(value["kind"], ("record", "file", "link"))
    common = ("key", "kind")
    if kind == "record":
        shape(value, common + ("path",))
    else:
        origin = ("name", "project_id", "session_id", "origin", "asset_id")
        if kind == "file":
            shape(value, common + ("path",), origin)
        else:
            shape(value, common + ("url", "name"), ("expires_at", "project_id", "session_id", "origin", "asset_id"))
        if "asset_id" in value:
            ident(value["asset_id"])
        if "origin" in value:
            one_of(value["origin"], ("user_upload", "ai_generated", "workspace_artifact"))
    return Item(key, kind, value)


class ManifestAdapter:
    capabilities = Capabilities(True, False, True, False, False, False)

    def items(self, root, level, allow_raw):
        data = read_json(checked_relative(root, MANIFEST))
        shape(data, ("schema_version", "items"))
        one_of(data["schema_version"], (SCHEMA,))
        items = seq(data["items"])
        counts = Counter(value["key"] for value in items if isinstance(value, dict) and isinstance(value.get("key"), str))
        for index, value in enumerate(items, start=1):
            try:
                item = manifest_item(value)
                if counts[item.key] > 1:
                    raise HubError("manifest item key is duplicated")
                yield item
            except HubError as exc:
                yield invalid_item(index, exc)


class ChatGPTExport:
    capabilities = Capabilities(True, False, False, False, False, False)

    def items(self, root, level, allow_raw):
        for index, (counts, entry) in enumerate(chatgpt_conversations(root), start=1):
            try:
                export_id = text(chatgpt_id(entry), 400)
                if counts[export_id] > 1:
                    raise HubError("conversation ID is duplicated")
            except HubError as exc:
                yield invalid_item(index, exc)
                continue
            entry_id = "chatgpt-" + uuid5(NAMESPACE_URL, export_id).hex
            source = {"provider": "chatgpt", "kind": "provider_export", "locator": "chatgpt-export:" + export_id}
            updated = entry.get("update_time")
            if type(updated) in (int, float):
                try:
                    source["observed_at"] = datetime.fromtimestamp(updated, timezone.utc).isoformat()
                except (ValueError, OverflowError, OSError):
                    pass
            # A visible export supplies a title, but supplies no Hub summary or decisions.
            fields = {"title": entry.get("title") or "Untitled conversation"}
            if allow_raw:
                yield Item(entry_id, "chatgpt_raw", {
                    "schema_version": SCHEMA, "kind": "session", "id": entry_id, "sensitivity": level,
                    "source": source, "data": fields, "conversation": entry,
                })
            else:
                yield Item(entry_id, "document", {
                    "schema_version": SCHEMA, "kind": "session", "id": entry_id, "sensitivity": level,
                    "source": source, "data": fields,
                })


def chatgpt_conversations(path):
    if path.suffix.lower() == ".json":
        entries = seq(read_json(path))
        counts = chatgpt_counts(entries)
        yield from ((counts, entry) for entry in entries)
        return
    try:
        with zipfile.ZipFile(path) as archive:
            shards = [member for member in archive.infolist() if CHATGPT_SHARD.fullmatch(member.filename)]
            if not shards:
                raise HubError("no supported conversation JSON at the ZIP root; select an extracted JSON file")
            if len({member.filename for member in shards}) != len(shards):
                raise HubError("duplicate conversation ZIP member")
            if len(shards) > 64 or sum(member.file_size for member in shards) > MAX_EXPORT:
                raise HubError("export exceeds the ZIP import limit; use smaller JSON slices")
            ordered = sorted(shards, key=lambda member: member.filename)
            counts = Counter()
            for member in ordered:
                counts.update(chatgpt_counts(read_chatgpt_shard(archive, member)))
                if len(counts) > 100_000:
                    raise HubError("conversation limit reached; authorize smaller export slices")
            for member in ordered:
                for entry in read_chatgpt_shard(archive, member):
                    yield counts, entry
    except (zipfile.BadZipFile, NotImplementedError) as exc:
        raise HubError("invalid or unsupported export ZIP") from exc


def read_chatgpt_shard(archive, member):
    if member.orig_filename != member.filename or member.file_size > MAX_SHARD or member.flag_bits & 1:
        raise HubError("conversation ZIP member has an irregular name, exceeds its limit or is encrypted")
    with archive.open(member) as stream:
        data = stream.read(MAX_SHARD + 1)
    if len(data) != member.file_size or len(data) > MAX_SHARD:
        raise HubError("conversation ZIP member size mismatch")
    return seq(strict_json(data.decode("utf-8-sig")))


def chatgpt_counts(entries):
    if len(entries) > 100_000:
        raise HubError("conversation limit reached; authorize smaller export slices")
    return Counter(key for entry in entries if isinstance((key := chatgpt_id(entry)), str) and len(key) <= 400)


def chatgpt_id(entry):
    return (entry.get("id") or entry.get("conversation_id")) if isinstance(entry, dict) else None


def invalid_item(index, error):
    return Item(f"entry:{index}", "invalid", {"reason": str(error)})


def visible_chatgpt_messages(conversation):
    nodes = conversation.get("mapping")
    cursor = conversation.get("current_node")
    if not isinstance(nodes, dict) or not isinstance(cursor, str) or not cursor:
        raise HubError("unrecognized ChatGPT export branch; use normalized manual import")
    seen = set()
    messages = []
    while cursor is not None:
        if not isinstance(cursor, str) or cursor in seen or not isinstance(nodes.get(cursor), dict):
            raise HubError("invalid ChatGPT export branch")
        seen.add(cursor)
        node = nodes[cursor]
        message = node.get("message")
        if isinstance(message, dict):
            author = message.get("author")
            metadata = message.get("metadata")
            content = message.get("content")
            role = author.get("role") if isinstance(author, dict) else None
            hidden = not isinstance(metadata, dict) or metadata.get("is_visually_hidden_from_conversation")
            if (role in ("user", "assistant") and not hidden and message.get("recipient", "all") == "all"
                    and isinstance(content, dict) and content.get("content_type") == "text"
                    and isinstance(content.get("parts"), list)):
                parts = [part for part in content["parts"] if isinstance(part, str) and part.strip()]
                if parts:
                    messages.append({
                        "id": "message-" + uuid5(NAMESPACE_URL, cursor).hex,
                        "role": role, "text": "\n".join(parts),
                    })
        cursor = node.get("parent")
    if not messages:
        raise HubError("no eligible visible text on the selected conversation branch")
    return list(reversed(messages))


ADAPTERS = {
    "normalized": ManifestAdapter(),
    "codex_workspace": ManifestAdapter(),
    "local_checkpoint": ManifestAdapter(),
    "chatgpt_export": ChatGPTExport(),
}


def grant(store, source_id, adapter, path, allow_raw):
    ident(source_id)
    one_of(adapter, ADAPTERS)
    if allow_raw and store.level not in ("private", "restricted"):
        raise Denied("raw imports require a private or restricted instance")
    path = local_input(Path(path).expanduser().absolute())
    if adapter == "chatgpt_export":
        if not path.is_file():
            raise Missing("choose an existing local ChatGPT ZIP or conversation JSON")
        if path.suffix.lower() not in (".json", ".zip"):
            raise HubError("ChatGPT grant requires a ZIP or JSON file")
    elif not path.is_dir():
        raise Missing("choose an existing source directory")
    with store.transaction(write=True) as db:
        old = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if old and (old["adapter"], old["path"], old["allow_raw"]) != (adapter, str(path), int(allow_raw)):
            raise Denied("revoke the existing source grant before changing its scope")
        if not old:
            db.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?,?)",
                (source_id, adapter, str(path), int(allow_raw), uuid4().hex, now()),
            )
    return {"status": "unchanged" if old else "granted", "source_id": source_id, "adapter": adapter}


def revoke(store, source_id):
    with store.transaction(write=True) as db:
        changed = db.execute("DELETE FROM sources WHERE id=?", (ident(source_id),)).rowcount
    return {"status": "revoked" if changed else "unchanged", "source_id": source_id}


def list_sources(db):
    return [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY id")]


def describe(source):
    path = Path(source["path"])
    try:
        local_input(path)
        if source["adapter"] != "chatgpt_export":
            path = checked_relative(path, MANIFEST)
        if not path.is_file():
            raise Missing("source file is missing or invalid")
        with path.open("rb"):
            pass
        status = "readable"
    except (PermissionError, Denied):
        status = "permission_denied"
    except (FileNotFoundError, Missing):
        status = "missing"
    except OSError:
        status = "unreachable"
    return {
        "id": source["id"], "adapter": source["adapter"], "state": status,
        "authorization": "granted", "granted_at": source["granted_at"], "raw_grant": bool(source["allow_raw"]),
        "capabilities": asdict(ADAPTERS[source["adapter"]].capabilities),
    }
