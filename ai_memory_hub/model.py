"""Versioned import documents and shared validation."""

import hashlib
import json
import math
import os
import stat
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import SCHEMA

LEVELS = ("public", "internal", "private", "restricted")
FEATURES = ("weekly", "full", "event", "daily", "handoff")
PRESETS = {
    "ordinary": (True, True, False, False, False),
    "archive": (True, True, False, True, False),
    "collaboration": (True, True, True, True, True),
}
SCALARS = ("goal",)
LISTS = (
    "requirements", "constraints", "discussion", "interactions", "evolution",
    "decisions", "rejected_options", "outcomes", "verification",
    "open_questions", "next_actions", "file_refs",
)
EVIDENCE_TYPES = ("user_checkpoint", "workspace_artifact", "provider_export", "observed_messages")
SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:gh[pousr]_|github_pat_|sk-proj-)[a-z0-9_-]{20,}"
    r"|\bAKIA[A-Z0-9]{16}\b|(?:password|api[_-]?key|token|secret)\s*[:=]\s*['\"]?[^\s'\"]{12,}",
    re.IGNORECASE,
)
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")


class HubError(ValueError):
    code = "invalid_input"


class Conflict(HubError):
    code = "conflict"


class Denied(HubError):
    code = "permission_denied"


class Missing(HubError):
    code = "missing"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def iso_date(value):
    text(value)
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, OverflowError):
        raise HubError("a timestamp must include a time zone") from None


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise HubError("JSON keys must be unique")
            result[key] = item
        return result

    def reject_constant(_value):
        raise HubError("JSON numbers must be finite")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            reject_constant(value)
        return result

    try:
        return json.loads(value, object_pairs_hook=unique, parse_constant=reject_constant, parse_float=finite_float)
    except (HubError, json.JSONDecodeError):
        raise
    except ValueError as exc:
        raise HubError("JSON number is out of range") from exc


def windows_file_path(fd):
    from ctypes import WinDLL, create_unicode_buffer, get_last_error, WinError
    from ctypes.wintypes import DWORD, HANDLE, LPWSTR
    from msvcrt import get_osfhandle

    resolve = WinDLL("Kernel32", use_last_error=True).GetFinalPathNameByHandleW
    resolve.argtypes = HANDLE, LPWSTR, DWORD, DWORD
    resolve.restype = DWORD
    handle = get_osfhandle(fd)
    size = resolve(handle, None, 0, 0)
    if not size:
        raise WinError(get_last_error())
    buffer = create_unicode_buffer(size)
    written = resolve(handle, buffer, size, 0)
    if not 0 < written < size:
        raise WinError(get_last_error())
    return Path(buffer.value.removeprefix("\\\\?\\"))


def windows_long_path(path):
    from ctypes import WinDLL, create_unicode_buffer, get_last_error, WinError
    from ctypes.wintypes import DWORD, LPCWSTR, LPWSTR

    # Check the named components without following a reparse point first.
    for entry in reversed((path, *path.parents)):
        if entry.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise Denied("source path contains a Windows reparse point")
    expand = WinDLL("Kernel32", use_last_error=True).GetLongPathNameW
    expand.argtypes = LPCWSTR, LPWSTR, DWORD
    expand.restype = DWORD
    size = expand(str(path), None, 0)
    if not size:
        raise WinError(get_last_error())
    buffer = create_unicode_buffer(size)
    written = expand(str(path), buffer, size)
    if not 0 < written < size:
        raise WinError(get_last_error())
    return Path(buffer.value.removeprefix("\\\\?\\"))


def open_unix_path(path):
    parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        return os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)


@contextmanager
def open_source(path):
    """Verify the opened object before consuming bytes from an approved path."""
    path = Path(os.path.abspath(path))
    if not path.name:
        raise Denied("source must be an approved regular file")
    expected = windows_long_path(path) if os.name == "nt" else path
    fd = os.open(path, os.O_RDONLY | os.O_BINARY) if os.name == "nt" else open_unix_path(path)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Denied("source must be a regular file with a single filesystem link")
        if os.name == "nt" and windows_file_path(fd) != expected:
            raise Denied("opened source resolves outside its approved path")
        yield stream


def read_json(path):
    with open_source(path) as stream:
        data = stream.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024:
        raise HubError("JSON input exceeds 128 MiB")
    return strict_json(data.decode("utf-8-sig"))


def shape(value, required, optional=()):
    if not isinstance(value, dict):
        raise HubError("expected a JSON object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing:
        raise HubError("missing fields: " + ", ".join(sorted(missing)))
    if unknown:
        raise HubError("unrecognized fields")


def text(value, limit=200_000):
    if not isinstance(value, str) or not value.strip() or "\0" in value or len(value) > limit:
        raise HubError("expected non-empty bounded text")
    return value


def ident(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value.endswith("."):
        raise HubError("invalid identifier")
    return value


def one_of(value, choices):
    if value not in choices:
        raise HubError("unrecognized option")
    return value


def seq(value):
    if not isinstance(value, list):
        raise HubError("expected a list")
    return value


def revision(value, minimum=1):
    if type(value) is not int or not minimum <= value < 2**63:
        raise HubError("invalid revision")
    return value


def no_credentials(value):
    if SECRET.search(value):
        raise Denied("possible credential detected")


def external_url(value):
    no_credentials(text(value, 3072))
    if "\\" in value or any(c.isspace() or ord(c) < 32 for c in value):
        raise HubError("invalid external URL")
    try:
        url = urlsplit(value)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError
        if url.username is not None or url.password is not None:
            raise ValueError
        url.port
    except ValueError:
        raise HubError("external links need a stable HTTP(S) URL without credentials, query or fragment") from None
    return value


def evidence(value):
    shape(value, ("provider", "kind", "locator"), ("observed_at",))
    text(value["provider"], 120)
    one_of(value["kind"], EVIDENCE_TYPES)
    locator = text(value["locator"], 1024)
    no_credentials(locator)
    if locator.startswith(("https:", "http:")):
        external_url(locator)
    if "observed_at" in value:
        iso_date(value["observed_at"])
    return value


def file_ref(value):
    shape(value, ("asset_id",), ("version", "purpose"))
    ident(value["asset_id"])
    if "version" in value:
        revision(value["version"])
    if "purpose" in value:
        text(value["purpose"])


def detail(value, patch=False):
    if patch:
        shape(value, (), SCALARS + LISTS)
    else:
        shape(value, SCALARS + LISTS)
    for key in value.keys() & set(SCALARS):
        text(value[key])
    for key in value.keys() & set(LISTS):
        for item in seq(value[key]):
            if key == "file_refs":
                file_ref(item)
            elif key == "rejected_options":
                shape(item, ("option", "reason"))
                text(item["option"])
                text(item["reason"])
            else:
                text(item)


def messages(items):
    if not seq(items):
        raise HubError("raw messages cannot be empty")
    for item in items:
        shape(item, ("id", "role", "text"), ("at",))
        ident(item["id"])
        one_of(item["role"], ("user", "assistant", "tool"))
        text(item["text"])
        if "at" in item:
            iso_date(item["at"])
    if len({item["id"] for item in items}) != len(items):
        raise HubError("raw message IDs must be unique")


def document(data, level, allow_raw=False, allow_review=False):
    shape(data, ("schema_version", "kind", "id", "sensitivity", "source", "data"), ("base_revision",))
    one_of(data["schema_version"], (SCHEMA,))
    ident(data["id"])
    one_of(data["sensitivity"], LEVELS)
    if data["sensitivity"] != level:
        raise Denied("record sensitivity must match the instance boundary")
    if "base_revision" in data:
        revision(data["base_revision"], 0)
    source = evidence(data["source"])
    kind, fields = data["kind"], data["data"]
    if kind == "session":
        shape(fields, ("title",), ("project_id", "summary", "checkpoint", "append", "messages"))
        text(fields["title"], 500)
        if "project_id" in fields:
            ident(fields["project_id"])
        if "summary" in fields:
            text(fields["summary"])
        if "checkpoint" in fields:
            detail(fields["checkpoint"])
        if "append" in fields:
            if "checkpoint" in fields:
                raise HubError("choose a complete checkpoint or an append")
            detail(fields["append"], patch=True)
        if "messages" in fields:
            if not allow_raw or level not in ("private", "restricted"):
                raise Denied("L3 requires separate raw consent and a private or restricted instance")
            if source["kind"] not in ("provider_export", "observed_messages"):
                raise Denied("L3 requires a real authorized message source")
            messages(fields["messages"])
    elif kind == "project":
        shape(fields, ("title", "state"), ("summary", "timeline", "file_refs"))
        text(fields["title"], 500)
        one_of(fields["state"], ("planned", "active", "blocked", "done", "archived"))
        if "summary" in fields:
            text(fields["summary"])
        for entry in seq(fields.get("timeline", [])):
            shape(entry, ("at", "description"))
            iso_date(entry["at"])
            text(entry["description"])
        for entry in seq(fields.get("file_refs", [])):
            file_ref(entry)
    elif kind == "memory":
        shape(fields, ("key", "claim", "status"), ("classification",))
        if "classification" in fields:
            one_of(fields["classification"], ("fact", "rule", "preference", "inference"))
        text(fields["key"], 120)
        text(fields["claim"])
        one_of(fields["status"], ("candidate", "accepted", "rejected", "retired"))
        if fields["status"] != "candidate" and not allow_review:
            raise Denied("reviewed memory requires a separate manual decision")
    else:
        raise HubError("document kind must be session, project, or memory")
    return data
