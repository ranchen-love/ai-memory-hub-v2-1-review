"""Authorize an exact, redacted selection of private Vault records."""

import re

from . import candidates
from .model import Conflict, Denied, HubError, Missing, canonical, digest, ident, one_of, revision, seq, shape, strict_json
from .projection import FORMAT, MAX_FILE, MAX_SELECTIONS, MEMORY_CLASSES, REVIEWED_PATHS, encoded, json_value, safe_text
from .transfer import checksum


POLICY = "private-reviewed"
RECEIPT_PREFIX = "projection_review:"
PUBLICATION_PREFIX = "projection_publication:"
PURPOSES = {"memory": ("reference",), "project": ("continuity",), "session": ("navigation", "continuity")}
STATES = ("planned", "active", "blocked", "done", "archived")


def target_name(value):
    from .github_publish import target_name as parse

    owner, name = parse(value)
    return f"{owner.lower()}/{name.lower()}"


def alias(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        raise HubError("choose a portable shareable alias using lowercase letters, digits and hyphens")
    safe_text(value)
    return value


def checked_text(value, limit):
    safe_text(value)
    if len(value) > limit:
        raise HubError("reviewed text exceeds its field limit")


def validate_data(kind, data, *, published=False):
    if kind == "memory":
        shape(data, ("key", "claim", "classification") if published else ("key", "claim"))
        checked_text(data["key"], 120)
        checked_text(data["claim"], 1000)
        if published:
            one_of(data["classification"], MEMORY_CLASSES)
        return
    required = ("title", "state") if published and kind == "project" else ("title",)
    optional = ("summary", "checkpoint", "project") if kind == "session" else ("summary", "checkpoint")
    shape(data, required, optional)
    checked_text(data["title"], 160)
    if "summary" in data:
        checked_text(data["summary"], 1000)
    if "state" in data:
        one_of(data["state"], STATES)
    if "project" in data:
        alias(data["project"])
    if "checkpoint" in data:
        checkpoint = data["checkpoint"]
        shape(checkpoint, ("goal",), ("decisions", "next_actions"))
        checked_text(checkpoint["goal"], 480)
        for key in ("decisions", "next_actions"):
            values = seq(checkpoint.get(key, []))
            if len(values) > 8:
                raise HubError("reviewed checkpoints allow at most eight entries per list")
            for value in values:
                checked_text(value, 360)


def validate_review_binding(binding):
    shape(binding, ("digest", "target", "sensitivity"))
    checksum(binding["digest"])
    if binding["target"] != target_name(binding["target"]) or binding["sensitivity"] != POLICY:
        raise Denied("review must be bound to one canonical Private destination")


def validate_sections(sections):
    aliases, projects, links, references, keys = set(), set(), set(), set(), set()
    for kind, section in sections.items():
        shape(section, ("format", "kind", "records"))
        one_of(section["format"], (FORMAT,))
        one_of(section["kind"], (kind,))
        records = seq(section["records"])
        if not records:
            raise HubError("omit empty reviewed sections")
        order = []
        for row in records:
            shape(row, ("id", "purpose", "revision", "source_ref", "data"))
            name = alias(row["id"])
            source_ref = checksum(row["source_ref"])
            if name in aliases or source_ref in references:
                raise Conflict("review contains duplicate aliases or source references")
            order.append(name)
            aliases.add(name)
            references.add(source_ref)
            one_of(row["purpose"], PURPOSES[kind])
            revision(row["revision"])
            validate_data(kind, row["data"], published=True)
            if kind == "project":
                projects.add(name)
            elif kind == "session" and "project" in row["data"]:
                links.add(row["data"]["project"])
            elif kind == "memory":
                key = candidates.normalized(row["data"]["key"]).casefold()
                if key in keys:
                    raise Conflict("review contains conflicting or duplicate memory keys")
                keys.add(key)
        if order != sorted(order):
            raise HubError("reviewed section records must be sorted by alias")
    if len(aliases) > MAX_SELECTIONS or links - projects:
        raise Conflict("review contains too many records or a session links to an unapproved project")


def source_record(store, db, kind, source, edition, fields):
    if kind == "session":
        # Inspect only index metadata. No original text or raw message fields are returned.
        item = db.execute(
            """SELECT revision, fingerprint AS record_digest,
               json_extract(content, '$.data.project_id') AS project_id,
               json_type(content, '$.data.summary') AS summary_type,
               json_type(content, '$.data.checkpoint') AS checkpoint_type
               FROM revisions WHERE kind='session' AND id=? ORDER BY revision DESC LIMIT 1""", (source,),
        ).fetchone()
    else:
        item = store.get(db, kind, source)
    if item is None:
        raise Missing("a selected review source does not exist")
    if item["revision"] != edition:
        raise Conflict("a selected review source revision changed")
    if kind == "memory":
        memory = item["data"]
        lifecycle = store.get(db, candidates.KIND, source)
        if (memory["status"] != "accepted" or memory.get("classification") not in MEMORY_CLASSES
                or (lifecycle and lifecycle["state"] != "active")):
            raise Denied("only accepted, reviewed, non-inferred memories may be shared")
        if any(peer["relation"] == "conflict" for peer in candidates.peer_advice(store, db, item)):
            raise Conflict("resolve conflicting memory evidence before preparing publication")
        fields = {**fields, "classification": memory["classification"]}
    if kind == "project":
        fields = {**fields, "state": item["data"]["state"]}
    project = None
    if kind == "session":
        project = item["project_id"]
        if (("summary" in fields and item["summary_type"] != "text")
                or ("checkpoint" in fields and item["checkpoint_type"] != "object")):
            raise Denied("the reviewed session cannot claim a layer absent from its source")
    return item["record_digest"], project, fields


def collect_review(store, db, spec):
    if store.level != "private":
        raise Denied("redacted review is available for the private Vault boundary")
    shape(spec, ("format", "target", "items"))
    one_of(spec["format"], (FORMAT,))
    target = target_name(spec["target"])
    items = seq(spec["items"])
    if not 0 < len(items) <= MAX_SELECTIONS:
        raise HubError("review must contain between one and 128 selected records")
    selected, projects, relations, seen = [], {}, [], set()
    for row in items:
        shape(row, ("kind", "source", "id", "purpose", "data"))
        kind = one_of(row["kind"], tuple(PURPOSES))
        name = alias(row["id"])
        purpose = one_of(row["purpose"], PURPOSES[kind])
        shape(row["source"], ("id", "revision"))
        source, edition = ident(row["source"]["id"]), revision(row["source"]["revision"])
        if (kind, source) in seen:
            raise Conflict("a Vault source can only appear once in a review")
        seen.add((kind, source))
        fields = row["data"]
        validate_data(kind, fields)
        fingerprint, project, data = source_record(store, db, kind, source, edition, fields)
        if kind == "project":
            projects[name] = source
        if kind == "session" and "project" in data:
            relations.append((data["project"], project))
        selected.append({"kind": kind, "source": {"id": source, "revision": edition, "digest": fingerprint},
                         "id": name, "purpose": purpose, "data": data})
    if any(not project or projects.get(name) != project for name, project in relations):
        raise Conflict("session project alias does not match its approved Vault project source")
    return {"format": FORMAT, "target": target, "sensitivity": POLICY,
            "items": sorted(selected, key=lambda item: (item["kind"], item["id"]))}


def render(receipt):
    approval = digest(receipt)
    sections = {}
    for item in receipt["items"]:
        kind, source = item["kind"], item["source"]
        section = sections.setdefault(kind, {"format": FORMAT, "kind": kind, "records": []})
        section["records"].append({
            "id": item["id"], "purpose": item["purpose"], "revision": source["revision"],
            "source_ref": digest([approval, kind, source]),
            "data": item["data"],
        })
    validate_sections(sections)
    files = {REVIEWED_PATHS[kind]: encoded(section) for kind, section in sections.items()}
    if any(len(contents) > MAX_FILE for contents in files.values()):
        raise Denied("reviewed section exceeds the 512 KiB publication limit")
    return files


def review(store, spec, *, expected=None, consent=False, redacted=False):
    approve = expected is not None
    if approve and (consent is not True or redacted is not True):
        raise Denied("approval needs explicit owner consent and confirmation of redaction")
    with store.transaction(write=approve) as db:
        receipt = collect_review(store, db, spec)
        files = render(receipt)
        approval = digest(receipt)
        if approve and approval != checksum(expected):
            raise Conflict("review content, source revision or destination differs from the approved digest")
        status = "review_ready"
        if approve:
            changed = db.execute(
                "INSERT OR IGNORE INTO settings VALUES (?, ?)", (RECEIPT_PREFIX + approval, canonical(receipt)),
            ).rowcount
            status = "approved" if changed else "unchanged"
    return {"status": status, "review_digest": approval, "target": receipt["target"],
            "sensitivity": POLICY, "items": receipt["items"],
            "files": {name: json_value(contents) for name, contents in files.items()}}


def original_request(receipt):
    items = []
    for row in receipt["items"]:
        fields = {key: value for key, value in row["data"].items() if key not in ("classification", "state")}
        items.append({**row, "data": fields, "source": {key: row["source"][key] for key in ("id", "revision")}})
    return {"format": FORMAT, "target": receipt["target"], "items": items}


def approved_sections(store, db, approval):
    row = db.execute("SELECT value FROM settings WHERE key=?", (RECEIPT_PREFIX + checksum(approval),)).fetchone()
    if row is None:
        raise Denied("this Vault has no approval for the selected review")
    receipt = strict_json(row["value"])
    if digest(receipt) != approval or collect_review(store, db, original_request(receipt)) != receipt:
        raise Conflict("review evidence or saved approval has changed")
    return {"digest": approval, "target": receipt["target"], "sensitivity": POLICY}, render(receipt)


def authorize_publication(store, db, files, binding, target):
    if store is None or binding["target"] != target_name(target):
        raise Denied("reviewed private material requires its approved Vault and exact destination")
    approved, content = approved_sections(store, db, binding["digest"])
    if approved != binding or content != {name: files[name] for name in REVIEWED_PATHS.values() if name in files}:
        raise Denied("published sections do not match the exact redacted Vault approval")


def publication_key(repository_id, projection_digest):
    return f"{PUBLICATION_PREFIX}{repository_id}:{projection_digest}"


def published_bases(db, repository_id, projection_digest, binding):
    row = db.execute("SELECT value FROM settings WHERE key=?",
                     (publication_key(repository_id, projection_digest),)).fetchone()
    if row is None:
        raise Denied("private projection history has no matching local publication authorization")
    receipt = strict_json(row["value"])
    if receipt["review"] != binding:
        raise Denied("private projection history differs from its local publication authorization")
    return receipt["bases"]


def remember_publication(db, repository_id, projection_digest, binding, base):
    key = publication_key(repository_id, projection_digest)
    if db.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone():
        bases = published_bases(db, repository_id, projection_digest, binding)
    else:
        bases = []
    if base not in bases:
        db.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, canonical({"review": binding, "bases": [*bases, base]})))
