import json
import os
import tempfile
import unittest
from pathlib import Path

from ai_memory_hub.assets import LocalVault, put_file, put_link
from ai_memory_hub.model import Conflict, Denied, HubError
from ai_memory_hub.projection import (
    MANIFEST, MANIFEST_FORMAT, PUBLIC_ASSETS, PUBLIC_MEMORY, STATIC, build_projection, declared_files, encoded,
    verify_projection, verify_projection_files,
)
from ai_memory_hub.shared_version import check, reload
from ai_memory_hub.store import Store
from ai_memory_hub.transfer import hash_bytes


SOURCE = {"provider": "fixture", "kind": "workspace_artifact", "locator": "fixture:SYNTHETIC_LOCAL_LOCATOR"}


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        parent = tempfile.TemporaryDirectory(prefix="hub-projection-test-")
        self.addCleanup(parent.cleanup)
        self.root = Path(parent.name).resolve()
        self.workspace = self.root / "owner-workspace"
        self.workspace.mkdir()
        self.path = self.root / "preview"

    def vault(self, level):
        return Store(self.root / (level + "-vault"), initialize=level)

    def memory(self, store, entry_id="policy", claim="A fictional standard permits plain text", *,
               status="accepted", classification="fact", base=0):
        envelope = {"schema_version": "2.1", "kind": "memory", "id": entry_id, "sensitivity": store.level,
                    "base_revision": base, "source": SOURCE,
                    "data": {"key": entry_id, "claim": claim, "status": status, "classification": classification}}
        with store.transaction(write=True) as db:
            store.ingest(db, envelope, allow_review=True)

    def build(self, store, path=None, **options):
        return build_projection(store, path or self.path, workspace=self.workspace, **options)

    def test_private_default_projects_only_aggregate_counts(self):
        store = self.vault("private")
        self.memory(store, claim="SYNTHETIC_PRIVATE_CLAIM")
        with store.transaction(write=True) as db:
            store.ingest(db, {"schema_version": "2.1", "kind": "session", "id": "private-chat",
                              "sensitivity": "private", "source": {**SOURCE, "kind": "observed_messages"},
                              "data": {"title": "SYNTHETIC_PRIVATE_TITLE", "messages": [
                                  {"id": "test-message", "role": "user", "text": "SYNTHETIC_RAW_TEXT"}
                              ]}}, allow_raw=True)
        preview = self.build(store)
        self.assertEqual(preview["status"], "created")
        files = verify_projection(self.path, preview["digest"])
        self.assertEqual(set(files), set(STATIC) | {"inventory.json", MANIFEST})
        combined = b"".join(files.values())
        for private in (b"SYNTHETIC_PRIVATE_CLAIM", b"SYNTHETIC_PRIVATE_TITLE", b"private-chat",
                        b"SYNTHETIC_RAW_TEXT", b"SYNTHETIC_LOCAL_LOCATOR"):
            self.assertNotIn(private, combined)
        self.assertEqual(json.loads(files["inventory.json"])["counts"],
                         {"asset": 0, "memory": 1, "project": 0, "session": 1})
        self.assertEqual(self.build(store)["status"], "unchanged")
        with self.assertRaises(Denied):
            self.build(store, selected=["policy"])

    def test_public_selection_version_diff_and_agent_compatibility(self):
        store = self.vault("public")
        self.memory(store)
        self.memory(store, "unselected", "SYNTHETIC_UNSELECTED_CLAIM")
        with store.transaction(write=True) as db:
            put_link(store, db, "https://example.org/fixture", "not projected.txt", SOURCE, "reference")
        original = self.root / "asset.bin"
        first_bytes = b"\0SYNTHETIC_ASSET_ORIGINAL\xff"
        original.write_bytes(first_bytes)
        blobs = LocalVault(store.root)
        with blobs.stage(original) as staged, store.transaction(write=True) as db:
            put_file(store, db, blobs, staged, original.name, SOURCE, "opaque-file")
        original.write_bytes(b"\0SYNTHETIC_ASSET_REVISED\xff")
        with blobs.stage(original) as staged, store.transaction(write=True) as db:
            put_file(store, db, blobs, staged, original.name, SOURCE, "opaque-file", base=1)
        first = self.build(store, selected=["policy"], assets=["reference@1", "opaque-file@1"])
        files = verify_projection(self.path, first["digest"])
        combined = b"".join(files.values())
        self.assertNotIn(b"SYNTHETIC_LOCAL_LOCATOR", combined)
        self.assertNotIn(b"SYNTHETIC_UNSELECTED_CLAIM", combined)
        self.assertNotIn(b"example.org", combined)
        self.assertNotIn(b"not projected.txt", combined)
        self.assertNotIn(b"SYNTHETIC_ASSET", combined)
        self.assertNotIn(b"asset.bin", combined)
        self.assertEqual(json.loads(files[PUBLIC_ASSETS])["refs"],
                         [{"id": "opaque-file", "version": 1, "storage": "vault", "sha256": hash_bytes(first_bytes)},
                          {"id": "reference", "version": 1, "storage": "external", "sha256": None}])
        for entry in first["files"]:
            self.assertEqual(entry["content"].encode("utf-8"), files[entry["path"]])
        peer = self.vault("private")
        checked = check(peer, "example", "agent", self.path / PUBLIC_MEMORY, consent=True)
        self.assertIsNone(checked["synced_sha"])
        loaded = reload(peer, "example", "agent", consent=True)
        record = loaded["scopes"]["reviewed"][0]
        self.assertEqual(record["source"]["locator"], "projection:public-memory:policy@1")
        self.assertEqual(record["revision"], 1)

        self.memory(store, claim="A revised fictional standard", base=1)
        with self.assertRaises(Conflict):
            self.build(store, selected=["policy"], assets=["reference@1", "opaque-file@1"])
        updated = self.build(store, self.root / "review-v2", selected=["policy"], previous=self.path)
        self.assertNotEqual(updated["digest"], first["digest"])
        changes = {entry["path"]: entry for entry in updated["changes"]}
        self.assertNotIn("README.md", changes)
        self.assertEqual(changes[PUBLIC_ASSETS]["status"], "removed")
        self.assertEqual(changes[PUBLIC_MEMORY]["status"], "changed")
        self.assertIn("A revised fictional standard", changes[PUBLIC_MEMORY]["diff"])
        self.assertEqual(verify_projection(self.path, first["digest"]), files)

    def test_rejects_pending_inference_and_sensitive_markers(self):
        store = self.vault("public")
        self.memory(store, "draft", status="candidate")
        self.memory(store, "inferred", classification="inference")
        self.memory(store, "unsafe", "The fictional file lives at C:/Users/fixture/raw.json")
        self.memory(store, "contact", "A synthetic contact user@example.org")
        self.memory(store, "secret", "Example Bearer " + "fixture" * 10)
        for entry in ("draft", "inferred", "unsafe", "contact", "secret"):
            with self.subTest(entry=entry):
                with self.assertRaises(Denied):
                    self.build(store, selected=[entry])
                self.assertFalse(self.path.exists())

    def test_tamper_extra_file_and_recomputed_dangerous_manifest(self):
        store = self.vault("public")
        self.memory(store)
        preview = self.build(store, selected=["policy"])
        files = verify_projection(self.path, preview["digest"])
        with self.assertRaises(Conflict):
            verify_projection(self.path, "0" * 64)
        with (self.path / PUBLIC_MEMORY).open("ab") as output:
            output.write(b" ")
        with self.assertRaises(HubError):
            verify_projection(self.path, preview["digest"])
        (self.path / PUBLIC_MEMORY).write_bytes(files[PUBLIC_MEMORY])
        (self.path / ".env").write_text("synthetic only", encoding="utf-8")
        with self.assertRaises(Denied):
            verify_projection(self.path, preview["digest"])

        forged = json.loads(files[PUBLIC_MEMORY])
        forged["scopes"]["reviewed"][0]["data"]["claim"] = "Synthetic disclosure fixture@example.org"
        payload = {**files, PUBLIC_MEMORY: encoded(forged)}
        payload.pop(MANIFEST)
        payload[MANIFEST] = encoded({"format": MANIFEST_FORMAT, "kind": "git_projection",
                                    "files": declared_files(payload)})
        with self.assertRaises(Denied):
            verify_projection_files(payload, hash_bytes(payload[MANIFEST]))

    def test_denies_nested_projection_targets_and_linked_files(self):
        store = self.vault("private")
        under_git = self.root / "repo"
        (under_git / ".git").mkdir(parents=True)
        for forbidden in (self.workspace, self.workspace / "inside", store.root / "inside",
                          self.root, under_git / "inside"):
            with self.subTest(target=forbidden), self.assertRaises(Denied):
                self.build(store, forbidden)
        ready = self.build(store)
        external_link = self.root / "linked-inventory.json"
        try:
            os.link(self.path / "inventory.json", external_link)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {type(exc).__name__}")
        with self.assertRaises(Denied):
            verify_projection(self.path, ready["digest"])
