"""Independent sync gates, resumable batch receipts, and explicit events."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from . import SCHEMA
from .adapters import ADAPTERS, describe, list_sources, local_input, manifest_item, visible_chatgpt_messages
from .assets import availability, put_file, put_link
from .model import Conflict, Denied, HubError, Missing, canonical, digest, ident, iso_date, now, one_of, read_json, shape
from .store import Store, checked_relative, document_digest, memory_review, reparse

EVENTS = ("decision_confirmed", "milestone_completed", "artifact_finalized", "conversation_checkpoint", "project_updated")
RECOVERABLE = (HubError, OSError, json.JSONDecodeError, UnicodeError, sqlite3.Error, RecursionError)


def failure(exc, source_id, item=None, kind=None):
    if isinstance(exc, HubError):
        reason = exc.code
        message = str(exc)
    elif isinstance(exc, FileNotFoundError):
        reason, message = "missing", "source file or directory is missing"
    elif isinstance(exc, PermissionError):
        reason, message = "permission_denied", "OS denied source access"
    elif isinstance(exc, (json.JSONDecodeError, UnicodeError, RecursionError)):
        reason, message = "invalid_input", "source is not supported UTF-8 JSON"
    elif isinstance(exc, sqlite3.Error):
        reason, message = "storage_error", "instance transaction failed"
    else:
        reason, message = "unreachable", "source could not be read"
    result = {"source_id": source_id, "code": reason, "message": message}
    if item is not None:
        result.update({"item": item, "kind": kind})
    return result


@contextmanager
def batch_lock(root):
    path = root / "sync.lock"
    if os.path.lexists(path) and reparse(path):
        raise Denied("sync lock must stay inside the instance boundary")
    with path.open("a+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Conflict("another sync is running") from exc
        yield


def verify_grant(db, grant):
    active = db.execute("SELECT grant_id FROM sources WHERE id=?", (grant["id"],)).fetchone()
    if active is None or active["grant_id"] != grant["grant_id"]:
        raise Denied("source grant is no longer active")


def item_source(grant, item):
    return {
        "provider": grant["adapter"], "kind": "workspace_artifact",
        "locator": grant["id"] + ":" + item.key + ":" + item.value.get("origin", "workspace_artifact"),
    }


def managed_asset(grant, item):
    scope = os.path.normcase(str(Path(grant["path"]).resolve()))
    owner = digest([grant["id"], grant["adapter"], scope, item.key])
    entry_id = item.value.get("asset_id") or "asset-" + uuid5(NAMESPACE_URL, owner).hex
    return entry_id, owner


def run_item(store, db, blobs, grant, base, item, event=None):
    opts = item.value
    if item.kind == "invalid":
        raise HubError(opts["reason"])
    if item.kind == "file":
        path = checked_relative(base, opts["path"])
        with blobs.stage(path) as staged:
            key = digest([opts, staged.sha256])
            if event and already_event(db, event, key):
                return {"status": "unchanged"}
            asset_id, owner = managed_asset(grant, item)
            result = put_file(
                store, db, blobs, staged, opts.get("name", path.name), item_source(grant, item),
                asset_id, opts.get("project_id"), opts.get("session_id"), managed_by=owner,
            )
    else:
        if item.kind == "record":
            record = read_json(checked_relative(base, opts["path"]))
        elif item.kind == "chatgpt_raw":
            record = dict(opts)
            conversation = record.pop("conversation")
            record["data"] = {**record["data"], "messages": visible_chatgpt_messages(conversation)}
        else:
            record = opts
        key = digest(record)
        if event and already_event(db, event, key):
            return {"status": "unchanged"}
        previous = db.execute(
            "SELECT digest FROM receipts WHERE grant_id=? AND item=?", (grant["grant_id"], item.key),
        ).fetchone()
        if not event and previous and previous["digest"] == key:
            return {"status": "unchanged"}
        if item.kind == "link":
            asset_id, owner = managed_asset(grant, item)
            result = put_link(
                store, db, opts["url"], opts["name"], item_source(grant, item), asset_id,
                opts.get("project_id"), opts.get("session_id"), expires_at=opts.get("expires_at"),
                managed_by=owner,
            )
        else:
            if item.kind in ("document", "chatgpt_raw"):
                record = advance_provider_record(db, record)
            result = store.ingest(db, record, allow_raw=bool(grant["allow_raw"]))
    if event:
        db.execute("INSERT INTO events VALUES (?,?)", (event["id"], digest([event, key])))
    else:
        db.execute(
            """INSERT INTO receipts VALUES (?,?,?) ON CONFLICT(grant_id, item)
            DO UPDATE SET digest=excluded.digest""", (grant["grant_id"], item.key, key),
        )
    return result


def advance_provider_record(db, data):
    previous = Store.get(db, "session", data["id"])
    if previous is None:
        return data
    history = Store.history(db, "session", data["id"])
    latest_export = next((r for r in reversed(history) if r["source"]["kind"] == "provider_export"
                          and r["source"]["locator"] == data["source"]["locator"]), None)
    if latest_export and latest_export["record_digest"] == document_digest(data):
        # The previous provider import still exists even if a manual checkpoint now follows it.
        return {**data, "base_revision": latest_export["revision"] - 1}
    incoming = data["source"].get("observed_at")
    previous_time = latest_export["source"].get("observed_at") if latest_export else None
    raw_upgrade = latest_export and incoming == previous_time and "messages" in data["data"] and "messages" not in latest_export["data"]
    if not raw_upgrade and (not latest_export or not incoming or not previous_time or iso_date(incoming) <= iso_date(previous_time)):
        raise Conflict("provider change needs a newer export timestamp or manual reconciliation")
    return {**data, "base_revision": previous["revision"]}


def already_event(db, event, payload_digest):
    old = db.execute("SELECT digest FROM events WHERE id=?", (event["id"],)).fetchone()
    if old and old["digest"] != digest([event, payload_digest]):
        raise Conflict("event ID was replayed with changed source or payload")
    return old is not None


def run_batch(store, blobs, feature, source_id=None, governance=None):
    one_of(feature, ("full", "daily", "weekly"))
    with store.transaction() as db:
        store.require(db, feature)
    with batch_lock(store.root):
        run_id = uuid4().hex
        with store.transaction(write=True) as db:
            store.require(db, feature)
            sources = list_sources(db)
            if source_id is not None:
                sources = [source for source in sources if source["id"] == ident(source_id)]
                if not sources:
                    raise Denied("source has no active grant")
            db.execute("INSERT INTO runs VALUES (?,?,?,NULL,'started',NULL)", (run_id, feature, now()))
        report = {
            "run_id": run_id, "feature": feature, "scope": "granted_local_sources", "sources": [],
            "created": 0, "updated": 0, "unchanged": 0, "errors": [],
        }
        for grant in sources:
            totals = {"source_id": grant["id"], "grant_id": grant["grant_id"],
                      "created": 0, "updated": 0, "unchanged": 0, "errors": 0}
            report["sources"].append(totals)
            try:
                adapter = ADAPTERS[grant["adapter"]]
                items = None
                while True:
                    item = None
                    try:
                        with store.transaction(write=True) as db:
                            store.require(db, feature)
                            verify_grant(db, grant)
                            base = local_input(Path(grant["path"]))
                            if items is None:
                                items = iter(adapter.items(base, store.level, bool(grant["allow_raw"])))
                            try:
                                item = next(items)
                            except StopIteration:
                                break
                            result = run_item(store, db, blobs, grant, base, item)
                        totals[result["status"]] += 1
                        report[result["status"]] += 1
                    except RECOVERABLE as exc:
                        if item is None:
                            raise
                        report["errors"].append(failure(exc, grant["id"], item.key, item.kind))
                        totals["errors"] += 1
            except RECOVERABLE as exc:
                report["errors"].append(failure(exc, grant["id"]))
                totals["errors"] += 1
        if feature == "weekly":
            try:
                with store.transaction(write=True) as db:
                    store.require(db, feature)
                    weekly_review(store, db, blobs, report, governance)
            except RECOVERABLE as exc:
                report["errors"].append(failure(exc, "instance-governance"))
        if report["errors"]:
            state = "partial"
        elif sources or feature == "weekly":
            state = "completed"
        else:
            state = "no_sources"
        report["status"] = state
        with store.transaction(write=True) as db:
            db.execute("UPDATE runs SET finished_at=?, state=?, report=? WHERE id=?",
                       (now(), state, canonical(report), run_id))
        return report


def weekly_review(store, db, blobs, report, governance):
    report["memory_review"] = memory_review(store.latest(db, "memory"))
    report["asset_integrity"] = {}
    for item in store.latest(db, "asset"):
        state = availability(db, blobs, item)["status"]
        report["asset_integrity"][state] = report["asset_integrity"].get(state, 0) + 1
        if state in ("missing", "corrupt", "unreachable", "permission_denied", "expired"):
            report["errors"].append({"code": state, "asset_id": item["id"], "kind": "asset"})
    if governance is not None:
        report["instance_governance"] = governance()
        if report["instance_governance"]["status"] != "pass":
            report["errors"].append({"code": "governance_failed", "kind": "memory"})


def dispatch(store, blobs, source_id, event_path):
    with store.transaction(write=True) as db:
        store.require(db, "event")
        grant = next((s for s in list_sources(db) if s["id"] == ident(source_id)), None)
        if grant is None or grant["adapter"] == "chatgpt_export":
            raise Denied("events require an active directory grant")
        root = local_input(Path(grant["path"]))
        event = read_json(checked_relative(root, event_path))
        shape(event, ("schema_version", "id", "type", "at", "item"))
        one_of(event["schema_version"], (SCHEMA,))
        ident(event["id"])
        one_of(event["type"], EVENTS)
        iso_date(event["at"])
        item = manifest_item(event["item"])
        if (event["type"] == "artifact_finalized") != (item.kind in ("link", "file")):
            raise HubError("event type cannot write this item kind")
        result = run_item(store, db, blobs, grant, root, item, event={**event, "grant_id": grant["grant_id"]})
    return {"event_id": event["id"], **result}


def status(store):
    with store.transaction() as db:
        sources = list_sources(db)
        events = db.execute("SELECT count(*) FROM events").fetchone()[0]
        recent = [dict(row) for row in db.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 10",
        )]
        last_success = {
            row["feature"]: row["finished_at"] for row in db.execute(
                "SELECT feature, max(finished_at) finished_at FROM runs WHERE state='completed' GROUP BY feature",
            )
        }
        reports = [json.loads(row["report"]) for row in db.execute(
            "SELECT report FROM runs WHERE report IS NOT NULL ORDER BY finished_at DESC",
        )]
    for entry in recent:
        entry["report"] = json.loads(entry["report"]) if entry["report"] else None
    active = {s["id"]: s["grant_id"] for s in sources}
    pending = []
    covered = {}
    for report in reports:
        for source in report["sources"]:
            source_id = source["source_id"]
            if active.get(source_id) == source["grant_id"] and source_id not in covered:
                covered[source_id] = "partial" if source["errors"] else "completed"
                pending.extend(error for error in report["errors"] if error.get("source_id") == source_id)
        if covered.keys() == active.keys():
            break
    return {
        "settings": store.settings(),
        "sources": [{**describe(source), "last_scan": covered.get(source["id"], "not_run")} for source in sources],
        "latest_runs": recent, "last_success": last_success, "pending": pending,
        "applied_events": events, "retry": "run the same sync feature with the same active source grants",
    }
