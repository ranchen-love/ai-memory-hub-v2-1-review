import base64
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_memory_hub import github_publish as publish, projection
from ai_memory_hub.model import Conflict, Denied


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
                    return objects[resource.removeprefix(prefix)]
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
        data = {"README.md": projection.README, "inventory.json": projection.encoded({
            "format": projection.FORMAT, "kind": "aggregate_inventory",
            "counts": {"session": number, "asset": 0, "project": 0, "memory": 0},
        })}
        data["projection.json"] = projection.encoded({
            "format": projection.FORMAT, "kind": "git_projection", "files": projection.declared_files(data),
        })
        for name, contents in data.items():
            (root / name).write_bytes(contents)
        return root, hashlib.sha256(data["projection.json"]).hexdigest()

    def publish(self, plan, **options):
        return publish.publish_projection(TARGET, *plan, consent=True, **options)

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
        self.assertEqual({item["path"]: item["sha"] for item in contents},
                         {path.name: publish.blob_id(path.read_bytes()) for path in plan[0].iterdir()})
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
