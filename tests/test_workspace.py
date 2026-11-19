import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from ai_memory_hub import VERSION
from ai_memory_hub.life import archive_coverage, health_coverage
from ai_memory_hub.model import Conflict, Denied, HubError
from ai_memory_hub.workspace import check_workspace, facts_projection, get_templates, init_workspace

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.resources = tempfile.TemporaryDirectory(prefix="hub-workspace-tests-")
        self.addCleanup(self.resources.cleanup)
        self.parent = Path(self.resources.name).resolve()

    def test_blank_safe_pair_and_navigation(self):
        root = self.parent / "blank"
        vault = self.parent / "explicit-vault"
        initialized = init_workspace(root, vault, "internal")
        self.assertEqual(initialized["vault"], str(vault))
        self.assertFalse(root.is_relative_to(vault))
        self.assertFalse(vault.is_relative_to(root))
        current = check_workspace(root)
        self.assertEqual((current["template_version"], current["engine_version"]), (VERSION, VERSION))
        self.assertEqual(current["life_archive"]["states"], {"unknown": 12, "partial": 0, "reviewed": 0})
        self.assertEqual(current["switches"], {"weekly": True, "full": True, "daily": False,
                                              "event": False, "handoff": False})
        self.assertFalse((root / "demo-inbox").exists())
        self.assertEqual(facts_projection(root)["facts"], [])
        originals = (root / "AGENTS.md").read_bytes(), (vault / "index.sqlite").read_bytes()
        with self.assertRaises(Conflict):
            init_workspace(root, vault)
        self.assertEqual(originals, ((root / "AGENTS.md").read_bytes(), (vault / "index.sqlite").read_bytes()))
        self.check_links(root)
        for entry in ("docs/agent-onboarding.md",
                      "docs/agent-onboarding.zh-CN.md", "docs/adapters.md"):
            self.assertTrue((root / entry).is_file(), entry)

    def test_rejects_targets_under_git_or_inside_each_other(self):
        git_tree = self.parent / "repo"
        git_tree.mkdir()
        (git_tree / ".git").mkdir()
        for path, vault in [(git_tree / "profile", self.parent / "outside"),
                            (self.parent / "outside", git_tree / "vault"),
                            (self.parent / "profile", self.parent / "profile" / "vault")]:
            with self.subTest(path=path, vault=vault), self.assertRaises(Denied):
                init_workspace(path, vault)
            self.assertFalse(path.exists())
            self.assertFalse(vault.exists())

    def test_rejects_denied_reservation_and_only_cleans_own_roots(self):
        root, vault = self.parent / "profile", self.parent / "private"
        existing = self.parent / "untouched"
        existing.mkdir()
        self.addCleanup(existing.rmdir)
        with patch("ai_memory_hub.workspace.protect_root", side_effect=Denied("synthetic ACL denial")):
            with self.assertRaises(Denied):
                init_workspace(root, vault)
        self.assertFalse(root.exists())
        self.assertFalse(vault.exists())
        self.assertTrue(existing.is_dir())

    def test_partial_failure_preserves_concurrently_created_vault(self):
        from ai_memory_hub.store import Store

        root, vault = self.parent / "workspace", self.parent / "concurrent-vault"
        def interrupted(*_args):
            Store(vault, initialize="private")
            raise OSError("synthetic interruption")

        with patch("ai_memory_hub.workspace.write_exclusive", side_effect=interrupted):
            with self.assertRaises(OSError):
                init_workspace(root, vault)
        self.assertTrue((vault / "index.sqlite").is_file())
        self.assertEqual(Store(vault).settings()["sensitivity"], "private")

    def test_wrong_same_sensitivity_vault_binding_is_rejected(self):
        from ai_memory_hub.store import Store

        root = self.parent / "profile"
        init_workspace(root)
        vault = self.parent / "unrelated"
        Store(vault, initialize="private")
        config = root / "config/workspace.json"
        binding = json.loads(config.read_text(encoding="utf-8"))
        binding["vault"] = str(vault)
        config.write_text(json.dumps(binding), encoding="utf-8")
        with self.assertRaises(Denied):
            facts_projection(root)

    def test_rejects_directory_symlink_before_writing(self):
        location = self.parent / "existing"
        location.mkdir()
        alias = self.parent / "alias"
        try:
            alias.symlink_to(location, target_is_directory=True)
        except OSError:
            if os.name == "nt":
                self.skipTest("this Windows user cannot create directory symlinks")
            raise
        self.addCleanup(alias.unlink)
        with self.assertRaises(Denied):
            init_workspace(alias / "would-write", self.parent / "vault")
        self.assertEqual(list(location.iterdir()), [])

    def test_life_precision_and_health_consistency(self):
        profile = json.loads((ROOT / "life-archive/profile.json").read_text(encoding="utf-8"))
        timeline = {"schema_version": "1.0", "kind": "life_timeline", "events": [{
            "record_id":"event-1", "category":"11", "status":"self-report", "evidence_level":"unverified",
            "source":{"provider":"fixture","kind":"user_checkpoint","locator":"fixture:test"},
            "source_type":"user_statement", "created_at":"2000-01-01T00:00:00Z",
            "updated_at":"2000-01-01T00:00:00Z", "summary":"Synthetic event",
            "sensitivity":"private", "occurred_at":"2000-01", "date_precision":"month",
        }]}
        self.assertEqual(archive_coverage(profile, timeline, "private")["timeline_events"], 1)
        with self.assertRaises(Denied):
            archive_coverage(profile, timeline, "public")
        timeline["events"][0]["date_precision"] = "day"
        with self.assertRaises(HubError):
            archive_coverage(profile, timeline, "private")
        timeline["events"][0]["date_precision"] = "month"
        other = {**timeline["events"][0], "record_id":"event-2", "supersedes":["event-1"]}
        timeline["events"][0]["supersedes"] = ["event-2"]
        timeline["events"].append(other)
        with self.assertRaisesRegex(HubError, "cycle"):
            archive_coverage(profile, timeline, "private")
        health = json.loads((ROOT / "life-archive/health/synthetic.json").read_text(encoding="utf-8"))
        self.assertEqual(health_coverage(health), {"status": "valid", "observations": 1})
        health["observations"].append(health["observations"][0].copy())
        with self.assertRaises(HubError):
            health_coverage(health)

    def check_links(self, directory):
        for name in get_templates()["files"]:
            document = directory / name
            if document.suffix != ".md":
                continue
            markdown = document.read_text(encoding="utf-8")
            for link in re.findall(r"\[[^\]]+\]\(([^ )]+)\)", markdown):
                url = urlsplit(link)
                if url.scheme or not url.path:
                    continue
                target = (document.parent / unquote(url.path)).resolve()
                self.assertTrue(target.is_relative_to(directory), (name, link))
                self.assertTrue(target.exists(), (name, link))

    def test_workspace_schemas_resolve_and_accept_shipped_inputs(self):
        try:
            from jsonschema import Draft202012Validator
            from referencing import Registry, Resource
        except ImportError:
            self.skipTest("jsonschema is an optional test dependency")
        docs = {
            item.name: json.loads(item.read_text(encoding="utf-8"))
            for item in (ROOT / "schemas").glob("*.schema.json")
        }
        registry = Registry().with_resources((name, Resource.from_contents(value)) for name,value in docs.items())
        fixtures = {
            "life-archive.schema.json": ["life-archive/profile.json", "life-archive/timeline.json"],
            "health-summary.schema.json": ["life-archive/health/synthetic.json"],
            "memory-candidate.schema.json": ["examples/memory.json"],
            "workspace-index.schema.json": ["memory/facts.yaml", "sessions/index.json", "assets/manifest.json"],
        }
        for name, paths in fixtures.items():
            Draft202012Validator.check_schema(docs[name])
            validator = Draft202012Validator(docs[name], registry=registry,
                                           format_checker=Draft202012Validator.FORMAT_CHECKER)
            for path in paths:
                with self.subTest(schema=name, input=path):
                    validator.validate(json.loads((ROOT / path).read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
