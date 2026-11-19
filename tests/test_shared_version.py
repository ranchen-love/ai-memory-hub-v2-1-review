import json
import tempfile
import unittest
from pathlib import Path

from ai_memory_hub.model import Conflict, Denied, HubError
from ai_memory_hub.shared_version import check, confirm, reload, snapshot
from ai_memory_hub.store import Store

SOURCE = {"provider": "fixture", "kind": "user_checkpoint", "locator": "fixture:approval"}


def envelope(entry_id, claim, *, base=0, status="accepted"):
    return {"schema_version": "2.1", "kind": "memory", "id": entry_id, "base_revision": base,
            "sensitivity": "private", "source": SOURCE,
            "data": {"key": entry_id, "claim": claim, "status": status, "classification": "fact"}}


class VersionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hub-version-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.store = Store(self.root / "reader", initialize="private")
        self.peer = Store(self.root / "publisher", initialize="private")
        self.path = self.root / "approved-snapshot.json"

    def publish(self, name, selected):
        export = snapshot(self.peer, name, selected, consent=True)
        self.path.write_bytes(Path(export["path"]).read_bytes())

    def seed(self, entry_id, value, base=0, status="accepted"):
        with self.peer.transaction(write=True) as db:
            return self.peer.ingest(db, envelope(entry_id, value, base=base, status=status), allow_review=True)

    def check(self, agent="agent-a"):
        return check(self.store, "demo", agent, self.path, consent=True)

    def reload(self, *scopes, agent="agent-a"):
        return reload(self.store, "demo", agent, scopes, consent=True)

    def confirm(self, read, agent="agent-a"):
        return confirm(self.store, "demo", agent, read["detected_sha"], read["receipt"], consent=True)

    def test_unknown_first_check_and_explicit_per_agent_receipt(self):
        self.assertEqual(self.check()["status"], "unknown")
        self.seed("policy", "Only trusted inputs")
        self.publish("initial", {"rules": ["policy"]})
        detected = self.check()
        self.assertEqual(detected["status"], "first_check")
        self.assertIsNone(detected["synced_sha"])
        self.assertTrue(detected["pending_reload"])
        self.assertEqual(detected["reload_scope"], ["rules"])
        self.assertNotIn("scopes", detected)
        with self.assertRaises(Conflict):
            confirm(self.store, "demo", "agent-a", detected["detected_sha"], "0" * 32, consent=True)
        read = self.reload("rules")
        self.assertEqual(read["scopes"]["rules"][0]["data"]["claim"], "Only trusted inputs")
        self.assertIsNone(self.check()["synced_sha"])
        with self.assertRaises(Conflict):
            self.confirm(read, agent="agent-b")
        with self.assertRaises(Denied):
            confirm(self.store, "demo", "agent-a", read["detected_sha"], read["receipt"])
        self.assertEqual(self.confirm(read)["synced_sha"], detected["detected_sha"])
        unchanged = self.check()
        self.assertEqual(unchanged["status"], "unchanged")
        self.assertTrue(unchanged["in_sync"])
        self.assertTrue(self.check("agent-b")["pending_reload"])
        self.path.unlink()
        offline = self.check()
        self.assertEqual(offline["status"], "unknown")
        self.assertEqual(offline["synced_sha"], detected["detected_sha"])
        self.assertIsNone(offline["in_sync"])

    def test_scope_diff_partial_confirmation_and_deletion(self):
        for name in ("policy", "routine", "goal"):
            self.seed(name, f"Old {name}")
        self.publish("before", {"rules": ["policy"], "preferences": ["routine"], "goals": ["goal"]})
        self.check()
        original = self.confirm(self.reload())["synced_sha"]
        self.seed("policy", "Changed policy", base=1)
        self.publish("after", {"rules": ["policy"], "goals": ["goal"]})
        detected = self.check()
        self.assertEqual(detected["status"], "changed")
        self.assertEqual(detected["reload_scope"], ["preferences", "rules"])
        removed = self.reload("preferences")
        self.assertIsNone(removed["scopes"]["preferences"])
        partial = self.confirm(removed)
        self.assertTrue(partial["pending_reload"])
        self.assertEqual(partial["synced_sha"], original)
        self.assertEqual(self.check()["reload_scope"], ["rules"])
        final = self.confirm(self.reload("rules"))
        self.assertFalse(final["pending_reload"])
        self.assertNotEqual(final["synced_sha"], original)

    def test_unavailable_or_changed_since_read_prevents_confirmation(self):
        self.seed("policy", "Initial")
        self.publish("before", {"rules": ["policy"]})
        first = self.check()
        read = self.reload()
        self.path.unlink()
        unknown = self.check()
        self.assertEqual((unknown["status"], unknown["availability"]), ("unknown", "unavailable"))
        self.assertEqual(unknown["detected_sha"], first["detected_sha"])
        self.assertTrue(unknown["pending_reload"])
        with self.assertRaises(HubError):
            self.confirm(read)
        self.seed("policy", "Replacement", base=1)
        self.publish("after", {"rules": ["policy"]})
        with self.assertRaises(Conflict):
            self.confirm(read)
        changed = self.check()
        self.assertNotEqual(changed["detected_sha"], first["detected_sha"])
        self.assertIsNone(changed["synced_sha"])
        self.assertFalse(self.confirm(self.reload())["pending_reload"])

    def test_explicit_scope_only_and_pinned_source(self):
        self.seed("draft", "Unapproved", status="candidate")
        with self.assertRaises(Denied):
            snapshot(self.peer, "blocked", {"rules": ["draft"]}, consent=True)
        with self.assertRaises(Denied):
            snapshot(self.peer, "blocked", {})
        self.publish("empty", {})
        detected = self.check()
        self.assertTrue(detected["pending_reload"])
        read = self.reload()
        self.assertEqual(read["scopes"], {})
        self.assertFalse(self.confirm(read)["pending_reload"])
        other = self.root / "other.json"
        other.write_bytes(self.path.read_bytes())
        with self.assertRaises(Conflict):
            check(self.store, "demo", "agent-a", other, consent=True)
        with self.assertRaises(Denied):
            check(self.store, "demo", "agent-b", self.path)
        self.path.write_text(json.dumps({"scope": "invalid"}), encoding="utf-8")
        self.assertEqual(self.check()["status"], "unknown")

    def test_snapshot_schema_and_sensitivity_are_enforced(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema is an optional test dependency")
        self.seed("policy", "Synthetic policy")
        self.publish("authorized", {"rules": ["policy"]})
        schema_path = Path(__file__).resolve().parents[1] / "schemas"
        protocol = json.loads((schema_path / "protocol.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource("protocol.schema.json", Resource.from_contents(protocol))
        spec = json.loads((schema_path / "shared-memory.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(spec)
        validator = Draft202012Validator(spec, registry=registry)
        value = json.loads(self.path.read_text(encoding="utf-8"))
        validator.validate(value)
        internal = Store(self.root / "internal-reader", initialize="internal")
        denied = check(internal, "demo", "agent", self.path, consent=True)
        self.assertEqual((denied["status"], denied["reason"]), ("unknown", "permission_denied"))
        self.assertIsNone(denied["synced_sha"])
        value["scopes"]["rules"][0]["data"]["status"] = "candidate"
        self.assertFalse(validator.is_valid(value))
        self.path.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(self.check()["reason"], "permission_denied")
