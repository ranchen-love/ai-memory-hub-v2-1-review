"""Validate explicitly selected life archive metadata and optional aggregate summaries."""

from datetime import date
import re

from .model import LEVELS, Denied, HubError, evidence, ident, iso_date, one_of, seq, shape, text

CATEGORIES = tuple(f"{index:02d}" for index in range(1, 13))
RECORD_STATES = ("fact", "self-report", "hypothesis", "pending")
EVIDENCE_LEVELS = ("official", "secondary", "unverified")
SOURCE_TYPES = ("user_statement", "document", "official_record", "system_sync", "secondary_source")
PRECISIONS = ("day", "month", "year", "unknown")
COVERAGE = ("unknown", "partial", "reviewed")
ARCHIVE_VERSION = "1.0"
DATE_PATTERNS = {"day": r"\d{4}-\d{2}-\d{2}", "month": r"\d{4}-\d{2}", "year": r"\d{4}"}


def archive_date(value, precision="day"):
    one_of(precision, PRECISIONS)
    if precision == "unknown":
        if value is not None:
            raise HubError("unknown precision requires a null date")
        return None
    if not isinstance(value, str) or not re.fullmatch(DATE_PATTERNS[precision], value, flags=re.ASCII):
        raise HubError("archive date and precision differ")
    try:
        suffix = {"day": "", "month": "-01", "year": "-01-01"}[precision]
        return date.fromisoformat(value + suffix)
    except ValueError as exc:
        raise HubError("archive date is invalid") from exc


def header(value, kind, fields):
    shape(value, ("schema_version", "kind", *fields))
    one_of(value["schema_version"], (ARCHIVE_VERSION,))
    one_of(value["kind"], (kind,))


def record(value, sensitivity, timeline=False):
    needed = ("record_id", "category", "status", "evidence_level", "source", "source_type",
              "created_at", "updated_at", "summary", "sensitivity")
    optional = ("valid_from", "valid_to", "supersedes", "superseded_by", "related_records", "extensions")
    time_fields = ("occurred_at", "date_precision") if timeline else ()
    shape(value, (*needed, *time_fields), optional)
    ident(value["record_id"])
    one_of(value["category"], CATEGORIES)
    one_of(value["status"], RECORD_STATES)
    one_of(value["evidence_level"], EVIDENCE_LEVELS)
    one_of(value["source_type"], SOURCE_TYPES)
    evidence(value["source"])
    text(value["summary"])
    level = one_of(value["sensitivity"], LEVELS)
    if LEVELS.index(level) > LEVELS.index(sensitivity):
        raise Denied("life record exceeds the workspace sensitivity")
    if iso_date(value["updated_at"]) < iso_date(value["created_at"]):
        raise HubError("updated_at precedes created_at")
    start = archive_date(value["valid_from"]) if value.get("valid_from") is not None else None
    end = archive_date(value["valid_to"]) if value.get("valid_to") is not None else None
    if start and end and end < start:
        raise HubError("invalid validity interval")
    if timeline:
        archive_date(value["occurred_at"], value["date_precision"])
    for field in ("supersedes", "related_records"):
        links = [ident(item) for item in seq(value.get(field, []))]
        if len(set(links)) != len(links):
            raise HubError("duplicate archive reference")
    if "superseded_by" in value:
        ident(value["superseded_by"])
    if "extensions" in value and not isinstance(value["extensions"], dict):
        raise HubError("extensions must be an object")


def archive_coverage(profile, timeline, sensitivity):
    header(profile, "life_profile", ("categories",))
    header(timeline, "life_timeline", ("events",))
    states, records = {}, {}

    def add(item, is_event=False):
        record(item, sensitivity, is_event)
        key = item["record_id"]
        if key in records:
            raise HubError("duplicate life record ID")
        records[key] = item

    for category in seq(profile["categories"]):
        shape(category, ("category", "status", "records"))
        category_id = one_of(category["category"], CATEGORIES)
        state = one_of(category["status"], COVERAGE)
        items = seq(category["records"])
        if category_id in states or bool(items) != (state != "unknown"):
            raise HubError("duplicate category or inconsistent coverage state")
        if state == "reviewed" and any(
            not isinstance(item, dict) or item.get("status") not in ("fact", "self-report")
            for item in items
        ):
            raise HubError("reviewed coverage permits confirmed facts and labeled self-reports")
        states[category_id] = state
        for item in items:
            add(item)
            if item["category"] != category_id:
                raise HubError("life record appears in the wrong category")
    if set(states) != set(CATEGORIES):
        raise HubError("profile must cover all twelve categories")
    for item in seq(timeline["events"]):
        add(item, is_event=True)
    validate_lineage(records)
    return {"categories": len(CATEGORIES), "states": {
        state: sum(value == state for value in states.values()) for state in COVERAGE
    }, "timeline_events": len(timeline["events"])}


def validate_lineage(records):
    successors = {}

    def connect(old, new):
        if successors.setdefault(old, new) != new:
            raise HubError("life record has conflicting successors")

    for key, item in records.items():
        supersedes = item.get("supersedes", [])
        links = supersedes + item.get("related_records", [])
        if "superseded_by" in item:
            links = links + [item["superseded_by"]]
        if key in links or any(ref not in records for ref in links):
            raise HubError("life record contains an invalid reference")
        for old in supersedes:
            connect(old, key)
        if "superseded_by" in item:
            connect(key, item["superseded_by"])
    checked = set()
    for start in successors:
        path = set()
        node = start
        while node in successors and node not in checked:
            if node in path:
                raise HubError("life record supersession contains a cycle")
            path.add(node)
            node = successors[node]
        checked.update(path)


def health_coverage(summary):
    header(summary, "health_aggregate", ("source", "period_from", "period_to", "observations"))
    evidence(summary["source"])
    if archive_date(summary["period_from"]) > archive_date(summary["period_to"]):
        raise HubError("invalid aggregate period")
    keys = set()
    for item in seq(summary["observations"]):
        shape(item, ("metric", "unit", "value", "samples"))
        key = (ident(item["metric"]), text(item["unit"], 32))
        if key in keys:
            raise HubError("duplicate aggregate metric and unit")
        keys.add(key)
        value, samples = item["value"], item["samples"]
        if type(value) not in (int, float) or not -10**15 <= value <= 10**15:
            raise HubError("invalid aggregate value")
        if type(samples) is not int or not 1 <= samples <= 10**9:
            raise HubError("invalid sample count")
    return {"status": "valid", "observations": len(keys)}
