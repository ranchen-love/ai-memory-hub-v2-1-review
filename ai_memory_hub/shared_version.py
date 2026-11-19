"""Detect and acknowledge selected shared memory snapshots per receiving Agent."""

import json
import os
from pathlib import Path
from uuid import uuid4

from .adapters import local_input
from .model import (
    LEVELS, Conflict, Denied, HubError, Missing, canonical, digest, document, ident, no_credentials,
    one_of, read_json, revision, seq, shape, strict_json,
)


def require_consent(consent):
    if not consent:
        raise Denied("shared snapshots require explicit authorization")


def export_record(item):
    result = {key: item[key] for key in ("id", "kind", "schema_version", "sensitivity", "source", "data")}
    result["revision"] = item["revision"]
    return result


def snapshot(store, name, selected, *, consent=False):
    require_consent(consent)
    ident(name)
    scopes, used = {}, set()
    with store.transaction() as db:
        for scope, items in sorted(selected.items()):
            ident(scope)
            rows = []
            for key in sorted(items):
                ident(key)
                if key in used:
                    raise HubError("each selected memory belongs to one scope")
                used.add(key)
                item = store.get(db, "memory", key)
                if item is None:
                    raise Missing("selected memory does not exist")
                if item["data"]["status"] != "accepted" or item["data"].get("classification") == "inference":
                    raise Denied("only accepted memories with a non-inference classification can be shared")
                rows.append(export_record(item))
            if not rows:
                raise HubError("omit scopes without selected records")
            scopes[scope] = rows
    value = {"format": "1.0", "kind": "shared_memory", "scopes": scopes}
    data = canonical(value)
    no_credentials(data)
    directory = store.root / "snapshots"
    directory.mkdir(exist_ok=True)
    local_input(directory)
    target = directory / f"memory-{name}.json"
    try:
        with target.open("x", encoding="utf-8", newline="\n") as output:
            output.write(data + "\n")
    except FileExistsError as exc:
        raise Conflict("choose a new snapshot name") from exc
    return {"status": "created", "path": str(target), "sha": digest(value), "scopes": sorted(scopes)}


def read_snapshot(path, level):
    value = read_json(local_input(Path(path)))
    shape(value, ("format", "kind", "scopes"))
    one_of(value["format"], ("1.0",))
    one_of(value["kind"], ("shared_memory",))
    scopes = value["scopes"]
    if not isinstance(scopes, dict):
        raise HubError("shared memory scopes must be an object")
    used = set()
    for scope, records in scopes.items():
        ident(scope)
        if not seq(records):
            raise HubError("omit scopes without shared records")
        for item in records:
            shape(item, ("id", "kind", "schema_version", "sensitivity", "source", "data", "revision"))
            ident(item["id"])
            revision(item["revision"])
            one_of(item["kind"], ("memory",))
            sensitivity = one_of(item["sensitivity"], LEVELS)
            if LEVELS.index(sensitivity) > LEVELS.index(level):
                raise Denied("shared memory exceeds the recipient sensitivity boundary")
            envelope = {key: field for key, field in item.items() if key != "revision"}
            document(envelope, sensitivity, allow_review=True)
            if item["data"]["status"] != "accepted" or item["data"].get("classification") == "inference":
                raise Denied("shared memory contains an unapproved or inferred record")
            if item["id"] in used:
                raise HubError("duplicate memory identifier in shared snapshot")
            used.add(item["id"])
    no_credentials(canonical(value))
    return digest(value), scopes


def state_key(channel, agent):
    return "shared_version:" + canonical([ident(channel), ident(agent)])


def load_state(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is not None:
        return strict_json(row["value"])
    return {"path": None, "detected_sha": None, "synced_sha": None, "detected_scopes": {},
            "synced_scopes": {}, "acked": [], "ticket": None}


def save_state(db, key, state):
    db.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, canonical(state)))


def pending_scopes(state):
    before, after = state["synced_scopes"], state["detected_scopes"]
    return sorted(scope for scope in before.keys() | after.keys()
                  if before.get(scope) != after.get(scope) and scope not in state["acked"])


def report(state, status, availability="available"):
    pending = state["detected_sha"] != state["synced_sha"]
    return {"status": status, "availability": availability, "detected_sha": state["detected_sha"],
            "synced_sha": state["synced_sha"], "pending_reload": pending,
            "reload_scope": pending_scopes(state),
            "in_sync": not pending if availability == "available" else None}


def check(store, channel, agent, path, *, consent=False):
    require_consent(consent)
    key = state_key(channel, agent)
    path = os.path.abspath(Path(path).expanduser())
    with store.transaction(write=True) as db:
        state = load_state(db, key)
        if state["path"] is not None and os.path.normcase(state["path"]) != os.path.normcase(path):
            raise Conflict("this Agent/channel is already pinned to a different source")
        state["path"] = path
        try:
            sha, scopes = read_snapshot(path, store.level)
        except (OSError, HubError, json.JSONDecodeError, UnicodeError, RecursionError) as exc:
            save_state(db, key, state)
            return {**report(state, "unknown", "unavailable"), "reason": getattr(exc, "code", "unreadable")}
        prior = state["detected_sha"]
        status = "first_check" if prior is None else "unchanged" if sha == prior else "changed"
        if sha != prior:
            state.update(detected_sha=sha, detected_scopes={name: digest(items) for name, items in scopes.items()},
                         acked=[], ticket=None)
        save_state(db, key, state)
        return report(state, status)


def current_pending(store, state):
    if state["detected_sha"] == state["synced_sha"]:
        raise Conflict("there is no detected version awaiting reload")
    try:
        sha, scopes = read_snapshot(state["path"], store.level)
    except (OSError, json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise Missing("shared memory is unavailable; run version check") from exc
    if sha != state["detected_sha"]:
        raise Conflict("the snapshot changed; run version check before reloading or confirming")
    return scopes


def reload(store, channel, agent, selected=(), *, consent=False):
    require_consent(consent)
    key = state_key(channel, agent)
    with store.transaction(write=True) as db:
        state = load_state(db, key)
        scopes = current_pending(store, state)
        remaining = pending_scopes(state)
        selected = sorted(ident(scope) for scope in selected) if selected else remaining
        if len(set(selected)) != len(selected) or set(selected) - set(remaining):
            raise Conflict("select distinct pending scopes")
        ticket = {"id": uuid4().hex, "scopes": selected}
        state["ticket"] = ticket
        save_state(db, key, state)
        return {**report(state, "loaded"), "receipt": ticket["id"],
                "scopes": {name: scopes.get(name) for name in selected}}


def confirm(store, channel, agent, sha, receipt, *, consent=False):
    require_consent(consent)
    key = state_key(channel, agent)
    with store.transaction(write=True) as db:
        state = load_state(db, key)
        ticket = state["ticket"]
        if not ticket or sha != state["detected_sha"] or receipt != ticket["id"]:
            raise Conflict("confirmation requires the current version's read receipt for this Agent")
        current_pending(store, state)
        state["acked"] = sorted(set(state["acked"] + ticket["scopes"]))
        state["ticket"] = None
        pending = pending_scopes(state)
        if not pending:
            state.update(synced_sha=sha, synced_scopes=state["detected_scopes"], acked=[])
        save_state(db, key, state)
        return report(state, "reload_pending" if pending else "confirmed")
