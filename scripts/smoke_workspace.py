"""Initialize, govern and hand off synthetic data using the packaged CLI."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(base, installed=False):
    workspace = base / "my-workspace"
    vault = base / "separate-vault"
    recipient = base / "recipient-vault"
    prefix = [sys.executable, *(["-I"] if installed else []), "-m", "ai_memory_hub"]

    def cli(*args, expected=0):
        result = subprocess.run(prefix + list(map(str,args)), cwd=base if installed else ROOT,
                                capture_output=True, encoding="utf-8")
        if result.returncode != expected:
            raise RuntimeError(f"{args[:4]} returned {result.returncode}\n{result.stdout}\n{result.stderr}")
        return json.loads(result.stderr if expected == 2 else result.stdout)

    def hub(*args, expected=0):
        return cli("--root", vault, *args, expected=expected)

    if installed:
        script = """import json; from importlib.metadata import distribution; from ai_memory_hub.workspace import get_templates
d=distribution('ai-memory-hub'); p='ai_memory_hub/_workspace/'; t=get_templates()
assert {f.as_posix().removeprefix(p) for f in d.files if f.as_posix().startswith(p)} == set(t['files']+t['demo'])"""
        subprocess.run([sys.executable, "-I", "-c", script], cwd=base, check=True)
    init = cli("workspace", "init", "--path", workspace, "--vault", vault, "--demo")
    assert init["sensitivity"] == "private" and init["demo"] is True
    assert cli("workspace", "init", "--path", workspace, "--vault", vault, expected=2)["code"] == "conflict"
    info = cli("workspace", "check", "--path", workspace)
    assert info["life_archive"]["states"]["unknown"] == 12 and info["template_matches_engine"]
    assert hub("source", "list")["sources"] == []
    manifest = workspace / "demo-inbox"
    assert hub("source", "grant", "sample", "normalized", "--path", manifest, "--consent")["status"] == "granted"
    first = hub("local", "run", "--source", "sample")
    assert first["created"] == 4 and hub("local", "run", "--source", "sample")["unchanged"] == 4
    candidate = json.loads((manifest / "memory.json").read_text(encoding="utf-8"))
    cid = candidate["id"]
    assert hub("memory", "review")["candidates"] == 1
    assert not cli("workspace", "facts", "--path", workspace, "--consent")["facts"]
    candidate["data"].pop("classification")
    candidate["data"]["status"] = "accepted"
    candidate["base_revision"] = 1
    reviewed = workspace / "reviewed.json"
    reviewed.write_text(json.dumps(candidate), encoding="utf-8")
    assert hub("import", "--input", reviewed, "--consent", expected=2)["code"] == "permission_denied"
    assert hub("import", "--input", reviewed, "--review-decision", "--consent")["revision"] == 2
    assert len(hub("memory", "history", cid)["records"]) == 2
    facts = cli("workspace", "facts", "--path", workspace, "--consent")["facts"]
    assert facts[0]["data"]["classification"] == "rule" and facts[0]["revision"] == 2
    assert cli("workspace", "health-check", "--input", manifest / "synthetic.json", "--consent")["observations"] == 1
    assert hub("project", "show", "greenhouse-demo")["data"]["state"] == "active"
    assert hub("session", "show", "calibration-session", "--layer", "L2")["checkpoint"]["next_actions"]
    assert hub("asset", "check", "calibration-notes")["availability"]["status"] == "available"
    assert hub("config", "set", "handoff", "on")["switches"]["handoff"]
    assert hub("handoff", "--project", "greenhouse-demo", "--consent")["sessions"] == 1
    pack = hub("transfer", "pack", "--project", "greenhouse-demo", "--asset", "calibration-notes@1", "--consent")
    cli("--root", recipient, "init")
    cli("--root", recipient, "config", "set", "handoff", "on")
    receipt = cli("--root", recipient, "transfer", "receive", "--input", pack["path"], "--consent")
    actual = cli("--root", recipient, "transfer", "file", receipt["id"], "calibration-notes@1", "--consent")
    assert Path(actual["path"]).read_bytes() == (manifest / "checklist.txt").read_bytes()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true", help="use the installed engine outside the checkout")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hub-v23-onboarding-") as directory:
        check(Path(directory).resolve(), arguments.installed)
    print("PASS: workspace initialization, candidate approval and revision, project checkpoint, file and recipient bytes")
