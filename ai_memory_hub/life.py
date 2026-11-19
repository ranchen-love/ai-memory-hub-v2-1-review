"""Validate explicitly selected life archive metadata and optional aggregate summaries."""

from datetime import date
import re

from .model import LEVELS, Denied, HubError, evidence, ident, iso_date, no_credentials, one_of, read_json, seq, shape, text

CATEGORIES = tuple(f"{index:02d}" for index in range(1, 13))
RECORD_STATES = ("fact", "self-report", "hypothesis", "pending")
EVIDENCE_LEVELS = ("official", "secondary", "unverified")
SOURCE_TYPES = ("user_statement", "document", "official_record", "system_sync", "secondary_source")
PRECISIONS = ("day", "month", "year", "unknown")
COVERAGE = ("unknown", "partial", "reviewed")
ARCHIVE_VERSION = "1.0"
DATE_PATTERNS = {"day": r"\d{4}-\d{2}-\d{2}", "month": r"\d{4}-\d{2}", "year": r"\d{4}"}


DOMAIN_COUNTS = (5, 4, 4, 5, 4, 5, 4, 4, 4, 4, 4, 5)
FIELD_COUNTS = (12, 10, 12, 14, 10, 12, 10, 10, 10, 12, 10, 12)
FIELD_TYPES = ("text", "text_list", "integer", "date", "reference", "reference_list",
               "enum", "presence", "presence_list")
REGISTRY = "life-archive/field-registry.json"


def validate_registry(value):
    header(value, "life_field_registry", ("categories",))
    registry = {}
    for category in seq(value["categories"]):
        shape(category, ("id", "label", "domains", "fields"))
        key = one_of(category["id"], CATEGORIES)
        if key in registry:
            raise HubError("duplicate category in field registry")
        text(category["label"], 100)
        domains = category["domains"]
        domain_count = DOMAIN_COUNTS[int(key) - 1]
        field_count = FIELD_COUNTS[int(key) - 1]
        if not isinstance(domains, dict) or set(domains) != {
            f"{key}-{i:02d}" for i in range(1, domain_count + 1)
        }:
            raise HubError("life field registry has incomplete domain coverage")
        for label in domains.values():
            text(label, 100)
        fields, covered = {}, set()
        for field in seq(category["fields"]):
            shape(field, ("id", "domains", "type", "expected", "source_hint", "timing",
                          "minimum_sensitivity"), ("choices",))
            name = ident(field["id"])
            field_type = one_of(field["type"], FIELD_TYPES)
            if name in fields or type(field["expected"]) is not bool:
                raise HubError("duplicate or invalid field in life registry")
            assigned = [one_of(domain, tuple(domains)) for domain in seq(field["domains"])]
            if not assigned or len(assigned) != len(set(assigned)):
                raise HubError("life field needs unique domain memberships")
            if field_type == "enum":
                choices = [ident(item) for item in seq(field.get("choices"))]
                if not choices or len(set(choices)) != len(choices):
                    raise HubError("registry enum requires unique choices")
            elif "choices" in field:
                raise HubError("choices require an enum")
            one_of(field["source_hint"], ("reference", "review", "owner", "evidence", "system"))
            one_of(field["timing"], ("none", "interval", "point"))
            one_of(field["minimum_sensitivity"], LEVELS)
            fields[name] = field
            covered.update(assigned)
        if len(fields) != field_count or set(domains) != covered:
            raise HubError("life field registry has incomplete field coverage")
        registry[key] = {"domains": domains, "fields": fields}
    if set(registry) != set(CATEGORIES):
        raise HubError("life field registry must cover all twelve categories")
    return {key: registry[key] for key in CATEGORIES}


def field_registry():
    from .workspace import template_root

    return validate_registry(read_json(template_root() / REGISTRY))


def bounded_level(value, lower, upper):
    place = LEVELS.index(one_of(value, LEVELS))
    if not LEVELS.index(lower) <= place <= LEVELS.index(upper):
        raise Denied("life field sensitivity is outside the allowed boundary")


def validity(value):
    start = archive_date(value["valid_from"]) if value.get("valid_from") is not None else None
    end = archive_date(value["valid_to"]) if value.get("valid_to") is not None else None
    if start and end and end < start:
        raise HubError("invalid validity interval")


def presence(value):
    shape(value, ("presence",), ("ref",))
    one_of(value["presence"], ("present", "absent", "unknown"))
    if "ref" in value:
        ident(value["ref"])
        no_credentials(value["ref"])
        if value["presence"] != "present":
            raise HubError("an opaque reference requires present status")


def field_value(value, definition):
    kind = definition["type"]
    if kind == "integer":
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise HubError("life field requires a bounded integer")
    elif kind == "enum":
        one_of(value, definition["choices"])
    else:
        validator = {"text": lambda item: no_credentials(text(item)), "reference": lambda item: no_credentials(ident(item)),
                     "presence": presence, "date": archive_date}[kind.removesuffix("_list")]
        for item in seq(value) if kind.endswith("_list") else [value]:
            validator(item)


def registered_fields(record, category):
    domain = record.get("domain")
    if "domain" in record:
        if not isinstance(domain, str) or domain not in category["domains"]:
            raise HubError("life record uses an invalid category domain")
    if "extensions" not in record:
        return
    extensions = record["extensions"]
    if not isinstance(extensions, dict) or domain is None:
        raise HubError("registered extensions require a domain and a field object")
    for key, entry in extensions.items():
        definition = category["fields"].get(key)
        if definition is None or domain not in definition["domains"]:
            raise HubError("life field is not registered in the selected domain")
        shape(entry, ("value", "source", "source_type", "observed_at",
                      "valid_from", "valid_to", "sensitivity"))
        evidence(entry["source"])
        one_of(entry["source_type"], SOURCE_TYPES)
        iso_date(entry["observed_at"])
        validity(entry)
        bounded_level(entry["sensitivity"], definition["minimum_sensitivity"], record["sensitivity"])
        field_value(entry["value"], definition)


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


def record(value, sensitivity, category_registry, timeline=False):
    needed = ("record_id", "category", "status", "evidence_level", "source", "source_type",
              "created_at", "updated_at", "summary", "sensitivity")
    optional = ("valid_from", "valid_to", "supersedes", "superseded_by", "related_records", "extensions", "domain")
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
    validity(value)
    if timeline:
        archive_date(value["occurred_at"], value["date_precision"])
    for field in ("supersedes", "related_records"):
        links = [ident(item) for item in seq(value.get(field, []))]
        if len(set(links)) != len(links):
            raise HubError("duplicate archive reference")
    if "superseded_by" in value:
        ident(value["superseded_by"])
    registered_fields(value, category_registry[value["category"]])


def archive_coverage(profile, timeline, sensitivity, registry=None):
    header(profile, "life_profile", ("categories",))
    header(timeline, "life_timeline", ("events",))
    registry = field_registry() if registry is None else registry
    states, records = {}, {}

    def add(item, is_event=False):
        record(item, sensitivity, registry, is_event)
        key = item["record_id"]
        if key in records:
            raise HubError("duplicate life record ID")
        records[key] = item

    for category in seq(profile["categories"]):
        shape(category, ("category", "status", "records"), ("domains",))
        category_id = one_of(category["category"], CATEGORIES)

        if "domains" in category:
            allowed = tuple(registry[category_id]["domains"])
            indexed = [one_of(domain, allowed) for domain in seq(category["domains"])]
            if len(indexed) != len(allowed) or set(indexed) != set(allowed):
                raise HubError("profile domain index must match the life field registry")
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
    replaced = validate_lineage(records)
    active = [item for key, item in records.items() if key not in replaced]
    return {"categories": len(CATEGORIES), "states": {
        state: sum(value == state for value in states.values()) for state in COVERAGE
    }, "timeline_events": len(timeline["events"]), **field_coverage(registry, active)}


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
    return successors


def field_coverage(registry, records):
    observed, reviewed = {}, {}
    for item in records:
        domain = item.get("domain")
        if domain is None:
            continue
        keys = item.get("extensions", {}).keys()
        observed.setdefault(domain, set()).update(keys)
        if item["status"] in ("fact", "self-report"):
            reviewed.setdefault(domain, set()).update(keys)
    missing_fields, required_gaps, states = [], [], {}
    field_count = 0
    for category, spec in registry.items():
        fields = spec["fields"]
        field_count += len(fields)
        for name, field in fields.items():
            if not any(name in reviewed.get(domain, ()) for domain in field["domains"]):
                key = f"{category}.{name}"
                missing_fields.append(key)
                if field["expected"]:
                    required_gaps.append(key)
        for domain in spec["domains"]:
            allowed = {name for name, field in fields.items() if domain in field["domains"]}
            expected = {name for name in allowed if fields[name]["expected"]} or allowed
            fields_seen = observed.get(domain, set())
            states[domain] = ("reviewed" if expected <= reviewed.get(domain, set()) else
                              "partial" if fields_seen else "unknown")
    return {"registered": {"categories": len(registry), "domains": len(states), "fields": field_count},
            "domains": states, "missing_fields": missing_fields, "required_gaps": required_gaps,
            "legacy_uncategorized_records": sum("domain" not in item for item in records)}


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
