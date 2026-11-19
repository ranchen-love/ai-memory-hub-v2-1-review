import copy
import json
import unittest
from pathlib import Path

from ai_memory_hub.life import archive_coverage, field_registry
from ai_memory_hub.model import Denied, HubError

ROOT = Path(__file__).resolve().parents[1]
AT = "2000-01-01T00:00:00Z"
SOURCE = {"provider": "fixture", "kind": "user_checkpoint", "locator": "fixture:profile"}


def fixture(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class LifeRegistryTests(unittest.TestCase):
    def setUp(self):
        self.profile = fixture("life-archive/profile.json")
        self.timeline = fixture("life-archive/timeline.json")

    def check(self, level="private"):
        return archive_coverage(self.profile, self.timeline, level)

    def record(self, category, domain, name, value, level="internal"):
        entry = {"record_id": "example-record", "category": category, "domain": domain,
                 "status": "self-report", "evidence_level": "unverified", "source": SOURCE,
                 "source_type": "user_statement", "created_at": AT, "updated_at": AT,
                 "summary": "Synthetic observation", "sensitivity": level,
                 "extensions": {name: {"value": value, "source": SOURCE, "source_type": "user_statement",
                                       "observed_at": AT, "valid_from": None, "valid_to": None,
                                       "sensitivity": level}}}
        bucket = self.profile["categories"][int(category) - 1]
        bucket.update(status="partial", records=[entry])
        return entry["extensions"][name]

    def test_exact_independent_structure_and_blank_coverage(self):
        registry = field_registry()
        self.assertEqual(tuple(registry), tuple(f"{i:02d}" for i in range(1, 13)))
        domains = tuple(len(item["domains"]) for item in registry.values())
        counts = tuple(len(item["fields"]) for item in registry.values())
        self.assertEqual(domains, (5, 4, 4, 5, 4, 5, 4, 4, 4, 4, 4, 5))
        self.assertEqual(counts, (12, 10, 12, 14, 10, 12, 10, 10, 10, 12, 10, 12))
        report = self.check()
        self.assertEqual(report["registered"], {"categories": 12, "domains": 52, "fields": 134})
        self.assertEqual(len(report["missing_fields"]), 134)
        self.assertEqual(set(report["domains"].values()), {"unknown"})
        self.assertEqual(report["legacy_uncategorized_records"], 0)

        self.assertEqual(sum(len(category["domains"]) for category in self.profile["categories"]), 52)
        self.profile["categories"][0]["domains"].pop()
        with self.assertRaises(HubError):
            self.check()

    def test_registered_value_provenance_dates_and_coverage(self):
        entry = self.record("01", "01-01", "birth_year", 2000)
        result = self.check()
        self.assertEqual(result["domains"]["01-01"], "partial")
        self.assertEqual(len(result["missing_fields"]), 133)
        for name, invalid in (("value", True), ("observed_at", "2000-01-01"),
                              ("source", {}), ("source_type", "unknown"), ("valid_to", "not-a-date")):
            previous = entry[name]
            entry[name] = invalid
            with self.subTest(field=name), self.assertRaises(HubError):
                self.check()
            entry[name] = previous
        entry.update(valid_from="2001-01-01", valid_to="2000-01-01")
        with self.assertRaisesRegex(HubError, "validity"):
            self.check()

    def test_wrong_domain_and_unregistered_field_are_rejected(self):
        self.record("01", "01-02", "birth_year", 2000)
        with self.assertRaisesRegex(HubError, "registered"):
            self.check()
        self.record("01", "01-01", "unregistered", "synthetic")
        with self.assertRaisesRegex(HubError, "registered"):
            self.check()
        self.record("01", "09-01", "birth_year", 2000)
        with self.assertRaisesRegex(HubError, "domain"):
            self.check()

    def test_sensitive_value_and_opaque_index_only(self):
        self.record("01", "01-04", "legal_name", "Synthetic person", "restricted")
        with self.assertRaises(Denied):
            self.check()
        entry = self.profile["categories"][0]["records"][0]["extensions"]["legal_name"]
        entry["value"] = {"presence": "present", "ref": "opaque-id"}
        self.check("restricted")
        entry["value"]["raw"] = "synthetic leaked value"
        with self.assertRaises(HubError):
            self.check("restricted")
        self.record("01", "01-01", "birth_year", 2000, "public")
        with self.assertRaises(Denied):
            self.check()

    def test_invalid_registry_and_legacy_unscoped_notes(self):
        from ai_memory_hub.life import validate_registry

        model = fixture("life-archive/field-registry.json")
        wrong = copy.deepcopy(model)
        wrong["categories"][0]["fields"].pop()
        with self.assertRaises(HubError):
            validate_registry(wrong)
        self.record("01", "01-01", "birth_year", 2000)
        note = self.profile["categories"][0]["records"][0]
        note.pop("domain")
        note.pop("extensions")
        report = self.check()
        self.assertEqual(report["legacy_uncategorized_records"], 1)
        self.assertEqual(len(report["missing_fields"]), 134)

    def test_schema_matches_every_registered_domain_and_field_contract(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema is an optional test dependency")
        names = ("life-fields.schema.json", "life-archive.schema.json", "protocol.schema.json")
        specs = {name: fixture("schemas/" + name) for name in names}
        registry = Registry().with_resources((name, Resource.from_contents(value)) for name, value in specs.items())
        options = {"registry": registry, "format_checker": Draft202012Validator.FORMAT_CHECKER}
        fields_spec = specs[names[0]]
        Draft202012Validator.check_schema(fields_spec)
        Draft202012Validator(fields_spec, **options).validate(fixture("life-archive/field-registry.json"))
        domain_rules = fields_spec["$defs"]["registered_fields"]["allOf"]
        compiled = {rule["if"]["properties"]["domain"]["const"]: rule["then"]["properties"] for rule in domain_rules}
        self.assertEqual(len(compiled), 52)
        samples = {"text": "Synthetic", "text_list": ["Synthetic"], "integer": 12, "date": "2000-01-01",
                   "reference": "ref", "reference_list": ["ref"], "presence": {"presence": "absent"},
                   "presence_list": [{"presence": "unknown"}]}
        for cid, category in field_registry().items():
            for domain, schema_fields in ((key, compiled[key]) for key in category["domains"]):
                self.assertEqual(schema_fields["category"]["const"], cid)
                expected = {key for key, value in category["fields"].items() if domain in value["domains"]}
                self.assertEqual(set(schema_fields["extensions"]["properties"]), expected)
            for key, spec in category["fields"].items():
                with self.subTest(category=cid, key=key):
                    domain = spec["domains"][0]
                    value = spec["choices"][0] if spec["type"] == "enum" else samples[spec["type"]]
                    self.profile = fixture("life-archive/profile.json")
                    slot = self.record(cid, domain, key, value, "restricted")
                    validator = Draft202012Validator(specs[names[1]], **options)
                    validator.validate(self.profile)
                    self.check("restricted")
                    slot["value"] = {"unregistered": True}
                    self.assertFalse(validator.is_valid(self.profile))
