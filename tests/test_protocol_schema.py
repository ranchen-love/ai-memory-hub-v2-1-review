import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


@unittest.skipUnless(Draft202012Validator, "install jsonschema to verify the public JSON Schema")
class ProtocolSchemaTests(unittest.TestCase):
    def test_examples_and_rejected_unknown_fields(self):
        root = Path(__file__).resolve().parent.parent
        schema = json.loads((root / "schemas/protocol.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        fixtures = sorted((root / "examples").glob("*.json"))
        plan_schema = json.loads((root / "schemas/onboarding.schema.json").read_text(encoding="utf-8"))
        plan_validator = Draft202012Validator(plan_schema)
        self.assertEqual(sum(path.name != "onboarding-request.json" for path in fixtures), 6)
        for path in fixtures:
            with self.subTest(example=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                fixture_validator = plan_validator if path.name == "onboarding-request.json" else validator
                fixture_validator.validate(value)
                value["unexpected"] = True
                self.assertFalse(fixture_validator.is_valid(value))
