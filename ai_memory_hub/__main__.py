"""Command-line entry point for local users and authorized executors."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import VERSION
from .adapters import ADAPTERS, describe, grant, list_sources, local_input, revoke
from .assets import (
    LINK_STATES, LocalVault, availability, export_public_text, observe_link, put_file, put_link, references, retrieve_blob,
)
from . import candidates, shared_version
from .handoff import create_handoff
from .life import health_coverage
from .model import FEATURES, LEVELS, PRESETS, Denied, HubError, Missing, ident, read_json, revision
from .store import Store, memory_review, view_session
from .sync import dispatch, failure, run_batch, status
from .transfer import inspect_transfer, pack_transfer, receive_transfer, retrieve_transfer
from .workspace import check_workspace, facts_projection, init_workspace


ORIGINS = ("user_upload", "ai_generated", "workspace_artifact")


def consent(args):
    if not args.consent:
        raise Denied("pass --consent only for material you are authorized to use")


def permit(command):
    command.add_argument("--consent", action="store_true", help="confirm authorization for this operation")


def sub(command):
    return command.add_subparsers(dest="action", required=True)


def parser():
    cli = argparse.ArgumentParser(prog="ai-memory-hub", description="Manage authorized context and files locally")
    cli.add_argument("--version", action="version", version=VERSION)
    cli.add_argument("--root", default=os.environ.get("AI_MEMORY_HUB_ROOT"), help="instance directory outside Git")
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize an owner-only instance")
    init.add_argument("--sensitivity", choices=LEVELS, default="private")
    setup = init.add_mutually_exclusive_group()
    setup.add_argument("--preset", choices=PRESETS, default="ordinary")
    setup.add_argument("--wizard", action="store_true", help="choose a path and sync preset interactively")
    config = sub(commands.add_parser("config", help="view or change independent sync switches"))
    config.add_parser("show")
    swap = config.add_parser("preset")
    swap.add_argument("preset", choices=PRESETS)
    switch = config.add_parser("set")
    switch.add_argument("feature", choices=FEATURES)
    switch.add_argument("value", choices=("on", "off"))

    manual = commands.add_parser("import", help="import one normalized record")
    manual.add_argument("--input", required=True, type=Path)
    manual.add_argument("--allow-raw", action="store_true")
    manual.add_argument("--review-decision", action="store_true", help="apply a confirmed memory review decision")
    permit(manual)
    for kind in ("session", "project", "memory"):
        actions = sub(commands.add_parser(kind, help=f"inspect {kind} records"))
        listing = actions.add_parser("list")
        show = actions.add_parser("show")
        show.add_argument("id")
        show.add_argument("--revision", type=int)
        history = actions.add_parser("history")
        history.add_argument("id")
        if kind == "session":
            listing.add_argument("--project")
            listing.add_argument("--text")
            show.add_argument("--layer", choices=("L0", "L1", "L2", "L3"), default="L2")
            permit(show)
        if kind == "memory":
            actions.add_parser("review", help="report candidate duplicates and conflicts")

    assets = sub(commands.add_parser("asset", help="store, inspect, verify or retrieve files"))
    assets.add_parser("list")
    for name in ("check", "copy", "git-export", "refs", "observe"):
        operation = assets.add_parser(name)
        operation.add_argument("id")
        if name != "refs":
            operation.add_argument("--version", type=int)
        if name in ("copy", "git-export", "observe"):
            permit(operation)
        if name == "git-export":
            operation.add_argument("--output", required=True, type=Path)
        if name == "observe":
            operation.add_argument("--state", required=True, choices=LINK_STATES)
            operation.add_argument("--evidence", required=True)
    for name in ("add", "link"):
        command = assets.add_parser(name)
        permit(command)
        command.add_argument("--id")
        command.add_argument("--base", type=int)
        command.add_argument("--name", required=name == "link")
        command.add_argument("--project")
        command.add_argument("--session")
        command.add_argument("--origin", choices=ORIGINS, default="user_upload")
        command.add_argument("--evidence", required=True)
        if name == "add":
            command.add_argument("--file", required=True, type=Path)
        else:
            command.add_argument("--url", required=True)
            command.add_argument("--expires-at")

    sources = sub(commands.add_parser("source", help="authorize an explicit local input"))
    sources.add_parser("list")
    new_source = sources.add_parser("grant")
    new_source.add_argument("id")
    new_source.add_argument("adapter", choices=ADAPTERS)
    new_source.add_argument("--path", required=True, type=Path)
    new_source.add_argument("--allow-raw", action="store_true")
    permit(new_source)
    sources.add_parser("revoke").add_argument("id")

    jobs = sub(commands.add_parser("sync", help="run or inspect synchronization"))
    jobs.add_parser("status")
    for mode in ("full", "daily", "weekly"):
        job = jobs.add_parser(mode)
        job.add_argument("--source")
    event = jobs.add_parser("event")
    event.add_argument("--source", required=True)
    event.add_argument("--event", required=True, help="event JSON path relative to an active source")
    permit(event)
    local = sub(commands.add_parser("local", help="run or inspect an authorized local archive"))
    local.add_parser("status")
    local_run = local.add_parser("run")
    local_run.add_argument("--source", required=True, help="an existing explicit source grant")
    local_run.add_argument("--mode", choices=("full", "weekly", "daily"), default="full")
    handoff = commands.add_parser("handoff", help="write a local project context package")
    handoff.add_argument("--project", required=True)
    permit(handoff)
    transfer = sub(commands.add_parser("transfer", help="prepare or receive a project package"))
    sender = transfer.add_parser("pack")
    sender.add_argument("--project", required=True)
    sender.add_argument("--asset", action="append", default=[], metavar="ID@REV")
    permit(sender)
    receiver = transfer.add_parser("receive")
    receiver.add_argument("--input", required=True, type=Path)
    permit(receiver)
    for action in ("inspect", "file"):
        read = transfer.add_parser(action)
        read.add_argument("id")
        if action == "file":
            read.add_argument("asset", metavar="ID@REV")
        permit(read)
    candidate = sub(commands.add_parser("candidate", help="validate and review revision-pinned memory proposals"))
    for operation in ("suggest", "history", "advance"):
        action = candidate.add_parser(operation)
        action.add_argument("id")
        permit(action)
        if operation == "advance":
            action.add_argument("state", choices=sorted({state for targets in candidates.TRANSITIONS.values() for state in targets}))
            action.add_argument("--base", type=int, required=True, help="expected lifecycle revision, or 0")
            action.add_argument("--record-revision", type=int, help="exact draft revision at validation")
            action.add_argument("--actor", required=True)
            action.add_argument("--reason", required=True)
            action.add_argument("--evidence-verified", action="store_true", help="attest to reviewed evidence")
            action.add_argument("--ack-peer", action="append", metavar="ID@REV")
            action.add_argument("--supersede", action="append", metavar="ID@REV")
            action.add_argument("--pr-ref", help="URL of an externally reviewed PR")

    version = sub(commands.add_parser("version", help="detect and acknowledge shared memory revisions"))
    snapshot = version.add_parser("snapshot")
    snapshot.add_argument("--name", required=True)
    selection = snapshot.add_mutually_exclusive_group(required=True)
    selection.add_argument("--include", action="append", metavar="SCOPE=ID")
    selection.add_argument("--empty", action="store_true")
    permit(snapshot)
    for operation in ("check", "reload", "confirm"):
        action = version.add_parser(operation)
        action.add_argument("--channel", required=True)
        action.add_argument("--agent", required=True)
        permit(action)
        if operation == "check":
            action.add_argument("--snapshot", type=Path, required=True)
        elif operation == "reload":
            action.add_argument("--scope", action="append", default=[])
        else:
            action.add_argument("--sha", required=True)
            action.add_argument("--receipt", required=True)

    workspace = sub(commands.add_parser("workspace", help="initialize or verify a portable memory workspace"))
    initialize = workspace.add_parser("init")
    initialize.add_argument("--path", required=True, type=Path)
    initialize.add_argument("--vault", type=Path)
    initialize.add_argument("--sensitivity", choices=LEVELS, default="private")
    initialize.add_argument("--demo", action="store_true", help="include synthetic inputs without authorizing them")
    workspace.add_parser("check").add_argument("--path", required=True, type=Path)
    facts = workspace.add_parser("facts")
    facts.add_argument("--path", required=True, type=Path)
    permit(facts)
    health = workspace.add_parser("health-check")
    health.add_argument("--input", required=True, type=Path)
    permit(health)
    return cli


def show_records(store, args):
    with store.transaction() as db:
        if args.action == "list":
            items = store.latest(db, args.command)
            if args.command == "session":
                items = [view_session(item, "L1") for item in items]
                if args.project:
                    items = [item for item in items if item["project_id"] == args.project]
                if args.text:
                    needle = args.text.casefold()
                    items = [item for item in items if needle in (item["title"] + " " + (item["summary"] or "")).casefold()]
            return {"records": items}
        if args.action == "review":
            return memory_review(store.latest(db, "memory"))
        if args.action == "history":
            items = store.history(db, args.command, args.id)
            return {"records": [view_session(item, "L0") for item in items] if args.command == "session" else items}
        if args.command == "session" and args.layer == "L3":
            consent(args)
        item = store.get(db, args.command, args.id, args.revision)
        if item is None:
            raise Missing("record not found")
        if args.command != "session":
            return item
        return store.session_view(db, item, args.layer, raw_consent=args.consent)


def asset_command(store, blobs, args):
    action = args.action
    if action in ("add", "link"):
        consent(args)
        source = {"provider": "manual", "kind": "workspace_artifact", "locator": args.origin + ":" + args.evidence}
        fields = {"asset_id": args.id, "project_id": args.project, "session_id": args.session, "base": args.base}
        if action == "link":
            with store.transaction(write=True) as db:
                return put_link(store, db, args.url, args.name, source, expires_at=args.expires_at, **fields)
        with blobs.stage(local_input(args.file.expanduser().absolute())) as staged, store.transaction(write=True) as db:
            return put_file(store, db, blobs, staged, args.name or args.file.name, source, **fields)
    with store.transaction(write=action == "observe") as db:
        if action == "list":
            return {"assets": [
                {**item, "availability": availability(db, blobs, item)} for item in store.latest(db, "asset")
            ]}
        if action == "refs":
            return references(db, args.id)
        if action == "observe":
            consent(args)
            source = {"provider": "manual", "kind": "user_checkpoint", "locator": args.evidence}
            return observe_link(db, args.id, args.version, args.state, source)
        item = store.get(db, "asset", args.id, args.version)
        if item is None:
            raise Missing("asset revision not found")
        if action == "check":
            return {**item, "availability": availability(db, blobs, item)}
    consent(args)
    if action == "copy":
        if item["data"]["storage"] != "vault":
            raise Missing("the external reference has no stored file to copy")
        return retrieve_blob(store.root, blobs, item["data"]["sha256"], item["data"]["name"])
    return export_public_text(store, blobs, item, args.output)


def setup_wizard(root):
    def prompt(label):
        print(label, end=" ", file=sys.stderr, flush=True)
        try:
            return input().strip()
        except EOFError:
            raise HubError("setup wizard ended before a choice was entered") from None

    if not root:
        default = str(Path.home() / "AI-Memory-Hub")
        root = prompt(f"Instance path outside Git [{default}]") or default
    print(
        "1 Ordinary: weekly and on-demand. "
        "2 Archive: adds daily catch-up. "
        "3 Collaboration: adds daily, events and handoff.",
        file=sys.stderr,
    )
    option = prompt("Sync preset [1]")
    if option not in ("", "1", "2", "3"):
        raise HubError("choose 1, 2 or 3")
    return root, {"": "ordinary", "1": "ordinary", "2": "archive", "3": "collaboration"}[option]


def revision_choices(values):
    if values is None:
        return None
    choices = {}
    for entry in values:
        key, separator, number = entry.rpartition("@")
        if not separator or not number.isascii() or not number.isdecimal() or len(number) > 19:
            raise HubError("expected ID@REV")
        ident(key)
        if key in choices:
            raise HubError("duplicate review record ID")
        choices[key] = revision(int(number))
    return choices


def candidate_command(store, args):
    consent(args)
    if args.action == "suggest":
        return candidates.suggestions(store, args.id)
    if args.action == "history":
        return candidates.history(store, args.id)
    return candidates.step(
        store, args.id, args.state, base=args.base, record_revision=args.record_revision,
        actor=args.actor, reason=args.reason, consent=True, attest=args.evidence_verified,
        peers=revision_choices(args.ack_peer), supersede=revision_choices(args.supersede), pr_ref=args.pr_ref,
    )


def version_command(store, args):
    consent(args)
    if args.action == "snapshot":
        selected = {}
        for entry in args.include or ():
            scope, _, key = entry.partition("=")
            selected.setdefault(ident(scope), []).append(ident(key))
        return shared_version.snapshot(store, args.name, selected, consent=True)
    if args.action == "check":
        return shared_version.check(store, args.channel, args.agent, args.snapshot, consent=True)
    if args.action == "reload":
        return shared_version.reload(store, args.channel, args.agent, args.scope, consent=True)
    return shared_version.confirm(store, args.channel, args.agent, args.sha, args.receipt, consent=True)


def execute(args, governance=None, initial_switches=None):
    if args.command == "workspace":
        if args.action == "init":
            return init_workspace(args.path, args.vault, args.sensitivity, args.demo)
        if args.action == "check":
            return check_workspace(args.path)
        consent(args)
        if args.action == "facts":
            return facts_projection(args.path)
        return health_coverage(read_json(local_input(args.input.expanduser().absolute())))
    if args.command == "init" and args.wizard:
        args.root, args.preset = setup_wizard(args.root)
        initial_switches = None
    if not args.root:
        raise HubError("select an instance with --root or AI_MEMORY_HUB_ROOT")
    if args.command == "init":
        switches = initial_switches if initial_switches is not None else dict(zip(FEATURES, PRESETS[args.preset]))
        return Store(args.root, initialize=args.sensitivity, switches=switches).settings()
    store = Store(args.root)
    if args.command == "candidate":
        return candidate_command(store, args)
    if args.command == "version":
        return version_command(store, args)
    blobs = LocalVault(store.root)
    if args.command == "config":
        if args.action == "preset":
            return store.settings(preset=args.preset)
        if args.action == "set":
            return store.settings(feature=args.feature, enabled=args.value == "on")
        return store.settings()
    if args.command == "import":
        consent(args)
        record = read_json(local_input(args.input.expanduser().absolute()))
        with store.transaction(write=True) as db:
            return store.ingest(db, record, args.allow_raw, args.review_decision)
    if args.command in ("session", "project", "memory"):
        return show_records(store, args)
    if args.command == "asset":
        return asset_command(store, blobs, args)
    if args.command == "source":
        if args.action == "grant":
            consent(args)
            return grant(store, args.id, args.adapter, args.path, args.allow_raw)
        if args.action == "revoke":
            return revoke(store, args.id)
        with store.transaction() as db:
            sources = list_sources(db)
        return {"sources": [describe(source) for source in sources]}
    if args.command == "local":
        if args.action == "status":
            return status(store)
        return run_batch(store, blobs, args.mode, args.source, archive_only=True)
    if args.command == "transfer":
        consent(args)
        if args.action == "pack":
            return pack_transfer(store, blobs, args.project, args.asset)
        if args.action == "receive":
            return receive_transfer(store, blobs, args.input)
        if args.action == "inspect":
            return inspect_transfer(store, blobs, args.id)
        return retrieve_transfer(store, blobs, args.id, args.asset)
    if args.command == "handoff":
        consent(args)
        return create_handoff(store, blobs, args.project)
    if args.action == "status":
        return status(store)
    if args.action == "event":
        consent(args)
        return dispatch(store, blobs, args.source, args.event)
    return run_batch(store, blobs, args.action, args.source, governance)


def main(argv=None, governance=None, initial_switches=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args, governance=governance, initial_switches=initial_switches)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if result.get("status") in ("failed", "partial", "no_sources", "no_items") else 0
    except (HubError, OSError, json.JSONDecodeError, UnicodeError, sqlite3.Error, RecursionError) as exc:
        error = failure(exc, None)
        print(json.dumps({"status": "error", "code": error["code"], "reason": error["message"]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
