import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_memory_hub import candidates, github_publish as publish, projection, projection_review
from ai_memory_hub.__main__ import execute, parser
from ai_memory_hub.model import Conflict, Denied, HubError
from ai_memory_hub.workspace import bound_workspace


TARGET = "fixture-owner/memory-fixture"
OWNER = TARGET.split("/")[0]
BASE = f"repos/{TARGET}"


class FakeGitHub:
    """Synthetic REST state for the endpoints the runner is allowed to use."""

    def __init__(self, *, exists=True):
        self.metadata = {"id": 7, "full_name": TARGET, "default_branch": "main", "private": True,
                         "visibility": "private", "archived": False, "fork": False,
                         "owner": {"type": "User", "login": OWNER}, "permissions": {"push": True}}
        self.exists = exists
        self.user = OWNER
        self.calls = []
        self.refs = {}
        self.commits = {}
        self.trees = {}
        self.blobs = {}
        self.pull = None
        self.reject = None

    def writes(self):
        return [(method, endpoint) for method, endpoint, body in self.calls if method != "GET"]

    def object_sha(self, value):
        return hashlib.sha1(projection.encoded(value)).hexdigest()

    def ref(self, branch):
        return {"ref": f"refs/heads/{branch}", "object": {"type": "commit", "sha": self.refs[branch]}}

    def add_blob(self, data):
        sha = publish.blob_id(data)
        self.blobs[sha] = {"sha": sha, "size": len(data), "encoding": "base64", "content": publish.b64(data)}
        return sha

    def add_tree(self, entries):
        tree = [{**item, "size": self.blobs[item["sha"]]["size"]} for item in entries]
        for name in sorted({item["path"].split("/", 1)[0] for item in entries if "/" in item["path"]}):
            children = [item for item in tree if item["path"].startswith(name + "/")]
            tree.append({"path": name, "mode": "040000", "type": "tree", "sha": self.object_sha(children)})
        sha = self.object_sha(tree)
        self.trees[sha] = {"sha": sha, "tree": tree, "truncated": False}
        return sha

    def add_commit(self, message, tree, parents):
        result = {"message": message, "tree": {"sha": tree}, "parents": [{"sha": parent} for parent in parents]}
        sha = self.object_sha(result)
        self.commits[sha] = {**result, "sha": sha}
        return sha

    def request(self, endpoint, method="GET", body=None, *, missing=()):
        self.calls.append((method, endpoint, body))
        if self.reject == (method, endpoint):
            raise publish.GitHubError("synthetic GitHub write was denied", 403)
        if endpoint == "user" and method == "GET":
            return {"login": self.user}
        if endpoint == "user/repos" and method == "POST":
            assert body == {"name": TARGET.split("/")[1], "private": True, "auto_init": False}
            assert not self.exists
            self.exists = True
            return self.metadata.copy()
        if endpoint == BASE and method == "GET":
            if self.exists:
                return self.metadata.copy()
            assert 404 in missing
            return None
        assert endpoint.startswith(BASE + "/") and self.exists
        resource = endpoint.removeprefix(BASE)
        if resource == "/branches?per_page=1" and method == "GET":
            return [{"name": name} for name in list(self.refs)[:1]]
        if resource == "/contents/projection.json" and method == "PUT":
            assert not self.refs
            blob = self.add_blob(base64.b64decode(body["content"]))
            tree = self.add_tree([{"path": "projection.json", "sha": blob, "type": "blob", "mode": "100644"}])
            sha = self.add_commit(body["message"], tree, [])
            self.refs["main"] = sha
            return {"commit": {"sha": sha}, "content": {"sha": blob}}
        if resource.startswith("/git/ref/heads/") and method == "GET":
            branch = resource.removeprefix("/git/ref/heads/")
            if branch in self.refs:
                return self.ref(branch)
            assert set(missing) == {404, 409}
            return None
        if resource.startswith("/git/refs/heads/") and method == "PATCH":
            branch = resource.removeprefix("/git/refs/heads/")
            assert body["force"] is False
            assert self.commits[body["sha"]]["parents"] == [{"sha": self.refs[branch]}]
            self.refs[branch] = body["sha"]
            return self.ref(branch)
        if resource == "/git/refs" and method == "POST":
            branch = body["ref"].removeprefix("refs/heads/")
            assert branch not in self.refs
            self.refs[branch] = body["sha"]
            return self.ref(branch)
        if resource == "/git/blobs" and method == "POST":
            assert body["encoding"] == "base64"
            return {"sha": self.add_blob(base64.b64decode(body["content"]))}
        if resource == "/git/trees" and method == "POST":
            assert set(body) == {"tree"}
            return {"sha": self.add_tree(body["tree"])}
        if resource == "/git/commits" and method == "POST":
            return {"sha": self.add_commit(body["message"], body["tree"], body["parents"])}
        if method == "GET":
            for kind, objects in (("blobs", self.blobs), ("trees", self.trees), ("commits", self.commits)):
                prefix = f"/git/{kind}/"
                if resource.startswith(prefix):
                    key, _, options = resource.removeprefix(prefix).partition("?")
                    if kind == "trees":
                        assert options == "recursive=1"
                    return objects[key]
        if resource.startswith("/pulls?") and method == "GET":
            return [self.pull] if self.pull else []
        if resource == "/pulls" and method == "POST":
            assert body["draft"] is True and body["base"] == "main" and body["head"] != "main"
            self.pull = {"number": 1, "state": "open", "draft": True,
                         "base": {"ref": "main", "sha": self.refs["main"], "repo": {"id": self.metadata["id"]}},
                         "head": {"ref": body["head"], "sha": self.refs[body["head"]],
                                  "repo": {"id": self.metadata["id"]}}}
            return self.pull
        if resource == "/pulls/1" and method == "GET":
            return self.pull
        raise AssertionError(f"unexpected synthetic endpoint: {method} {endpoint}")


class GitHubPublicationTests(unittest.TestCase):
    def setUp(self):
        self.remote = FakeGitHub()
        connection = patch.object(publish, "GitHub", return_value=self.remote)
        connection.start()
        self.addCleanup(connection.stop)
        tmp = tempfile.TemporaryDirectory(prefix="hub-remote-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def build(self, number):
        root = self.root / str(number)
        root.mkdir()
        data = {**projection.STATIC, "inventory.json": projection.encoded({
            "format": projection.FORMAT, "kind": "aggregate_inventory",
            "counts": {"session": number, "asset": 0, "project": 0, "memory": 0},
        })}
        data["projection.json"] = projection.encoded({
            "format": projection.MANIFEST_FORMAT, "kind": "git_projection", "files": projection.declared_files(data),
        })
        for name, contents in data.items():
            destination = root / name
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(contents)
        return root, hashlib.sha256(data["projection.json"]).hexdigest()

    def publish(self, plan, **options):
        return publish.publish_projection(TARGET, *plan, consent=True, **options)

    def test_legacy_flat_publication_remains_auditable_but_new_head_is_modular(self):
        legacy = {"README.md": projection.README, "inventory.json": projection.encoded({
            "format": projection.FORMAT, "kind": "aggregate_inventory",
            "counts": dict.fromkeys(projection.RECORD_KINDS, 0),
        })}
        legacy[projection.MANIFEST] = projection.encoded({
            "format": projection.FORMAT, "kind": "git_projection", "files": projection.declared_files(legacy),
        })
        digest = hashlib.sha256(legacy[projection.MANIFEST]).hexdigest()
        seed = self.remote.add_tree([{"path": projection.MANIFEST, "mode": "100644", "type": "blob",
                                      "sha": self.remote.add_blob(legacy[projection.MANIFEST])}])
        initial = self.remote.add_commit(publish.BOOTSTRAP + digest, seed, [])
        tree = self.remote.add_tree([{"path": path, "mode": "100644", "type": "blob", "sha": self.remote.add_blob(data)}
                                     for path, data in legacy.items()])
        previous = self.remote.add_commit(publish.PUBLICATION + digest, tree, [initial])
        self.remote.refs["main"] = previous
        self.assertEqual(self.publish(self.build(1), expected_base=previous)["status"], "completed")

    def test_private_onboarding_review_and_modular_publication_end_to_end(self):
        self.remote.exists = False
        workspace = self.root / "workspace"
        request = self.root / "request.json"
        intake = self.root / "intake"
        intake.mkdir()

        def write(path, obj):
            path.write_bytes(projection.encoded(obj))

        def cli(*args):
            return execute(parser().parse_args(list(map(str, args))))

        examples = Path(__file__).resolve().parents[1] / "examples"
        read = lambda name: json.loads((examples / name).read_text(encoding="utf-8"))
        session = read("session.json")
        session["source"].update(kind="observed_messages", locator="fixture:SYNTHETIC_PRIVATE_LOCATOR")
        session["data"].update(title="SYNTHETIC_PRIVATE_TITLE", messages=[
            {"id": "memo", "role": "user", "text": "SYNTHETIC_PRIVATE_TRANSCRIPT"},
        ])
        memory, project, manifest = (read(name) for name in ("memory.json", "project.json", "memory-hub.json"))
        memory["data"]["claim"] = "SYNTHETIC_ORIGINAL_MEMORY_CLAIM"
        other = read("memory.json")
        other["id"] = "unselected-secret"
        other["data"].update(key="unselected", claim="SYNTHETIC_UNSELECTED_CLAIM")
        manifest["items"].append({"key": "unselected", "kind": "record", "path": "unselected.json"})
        for name, row in (("session", session), ("project", project), ("memory", memory),
                          ("unselected", other), ("memory-hub", manifest)):
            write(intake / f"{name}.json", row)
        (intake / "checklist.txt").write_bytes(b"SYNTHETIC_ATTACHMENT_BYTES")
        write(request, {
            "format": "1.0", "workspace": str(workspace), "vault": str(self.root / "vault"),
            "sources": [{"id": "fixture", "adapter": "codex_workspace", "path": str(intake),
                         "authorized": True, "allow_raw": True}],
            "github": {"target": TARGET, "visibility": "private"},
        })
        plan = cli("onboarding", "plan", "--request", request)
        cli("onboarding", "apply", "--request", request, "--approve-plan", plan["plan_digest"], "--consent")
        _, _, store = bound_workspace(workspace)
        self.assertEqual(store.level, "private")
        memory_id = memory["id"]
        spec = {"format": "1.0", "target": TARGET, "items": [
            {"kind": "memory", "id": "review-rule", "purpose": "reference",
             "source": {"id": memory_id, "revision": 1},
             "data": {"key": "verification", "claim": "Review measurements before accepting a result."}},
            {"kind": "project", "id": "instrument-review", "purpose": "continuity",
             "source": {"id": project["id"], "revision": 1},
             "data": {"title": "Instrument review", "checkpoint": {"goal": "Verify the reference sample."}}},
            {"kind": "session", "id": "reading-review", "purpose": "navigation",
             "source": {"id": session["id"], "revision": 1},
             "data": {"title": "Reading review", "summary": "A second reading is pending.",
                      "project": "instrument-review", "checkpoint": {"goal": "Record a second reading."}}},
        ]}
        input_path = self.root / "review.json"
        write(input_path, spec)
        action = ("--workspace", workspace, "--input", input_path)
        out = self.root / "modular-preview"
        preview = ("projection", "preview", "--workspace", workspace, "--output", out)
        default = cli(*preview[:-1], self.root / "totals")
        self.assertEqual(len(projection.MODULES), 19)
        self.assertTrue(not set(projection.REVIEWED_PATHS.values()) & {row["path"] for row in default["files"]})
        with self.assertRaises(Denied):
            cli("projection", "review", *action)
        for base, state in enumerate(("validated", "review", "approved", "active")):
            options = {"record_revision": 1} if state == "validated" else {"attest": True} if state == "approved" else {}
            candidates.step(store, memory_id, state, base=base, actor="tester", reason="Synthetic review",
                            consent=True, **options)
        report = cli("onboarding", "report", "--request", request)
        self.assertIn("active", [row["review_state"] for row in report["data"]["memory"]])
        spec["items"][0]["source"]["revision"] = 2
        wrong_project = copy.deepcopy(spec)
        wrong_project["items"][2]["data"]["project"] = "unapproved-project"
        write(input_path, wrong_project)
        with self.assertRaises(Conflict):
            cli("projection", "review", *action)
        write(input_path, spec)
        prepared = cli("projection", "review", *action)
        approved = prepared["review_digest"]
        with self.assertRaises(Denied):
            cli(*preview, "--review-digest", approved)
        with self.assertRaises(Denied):
            cli("projection", "approve", *action, "--digest", approved, "--consent")
        with self.assertRaises(Denied):
            cli("projection", "approve", *action, "--digest", approved, "--confirm-redacted")
        approve = ("projection", "approve", *action, "--digest", approved, "--confirm-redacted", "--consent")
        for field, value in (
            ("claim", "See C:/Users/synthetic/private.txt"), ("claim", "Contact fixture@example.org"),
            ("claim", "Authorization Bearer " + "fixture" * 6), ("messages", ["raw data"]),
        ):
            malicious = copy.deepcopy(spec)
            malicious["items"][0]["data"][field] = value
            write(input_path, malicious)
            with self.assertRaises(HubError):
                cli("projection", "review", *action)
        changed = copy.deepcopy(spec)
        changed["items"][0]["data"]["claim"] = "Different reviewed text."
        write(input_path, changed)
        with self.assertRaises(Conflict):
            cli(*approve)
        write(input_path, spec)
        self.assertEqual(cli(*approve)["status"], "approved")
        self.assertEqual(cli(*approve)["status"], "unchanged")
        reviewed = cli(*preview, "--review-digest", approved)
        self.assertEqual(cli(*preview, "--review-digest", approved)["status"], "unchanged")
        digest = reviewed["digest"]
        command = ("repo", "publish", "--workspace", workspace, "--target", TARGET,
                   "--repository-id", str(self.remote.metadata["id"]), "--projection", out, "--digest", digest)
        calls = len(self.remote.calls)
        with self.assertRaises(Denied):
            cli(*command)
        with self.assertRaises(Denied):
            publish.publish_projection("other-owner/other-repo", out, digest, consent=True, store=store)
        with self.assertRaises(Denied):
            publish.publish_projection(TARGET, out, digest, consent=True)
        self.assertEqual(len(self.remote.calls), calls)
        payload = projection.verify_projection(out, digest)
        forged = json.loads(payload[projection.REVIEWED_PATHS["memory"]])
        forged["records"][0]["data"]["claim"] = "Well formed text with no approved source."
        modified = {**payload, projection.REVIEWED_PATHS["memory"]: projection.encoded(forged)}
        binding = json.loads(modified.pop(projection.MANIFEST))
        binding["files"] = projection.declared_files(modified)
        modified[projection.MANIFEST] = projection.encoded(binding)
        forged_dir = self.root / "forged"
        projection.write_projection(forged_dir, modified)
        with self.assertRaises(Denied):
            publish.publish_projection(TARGET, forged_dir, hashlib.sha256(modified[projection.MANIFEST]).hexdigest(),
                                       consent=True, store=store, repository_id=7)
        self.assertEqual(len(self.remote.calls), calls)
        self.assertTrue(cli("repo", "create", "--workspace", workspace, "--target", TARGET, "--consent")["private"])
        self.remote.metadata["id"] = 8
        writes = self.remote.writes()
        self.assertEqual(cli(*command, "--consent")["status"], "blocked")
        self.assertEqual(self.remote.writes(), writes)
        self.remote.metadata["id"] = 7
        self.remote.reject = ("POST", BASE + "/git/blobs")
        seed = cli(*command, "--consent")
        self.assertEqual(seed["status"], "partial")
        self.assertEqual(seed["verified_step"], "bootstrap")
        self.remote.reject = None

        update = {"schema_version": "2.1", "kind": "session", "id": session["id"], "sensitivity": "private",
                  "base_revision": 1, "source": session["source"], "data": {"title": "SYNTHETIC_REVISION_TWO"}}
        with store.transaction(write=True) as db:
            self.assertEqual(store.ingest(db, update)["revision"], 2)
        self.assertEqual(cli(*command, "--consent")["status"], "blocked")
        spec["items"][2]["source"]["revision"] = 2
        write(input_path, spec)
        new_approval = cli("projection", "review", *action)["review_digest"]
        cli("projection", "approve", *action, "--digest", new_approval, "--confirm-redacted", "--consent")
        out = self.root / "recovered-projection"
        recovered = cli(*preview[:-1], out, "--review-digest", new_approval, "--previous", preview[-1])
        digest = recovered["digest"]
        command = (*command[:-3], out, "--digest", digest, "--base-sha", seed["commit_sha"])
        result = cli(*command, "--consent")
        self.assertEqual(result["status"], "completed")
        writes = self.remote.writes()
        self.assertEqual(cli(*command, "--consent")["outcome"], "unchanged")
        self.assertEqual(self.remote.writes(), writes)
        head = result["commit_sha"]
        repo = publish.Repository(self.remote, OWNER, TARGET.split("/")[1])
        repo.private()
        with store.transaction() as db:
            repo.review_history = lambda value, binding: projection_review.published_bases(db, 7, value, binding)
            self.assertFalse(repo.audit(head)[3])
        _, tree, parents = repo.commit(head)
        payload = projection.verify_projection(out, digest)
        self.assertEqual(set(repo.tree(tree)), set(payload))
        self.assertEqual({p.split("/")[0] for p in repo.tree(tree) if "/" in p}, set(projection.MODULES))
        navigation = re.findall(r"\]\(([^)]+)\)", payload["AGENTS.md"].decode("utf-8"))
        self.assertEqual(set(navigation), {f"{name}/README.md" for name in projection.MODULES})
        self.assertTrue(set(navigation) <= repo.tree(tree).keys())
        self.assertEqual(set(repo.tree(repo.commit(parents[0])[1])), {"projection.json"})
        combined = b"".join(base64.b64decode(blob["content"]) for blob in self.remote.blobs.values())
        for marker in (b"SYNTHETIC_", session["id"].encode(), project["id"].encode(), memory_id.encode(), b"index.sqlite"):
            self.assertNotIn(marker, combined)
        for reviewed_path in projection.REVIEWED_PATHS.values():
            self.assertIn(reviewed_path, repo.tree(tree))
        self.assertEqual(json.loads(payload["sessions/index.json"])["records"][0]["data"]["project"], "instrument-review")
        foreign_tree = self.remote.add_tree([
            {"path": path, "mode": "100644", "type": "blob", "sha": self.remote.add_blob(contents)}
            for path, contents in modified.items()
        ])
        foreign_digest = hashlib.sha256(modified[projection.MANIFEST]).hexdigest()
        self.remote.refs["main"] = self.remote.add_commit(publish.PUBLICATION + foreign_digest, foreign_tree, [head])
        default_args = (self.root / "totals", default["digest"])
        with self.assertRaises(Denied):
            publish.publish_projection(TARGET, *default_args, consent=True, store=store, repository_id=7)
        self.remote.refs["main"] = head
        self.assertEqual(self.remote.writes(), writes)
        conflict = copy.deepcopy(memory)
        conflict["id"] = "independent-conflict"
        conflict["data"]["claim"] = "Disagree with the original evidence."
        with store.transaction(write=True) as db:
            store.ingest(db, conflict)
        with self.assertRaises(Conflict):
            publish.publish_projection(TARGET, out, digest, consent=True, store=store, repository_id=7)
        self.assertEqual(self.remote.writes(), writes)

    def test_missing_tool_and_unverified_permissions(self):
        # Exercise the real tool detector while keeping all network calls mocked.
        with patch.object(publish, "GitHub", REAL_GITHUB), patch.object(publish.shutil, "which", return_value=None):
            self.assertEqual(publish.probe(TARGET)["status"], "blocked")
        self.remote.metadata["permissions"]["push"] = False
        self.assertEqual(publish.probe(TARGET)["push_permission"], "denied")
        with self.assertRaises(Denied):
            self.publish(self.build(0))
        self.assertEqual(self.remote.writes(), [])

    def test_private_creation_requires_consent_and_verified_owner(self):
        self.remote.exists = False
        self.assertEqual(publish.probe(TARGET)["creation_permission"], "not_verified")
        with self.assertRaises(Denied):
            publish.create_private(TARGET)
        self.remote.user = "other-account"
        with self.assertRaises(Denied):
            publish.create_private(TARGET, consent=True)
        self.remote.user = OWNER
        self.assertTrue(publish.create_private(TARGET, consent=True)["created"])
        self.assertFalse(publish.create_private(TARGET, consent=True)["created"])
        self.assertIsNone(publish.probe(TARGET)["base_commit"])
        self.assertEqual(self.remote.writes(), [("POST", "user/repos")])
        self.assertEqual(self.remote.refs, {})

    def test_public_or_unrelated_repository_is_rejected(self):
        plan = self.build(0)
        self.remote.metadata.update(private=False, visibility="public")
        with self.assertRaises(Denied):
            self.publish(plan)
        self.remote.metadata.update(private=True, visibility="private")
        self.remote.refs["main"] = self.remote.add_commit("unrelated history", "a" * 40, [])
        with self.assertRaises(Denied):
            self.publish(plan, expected_base=self.remote.refs["main"])
        self.assertEqual(self.remote.writes(), [])

    def test_tampered_or_unapproved_input_does_not_contact_github(self):
        root, digest = self.build(0)
        with self.assertRaises(Denied):
            publish.publish_projection(TARGET, root, digest)
        (root / "inventory.json").write_bytes(b"{}\n")
        with self.assertRaises(publish.HubError):
            self.publish((root, digest))
        self.assertEqual(self.remote.calls, [])
        with self.assertRaises(publish.HubError):
            publish.probe("https://fixture-owner/memory-fixture")

    def test_first_publish_creates_exact_tree_and_replays_without_writes(self):
        plan = self.build(1)
        result = self.publish(plan)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["private"])
        sha = result["commit_sha"]
        self.assertEqual(sha, self.remote.refs["main"])
        self.assertEqual(publish.probe(TARGET)["base_commit"], sha)
        contents = self.remote.trees[self.remote.commits[sha]["tree"]["sha"]]["tree"]
        self.assertEqual({item["path"]: item["sha"] for item in contents if item["type"] == "blob"},
                         {path.relative_to(plan[0]).as_posix(): publish.blob_id(path.read_bytes())
                          for path in plan[0].rglob("*") if path.is_file()})
        writes = self.remote.writes()
        self.assertEqual(self.publish(plan)["outcome"], "unchanged")
        self.assertEqual(self.remote.writes(), writes)

    def test_bootstrap_partial_retry_is_digest_bound(self):
        first = self.build(0)
        self.remote.reject = ("POST", BASE + "/git/blobs")
        blocked = self.publish(first)
        self.assertEqual((blocked["status"], blocked["verified_step"]), ("partial", "bootstrap"))
        self.assertEqual(blocked["commit_sha"], self.remote.refs["main"])
        with self.assertRaises(Conflict):
            self.publish(self.build(1))
        self.remote.reject = None
        self.assertEqual(self.publish(first)["status"], "completed")
        self.assertEqual(self.remote.writes().count(("PUT", BASE + "/contents/projection.json")), 1)

    def test_changes_require_approved_remote_baseline_and_keep_fast_forward(self):
        first = self.publish(self.build(0))
        new = self.build(1)
        writes = self.remote.writes()
        with self.assertRaises(Conflict):
            self.publish(new)
        with self.assertRaises(Conflict):
            self.publish(new, expected_base="b" * 40)
        self.assertEqual(self.remote.writes(), writes)
        result = self.publish(new, expected_base=first["commit_sha"])
        self.assertNotEqual(result["commit_sha"], first["commit_sha"])
        self.assertEqual(self.remote.commits[result["commit_sha"]]["parents"], [{"sha": first["commit_sha"]}])
        writes = self.remote.writes()
        self.assertEqual(self.publish(new, expected_base=first["commit_sha"])["outcome"], "unchanged")
        self.assertEqual(self.remote.writes(), writes)

    def test_pr_only_never_bootstraps_and_partial_pr_retry_does_not_republish(self):
        first = self.build(0)
        with self.assertRaises(Denied):
            self.publish(first, pull_request=True)
        self.assertEqual(self.remote.writes(), [])
        base = self.publish(first)["commit_sha"]
        plan = self.build(1)
        self.remote.reject = ("POST", BASE + "/pulls")
        partial = self.publish(plan, pull_request=True, expected_base=base)
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["commit_sha"], self.remote.refs[partial["branch"]])
        self.remote.reject = None
        recovered = self.publish(plan, pull_request=True, expected_base=base)
        self.assertEqual(self.remote.refs["main"], base)
        self.assertEqual(recovered["pull_request"]["number"], 1)
        self.assertEqual(recovered["commit_sha"], partial["commit_sha"])
        writes = self.remote.writes()
        self.assertEqual(self.publish(plan, pull_request=True, expected_base=base), recovered)
        self.assertEqual(self.remote.writes(), writes)

    def test_unsafe_ancestor_is_rejected_even_below_validated_head(self):
        baseline = self.publish(self.build(0))
        sha = baseline["commit_sha"]
        tree = self.remote.commits[sha]["tree"]["sha"]
        forbidden = self.remote.add_blob(b"Synthetic content placed under an unapproved path")
        contaminated = self.remote.add_tree([{"path": "index.sqlite", "mode": "100644", "type": "blob",
                                              "sha": forbidden}])
        ancestor = self.remote.add_commit(publish.PUBLICATION + baseline["digest"], contaminated, [sha])
        tip = self.remote.add_commit(publish.PUBLICATION + baseline["digest"], tree, [ancestor])
        self.remote.refs["main"] = tip
        writes = self.remote.writes()
        with self.assertRaises(Denied):
            self.publish(self.build(1), expected_base=tip)
        self.assertEqual(self.remote.writes(), writes)
        self.assertNotIn(("GET", BASE + f"/git/blobs/{forbidden}", None), self.remote.calls)

    def test_default_pr_merge_keeps_verifiable_projection_history(self):
        base = self.publish(self.build(0))["commit_sha"]
        change = self.publish(self.build(1), pull_request=True, expected_base=base)
        preview_commit = change["commit_sha"]
        tree = self.remote.commits[preview_commit]["tree"]["sha"]
        merge_message = f"Merge pull request #1 from {OWNER}/{change['branch']}\n\n"
        merge_message += publish.PUBLICATION + change["digest"]
        merged = self.remote.add_commit(merge_message, tree, [base, preview_commit])
        self.remote.refs["main"] = merged
        self.assertEqual(self.publish(self.build(2), expected_base=merged)["status"], "completed")

    def test_ref_failure_reports_prepared_commit_without_claiming_publication(self):
        base = self.publish(self.build(0))["commit_sha"]
        plan = self.build(1)
        self.remote.reject = ("PATCH", BASE + "/git/refs/heads/main")
        receipt = self.publish(plan, expected_base=base)
        self.assertEqual(receipt["status"], "partial")
        self.assertIsNone(receipt["private"])
        self.assertEqual(receipt["verified_step"], "prepared_commit")
        self.assertIn(receipt["candidate_commit_sha"], self.remote.commits)
        self.assertNotIn("commit_sha", receipt)
        self.assertEqual(self.remote.refs["main"], base)


REAL_GITHUB = publish.GitHub


class GitHubInvocationTests(unittest.TestCase):
    def test_cli_uses_verified_host_and_stdin_without_showing_credentials(self):
        response = subprocess.CompletedProcess(args=[], returncode=0, stdout=b'{"private":true}', stderr=b"")
        with (patch.object(publish.shutil, "which", return_value="mock-gh.exe"),
              patch.object(publish.subprocess, "run", return_value=response) as command,
              patch.dict(os.environ, {"GH_DEBUG": "api"})):
            self.assertEqual(publish.GitHub().request("user/repos", "POST", {"private": True}), {"private": True})
        args, kwargs = command.call_args
        self.assertEqual(args[0][-2:], ["--input", "-"])
        self.assertIn("github.com", args[0])
        self.assertEqual(json.loads(kwargs["input"]), {"private": True})
        self.assertNotIn("GH_DEBUG", kwargs["env"])
        self.assertFalse(kwargs.get("shell", False))

    def test_server_errors_do_not_print_untrusted_payload(self):
        response = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"server returned synthetic sensitive material",
            stderr=b"gh: synthetic sensitive material (HTTP 403)",
        )
        with (patch.object(publish.shutil, "which", return_value="mock-gh.exe"),
              patch.object(publish.subprocess, "run", return_value=response)):
            with self.assertRaisesRegex(publish.GitHubError, r"^GitHub POST request failed \(HTTP 403\)$"):
                publish.GitHub().request("user/repos", "POST", {"private": True})
