"""Local, revision-pinned review for long-term memory candidates."""

from unicodedata import normalize

from .model import (
    Conflict, Denied, HubError, Missing, digest, document, external_url, ident, no_credentials, revision, text,
)

KIND = "memory_lifecycle"
TRANSITIONS = {
    "candidate": ("validated", "rejected"),
    "validated": ("review", "candidate", "rejected"),
    "review": ("pending", "approved", "rejected", "candidate"),
    "pending": ("review", "candidate", "rejected"),
    "approved": ("active", "pr-open", "revoked", "review"),
    "pr-open": ("pr-reviewed", "revoked", "review"),
    "pr-reviewed": ("pr-merged", "revoked", "review"),
    "pr-merged": ("active", "revoked", "review"),
    "active": ("revoked", "archived"),
    "superseded": ("archived",),
    "rejected": ("archived",),
    "revoked": ("archived",),
    "archived": (),
}


def envelope(item):
    return {key: item[key] for key in ("kind", "id", "schema_version", "sensitivity", "source", "data")}


def select(store, db, entry_id):
    item = store.get(db, "memory", ident(entry_id))
    if item is None:
        raise Missing("memory candidate does not exist")
    return item


def normalized(value):
    return " ".join(normalize("NFKC", value).split())


def peer_advice(store, db, item):
    data = item["data"]
    key, claim = normalized(data["key"]).casefold(), normalized(data["claim"])
    result = []
    for other in store.latest(db, "memory"):
        fields = other["data"]
        if other["id"] == item["id"] or fields["status"] not in ("accepted", "candidate"):
            continue
        if normalized(fields["key"]).casefold() != key:
            continue
        duplicate = normalized(fields["claim"]) == claim
        result.append({"id": other["id"], "revision": other["revision"], "status": fields["status"],
                       "relation": "duplicate" if duplicate else "conflict",
                       "suggestion": "link_or_reject" if duplicate else "compare_evidence"})
    return sorted(result, key=lambda row: row["id"])


def suggestions(store, entry_id):
    with store.transaction() as db:
        item = select(store, db, entry_id)
        lifecycle = store.get(db, KIND, entry_id)
        return {"id": entry_id, "record_revision": item["revision"], "record_status": item["data"]["status"],
                "lifecycle_revision": lifecycle["revision"] if lifecycle else 0,
                "state": lifecycle["state"] if lifecycle else "unmanaged",
                "peers": peer_advice(store, db, item)}


def history(store, entry_id):
    with store.transaction() as db:
        select(store, db, entry_id)
        return {"id": entry_id, "events": store.history(db, KIND, entry_id),
                "records": store.history(db, "memory", entry_id)}


def peer_revisions(peers):
    return {row["id"]: row["revision"] for row in peers}


def authorize_approval(item, advice, peers, supersede, attest):
    if not attest or item["data"].get("classification") not in ("fact", "rule", "preference"):
        raise Denied("approval needs explicit evidence verification and a confirmed fact, rule or preference class")
    if peers != peer_revisions(advice):
        raise Conflict("review and acknowledge the exact revisions of all matching peer records")
    accepted = [peer for peer in advice if peer["status"] == "accepted"]
    if any(peer["relation"] == "duplicate" for peer in accepted):
        raise Conflict("link to the accepted duplicate or reject this candidate")
    if supersede != peer_revisions(accepted):
        raise Conflict("explicitly list the accepted records and revisions to supersede")
    return {"peers": peers, "supersede": supersede, "evidence_verified": True}


def audit(store, db, item, previous, state, actor, reason, **fields):
    event = {"state": state, "actor": actor, "reason": reason, "memory_revision": item["revision"], **fields}
    result = store.append(db, KIND, item["id"], event, digest(event), previous)
    return {"id": item["id"], "state": state, "lifecycle_revision": result["revision"],
            "record_revision": item["revision"], **fields}


def write_status(store, db, item, status):
    value = envelope(item)
    value["base_revision"] = item["revision"]
    value["data"] = {**value["data"], "status": status}
    result = store.ingest(db, value, allow_review=True, lifecycle_decision=True)
    return {**item, "data": value["data"], "revision": result["revision"]}


def activate(store, db, item, approval, actor, reason):
    advice = peer_advice(store, db, item)
    if approval["peers"] != peer_revisions(advice):
        raise Conflict("matching peer records changed; return to review before activating")
    replacement = write_status(store, db, item, "accepted")
    for entry_id in approval["supersede"]:
        old = select(store, db, entry_id)
        prior = store.get(db, KIND, entry_id)
        old = write_status(store, db, old, "retired")
        audit(store, db, old, prior, "superseded", actor, reason,
              replacement={"id": replacement["id"], "revision": replacement["revision"]},
              replaced_revision=approval["supersede"][entry_id])
    return replacement


def step(store, entry_id, target, *, base, actor, reason, consent=False, record_revision=None,
         attest=False, peers=None, supersede=None, pr_ref=None):
    if not consent:
        raise Denied("candidate decisions require explicit authorization")
    code = ident(actor)
    no_credentials(text(reason, 1024))
    revision(base, 0)
    if target != "approved" and (attest or peers is not None or supersede is not None):
        raise HubError("evidence verification and peer choices are approval options")
    if (target == "pr-open") != (pr_ref is not None):
        raise HubError("supply a review link only when recording an opened PR")
    if pr_ref is not None and not external_url(pr_ref).startswith("https://"):
        raise HubError("PR evidence requires HTTPS")
    with store.transaction(write=True) as db:
        item = select(store, db, entry_id)
        previous = store.get(db, KIND, entry_id)
        current = previous["state"] if previous else "candidate"
        if base != (previous["revision"] if previous else 0):
            raise Conflict("candidate lifecycle base revision is stale")
        if target not in TRANSITIONS[current]:
            raise Conflict("illegal candidate state transition")
        if (previous is None or current == "candidate") and item["data"]["status"] != "candidate":
            raise Conflict("only draft memory candidates can start this workflow")
        if target == "validated" or previous is None:
            if record_revision is None or revision(record_revision) != item["revision"]:
                raise Conflict("select the exact candidate record revision")
        elif record_revision is not None or (current != "candidate" and previous["memory_revision"] != item["revision"]):
            raise Conflict("candidate record changed since validation")
        fields = {}
        if target == "validated":
            document(envelope(item), store.level)
            no_credentials(item["data"]["claim"])
            fields["source"] = item["source"]
        if target == "review":
            fields["peers"] = peer_advice(store, db, item)
        if target == "approved":
            fields["approval"] = authorize_approval(item, peer_advice(store, db, item), peers or {},
                                                   supersede or {}, attest)
        if target in ("pr-open", "pr-reviewed", "pr-merged", "active"):
            fields["approval"] = previous["approval"]
            link = pr_ref or previous.get("pr_ref")
            if link:
                fields["pr_ref"] = link
            if target == "active":
                item = activate(store, db, item, fields["approval"], code, reason)
        if target in ("rejected", "revoked") or (target == "archived" and current == "active"):
            item = write_status(store, db, item, "rejected" if target == "rejected" else "retired")
        return audit(store, db, item, previous, target, code, reason, **fields)
