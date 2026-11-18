import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from ai_memory_hub.adapters import grant
from ai_memory_hub.assets import LocalVault, put_file
from ai_memory_hub.model import Conflict, Denied, LISTS
from ai_memory_hub.store import Store
from ai_memory_hub.sync import run_batch, status
from ai_memory_hub.transfer import inspect_transfer, pack_transfer, receive_transfer, retrieve_transfer

SOURCE = {"provider": "demo", "kind": "user_checkpoint", "locator": "synthetic:scope"}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hub-deployment-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.sender = Store(self.base / "sender", initialize="private")
        self.blobs = LocalVault(self.sender.root)

    def receiver(self, level="private"):
        store = Store(self.base / ("target-" + level), initialize=level)
        return store, LocalVault(store.root)

    def write_project(self):
        file = self.base / "fixture.pdf"
        file.write_bytes(b"synthetic document contents")
        with self.blobs.stage(file) as staged, self.sender.transaction(write=True) as db:
            for key in ("output-1", "output-2"):
                put_file(self.sender, db, self.blobs, staged, file.name, SOURCE, asset_id=key, project_id="test-project")
        fields = {key: [] for key in LISTS}
        fields["goal"] = "Synthetic scope only"
        fields["verification"] = ["File was committed to the Vault"]
        fields["file_refs"] = [{"asset_id": "output-1"}]
        with self.sender.transaction(write=True) as db:
            self.sender.ingest(db, {
                "schema_version": "2.1", "kind": "session", "id": "example-session",
                "sensitivity": "private", "source": {**SOURCE,"kind": "observed_messages"},
                "data": {"title":"Example", "project_id":"test-project", "checkpoint": fields,
                         "messages":[{"id":"raw","role":"user","text":"SYNTHETIC-L3-ONLY"}]},
            }, allow_raw=True)
        return file

    def test_authorized_receive_and_repair_uses_recipient_bytes(self):
        original = self.write_project()
        target, target_blobs = self.receiver()
        with self.assertRaises(Denied):
            pack_transfer(self.sender, self.blobs, "test-project", ["output-1@1"])
        self.sender.settings(feature="handoff", enabled=True)
        result = pack_transfer(self.sender, self.blobs, "test-project", ["output-1@1", "output-2@1"])
        path = Path(result["path"])
        self.assertEqual(result["unique_blobs"], 1)
        with self.assertRaises(Denied):
            receive_transfer(target, target_blobs, path)
        target.settings(feature="handoff", enabled=True)
        received = receive_transfer(target, target_blobs, path)
        self.assertEqual(received["status"], "received")
        self.assertEqual(receive_transfer(target, target_blobs, path)["status"], "unchanged")
        context = inspect_transfer(target, target_blobs, result["id"])["context"]
        self.assertNotIn("SYNTHETIC-L3-ONLY", json.dumps(context))
        self.assertEqual([item["recipient_status"] for item in context["files"]], ["available", "available"])
        store_file = target_blobs.directory / context["files"][0]["sha256"]
        self.assertEqual(store_file.read_bytes(), original.read_bytes())
        out = retrieve_transfer(target, target_blobs, result["id"], "output-1@1")
        self.assertEqual(Path(out["path"]).read_bytes(), original.read_bytes())
        store_file.unlink()
        self.assertEqual(inspect_transfer(target, target_blobs, result["id"])["context"]["files"][0]["recipient_status"], "missing")
        self.assertEqual(receive_transfer(target, target_blobs, path)["status"], "restored")
        self.assertEqual(store_file.read_bytes(), original.read_bytes())
        target.settings(feature="handoff", enabled=False)
        with self.assertRaises(Denied):
            inspect_transfer(target, target_blobs, result["id"])
        with self.assertRaises(Denied):
            retrieve_transfer(target, target_blobs, result["id"], "output-1@1")

    def test_context_only_reference_and_wrong_realm_are_not_readable(self):
        self.write_project()
        self.sender.settings(feature="handoff", enabled=True)
        with self.assertRaises(Denied):
            pack_transfer(self.sender, self.blobs, "test-project", ["out-of-scope@1"])
        result = pack_transfer(self.sender, self.blobs, "test-project", [])
        wrong, wrong_blobs = self.receiver("public")
        wrong.settings(feature="handoff", enabled=True)
        with self.assertRaises(Denied):
            receive_transfer(wrong, wrong_blobs, Path(result["path"]))
        self.assertFalse((wrong.root / "received").exists())
        target, target_blobs = self.receiver()
        target.settings(feature="handoff", enabled=True)
        receive_transfer(target, target_blobs, Path(result["path"]))
        context = inspect_transfer(target, target_blobs, result["id"])["context"]
        self.assertFalse(target_blobs.directory.exists())
        self.assertEqual(context["files"][0]["recipient_status"], "not_transferred")
        with self.assertRaises(Denied):
            retrieve_transfer(target, target_blobs, result["id"], "output-1@1")

    def test_receiver_rejects_corrupt_bytes_before_publishing_receipt(self):
        self.write_project()
        self.sender.settings(feature="handoff", enabled=True)
        packaged = pack_transfer(self.sender, self.blobs, "test-project", ["output-1@1"])
        tampered = self.base / "bad.zip"
        with zipfile.ZipFile(packaged["path"]) as original, zipfile.ZipFile(tampered,"w") as modified:
            for name in original.namelist():
                data = original.read(name)
                if name.startswith("blobs/"):
                    data = b"x" * len(data)
                modified.writestr(name,data)
        target, target_blobs = self.receiver()
        target.settings(feature="handoff", enabled=True)
        with self.assertRaises(Conflict):
            receive_transfer(target, target_blobs, tampered)
        self.assertFalse((target.root / "received").exists())
        self.assertEqual(list(target_blobs.directory.iterdir()), [])

    def test_local_weekly_uses_scope_and_ignores_cloud_governance(self):
        root = self.base / "inbox"
        root.mkdir()
        (root/"memory-hub.json").write_text(
            '{"schema_version":"2.1","items":[{"key":"file","kind":"file","path":"sample.png","origin":"user_upload"}]}',
            encoding="utf-8",
        )
        (root/"sample.png").write_bytes(b"synthetic bytes")
        grant(self.sender, "selected", "local_checkpoint", root, False)
        report = run_batch(self.sender, self.blobs, "weekly", "selected", archive_only=True)
        self.assertEqual(report["governance"]["status"], "not_run")
        self.assertEqual(report["execution"]["scheduler"], "not_verified")
        self.assertEqual(report["archive"]["items"]["asset"], 1)
        snapshot = status(self.sender)
        self.assertEqual(snapshot["sources"][0]["authorization"], "granted")
        self.assertTrue(snapshot["sources"][0]["last_archive_success"])
        self.assertFalse(snapshot["last_governance_success"])
        self.sender.settings(feature="weekly", enabled=False)
        with self.assertRaises(Denied):
            run_batch(self.sender, self.blobs, "weekly", "selected", archive_only=True)
        self.assertEqual(run_batch(self.sender, self.blobs, "full", "selected", archive_only=True)["unchanged"], 1)

    def test_approved_zip_shards_preserve_actual_visible_message_evidence(self):
        export = self.base / "chatgpt.zip"
        def conversation(item):
            return {"id":f"example-{item}","title":f"Chat {item}","current_node":"node","update_time":1700000000,
                    "mapping":{"node":{"parent":None,"message":{"author":{"role":"user"},"metadata":{},
                      "content":{"content_type":"text","parts":["Visible synthetic text"]}}}}}
        with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("conversations-001.json",json.dumps([conversation(1)]))
            archive.writestr("conversations-002.json",json.dumps([conversation(2)]))
            archive.writestr("account-metadata.json", b"unrelated nonJSON ignored")
        grant(self.sender, "chat", "chatgpt_export", export, True)
        report = run_batch(self.sender, self.blobs, "full")
        self.assertEqual(report["archive"]["items"]["session"], 2)
        self.assertEqual(run_batch(self.sender, self.blobs, "full")["unchanged"], 2)
        with self.sender.transaction() as db:
            saved = self.sender.latest(db,"session")
            self.assertEqual({item["source"]["locator"] for item in saved},
                             {"chatgpt-export:example-1","chatgpt-export:example-2"})
            raw = self.sender.session_view(db,saved[0],"L3",raw_consent=True)
            self.assertEqual(raw["messages"][0]["text"], "Visible synthetic text")
        with zipfile.ZipFile(export, "w") as archive:
            archive.writestr("conversations-001.json", json.dumps([conversation(3)]))
            archive.writestr("conversations-002.json", json.dumps([conversation(3)]))
        duplicate = run_batch(self.sender, self.blobs, "full")
        self.assertEqual(duplicate["created"], 0)
        self.assertEqual([error["code"] for error in duplicate["errors"]], ["invalid_input", "invalid_input"])
