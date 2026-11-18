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
            kind = "asset" if item.kind == "link" else record["kind"]
            return {"status": "unchanged", "kind": kind}
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


def run_batch(store, blobs, feature, source_id=None, governance=None, archive_only=False):
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
            "execution": {"runtime": "local_cli",
                          "entrypoint": "local_archive" if archive_only else "sync",
                          "scheduler": "not_verified"},
        }
        items_by_kind = dict.fromkeys(("session", "project", "memory", "asset"), 0)
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
                        items_by_kind[result["kind"]] += 1
                    except RECOVERABLE as exc:
                        if item is None:
                            raise
                        report["errors"].append(failure(exc, grant["id"], item.key, item.kind))
                        totals["errors"] += 1
            except RECOVERABLE as exc:
                report["errors"].append(failure(exc, grant["id"]))
                totals["errors"] += 1
            totals["status"] = source_outcome(totals)
        report["archive"] = {
            "status": archive_coverage(report["sources"]),
            "selection": "all_active_grants" if source_id is None else "selected_grant",
            "configured_sources": len(sources), "items": items_by_kind,
        }
        if feature == "weekly" and archive_only:
            report["governance"] = {"status": "not_run", "scope": "local_archive_only"}
        if feature == "weekly" and not archive_only:
            report["governance"] = {"status": "failed", "scope": "long_term_memory"}
            try:
                with store.transaction(write=True) as db:
                    store.require(db, feature)
                    weekly_review(store, db, blobs, report, governance)
            except RECOVERABLE as exc:
                report["errors"].append(failure(exc, "instance-governance"))
        archive = report["archive"]["status"]
        governed = report.get("governance", {}).get("status") == "completed"
        if report["errors"] or archive == "partial":
            state = "partial" if governed or archive in ("partial", "completed") else "failed"
        elif archive == "completed":
            state = "completed"
        elif governed:
            state = "governance_only"
        else:
            state = "no_sources" if archive == "not_configured" else archive
        report["status"] = state
        with store.transaction(write=True) as db:
            db.execute("UPDATE runs SET finished_at=?, state=?, report=? WHERE id=?",
                       (now(), state, canonical(report), run_id))
        return report


def source_outcome(counts):
    successful = any(counts[key] for key in ("created", "updated", "unchanged"))
    if counts["errors"]:
        return "partial" if successful else "failed"
    return "completed" if successful else "no_items"


def archive_coverage(sources):
    states = {source["status"] for source in sources}
    if not states:
        return "not_configured"
    if states == {"completed"} or states == {"no_items"}:
        return next(iter(states))
    return "partial" if states.intersection({"completed", "partial"}) else "failed"


def weekly_review(store, db, blobs, report, governance):
    try:
        report["memory_review"] = memory_review(store.latest(db, "memory"))
        if governance is not None:
            report["instance_governance"] = governance()
        if report.get("instance_governance", {"status": "pass"})["status"] == "pass":
            report["governance"]["status"] = "completed"
        else:
            report["errors"].append({"code": "governance_failed", "kind": "memory"})
    except RECOVERABLE as exc:
        report["errors"].append(failure(exc, "instance-governance"))
    report["asset_integrity"] = {}
    for item in store.latest(db, "asset"):
        state = availability(db, blobs, item)["status"]
        report["asset_integrity"][state] = report["asset_integrity"].get(state, 0) + 1
        if state in ("missing", "corrupt", "unreachable", "permission_denied", "expired"):
            report["errors"].append({"code": state, "asset_id": item["id"], "kind": "asset"})


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
        active = {source["id"]: source["grant_id"] for source in sources}
        covered, source_success, pending = {}, {}, []
        last_success, last_archive, last_governance = {}, {}, {}
        for row in db.execute(
            "SELECT feature, finished_at, report FROM runs WHERE report IS NOT NULL ORDER BY finished_at DESC",
        ):
            report = json.loads(row["report"])
            feature, finished = row["feature"], row["finished_at"]
            archive = report.get("archive")
            selected = {source["source_id"]: source["grant_id"] for source in report["sources"]}
            if (archive and archive["selection"] == "all_active_grants" and archive["status"] == "completed"
                    and selected == active):
                last_archive.setdefault(feature, finished)
                if report["status"] == "completed":
                    last_success.setdefault(feature, finished)
            if report.get("governance", {}).get("status") == "completed":
                last_governance.setdefault(feature, finished)
            for source in report["sources"]:
                source_id = source["source_id"]
                if active.get(source_id) == source["grant_id"] and source.get("status") == "completed":
                    source_success.setdefault(source_id, finished)
                if active.get(source_id) == source["grant_id"] and source_id not in covered:
                    covered[source_id] = source.get("status", "legacy_unclassified")
                    pending.extend(error for error in report["errors"] if error.get("source_id") == source_id)
    for entry in recent:
        entry["report"] = json.loads(entry["report"]) if entry["report"] else None
        if entry["report"] and "archive" not in entry["report"]:
            entry["report"]["legacy_status"] = entry["report"]["status"]
            entry["state"] = entry["report"]["status"] = "legacy_unclassified"
    return {
        "settings": store.settings(),
        "execution": {"runtime": "local_cli", "vault": "opened", "scheduler": "not_verified"},
        "sources": [{**describe(source), "last_scan": covered.get(source["id"], "not_run"),
                     "last_archive_success": source_success.get(source["id"])} for source in sources],
        "latest_runs": recent, "last_success": last_success, "pending": pending,
        "last_archive_success": last_archive, "last_governance_success": last_governance,
        "applied_events": events, "retry": "run the same sync feature with the same active source grants",
    }
