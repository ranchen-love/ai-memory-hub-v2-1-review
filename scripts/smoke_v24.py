"""Exercise the installed V2.4 first-use journey against synthetic fixtures."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


FIXTURES = Path(__file__).resolve().parents[1] / "examples"


def check(base):
    def cli(*args, expected=0):
        reply = subprocess.run(
            [sys.executable, "-I", "-m", "ai_memory_hub", *map(str, args)], cwd=base,
            capture_output=True, encoding="utf-8", timeout=60,
        )
        if reply.returncode != expected:
            raise RuntimeError(f"{args[:3]} exited {reply.returncode}: {reply.stdout}\n{reply.stderr}")
        return json.loads(reply.stderr if expected == 2 else reply.stdout)

    inbox = base / "inbox"
    inbox.mkdir()
    for name in ("memory-hub.json", "session.json", "project.json", "memory.json"):
        shutil.copyfile(FIXTURES / name, inbox / name)
    request = base / "request.json"
    request.write_text(json.dumps({
        "format": "1.0", "workspace": "workspace", "vault": "vault",
        "sources": [{"id": "approved", "adapter": "normalized", "path": "inbox", "authorized": True}],
    }), encoding="utf-8")
    workspace = base / "workspace"
    plan = cli("onboarding", "plan", "--request", request)
    assert not workspace.exists()
    apply = ("onboarding", "apply", "--request", request, "--approve-plan", plan["plan_digest"])
    assert cli(*apply, expected=2)["code"] == "permission_denied"
    first = cli(*apply, "--consent", expected=1)
    assert first["sources"][0]["created"] == 3 and first["sources"][0]["errors"][0]["code"] == "missing"
    shutil.copyfile(FIXTURES / "checklist.txt", inbox / "checklist.txt")
    assert cli(*apply, "--consent")["sources"][0]["created"] == 1
    assert cli(*apply, "--consent")["sources"][0]["unchanged"] == 4
    report_path = workspace / "first-report.md"
    result = cli("onboarding", "report", "--request", request, "--markdown", report_path)
    assert result["data"]["session"][0]["layers"] == {"L0": True, "L1": True, "L2": True, "L3": False}
    assert result["sync"]["scheduler"] == "not_verified" and report_path.is_file()
    for name in ("AGENTS.md", "docs/agent-onboarding.md", "docs/agent-onboarding.zh-CN.md"):
        path = workspace / name
        for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = link.split("#", 1)[0]
            if target and "://" not in target:
                assert (path.parent / target).exists(), (name, target)
    preview = cli("projection", "preview", "--workspace", workspace, "--output", base / "projection")
    assert preview["digest"] and len([path for path in (base / "projection").iterdir() if path.is_dir()]) == 19
    assert not any((base / "projection").rglob("*.sqlite"))
    assert cli("projection", "preview", "--workspace", workspace,
               "--output", workspace / "denied", expected=2)["code"] == "permission_denied"
    review = base / "review.json"
    review.write_text(json.dumps({
        "format": "1.0", "target": "fixture-owner/fixture-repository",
        "items": [{"kind": "session", "id": "second-reading", "purpose": "navigation",
                   "source": {"id": result["data"]["session"][0]["id"], "revision": 1},
                   "data": {"title": "Second reading", "summary": "A specimen needs review."}}],
    }), encoding="utf-8")
    input_args = ("--workspace", workspace, "--input", review)
    approval = cli("projection", "review", *input_args)["review_digest"]
    reviewed = ("projection", "preview", "--workspace", workspace, "--output", base / "reviewed",
                "--review-digest", approval)
    assert cli(*reviewed, expected=2)["code"] == "permission_denied"
    assert cli("projection", "approve", *input_args, "--digest", approval,
               "--confirm-redacted", "--consent")["status"] == "approved"
    assert cli(*reviewed)["status"] == "created"
    index = json.loads((base / "reviewed" / "sessions" / "index.json").read_text(encoding="utf-8"))
    assert index["records"][0]["id"] == "second-reading"
    print("PASS: installed V2.4 plan, isolated Workspace/Vault, retry, report, links and approved modular projection")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="hub-v24-smoke-") as directory:
        check(Path(directory).resolve())
