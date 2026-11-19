"""Publish an individually approved projection through an existing GitHub CLI session."""

import base64
import binascii
import hashlib
import os
import re
import shutil
import subprocess
from urllib.parse import quote, urlencode

from .model import Conflict, Denied, HubError, Missing, canonical, no_credentials, strict_json
from .projection import CLASSES, MANIFEST, MAX_FILE, verify_projection, verify_projection_files

OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
REF = re.compile(r"[A-Za-z0-9._/-]{1,200}")
BOOTSTRAP = "AI Memory Hub projection bootstrap "
PUBLICATION = "AI Memory Hub projection "
MAX_HISTORY = 96


class GitHubError(HubError):
    code = "remote_error"

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status
        if status in (401, 403):
            self.code = "permission_denied"
        elif status in (409, 422):
            self.code = "conflict"


def target_name(value):
    if not isinstance(value, str):
        raise HubError("GitHub destination must be an explicit owner/repository")
    owner, _, name = value.partition("/")
    if not OWNER.fullmatch(owner) or not NAME.fullmatch(name) or name in (".", "..") or name.endswith("."):
        raise HubError("GitHub destination must be an explicit owner/repository")
    no_credentials(value)
    return owner, name


def object_id(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise GitHubError("GitHub did not return a valid Git object ID")
    return value


def branch_name(value):
    if (not isinstance(value, str) or not REF.fullmatch(value)
            or ".." in value or any(
                not part or part.startswith(".") or part.endswith((".", ".lock")) for part in value.split("/"))):
        raise GitHubError("GitHub returned an unsupported default branch name")
    return value


def blob_id(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data, usedforsecurity=False).hexdigest()


def b64(data):
    return base64.b64encode(data).decode("ascii")


def record(value):
    if not isinstance(value, dict):
        raise GitHubError("GitHub response is missing required result metadata")
    return value


def array(value):
    if not isinstance(value, list):
        raise GitHubError("GitHub response is missing required result metadata")
    return value


class GitHub:
    def __init__(self):
        self.cli = shutil.which("gh")
        if self.cli is None or (os.name == "nt" and not self.cli.lower().endswith(".exe")):
            raise Denied("GitHub CLI (gh) is unavailable. Authenticate gh on github.com or use manual setup")

    def request(self, endpoint, method="GET", body=None, *, missing=()):
        args = [self.cli, "api", "--hostname", "github.com", "--method", method,
                "--header", "Accept: application/vnd.github+json", endpoint]
        env = os.environ.copy()
        env.pop("GH_DEBUG", None)
        env.pop("GH_FORCE_TTY", None)
        env.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", NO_COLOR="1")
        body_bytes = None
        if body is not None:
            args.extend(("--input", "-"))
            body_bytes = canonical(body).encode("utf-8")
        try:
            result = subprocess.run(args, input=body_bytes, capture_output=True, env=env, timeout=45, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubError("GitHub CLI request failed or timed out") from exc
        if result.returncode:
            status_match = re.search(rb"\(HTTP (\d{3})\)", result.stderr)
            status = int(status_match[1]) if status_match else None
            if status in missing:
                return None
            if endpoint == "user" and status is None:
                raise Denied("GitHub authentication could not be verified. Check gh auth status for github.com")
            label = f" (HTTP {status})" if status else ""
            raise GitHubError(f"GitHub {method} request failed{label}", status)
        try:
            return strict_json(result.stdout.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise GitHubError("GitHub CLI returned an invalid JSON response") from exc


def verify_owner(api, owner):
    actor = record(api.request("user")).get("login")
    if not isinstance(actor, str) or not OWNER.fullmatch(actor):
        raise GitHubError("GitHub did not verify the authenticated account")
    if actor.casefold() != owner.casefold():
        raise Denied("the destination owner must be the authenticated personal GitHub account")
    return actor


class Repository:
    def __init__(self, api, owner, name):
        self.api = api
        self.target = f"{owner}/{name}"
        self.id = None
        self.base = None
        self.git_commits = {}
        self.git_trees = {}
        self.git_blobs = {}
        self.history = {}

    def request(self, endpoint, method="GET", body=None, *, missing=()):
        return self.api.request(f"repos/{self.target}{endpoint}", method, body, missing=missing)

    def private(self, *, missing=False, require_push=True):
        remote = self.request("", missing=(404,) if missing else ())
        if remote is None:
            return False
        remote = record(remote)
        full_name = remote.get("full_name")
        owner = record(remote.get("owner"))
        if (not isinstance(full_name, str) or full_name.casefold() != self.target.casefold()
                or owner.get("type") != "User" or not isinstance(owner.get("login"), str)
                or owner["login"].casefold() != self.target.split("/")[0].casefold()):
            raise Denied("GitHub did not verify the exact personal repository destination")
        if remote.get("private") is not True or remote.get("visibility") != "private":
            raise Denied("publish and setup require an independently verified Private repository")
        if remote.get("fork") is not False or remote.get("archived") is not False or remote.get("disabled") is True:
            raise Denied("the destination must be an active, standalone repository")
        repo_id = remote.get("id")
        if type(repo_id) is not int or repo_id <= 0:
            raise GitHubError("GitHub did not verify the repository identity")
        base = branch_name(remote.get("default_branch"))
        if self.id is not None and (repo_id, base) != (self.id, self.base):
            raise Conflict("the remote repository identity or default branch changed")
        self.id, self.base = repo_id, base
        permissions = remote.get("permissions")
        push = isinstance(permissions, dict) and permissions.get("push") is True
        if require_push and not push:
            raise Denied("GitHub did not report write permission for the Private repository")
        return {"id": repo_id, "push": push, "default_branch": base}

    def receipt(self):
        return {"target": self.target, "repository_id": self.id, "private": True,
                "url": f"https://github.com/{self.target}", "default_branch": self.base}

    def ref(self, branch):
        result = self.request("/git/ref/heads/" + quote(branch, safe="/"), missing=(404, 409))
        if result is None:
            return None
        return self.ref_result(result, branch)

    @staticmethod
    def ref_result(result, branch):
        result = record(result)
        target = record(result.get("object"))
        if result.get("ref") != f"refs/heads/{branch}" or target.get("type") != "commit":
            raise GitHubError("GitHub did not verify the requested branch reference")
        return object_id(target.get("sha"))

    def commit(self, sha):
        if sha not in self.git_commits:
            data = record(self.request(f"/git/commits/{sha}"))
            if data.get("sha") != sha:
                raise GitHubError("GitHub commit identity does not match the requested SHA")
            message = data.get("message")
            if not isinstance(message, str) or len(message) > 1000:
                raise Denied("destination history contains a commit outside the projection protocol")
            tree = object_id(record(data.get("tree")).get("sha"))
            parents = tuple(object_id(record(parent).get("sha")) for parent in array(data.get("parents")))
            self.git_commits[sha] = (message.rstrip("\n"), tree, parents)
        return self.git_commits[sha]

    def tree(self, sha):
        if sha not in self.git_trees:
            data = record(self.request(f"/git/trees/{sha}"))
            if data.get("sha") != sha or data.get("truncated") is not False:
                raise GitHubError("GitHub did not verify a complete requested Git tree")
            entries = {}
            for item in array(data.get("tree")):
                item = record(item)
                path = item.get("path")
                size = item.get("size")
                if (not isinstance(path, str) or path not in CLASSES or path in entries
                        or item.get("mode") != "100644" or item.get("type") != "blob"
                        or type(size) is not int or not 0 < size <= MAX_FILE):
                    raise Denied("destination history contains a path outside the projection allowlist")
                entries[path] = (object_id(item.get("sha")), size)
            self.git_trees[sha] = entries
        return self.git_trees[sha]

    def blob(self, sha, size):
        if sha not in self.git_blobs:
            result = record(self.request(f"/git/blobs/{sha}"))
            content = result.get("content")
            if (result.get("sha") != sha or result.get("encoding") != "base64"
                    or result.get("size") != size or not isinstance(content, str)
                    or len(content) > 2 * MAX_FILE):
                raise GitHubError("GitHub did not verify the requested Git blob")
            try:
                data = base64.b64decode("".join(content.split()), validate=True)
            except (ValueError, binascii.Error) as exc:
                raise GitHubError("GitHub returned invalid Git blob bytes") from exc
            if len(data) != size or blob_id(data) != sha:
                raise GitHubError("GitHub blob bytes failed Git object verification")
            self.git_blobs[sha] = data
        data = self.git_blobs[sha]
        if len(data) != size:
            raise GitHubError("GitHub tree size is inconsistent with a verified Git blob")
        return data

    def audit(self, head):
        return self._audit(head, set())

    def _audit(self, commit, visiting):
        if commit in self.history:
            return self.history[commit]
        if commit in visiting or len(visiting) + len(self.history) >= MAX_HISTORY:
            raise Denied("destination history exceeds the bounded projection audit")
        visiting.add(commit)
        message, tree, parents = self.commit(commit)
        bootstrap = re.fullmatch(re.escape(BOOTSTRAP) + r"([0-9a-f]{64})", message)
        published = re.fullmatch(re.escape(PUBLICATION) + r"([0-9a-f]{64})", message)
        merge = re.fullmatch(
            r"Merge pull request #[1-9][0-9]* from " + re.escape(self.target.split("/")[0])
            + r"/hub-review-[0-9a-f]{64}-[0-9a-f]{12}(?:\n\n" + re.escape(PUBLICATION) + r"[0-9a-f]{64})?",
            message, re.IGNORECASE,
        )
        if bootstrap and not parents:
            entries = self.tree(tree)
            if set(entries) != {MANIFEST} or hashlib.sha256(self.blob(*entries[MANIFEST])).hexdigest() != bootstrap[1]:
                raise Denied("GitHub bootstrap tree does not match its projection receipt")
            result = (bootstrap[1], tree, commit, True)
        elif published and len(parents) == 1:
            previous = self._audit(parents[0], visiting)
            if previous[3] and previous[0] != published[1]:
                raise Denied("the first complete projection does not match its approved bootstrap")
            files = {path: self.blob(*entry) for path, entry in self.tree(tree).items()}
            try:
                verify_projection_files(files, published[1])
            except (ValueError, RecursionError) as exc:
                raise Denied("destination history contains an invalid projection tree") from exc
            result = (published[1], tree, previous[2], False)
        elif merge and len(parents) == 2:
            left, right = (self._audit(parent, visiting) for parent in parents)
            if left[3] or right[3] or left[2] != right[2] or tree not in (left[1], right[1]):
                raise Denied("destination merge combines unknown or modified project history")
            result = left if tree == left[1] else right
        else:
            raise Denied("destination history was not created by the Hub projection protocol")
        visiting.remove(commit)
        self.history[commit] = result
        return result

    def seed(self, digest, contents):
        branches = self.request("/branches?per_page=1")
        if array(branches):
            raise Conflict("the default branch is missing, but the destination is not empty")
        self.private()
        result = record(self.request("/contents/" + MANIFEST, "PUT", {
            "content": b64(contents), "message": BOOTSTRAP + digest,
        }))
        sha = object_id(record(result.get("commit")).get("sha"))
        if record(result.get("content")).get("sha") != blob_id(contents) or self.ref(self.base) != sha:
            raise Conflict("GitHub did not verify the initial approved projection manifest")
        if self.audit(sha)[0] != digest:
            raise Conflict("GitHub initial projection differs from the approved digest")
        return sha

    def publish(self, files, digest, parent):
        self.private()
        expected = {path: (blob_id(data), len(data)) for path, data in files.items()}
        entries = []
        for path, data in sorted(files.items()):
            response = record(self.request("/git/blobs", "POST", {"content": b64(data), "encoding": "base64"}))
            sha = object_id(response.get("sha"))
            if expected[path][0] != sha:
                raise Conflict("GitHub stored a blob different from the approved bytes")
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
        tree = object_id(record(self.request("/git/trees", "POST", {"tree": entries})).get("sha"))
        if self.tree(tree) != expected:
            raise Conflict("GitHub tree differs from the exact approved projection")
        result = record(self.request("/git/commits", "POST", {
            "message": PUBLICATION + digest, "tree": tree, "parents": [parent],
        }))
        sha = object_id(result.get("sha"))
        if self.commit(sha) != (PUBLICATION + digest, tree, (parent,)):
            raise Conflict("GitHub commit does not match the approved tree and baseline")
        return sha

    def advance(self, branch, sha, before):
        self.private()
        if self.ref(self.base) != before:
            raise Conflict("default branch changed after review, inspect it before retrying")
        if branch == self.base:
            result = self.request("/git/refs/heads/" + quote(branch, safe="/"), "PATCH", {"sha": sha, "force": False})
        else:
            result = self.request("/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": sha})
        if self.ref_result(result, branch) != sha or self.ref(branch) != sha:
            raise Conflict("GitHub did not verify the requested branch update")
        self.private()

    def draft(self, branch, sha, digest, before):
        self.private()
        if self.ref(self.base) != before or self.ref(branch) != sha:
            raise Conflict("the default branch or review branch changed before PR creation")
        query = urlencode({"state": "open", "head": f"{self.target.split('/')[0]}:{branch}", "base": self.base})
        existing = array(self.request("/pulls?" + query))
        if len(existing) > 1:
            raise Conflict("more than one open pull request matches this approved projection")
        if existing:
            result = record(existing[0])
        else:
            result = record(self.request("/pulls", "POST", {
                "head": branch, "base": self.base, "title": PUBLICATION + digest, "draft": True,
                "body": "Reviewed AI Memory Hub Git projection.",
            }))
        number = result.get("number")
        if type(number) is not int or number <= 0:
            raise GitHubError("GitHub did not return a valid pull request ID")
        pr = record(self.request(f"/pulls/{number}"))
        head, base = record(pr.get("head")), record(pr.get("base"))
        base_repo, head_repo = record(base.get("repo")), record(head.get("repo"))
        if (pr.get("number") != number or pr.get("state") != "open" or type(pr.get("draft")) is not bool
                or head.get("ref") != branch or head.get("sha") != sha or base.get("ref") != self.base
                or base.get("sha") != before or base_repo.get("id") != self.id or head_repo.get("id") != self.id):
            raise Conflict("GitHub did not verify the pull request destination and approved commit")
        self.private()
        return {"number": number, "url": f"https://github.com/{self.target}/pull/{number}", "draft": pr["draft"]}


def probe(target):
    owner, name = target_name(target)
    try:
        api = GitHub()
        actor = verify_owner(api, owner)
        repository = Repository(api, actor, name)
        remote = repository.private(missing=True, require_push=False)
        if remote:
            result = {**repository.receipt(), "authenticated_as": actor, "exists": True,
                      "creation_permission": "not_requested", "push_permission": "reported" if remote["push"] else "denied"}
            if not remote["push"]:
                return {**result, "status": "blocked", "reason": "GitHub did not report repository write permission"}
            return {**result, "status": "completed", "base_commit": repository.ref(repository.base)}
        return {"status": "completed", "authenticated_as": actor, "target": repository.target,
                "exists": "not_visible", "creation_permission": "not_verified", "push_permission": "not_verified"}
    except HubError as exc:
        return {"status": "blocked", "target": f"{owner}/{name}", "reason": str(exc), "code": exc.code}


def create_private(target, *, consent=False):
    if consent is not True:
        raise Denied("creating a new Private GitHub repository requires explicit destination consent")
    owner, name = target_name(target)
    api = GitHub()
    repository = Repository(api, verify_owner(api, owner), name)
    if repository.private(missing=True):
        return {**repository.receipt(), "status": "completed", "outcome": "existing", "created": False}
    response = record(api.request("user/repos", "POST", {"name": name, "private": True, "auto_init": False}))
    repository.private()
    if (response.get("id") != repository.id or response.get("private") is not True
            or response.get("visibility") != "private"):
        raise Conflict("GitHub creation response did not match the independently verified Private repository")
    return {**repository.receipt(), "status": "completed", "outcome": "created", "created": True}


def publish_projection(target, projection_path, digest, *, consent=False, pull_request=False, expected_base=None):
    if consent is not True:
        raise Denied("publication requires explicit consent for this destination, digest and Git action")
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        raise HubError("publication needs the approved SHA-256 projection digest")
    if expected_base is not None and (not isinstance(expected_base, str) or not SHA.fullmatch(expected_base)):
        raise HubError("approved remote baseline must be a full 40-character Git commit SHA")
    owner, name = target_name(target)
    files = verify_projection(projection_path, digest)
    if any(path not in CLASSES or not 0 < len(data) <= MAX_FILE for path, data in files.items()):
        raise Denied("the projection exceeds the GitHub publication allowlist or file size limit")
    api = GitHub()
    repository = Repository(api, verify_owner(api, owner), name)
    if not repository.private(missing=True):
        raise Missing("approved Private repository is unavailable, verify gh access or create it first")
    head = repository.ref(repository.base)
    details = {**repository.receipt(), "digest": digest, "approved_action": "pull_request" if pull_request else "direct"}
    return publish_on_baseline(repository, files, digest, head, details, pull_request, expected_base)


def publish_on_baseline(repository, files, digest, head, details, pull_request, expected_base):
    progress = None
    try:
        if head is None:
            if pull_request:
                raise Denied("a pull request needs a complete baseline, separately approve a direct first publication")
            if expected_base is not None:
                raise Conflict("the reviewed default branch is no longer available")
            head = repository.seed(digest, files[MANIFEST])
        previous_digest, _, _, bootstrap = repository.audit(head)
        if bootstrap:
            if pull_request or previous_digest != digest or expected_base not in (None, head):
                raise Conflict("finish the initial direct publication with its original approved digest")
            progress = {"branch": repository.base, "commit_sha": head, "verified_step": "bootstrap"}
        elif previous_digest == digest:
            repository.private()
            if repository.ref(repository.base) != head:
                raise Conflict("default branch changed while checking the current projection")
            return {**details, "status": "completed", "outcome": "unchanged", "branch": repository.base,
                    "commit_sha": head, "pull_request": None}
        elif expected_base != head:
            raise Conflict("review the current default branch commit and approve it with --base-sha")
        extra_commits = 2 if pull_request else 1
        if len(repository.history) + extra_commits > MAX_HISTORY:
            raise Denied("the approved change would exceed the supported remote history audit")
        branch = f"hub-review-{digest}-{head[:12]}" if pull_request else repository.base
        review_head = repository.ref(branch) if pull_request else None
        if review_head:
            if repository.audit(review_head)[0] != digest or repository.commit(review_head)[2] != (head,):
                raise Conflict("the existing review branch does not match the approved digest and baseline")
            commit = review_head
        else:
            commit = repository.publish(files, digest, head)
            progress = {**(progress or {"verified_step": "prepared_commit"}), "candidate_commit_sha": commit}
            repository.advance(branch, commit, head)
        progress = {"branch": branch, "commit_sha": commit, "verified_step": "published_branch"}
        pr = repository.draft(branch, commit, digest, head) if pull_request else None
        return {**details, **progress, "status": "completed", "outcome": "published", "pull_request": pr}
    except HubError as exc:
        if progress is None:
            raise
        return {**details, **progress, "status": "partial", "private": None, "private_verified_at_start": True,
                "code": exc.code, "reason": str(exc),
                "retry": "retry the same approved publication after verifying remote state"}
