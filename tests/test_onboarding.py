import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ai_memory_hub import onboarding, shared_version
from ai_memory_hub.adapters import grant, revoke
from ai_memory_hub.model import Denied, open_source
from ai_memory_hub.store import Store
from ai_memory_hub.workspace import PROFILE, bootstrap_workspace, check_workspace


ROOT = Path(__file__).resolve().parents[1]


def fixture(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace, self.vault = self.root / "workspace", self.root / "vault"
        self.request_path = self.root / "request.json"
        self.spec = {"format": "1.0", "workspace": "workspace", "vault": "vault", "sources": []}

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def request(self):
        self.write(self.request_path, self.spec)
        return onboarding.read_request(self.request_path)

    def apply(self, request):
        return onboarding.apply(request, onboarding.plan_fingerprint(request), True)

    def test_blank_read_only_approval_and_markdown(self):
        request = self.request()
        plan = onboarding.plan(request)
        self.assertEqual(plan["storage"]["paths"], {"workspace": "new", "vault": "new"})
        self.assertIn("Onboarding plan", plan["markdown"])
        self.assertFalse(self.workspace.exists())
        self.assertFalse(self.vault.exists())
        with self.assertRaises(Denied):
            onboarding.apply(request, onboarding.plan_fingerprint(request), False)
        with self.assertRaises(Denied):
            onboarding.apply({**request, "sensitivity": "restricted"}, plan["plan_digest"], True)
        report = self.apply(request)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["sync"]["scheduler"], "not_verified")
        self.assertIsNone(Store(self.vault).settings()["weekly_preference"])
        self.assertEqual(len(report["life_archive"]["missing_fields"]), 134)
        self.assertEqual(set(report["life_archive"]["domains"].values()), {"unknown"})
        self.assertEqual(self.apply(request)["storage"], report["storage"])
        path = self.workspace / "first.md"
        onboarding.write_markdown(request, path, report)
        self.assertIn("12/52/134", path.read_text(encoding="utf-8"))
        with self.assertRaises(FileExistsError):
            onboarding.write_markdown(request, path, report)
        with self.assertRaises(Denied):
            onboarding.write_markdown(request, self.root / "outside.md", report)
        with self.assertRaises(Denied):
            onboarding.write_markdown(request, self.workspace / ".git", report)
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        schema = fixture("schemas/onboarding.schema.json")
        Draft202012Validator.check_schema(schema)
        for response in (self.spec, plan, report):
            Draft202012Validator(schema).validate(response)

    def test_existing_unbound_data_preserved_and_interrupted_templates_resume(self):
        request = self.request()
        self.assertFalse(self.vault.exists())
        def interrupt(path, contents):
            if path.name == "INDEX.md":
                raise OSError("synthetic interrupted template write")
            return onboarding.write_atomic(path, contents)

        with patch("ai_memory_hub.workspace.write_atomic", side_effect=interrupt):
            self.assertEqual(self.apply(request)["status"], "blocked")
        self.assertTrue((self.vault / "index.sqlite").is_file())
        self.assertFalse((self.workspace / "config/workspace.json").exists())
        self.assertEqual(self.apply(request)["status"], "completed")
        self.assertEqual(check_workspace(self.workspace)["schema_version"], "2.1")
        self.spec.update(workspace="other", vault="other-vault")
        other, _, _ = bootstrap_workspace(self.root / "extra", self.root / "extra-vault", "private")
        other.rename(self.root / "other")
        binding = self.root / "other/config/workspace.json"
        original = binding.read_bytes()
        with patch("ai_memory_hub.workspace.Store", side_effect=AssertionError("unapproved Vault opened")):
            self.assertEqual(self.apply(self.request())["status"], "blocked")
        self.assertEqual(binding.read_bytes(), original)
        self.assertFalse((self.root / "other-vault").exists())

    def setup_inbox(self):
        inbox = self.root / "inbox"
        inbox.mkdir()
        for name in ("session.json", "project.json", "memory.json", "memory-hub.json"):
            self.write(inbox / name, fixture(f"examples/{name}"))
        session = fixture("examples/session.json")
        session["source"]["kind"] = "observed_messages"
        session["source"]["locator"] = "SYNTHETIC-PROSE-IN-LOCATOR"
        session["source"]["observed_at"] = "2000-01-01T00:00:00Z"
        session["data"]["messages"] = [{"id": "raw-1", "role": "user", "text": "SYNTHETIC-RAW-EXPECTATION"}]
        self.write(inbox / "session.json", session)
        candidate = fixture("examples/memory.json")
        candidate["id"] = "duplicate-candidate"
        self.write(inbox / "duplicate.json", candidate)
        manifest = fixture("examples/memory-hub.json")
        manifest["items"].append({"key": "duplicate", "kind": "record", "path": "duplicate.json"})
        self.write(inbox / "memory-hub.json", manifest)
        self.spec["sources"].append({"id": "intake", "adapter": "codex_workspace", "path": "inbox",
                                     "authorized": True, "allow_raw": True})
        return inbox

    def test_partial_retry_file_bytes_layers_and_conflicts_without_raw_report(self):
        inbox = self.setup_inbox()
        request = self.request()
        first = self.apply(request)
        self.assertEqual(first["status"], "partial")
        self.assertEqual(first["sources"][0]["created"], 4, first["sources"][0]["errors"])
        self.assertEqual(first["sources"][0]["errors"][0]["code"], "missing")
        (inbox / "checklist.txt").write_bytes(b"Synthetic file bytes\x00\xff")
        second = self.apply(request)
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["sources"][0]["created"], 1)
        self.assertEqual(second["sources"][0]["unchanged"], 4)
        self.assertEqual(second["sources"][0]["date_coverage"]["dated_records"], 1)
        self.assertEqual(second["sources"][0]["date_coverage"]["from"], "2000-01-01T00:00:00Z")
        self.assertEqual(second["data"]["session"][0]["layers"], dict.fromkeys(("L0", "L1", "L2", "L3"), True))
        self.assertEqual(len(second["data"]["project"]), 1)
        self.assertEqual(len(second["data"]["memory"]), 2)
        self.assertEqual(second["memory_review"]["candidates"], 2)
        self.assertEqual(len(second["memory_review"]["duplicates"]), 2)
        self.assertNotIn("SYNTHETIC-RAW-EXPECTATION", json.dumps(second))
        self.assertNotIn("SYNTHETIC-PROSE-IN-LOCATOR", json.dumps(second))
        asset = second["data"]["asset"][0]
        self.assertEqual(asset["storage"], "vault")
        self.assertEqual((self.vault / "blobs" / asset["sha256"]).read_bytes(), (inbox / "checklist.txt").read_bytes())
        third = self.apply(request)
        self.assertEqual(third["sources"][0]["unchanged"], 5)
        self.assertTrue(all(row["revision"] == 1 for row in third["sources"][0]["records"]))
        with closing(sqlite3.connect(self.vault / "index.sqlite")) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 210)

    def test_unapproved_and_unsupported_sources_never_inspected(self):
        self.spec["sources"] = [
            {"id": "blocked", "adapter": "codex_workspace", "path": "not-authorized", "authorized": False},
            {"id": "unknown", "adapter": "other-ai", "path": "outside", "authorized": True},
        ]
        request = self.request()
        with patch("ai_memory_hub.onboarding.local_input", side_effect=AssertionError("unexpected source inspection")):
            self.assertEqual([item["status"] for item in onboarding.plan(request)["sources"]], ["blocked", "blocked"])
            report = self.apply(request)
        self.assertEqual(report["status"], "partial")
        changed = self.root / "changed"
        changed.mkdir()
        self.spec["sources"] = [{"id": "one", "adapter": "codex_workspace", "path": "changed", "authorized": True}]
        self.write(changed / "memory-hub.json", {"schema_version": "2.1", "items": []})
        self.apply(self.request())
        other = self.root / "other-source"
        other.mkdir()
        self.spec["sources"][0]["path"] = "other-source"
        result = self.apply(self.request())
        self.assertEqual(result["sources"][0]["status"], "blocked")
        self.assertIn("revoke", result["sources"][0]["reason"])

    def test_revoked_grant_cannot_substitute_a_source_before_batch(self):
        inbox = self.setup_inbox()
        other = self.root / "other-input"
        other.mkdir()
        self.write(other / "memory-hub.json", fixture("examples/memory-hub.json"))
        run_batch = onboarding.run_batch

        def swap(store, blobs, mode, source, **options):
            revoke(store, source)
            grant(store, source, "codex_workspace", other, True)
            return run_batch(store, blobs, mode, source, **options)

        with patch("ai_memory_hub.onboarding.run_batch", side_effect=swap):
            result = self.apply(self.request())
        self.assertEqual(result["sources"][0]["status"], "blocked")
        self.assertIn("grant changed", result["sources"][0]["reason"])
        self.assertFalse(result["data"]["session"])
        self.assertTrue((inbox / "session.json").is_file())

    def test_hardlinked_source_rejected_before_consuming_bytes(self):
        sample = self.root / "only-approved-by-name.json"
        self.write(sample, {"synthetic": True})
        try:
            os.link(sample, self.root / "other-path.json")
        except (NotImplementedError, OSError):
            self.skipTest("local filesystem does not support hardlinks")
        with self.assertRaises(Denied):
            with open_source(sample):
                self.fail("multiply linked source reached the consumer")

    def test_life_import_idempotent_missing_fields_and_bad_payload(self):
        profile_path = self.root / "profile.json"
        source = {"provider": "synthetic", "kind": "user_checkpoint", "locator": "fixture:life"}
        at = "2000-01-01T00:00:00Z"
        entry = {"record_id": "fixture-life", "category": "01", "domain": "01-01",
                 "status": "self-report", "evidence_level": "unverified", "source": source,
                 "source_type": "user_statement", "created_at": at, "updated_at": at,
                 "summary": "Synthetic observation", "sensitivity": "internal", "extensions": {
                     "birth_year": {"value": 2000, "source": source, "source_type": "user_statement",
                                    "observed_at": at, "valid_from": None, "valid_to": None, "sensitivity": "internal"}}}
        profile = {"schema_version": "1.0", "kind": "life_profile",
                   "categories": [{"category": "01", "status": "partial", "records": [entry]}]}
        self.write(profile_path, profile)
        self.spec["sources"] = [{"id": "life", "adapter": "life_profile", "path": "profile.json", "authorized": True}]
        request = self.request()
        first = self.apply(request)
        self.assertEqual(first["life_archive"]["registered"], {"categories": 12, "domains": 52, "fields": 134})
        self.assertEqual(len(first["life_archive"]["missing_fields"]), 133)
        self.assertEqual(self.apply(request)["sources"][0]["outcome"], "unchanged")
        saved = (self.workspace / PROFILE).read_bytes()
        entry["record_id"] = "other-life"
        entry["extensions"]["birth_year"]["value"] = True
        self.write(profile_path, profile)
        self.assertEqual(self.apply(request)["sources"][0]["status"], "failed")
        self.assertEqual((self.workspace / PROFILE).read_bytes(), saved)

    def test_existing_agent_ack_and_optional_remote_receipt(self):
        self.spec["github"] = {"target": "synthetic/owner-example", "visibility": "private"}
        request = self.request()
        self.assertEqual(self.apply(request)["status"], "partial")
        store = Store(self.vault)
        onboarding.require_repo_target(store, "Synthetic/Owner-Example")
        with self.assertRaises(Denied):
            onboarding.require_repo_target(store, "synthetic/wrong")
        snapshot = shared_version.snapshot(store, "demo", {}, consent=True)
        shared_version.check(store, "synthetic-channel", "agent-a", snapshot["path"], consent=True)
        current = onboarding.report(request)
        self.assertEqual(current["sync"]["agents"], [{
            "channel": "synthetic-channel", "agent": "agent-a", "detected_sha": snapshot["sha"], "synced_sha": None,
        }])
        onboarding.save_repo_receipt(store, "create", "synthetic/owner-example",
                                     {"status": "completed", "target": "synthetic/owner-example", "private": True})
        self.assertEqual(onboarding.report(request)["github"]["receipts"]["create"]["private"], True)
        onboarding.save_repo_receipt(store, "create", "synthetic/owner-example", {"status": "blocked"})
        remote = onboarding.report(request)["github"]
        self.assertEqual(remote["receipts"]["create"]["status"], "blocked")
        self.assertTrue(remote["last_success"]["create"]["private"])


if __name__ == "__main__":
    unittest.main()
