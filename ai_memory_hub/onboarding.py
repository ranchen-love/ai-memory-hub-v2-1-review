"""Plan and apply explicit owner-selected bootstrap work, with local evidence."""

import os
import platform
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import SCHEMA, VERSION, candidates
from .adapters import ADAPTERS, MANIFEST, grant, local_input
from .assets import LocalVault, availability
from .life import archive_coverage
from .model import (
    LEVELS, Conflict, Denied, HubError, Missing, canonical, digest, ident, no_credentials, now,
    one_of, open_source, read_json, seq, shape, strict_json, text,
)
from .store import checked_relative, instance_path, memory_review
from .sync import batch_lock, failure, run_batch, status
from .workspace import (
    BOOTSTRAP_LOCK, PROFILE, TIMELINE, bootstrap_workspace, bound_workspace, check_bound_workspace,
    private_pair, write_atomic, write_exclusive,
)


FORMAT = "1.0"
LIFE_INPUTS = {"life_profile": PROFILE, "life_timeline": TIMELINE}
SOURCE_KEY = "onboarding:source:"
REPO_KEY = "onboarding:github:"
TARGET_KEY = "onboarding:target"
RECOVERABLE = (HubError, OSError, ValueError, sqlite3.Error, RecursionError)


def request_path(base, value):
    value = Path(text(value, 3000)).expanduser()
    return str(Path(os.path.abspath(base / value)))


def read_request(path):
    path = local_input(Path(path).expanduser().absolute())
    value = read_json(path)
    shape(value, ("format", "workspace"), ("vault", "sensitivity", "sources", "github"))
    one_of(value["format"], (FORMAT,))
    root = request_path(path.parent, value["workspace"])
    vault = request_path(path.parent, value["vault"]) if "vault" in value else root + "-vault"
    private_pair(Path(root), Path(vault))
    level = one_of(value.get("sensitivity", "private"), LEVELS)
    sources, seen = [], set()
    for item in seq(value.get("sources", [])):
        shape(item, ("id", "adapter", "path", "authorized"), ("allow_raw",))
        item_id, adapter = ident(item["id"]), ident(item["adapter"])
        raw, authorized = item.get("allow_raw", False), item["authorized"]
        if item_id in seen or type(raw) is not bool or type(authorized) is not bool:
            raise HubError("sources need unique IDs and boolean authorization")
        seen.add(item_id)
        if raw and (not authorized or adapter in LIFE_INPUTS or level not in ("private", "restricted")):
            raise Denied("raw input needs separate approval and a private Vault with a compatible source")
        sources.append({"id": item_id, "adapter": adapter, "path": request_path(path.parent, item["path"]),
                        "authorized": authorized, "allow_raw": raw})
    remote = value.get("github")
    if "github" in value:
        from .github_publish import target_name

        shape(remote, ("target", "visibility"))
        one_of(remote["visibility"], ("private",))
        owner, name = target_name(remote["target"])
        remote = {"target": f"{owner.lower()}/{name.lower()}", "visibility": "private"}
    request = {"format": FORMAT, "workspace": root, "vault": vault, "sensitivity": level,
               "sources": sources, "github": remote}
    no_credentials(canonical(request))
    return request


def problem(exc):
    problem = failure(exc, None)
    if isinstance(exc, ValueError) and not isinstance(exc, HubError):
        problem = {"code": "invalid_input", "message": "input does not match the required JSON format"}
    state = "blocked" if problem["code"] in ("permission_denied", "missing", "conflict", "unreachable") else "failed"
    return {"status": state, "code": problem["code"], "reason": problem["message"]}


def storage_plan(request):
    try:
        root, vault = (instance_path(request[key]) for key in ("workspace", "vault"))
        private_pair(root, vault)
        if not all(path.parent.is_dir() for path in (root, vault)):
            raise Missing("Workspace and Vault must have existing parent directories")
        states = {}
        for name, path in (("workspace", root), ("vault", vault)):
            if not path.exists():
                states[name] = "new"
            elif not path.is_dir():
                raise Denied("storage path must be a directory")
            else:
                states[name] = "existing; binding and ACL checked during apply"
        return {"status": "not_verified", "paths": states}
    except RECOVERABLE as exc:
        return problem(exc)


def source_readiness(item, *, probe):
    if not item["authorized"]:
        return {"status": "blocked", "reason": "source lacks owner authorization"}
    adapter = item["adapter"]
    if adapter not in ADAPTERS and adapter not in LIFE_INPUTS:
        return {"status": "blocked", "reason": "use an approved local export or normalized checkpoint"}
    if probe:
        try:
            path = local_input(Path(item["path"]))
            payload = path if adapter in (*LIFE_INPUTS, "chatgpt_export") else checked_relative(path, MANIFEST)
            if not payload.is_file():
                raise Missing("approved input file or manifest is unavailable")
            # Open only the explicitly authorized entry point, with no content read in plan.
            with open_source(payload):
                pass
        except RECOVERABLE as exc:
            return problem(exc)
    return {"status": "not_verified", "reason": "content validation and coverage require apply"}


def plan_fingerprint(request):
    return digest({"engine_version": VERSION, "request": request})


def plan(request):
    desired = request["github"]
    if desired:
        from . import github_publish

        try:
            remote = github_publish.probe(desired["target"])
        except RECOVERABLE as exc:
            remote = problem(exc)
    else:
        remote = {"status": "not_requested"}
    result = {
        "format": FORMAT, "kind": "onboarding_plan", "status": "planned", "plan_digest": plan_fingerprint(request),
        "engine_version": VERSION, "vault_schema_version": SCHEMA, "request": request,
        "storage": storage_plan(request),
        "capabilities": {
            "python": platform.python_version(), "python_path": sys.executable, "platform": platform.system(),
            "git_installed": shutil.which("git") is not None, "gh_installed": shutil.which("gh") is not None,
            "provider_live_access": "not_verified", "filesystem_scope": "selected_local_inputs",
            "scheduler": "not_verified",
        },
        "github": remote,
        "sources": [{"id": item["id"], "adapter": item["adapter"], **source_readiness(item, probe=True)}
                    for item in request["sources"]],
    }
    result["markdown"] = markdown(result)
    return result


def merged_records(existing, incoming):
    found = {entry["record_id"]: entry for entry in existing}
    for entry in seq(incoming):
        if not isinstance(entry, dict) or "record_id" not in entry:
            raise HubError("invalid life archive entry")
        entry_id = ident(entry["record_id"])
        if entry_id in found and found[entry_id] != entry:
            raise Conflict("life record ID already exists with different content; add a reviewed successor")
        found[entry_id] = entry
    return list(found.values())


def import_life(root, level, item):
    incoming = read_json(local_input(Path(item["path"])))
    no_credentials(canonical(incoming))
    profile = read_json(checked_relative(root, PROFILE))
    timeline = read_json(checked_relative(root, TIMELINE))
    destination = checked_relative(root, LIFE_INPUTS[item["adapter"]])
    old = profile if item["adapter"] == "life_profile" else timeline
    shape(incoming, ("schema_version", "kind", "categories" if old is profile else "events"))
    one_of(incoming["schema_version"], (old["schema_version"],))
    one_of(incoming["kind"], (item["adapter"],))
    if old is profile:
        by_category = {row["category"]: row for row in profile["categories"]}
        used = set()
        for group in seq(incoming["categories"]):
            shape(group, ("category", "status", "records"), ("domains",))
            category = one_of(group["category"], tuple(by_category))
            if category in used:
                raise HubError("duplicate source life category")
            used.add(category)
            previous = by_category[category]
            provided = seq(group["records"])
            one_of(group["status"], ("unknown", "partial", "reviewed"))
            if bool(provided) != (group["status"] != "unknown"):
                raise HubError("source life category state does not match its records")
            if "domains" in group:
                domain_ids = [ident(item) for item in seq(group["domains"])]
                if len(domain_ids) != len(previous["domains"]) or set(domain_ids) != set(previous["domains"]):
                    raise HubError("source life category domains differ from its registry")
            records = merged_records(previous["records"], provided)
            state = group["status"] if not previous["records"] else previous["status"]
            if any(entry.get("status") not in ("fact", "self-report") for entry in records):
                state = "partial"
            by_category[category] = {**previous, "records": records, "status": state}
        profile = {**profile, "categories": list(by_category.values())}
        chosen = [entry for group in incoming["categories"] for entry in group["records"]]
        updated = profile
    else:
        timeline = {**timeline, "events": merged_records(timeline["events"], incoming["events"])}
        chosen = incoming["events"]
        updated = timeline
    archive_coverage(profile, timeline, level)
    if updated != old:
        write_atomic(destination, (canonical(updated) + "\n").encode("utf-8"))
    return {"status": "completed" if chosen else "partial", "outcome": "updated" if updated != old else "unchanged",
            "records": sorted({entry["record_id"] for entry in chosen}), "source_digest": digest(incoming),
            "date_coverage": source_dates([entry["source"] for entry in chosen])}


def save_setting(store, key, value):
    with store.transaction(write=True) as db:
        db.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, canonical(value)))


def load_settings(store, prefix):
    with store.transaction() as db:
        return {row["key"][len(prefix):]: strict_json(row["value"]) for row in db.execute(
            "SELECT key, value FROM settings WHERE substr(key, 1, ?) = ? ORDER BY key", (len(prefix), prefix),
        )}


def receipt_scope(item):
    return digest(item)


def source_dates(records):
    observed = sorted((record["observed_at"] for record in records if record.get("observed_at")),
                      key=datetime.fromisoformat)
    return {"basis": "source_observed_at", "from": observed[0] if observed else None,
            "through": observed[-1] if observed else None, "dated_records": len(observed),
            "undated_records": len(records) - len(observed)}


def apply_source(root, store, item):
    ready = source_readiness(item, probe=False)
    if ready["status"] == "blocked":
        return ready
    try:
        if item["adapter"] in LIFE_INPUTS:
            return import_life(root, store.level, item)
        approved = grant(store, item["id"], item["adapter"], item["path"], item["allow_raw"], capture_id=True)
        run = run_batch(store, LocalVault(store.root), "full", item["id"], archive_only=True, trace_items=True,
                        expected_grant=approved["grant_id"])
        state = {"no_items": "partial", "no_sources": "blocked"}.get(run["status"], run["status"])
        return {"status": state, "run_id": run["run_id"], "created": run["created"], "updated": run["updated"],
                "unchanged": run["unchanged"], "records": run["records"], "errors": run["errors"],
                "date_coverage": source_dates(run["records"])}
    except RECOVERABLE as exc:
        return problem(exc)


def apply(request, expected, consent):
    if not consent or expected != plan_fingerprint(request):
        raise Denied("apply requires explicit consent and the digest from this exact plan")
    try:
        root, binding, store = bootstrap_workspace(request["workspace"], request["vault"], request["sensitivity"])
        with batch_lock(root, filename=BOOTSTRAP_LOCK):
            save_setting(store, TARGET_KEY, request["github"]["target"] if request["github"] else None)
            for item in request["sources"]:
                result = apply_source(root, store, item)
                save_setting(store, SOURCE_KEY + item["id"],
                             {**result, "scope_digest": receipt_scope(item), "attempted_at": now()})
    except RECOVERABLE as exc:
        return report(request, workspace_failure=problem(exc))
    return report(request, bound=(root, binding, store))


def record_rows(store):
    """Summarize evidence without returning checkpoint, message, or claim content."""
    blobs = LocalVault(store.root)
    with store.transaction() as db:
        records = {kind: store.latest(db, kind) for kind in ("session", "project", "asset", "memory")}
        current_raw = {row["id"]: row["raw_revision"] for row in db.execute(
            """SELECT id, max(revision) AS raw_revision FROM revisions
            WHERE kind='session' AND json_type(content, '$.data.messages')='array' GROUP BY id""",
        )}
        lifecycle = dict(db.execute(
            "SELECT id, json_extract(content, '$.state') FROM revisions WHERE kind=? ORDER BY revision",
            (candidates.KIND,),
        ))
        result = {kind: [] for kind in records}
        for kind, entries in records.items():
            for entry in entries:
                fields = entry["data"]
                row = {key: entry[key] for key in ("id", "revision", "created_at", "record_digest")}
                source = entry["source"]
                row["source"] = {"kind": source["kind"], "observed_at": source.get("observed_at"),
                                 "evidence_sha256": digest(source)}
                if kind == "session":
                    row.update(project_id=fields.get("project_id"), layers={
                        "L0": True, "L1": bool(fields.get("summary")), "L2": bool(fields.get("checkpoint")),
                        "L3": entry["id"] in current_raw,
                    }, raw_revision=current_raw.get(entry["id"]))
                if kind == "asset":
                    row.update({key: fields[key] for key in ("storage", "sha256", "size", "project_id", "session_id")})
                    row["availability"] = availability(db, blobs, entry)["status"]
                    row["local_versions"] = [
                        {"revision": version["revision"], "storage": version["data"]["storage"],
                         "sha256": version["data"]["sha256"], "size": version["data"]["size"]}
                        for version in store.history(db, "asset", entry["id"])
                    ]
                if kind == "memory":
                    row.update(status=fields["status"], review_state=lifecycle.get(entry["id"], "not_started"))
                result[kind].append(row)
        return result, memory_review(records["memory"])


def agent_versions(store):
    return [
        {"channel": channel, "agent": agent, "detected_sha": state["detected_sha"], "synced_sha": state["synced_sha"]}
        for key, state in load_settings(store, "shared_version:").items()
        for channel, agent in [strict_json(key)]
    ]


def requested_repo(store, desired):
    if not desired:
        return {"status": "not_requested"}
    receipts = load_settings(store, REPO_KEY + desired["target"] + ":") if store else {}
    default = "not_verified" if shutil.which("gh") else "blocked"
    return {"status": receipts.get("publish", receipts.get("create", {})).get("status", default),
            "creation": receipts.get("create", {}).get("status", default),
            "publication": receipts.get("publish", {}).get("status", "not_requested"),
            **desired, "receipts": {key: val for key, val in receipts.items() if not key.endswith(":last_success")},
            "last_success": {key.removesuffix(":last_success"): val for key, val in receipts.items()
                             if key.endswith(":last_success")}}


def save_repo_receipt(store, action, target, result):
    key = REPO_KEY + target.lower() + ":" + action
    encoded = canonical({**result, "recorded_at": now()})
    writes = [(key, encoded)]
    if result["status"] == "completed":
        writes.append((key + ":last_success", encoded))
    with store.transaction(write=True) as db:
        db.executemany("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", writes)


def require_repo_target(store, target):
    saved = load_settings(store, TARGET_KEY)
    if saved.get("") != target.lower():
        raise Denied("apply a reviewed onboarding plan with this exact private GitHub target first")


def report(request, *, workspace_failure=None, bound=None):
    result = {"format": FORMAT, "kind": "onboarding_report", "plan_digest": plan_fingerprint(request),
              "engine_version": VERSION, "vault_schema_version": SCHEMA, "workspace": request["workspace"],
              "vault": request["vault"], "storage": workspace_failure, "sources": [],
              "github": requested_repo(None, request["github"]), "sync": {"scheduler": "not_verified"},
              "next_actions": []}
    store = None
    if workspace_failure is None:
        try:
            root, binding, store = bound or bound_workspace(
                request["workspace"], expected_vault=request["vault"], expected_level=request["sensitivity"],
            )
            result["life_archive"] = check_bound_workspace(root, binding, store)["life_archive"]
            result["data"], result["memory_review"] = record_rows(store)
            result["storage"] = {"status": "completed", "template_version": binding["template_version"],
                                 "vault_identity": binding["vault_identity"], "sensitivity": store.level}
        except RECOVERABLE as exc:
            store = None
            result["storage"] = problem(exc)
    saved = load_settings(store, SOURCE_KEY) if store else {}
    for item in request["sources"]:
        readiness = source_readiness(item, probe=False)
        receipt = saved.get(item["id"], {})
        if readiness["status"] != "blocked" and receipt.get("scope_digest") == receipt_scope(item):
            readiness = receipt
        result["sources"].append({"id": item["id"], "adapter": item["adapter"],
                                  "raw_authorized": item["allow_raw"], **readiness})
    if store:
        current = status(store, probe_sources=False)
        result["sync"] = {"scheduler": current["execution"]["scheduler"],
                          "switches": current["settings"]["switches"],
                          "source_status": current["sources"], "latest_runs": [
                              {key: row[key] for key in ("id", "feature", "started_at", "finished_at", "state")}
                              for row in current["latest_runs"]], "last_success": current["last_success"],
                          "last_archive_success": current["last_archive_success"], "agents": agent_versions(store)}
        result["github"] = requested_repo(store, request["github"])
    states = Counter(entry["status"] for entry in result["sources"])
    if not store:
        result["status"] = result["storage"]["status"]
    else:
        incomplete = (set(states) - {"completed"}
                      or result["github"]["status"] not in ("not_requested", "completed"))
        result["status"] = "partial" if incomplete else "completed"
    if not request["sources"]:
        result["next_actions"].append("Add explicit source paths and scope to the request if import is desired.")
    for entry in result["sources"]:
        if entry["status"] != "completed":
            result["next_actions"].append(
                f"Resolve the blocker for {entry['id']}, then review the plan and retry with that source.")
    if result.get("life_archive", {}).get("required_gaps"):
        result["next_actions"].append("Review the required life fields with the owner; leave unknowns unset.")
    if result.get("memory_review", {}).get("candidates"):
        result["next_actions"].append("Review candidate evidence, duplicates and conflicts before activation.")
    if result["github"]["status"] not in ("not_requested", "completed"):
        result["next_actions"].append("Review a separate Git projection and explicitly approve the target and digest.")
    if not store:
        result["next_actions"].append("Resolve the storage blocker and rerun the same approved apply.")
    result["markdown"] = markdown(result)
    return result


def markdown(result):
    labels = {"onboarding_plan": "Onboarding plan", "onboarding_report": "Onboarding report"}
    rows = [f"# {labels[result['kind']]}", "", f"- Status: `{result['status']}`",
            f"- Engine / Vault protocol: `{VERSION}` / `{SCHEMA}`",
            f"- Plan digest: `{result['plan_digest']}`",
            f"- Storage: `{result['storage']['status']}`",
            f"- GitHub: `{result['github'].get('status', 'not_verified')}`",
            f"- Scheduler: `{result.get('sync', {}).get('scheduler', 'not_verified')}`",
            "", "## Sources", ""]
    for source in result["sources"]:
        count = len(source.get("records", ()))
        suffix = f" {source['reason']}" if "reason" in source else ""
        rows.append(f"- `{source['id']}` / `{source['adapter']}` — `{source['status']}`, {count} recorded items.{suffix}")
        if source.get("run_id"):
            rows.append(f"  - Run `{source['run_id']}`, created {source['created']}, updated {source['updated']}, "
                        f"unchanged {source['unchanged']}, errors {len(source['errors'])}.")
        dates = source.get("date_coverage")
        if dates and dates["dated_records"]:
            rows.append(f"  - Observed from `{dates['from']}` through `{dates['through']}`.")
    if not result["sources"]:
        rows.append("- No source was requested.")
    if "data" in result:
        rows.extend(("", "## Local coverage", ""))
        for kind, records in result["data"].items():
            names = ", ".join(f"`{row['id']}@{row['revision']}`" for row in records)
            rows.append(f"- {kind}: {len(records)}" + (f" ({names})" if names else ""))
        sessions = result["data"]["session"]
        counts = ", ".join(f"{layer} {sum(row['layers'][layer] for row in sessions)}" for layer in ("L0", "L1", "L2", "L3"))
        life = result["life_archive"]
        rows += [f"- Session layers: {counts}.",
                 f"- Life archive: {life['registered']['categories']}/{life['registered']['domains']}/"
                 f"{life['registered']['fields']}, {len(life['missing_fields'])} fields without reviewed evidence.",
                 f"- Candidates: {result['memory_review']['candidates']}."]
        switches = result["sync"]["switches"]
        rows.append("- Sync switches: " + ", ".join(f"{name} {'on' if flag else 'off'}" for name, flag in switches.items()))
        for version in result["sync"]["agents"]:
            rows.append(f"- Agent `{version['agent']}` / `{version['channel']}`: detected "
                        f"`{version['detected_sha'] or 'unknown'}`, synced `{version['synced_sha'] or 'unknown'}`.")
    for action, receipt in result["github"].get("receipts", {}).items():
        rows.append(f"- GitHub {action}: `{receipt['status']}` at `{receipt['recorded_at']}`. "
                    f"Target `{receipt.get('target', result['github']['target'])}`, "
                    f"commit `{receipt.get('commit_sha') or 'unverified'}`, "
                    f"PR `{receipt.get('pull_request') or 'not_requested'}`.")
    if result.get("next_actions"):
        rows.extend(("", "## Next actions", ""))
        rows.extend(f"- {action}" for action in result["next_actions"])
    return "\n".join(rows) + "\n"


def write_markdown(request, path, result):
    root, _, _ = bound_workspace(
        request["workspace"], expected_vault=request["vault"], expected_level=request["sensitivity"],
    )
    path = Path(os.path.abspath(path.expanduser()))
    if path.suffix.lower() != ".md":
        raise Denied("select a new Markdown file inside the authorized Workspace")
    path = instance_path(path)
    if not path.is_relative_to(root):
        raise Denied("select a new Markdown file inside the authorized Workspace")
    if not path.parent.is_dir():
        raise Missing("the report parent directory must already exist")
    write_exclusive(path, result["markdown"].encode("utf-8"))
