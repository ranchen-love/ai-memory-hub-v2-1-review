import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from ai_memory_hub.adapters import grant, revoke
from ai_memory_hub.assets import LocalVault, availability, export_public_text, observe_link, put_file, put_link, references
from ai_memory_hub.handoff import create_handoff
from ai_memory_hub.model import Conflict, Denied, HubError, LISTS, Missing
from ai_memory_hub.store import Store, checked_relative, view_session
from ai_memory_hub.sync import batch_lock, dispatch, run_batch, status

SOURCE = {"provider": "synthetic", "kind": "user_checkpoint", "locator": "synthetic:decision-log"}
AT = "2026-01-01T00:00:00+00:00"


def record(kind="session", entry="session-1", fields=None, base=None):
    if fields is None:
        checkpoint = {key: [] for key in LISTS}
        checkpoint.update({"goal": "Calibrate the fictional sample", "next_actions": ["Run the example check"]})
        fields = {"title": "Sample checkpoint", "project_id": "demo", "summary": "Calibration pending",
                  "checkpoint": checkpoint}
    item = {"kind": kind, "schema_version": "2.1", "id": entry, "source": SOURCE,
            "sensitivity": "private", "data": fields}
    if base is not None:
        item["base_revision"] = base
    return item


class HubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hub-tests-")
        cls.base = Path(cls.temp.name).resolve()
        # Root ACL behavior is exercised independently. Most domain tests use separate databases.
        authorized = Store(cls.base / "test-root", initialize="private")
        cls.instances = authorized.root

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = self.instances / self._testMethodName
        self.directory.mkdir(mode=0o700)
        self.root = self.directory / "vault"
        self.inbox = self.directory / "inbox"
        self.inbox.mkdir()
        self.store = Store(self.root, initialize="private")
        self.blobs = LocalVault(self.store.root)

    def write(self, name, content):
        path = self.inbox / name
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    def manifest(self, *items):
        self.write("memory-hub.json", {"schema_version": "2.1", "items": items})

    def ingest(self, item, **kwargs):
        with self.store.transaction(write=True) as db:
            return self.store.ingest(db, item, **kwargs)

    def add(self, path, **kwargs):
        with self.blobs.stage(path) as staged, self.store.transaction(write=True) as db:
            return put_file(self.store, db, self.blobs, staged, path.name, SOURCE, **kwargs)

    def items(self, kind, entry):
        with self.store.transaction() as db:
            return self.store.history(db, kind, entry)

    def test_incremental_session_preserves_l2_provenance_and_replays(self):
        initial = record()
        self.assertEqual(self.ingest(initial)["status"], "created")
        delta = record(fields={"title": "Sample checkpoint", "append": {"verification": ["Example passes"]}}, base=1)
        delta["source"] = {**SOURCE, "locator": "synthetic:verification"}
        updated = self.ingest(delta)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(self.ingest(initial)["status"], "unchanged")
        self.assertEqual(self.ingest(delta)["status"], "unchanged")
        first, second = self.items("session", "session-1")
        self.assertEqual(first["data"]["checkpoint"]["verification"], [])
        l2 = view_session(second, "L2")
        self.assertEqual(l2["checkpoint"]["verification"], ["Example passes"])
        self.assertEqual(l2["summary"], "Calibration pending")
        self.assertEqual([e["source"]["locator"] for e in l2["checkpoint_sources"]],
                         ["synthetic:decision-log", "synthetic:verification"])
        invalid = record(fields={"title": "Other writer"}, base=1)
        with self.assertRaises(Conflict):
            self.ingest(invalid)

    def test_serialized_concurrent_writers_keep_one_update(self):
        self.ingest(record())
        edits = [record(fields={"title": title}, base=1) for title in ("Writer A", "Writer B")]
        def apply(item):
            try:
                return self.ingest(item)["status"]
            except Conflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(apply, edits), ["updated", "conflict"])
        self.assertEqual(len(self.items("session", "session-1")), 2)

    def test_raw_requires_consent_and_is_excluded_from_other_layers(self):
        doc = record()
        doc["data"]["messages"] = [{"id": "m1", "role": "user", "text": "synthetic raw text"}]
        with self.assertRaises(Denied):
            self.ingest(doc, allow_raw=True)
        doc["source"] = {**SOURCE, "kind": "observed_messages"}
        with self.assertRaises(Denied):
            self.ingest(doc)
        broken = copy.deepcopy(doc)
        broken["data"]["messages"][0]["reasoning"] = "unsupported"
        with self.assertRaises(HubError):
            self.ingest(broken, allow_raw=True)
        self.ingest(doc, allow_raw=True)
        item = self.items("session", "session-1")[0]
        for layer in ("L0", "L1", "L2"):
            self.assertNotIn("synthetic raw text", json.dumps(view_session(item, layer)))
        self.assertEqual(view_session(item, "L3")["messages"][0]["id"], "m1")

    def test_vault_dedupe_version_integrity_and_traceability(self):
        original = self.inbox / "demo.pdf"
        original.write_bytes(b"synthetic original")
        a = self.add(original, asset_id="report", project_id="demo")
        self.assertEqual(self.add(original, asset_id="report", project_id="demo")["status"], "unchanged")
        self.add(original, asset_id="other-report")
        records = [file for file in self.blobs.directory.iterdir() if not file.name.startswith(".")]
        self.assertEqual(len(records), 1)
        doc = record()
        doc["data"]["checkpoint"]["file_refs"] = [{"asset_id": "report"}]
        self.ingest(doc)
        original.write_bytes(b"synthetic update")
        with self.assertRaises(Conflict):
            self.add(original, asset_id=a["id"], project_id="demo")
        self.assertEqual(self.add(original, asset_id=a["id"], base=a["revision"], project_id="demo")["revision"], 2)
        original.write_bytes(b"synthetic original")
        self.assertEqual(self.add(original, asset_id=a["id"], project_id="demo")["revision"], 1)
        self.assertEqual(len(self.items("asset", a["id"])), 2)
        records[0].write_bytes(b"damaged")
        with self.store.transaction() as db:
            old = self.store.get(db, "asset", "report", 1)
            self.assertEqual(availability(db, self.blobs, old)["status"], "corrupt")
            self.assertEqual(references(db, "report")["references"][0]["asset_version"], 1)
        records[0].unlink()
        with self.store.transaction() as db:
            self.assertEqual(availability(db, self.blobs, old)["status"], "missing")
        with self.assertRaises(FileNotFoundError):
            self.add(self.inbox / "missing")

    def test_links_remain_external_and_only_report_observed_status(self):
        with self.store.transaction(write=True) as db:
            put_link(self.store, db, "https://example.invalid/report", "report.pdf", SOURCE, asset_id="report")
            item = self.store.get(db, "asset", "report")
            self.assertIsNone(item["data"]["sha256"])
            self.assertEqual(availability(db, self.blobs, item)["status"], "unverified")
            observe_link(db, "report", 1, "permission_denied", SOURCE)
            self.assertEqual(availability(db, self.blobs, item)["basis"], "reported_observation")
            self.assertEqual(availability(db, self.blobs, item)["status"], "permission_denied")
            observe_link(db, "report", 1, "missing", SOURCE)
            self.assertEqual(availability(db, self.blobs, item)["status"], "missing")
            put_link(self.store, db, "https://example.invalid/expired", "old.pdf", SOURCE,
                     asset_id="expired", expires_at=AT)
            self.assertEqual(availability(db, self.blobs, self.store.get(db, "asset", "expired"))["status"], "expired")
            with self.assertRaises(HubError):
                put_link(self.store, db, "https://example.invalid/report?short_lived=1", "temp.pdf", SOURCE)

    def test_boundary_requires_actual_private_root_and_scope(self):
        insecure = self.directory / "ambient"
        insecure.mkdir(mode=0o755)
        with self.assertRaises(Denied):
            Store(insecure, initialize="private")
        git = self.directory / "repo"
        git.mkdir()
        (git / ".git").mkdir()
        with self.assertRaises(Denied):
            Store(git / "private", initialize="private")
        with self.assertRaises(Denied):
            self.ingest({**record(), "sensitivity": "restricted"})
        with self.assertRaises(Conflict):
            Store(self.root, initialize="restricted")
        file = self.inbox / "demo.txt"
        file.write_bytes(b"sample")
        self.add(file, asset_id="restricted-from-git")
        with self.store.transaction() as db:
            item = self.store.get(db, "asset", "restricted-from-git")
        with self.assertRaises(Denied):
            export_public_text(self.store, self.blobs, item, git / "demo.txt")

    def test_public_text_export_is_explicit_bounded_and_no_overwrite(self):
        public = Store(self.directory / "public-vault", initialize="public")
        vault = LocalVault(public.root)
        git = self.directory / "repo"
        git.mkdir()
        (git / ".git").mkdir()
        sample = self.inbox / "demo.txt"
        sample.write_bytes(b"synthetic")
        with vault.stage(sample) as staged, public.transaction(write=True) as db:
            put_file(public, db, vault, staged, sample.name, SOURCE, asset_id="public-sample")
            item = public.get(db, "asset", "public-sample")
        target = git / "example.txt"
        self.assertEqual(export_public_text(public, vault, item, target)["status"], "written")
        self.assertEqual(target.read_bytes(), sample.read_bytes())
        with self.assertRaises(FileExistsError):
            export_public_text(public, vault, item, target)

    def test_partial_sync_retry_versions_and_success_time(self):
        self.write("s.json", record())
        self.manifest({"key": "session", "kind": "record", "path": "s.json"},
                      {"key": "artifact", "kind": "file", "path": "demo.xlsx", "project_id": "demo",
                       "origin": "ai_generated"})
        grant(self.store, "inbox", "codex_workspace", self.inbox, False)
        first = run_batch(self.store, self.blobs, "full")
        self.assertEqual((first["status"], first["created"]), ("partial", 1))
        self.assertEqual(status(self.store)["pending"][0]["code"], "missing")
        artifact = self.inbox / "demo.xlsx"
        artifact.write_bytes(b"demo version A")
        second = run_batch(self.store, self.blobs, "full")
        self.assertEqual((second["status"], second["created"], second["unchanged"]), ("completed", 1, 1))
        self.assertIn("full", status(self.store)["last_success"])
        self.assertFalse(status(self.store)["pending"])
        artifact.write_bytes(b"demo version B")
        third = run_batch(self.store, self.blobs, "full")
        self.assertEqual(third["updated"], 1)
        with self.store.transaction() as db:
            asset = self.store.latest(db, "asset")[0]
        self.assertEqual(asset["revision"], 2)
        (self.blobs.directory / asset["data"]["sha256"]).unlink()
        self.assertEqual(run_batch(self.store, self.blobs, "full")["unchanged"], 2)
        self.assertTrue((self.blobs.directory / asset["data"]["sha256"]).exists())

    def test_automatic_switches_are_independent_and_fail_closed(self):
        self.write("s.json", record())
        entry = {"key": "session", "kind": "record", "path": "s.json"}
        self.manifest(entry)
        self.write("event.json", {"schema_version": "2.1", "id": "event-1", "type": "decision_confirmed",
                                  "at": AT, "item": entry})
        grant(self.store, "inbox", "normalized", self.inbox, False)
        with self.assertRaises(Denied):
            run_batch(self.store, self.blobs, "daily")
        with self.assertRaises(Denied):
            dispatch(self.store, self.blobs, "inbox", "event.json")
        with self.assertRaises(Denied):
            create_handoff(self.store, self.blobs, "demo")
        for name in ("weekly", "full"):
            self.store.settings(feature=name, enabled=False)
            with self.assertRaises(Denied):
                run_batch(self.store, self.blobs, name)
        self.assertEqual(self.items("session", "session-1"), [])
        self.assertEqual(status(self.store)["latest_runs"], [])
        self.store.settings(feature="event", enabled=True)
        self.assertEqual(dispatch(self.store, self.blobs, "inbox", "event.json")["status"], "created")
        self.assertEqual(dispatch(self.store, self.blobs, "inbox", "event.json")["status"], "unchanged")
        self.write("s.json", record(fields={"title": "Changed"}))
        with self.assertRaises(Conflict):
            dispatch(self.store, self.blobs, "inbox", "event.json")

    def test_forbidden_source_and_revoked_grants(self):
        grant(self.store, "inbox", "normalized", self.inbox, False)
        self.manifest({"key": "escaped", "kind": "record", "path": "../outside.json"})
        report = run_batch(self.store, self.blobs, "full")
        self.assertEqual(report["errors"][0]["code"], "permission_denied")
        with patch("ai_memory_hub.sync.read_json", side_effect=PermissionError):
            self.manifest({"key": "denied", "kind": "record", "path": "some.json"})
            self.write("some.json", record())
            report = run_batch(self.store, self.blobs, "full")
        self.assertEqual(report["errors"][0]["code"], "permission_denied")
        revoke(self.store, "inbox")
        with self.assertRaises(Denied):
            run_batch(self.store, self.blobs, "full", "inbox")
        self.assertFalse(status(self.store)["pending"])

    def test_symlink_source_escape_rejected(self):
        link = self.inbox / "linked.json"
        outside = self.directory / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"OS cannot create symlinks: {exc.winerror if os.name == 'nt' else exc.errno}")
        with self.assertRaises(Denied):
            checked_relative(self.inbox, link.name)

    def test_interrupted_run_receipts_resume_without_duplicate_writes(self):
        self.write("s.json", record())
        self.manifest({"key": "s", "kind": "record", "path": "s.json"})
        grant(self.store, "inbox", "normalized", self.inbox, False)
        with batch_lock(self.store.root), self.assertRaises(Conflict):
            run_batch(self.store, self.blobs, "full")
        real_transaction = self.store.transaction
        with patch.object(self.store, "transaction", side_effect=[real_transaction(), real_transaction(write=True),
                                                                   real_transaction(write=True), KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                run_batch(self.store, self.blobs, "full")
        self.assertEqual(len(self.items("session", "session-1")), 1)
        self.assertEqual(run_batch(self.store, self.blobs, "full")["unchanged"], 1)
        self.assertEqual(len(self.items("session", "session-1")), 1)

    def test_handoff_links_all_sessions_projects_and_evidence_without_raw(self):
        self.ingest(record("project", "demo", {"title": "Demo", "state": "active",
                                             "timeline": [{"at": AT, "description": "Started"}]}))
        original = self.inbox / "result.pptx"
        original.write_bytes(b"synthetic")
        self.add(original, asset_id="result", session_id="session-1")
        item = record()
        item["data"]["checkpoint"]["file_refs"] = [{"asset_id": "result"}, {"asset_id": "missing"}]
        item["data"]["messages"] = [{"id": "msg", "role": "assistant", "text": "raw only"}]
        item["source"] = {**SOURCE, "kind": "observed_messages"}
        self.ingest(item, allow_raw=True)
        self.ingest(record(entry="session-2", fields={"title": "Index only", "project_id": "demo"}))
        self.store.settings(feature="handoff", enabled=True)
        bundle = json.loads(Path(create_handoff(self.store, self.blobs, "demo")["path"]).read_text(encoding="utf-8"))
        self.assertEqual(bundle["project"]["data"]["state"], "active")
        self.assertEqual(bundle["missing_l2"], ["session-2"])
        first = bundle["sessions"][0]
        self.assertEqual(first["checkpoint"]["next_actions"], ["Run the example check"])
        self.assertEqual(first["checkpoint_sources"][0]["source"], item["source"])
        self.assertEqual({a.get("version") for a in bundle["files"]}, {1, None})
        self.assertNotIn("raw only", json.dumps(bundle))
        self.assertEqual(len(bundle["timeline"]), 3)

    def test_weekly_memory_governance_keeps_review_manual(self):
        accepted = record("memory", "memory-1", {"key": "Sample tolerance", "claim": "2 mm", "status": "accepted"})
        with self.assertRaises(Denied):
            self.ingest(accepted)
        self.ingest(accepted, allow_review=True)
        self.ingest(record("memory", "memory-2", {"key": "sample tolerance", "claim": "5 mm", "status": "candidate"}))
        report = run_batch(self.store, self.blobs, "weekly")
        self.assertEqual(report["memory_review"]["conflicts"], [{"candidate": "memory-2", "other": "memory-1"}])
        self.assertEqual(self.items("memory", "memory-2")[-1]["data"]["status"], "candidate")
        downgrade = record("memory", "memory-1", {"key": "Sample tolerance", "claim": "9 mm", "status": "candidate"}, base=1)
        with self.assertRaises(Denied):
            self.ingest(downgrade)
        self.assertEqual(self.items("memory", "memory-1")[-1]["data"]["status"], "accepted")

    def test_chatgpt_export_only_visible_selected_branch_and_newer_exports(self):
        def message(role, value, hidden=False):
            return {"author": {"role": role}, "recipient": "all",
                    "metadata": {"is_visually_hidden_from_conversation": hidden},
                    "content": {"content_type": "text", "parts": [value]}}
        entry = {"id": "example-conversation", "title": "Synthetic", "current_node": "a", "update_time": 10,
                 "mapping": {"a": {"parent": "b", "message": message("assistant", "visible reply")},
                             "b": {"parent": "c", "message": message("assistant", "hidden", hidden=True)},
                             "c": {"parent": None, "message": message("user", "visible question")},
                             "other": {"parent": "c", "message": message("assistant", "other branch")}}}
        path = self.write("conversations.json", [entry])
        grant(self.store, "chat", "chatgpt_export", path, True)
        self.assertEqual(run_batch(self.store, self.blobs, "full")["created"], 1)
        with self.store.transaction() as db:
            item = self.store.latest(db, "session")[0]
        self.assertEqual([m["text"] for m in item["data"]["messages"]], ["visible question", "visible reply"])
        self.assertIsNone(view_session(item, "L2")["checkpoint"])
        self.assertEqual(run_batch(self.store, self.blobs, "full")["unchanged"], 1)
        entry.update({"update_time": 20, "title": "Newer title"})
        self.write("conversations.json", [entry])
        self.assertEqual(run_batch(self.store, self.blobs, "full")["updated"], 1)
        entry["update_time"] = 10
        self.write("conversations.json", [entry])
        self.assertEqual(run_batch(self.store, self.blobs, "full")["errors"][0]["code"], "conflict")

    def test_bad_items_and_extreme_revisions_do_not_block_later_entries(self):
        self.ingest(record())
        self.write("bad-revision.json", record(base=2**63-1))
        self.write("good.json", record(entry="another-session"))
        self.manifest({"key": "bad-shape", "kind": "file"},
                      {"key": "bad-rev", "kind": "record", "path": "bad-revision.json"},
                      {"key": "good", "kind": "record", "path": "good.json"})
        grant(self.store, "inbox", "normalized", self.inbox, False)
        report = run_batch(self.store, self.blobs, "full")
        self.assertEqual(report["created"], 1)
        self.assertEqual([item["code"] for item in report["errors"]], ["invalid_input", "conflict"])
        self.assertEqual(self.items("session", "another-session")[0]["revision"], 1)

    def test_revoked_snapshot_does_not_open_source(self):
        self.manifest({"key": "anything", "kind": "record", "path": "unused.json"})
        grant(self.store, "inbox", "normalized", self.inbox, False)
        transaction = self.store.transaction
        calls = 0

        @contextmanager
        def revoke_after_snapshot(*args, **kwargs):
            nonlocal calls
            calls += 1
            is_snapshot = calls == 2
            with transaction(*args, **kwargs) as db:
                yield db
            if is_snapshot:
                revoke(self.store, "inbox")

        with patch.object(self.store, "transaction", revoke_after_snapshot), patch("ai_memory_hub.adapters.read_json") as read:
            report = run_batch(self.store, self.blobs, "full")
            read.assert_not_called()
        self.assertEqual(report["errors"][0]["code"], "permission_denied")

    def test_regrant_same_scope_preserves_asset_lineage(self):
        self.manifest({"key": "notes", "kind": "file", "path": "notes.txt", "asset_id": "notes"})
        notes = self.inbox / "notes.txt"
        notes.write_bytes(b"first")
        grant(self.store, "inbox", "normalized", self.inbox, False)
        self.assertEqual(run_batch(self.store, self.blobs, "full")["created"], 1)
        revoke(self.store, "inbox")
        grant(self.store, "inbox", "normalized", self.inbox, False)
        notes.write_bytes(b"second")
        self.assertEqual(run_batch(self.store, self.blobs, "full")["updated"], 1)
        self.assertEqual([item["revision"] for item in self.items("asset", "notes")], [1, 2])

    def test_unsafe_existing_permissions_are_rejected(self):
        if os.name == "nt":
            fixture = self.root / "restored-example.txt"
            fixture.write_bytes(b"synthetic")
            icacls = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "icacls.exe"
            subprocess.run([str(icacls), str(fixture), "/grant", "*S-1-1-0:R"],
                           capture_output=True, check=True)
            with self.assertRaises(Denied):
                Store(self.root)
        else:
            self.root.chmod(0o755)
            try:
                with self.assertRaises(Denied):
                    Store(self.root)
            finally:
                self.root.chmod(0o700)

    def test_cli_routes_from_documented_entry_point(self):
        payload = self.write("sample.json", record())
        args = [sys.executable, "-m", "ai_memory_hub", "--root", str(self.root)]
        result = subprocess.run([*args, "import", "--input", str(payload), "--consent"], check=True, capture_output=True)
        self.assertEqual(json.loads(result.stdout)["status"], "created")
        result = subprocess.run([*args, "session", "list", "--project", "demo"], check=True, capture_output=True)
        self.assertEqual(json.loads(result.stdout)["records"][0]["id"], "session-1")
        result = subprocess.run([*args, "session", "show", "session-1", "--layer", "L3"], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["code"], "permission_denied")


if __name__ == "__main__":
    unittest.main()
