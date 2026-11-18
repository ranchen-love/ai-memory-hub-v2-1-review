"""Exercise the documented workflow exclusively with synthetic inputs."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(scratch):
    vault = scratch / "vault"
    cli = [sys.executable, "-m", "ai_memory_hub", "--root", str(vault)]

    def call(*arguments, code=0, stdin=None):
        proc = subprocess.run([*cli, *arguments], cwd=ROOT, input=stdin, text=True, capture_output=True)
        if proc.returncode != code:
            raise RuntimeError(f"unexpected exit for {arguments[:3]}: {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        return json.loads(proc.stderr if code == 2 else proc.stdout)

    assert call("init", "--wizard", stdin="\n")["switches"] == {
        "weekly": True, "full": True, "daily": False, "event": False, "handoff": False,
    }
    weekly = call("sync", "weekly")
    assert weekly["status"] == "governance_only" and weekly["archive"]["status"] == "not_configured"
    assert weekly["governance"]["status"] == "completed"
    assert call("sync", "daily", code=2)["code"] == "permission_denied"
    assert call("handoff", "--project", "greenhouse-demo", "--consent", code=2)["code"] == "permission_denied"

    assert call("source", "grant", "demo", "codex_workspace", "--path", "examples", "--consent")["status"] == "granted"
    result = call("sync", "full")
    assert result["status"] == "completed" and result["created"] == 4
    assert call("sync", "full")["unchanged"] == 4
    assert call("session", "list", "--project", "greenhouse-demo")["records"][0]["id"] == "calibration-session"
    for layer, field in (("L0", "title"), ("L1", "summary"), ("L2", "checkpoint")):
        assert call("session", "show", "calibration-session", "--layer", layer)[field]
    assert call("asset", "refs", "calibration-notes")["references"]

    source = scratch / "user-upload.txt"
    original = (ROOT / "examples/checklist.txt").read_bytes()
    source.write_bytes(original)
    command = ("asset", "add", "--id", "user-upload", "--file", str(source), "--project", "greenhouse-demo",
               "--session", "calibration-session", "--origin", "user_upload", "--evidence", "synthetic:uploaded", "--consent")
    assert call(*command)["revision"] == 1
    assert call(*command)["status"] == "unchanged"
    assert len(list((vault / "blobs").iterdir())) == 1
    source.write_bytes(b"synthetic second file revision\n")
    assert call(*command, "--base", "1")["revision"] == 2
    assert call("asset", "check", "user-upload", "--version", "1")["data"]["sha256"] == hashlib.sha256(original).hexdigest()
    retrieved = Path(call("asset", "copy", "user-upload", "--version", "1", "--consent")["path"])
    assert retrieved.read_bytes() == original

    event = ("sync", "event", "--source", "demo", "--event", "checkpoint-event.json", "--consent")
    assert call(*event, code=2)["code"] == "permission_denied"
    assert call("config", "set", "event", "on")["switches"]["event"]
    assert call(*event)["revision"] == 2
    assert call(*event)["status"] == "unchanged"
    assert call("config", "set", "event", "off")["switches"]["daily"] is False
    assert call("config", "set", "full", "off")["switches"]["full"] is False
    assert call("config", "set", "daily", "on")["switches"]["handoff"] is False
    assert call("sync", "full", code=2)["code"] == "permission_denied"
    assert call("sync", "daily")["unchanged"] == 4
    assert call("config", "set", "handoff", "on")["switches"]["weekly"]
    path = Path(call("handoff", "--project", "greenhouse-demo", "--consent")["path"])
    handoff = json.loads(path.read_text(encoding="utf-8"))
    assert handoff["sessions"][0]["checkpoint_sources"][-1]["revision"] == 2
    assert handoff["sessions"][0]["checkpoint"]["next_actions"]
    assert "messages" not in handoff["sessions"][0]
    assert {item["id"] for item in handoff["files"]} >= {"user-upload", "calibration-notes"}
    assert call("sync", "weekly")["archive"]["status"] == "completed"
    final = call("sync", "status")
    assert final["settings"]["scheduler"] == "not_verified"
    assert final["last_governance_success"]["weekly"]
    assert final["last_archive_success"]["weekly"]
    assert not final["pending"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="memory-hub-smoke-") as temp:
        smoke(Path(temp).resolve())
    print("PASS: wizard, five independent switches, synthetic import, L0–L2, both asset origins, version/retrieval/deduplication, project handoff and weekly coverage")
