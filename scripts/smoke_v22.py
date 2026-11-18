"""Exercise both sides of a local deployment with only synthetic data."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(vault, *args, code=0):
    command = [sys.executable, "-m", "ai_memory_hub", "--root", str(vault), *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != code:
        raise RuntimeError(f"{args[:4]} returned {result.returncode}\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stderr if code == 2 else result.stdout)


def save(file, value):
    file.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")


def share(result, transport):
    target = transport / Path(result["path"]).name
    shutil.copyfile(result["path"], target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest()
    return target


def verify(scratch):
    sender = scratch / "producer-vault"
    receiver = scratch / "recipient-vault"
    staging = scratch / "approved-input"
    transport = scratch / "approved-transfer"
    staging.mkdir()
    transport.mkdir()
    for vault in (sender, receiver):
        settings = cli(vault, "init")
        assert settings["switches"] == {"weekly": True, "full": True, "event": False, "daily": False, "handoff": False}
    initial = cli(sender, "local", "status")
    assert not initial["sources"] and not initial["last_archive_success"]
    no_source = cli(sender, "sync", "full", code=1)
    assert no_source["archive"]["status"] == "not_configured"
    print("PASS: independent Vaults, ordinary defaults and truthful no-source outcome", flush=True)

    upload = staging / "sample.pdf"
    generated = staging / "agent-output.xlsx"
    upload_v1 = b"%PDF-1.4 synthetic user upload revision 1"
    upload_v2 = b"%PDF-1.4 synthetic user upload revision 2"
    generated.write_bytes(b"synthetic AI-generated workbook bytes")
    session = json.loads((ROOT / "examples/session.json").read_text(encoding="utf-8"))
    session["data"]["checkpoint"]["file_refs"] = [{"asset_id": "agent-output", "version": 1}]
    project = json.loads((ROOT / "examples/project.json").read_text(encoding="utf-8"))
    project["data"]["file_refs"] = []
    save(staging / "session.json", session)
    save(staging / "project.json", project)
    save(staging / "memory-hub.json", {"schema_version":"2.1","items":[
        {"key":"agent","kind":"file","path":generated.name,"asset_id":"agent-output",
         "origin":"ai_generated","project_id":"greenhouse-demo","session_id":"calibration-session"},
        {"key":"upload","kind":"file","path":upload.name,"asset_id":"user-upload",
         "origin":"user_upload","project_id":"greenhouse-demo","session_id":"calibration-session"},
        {"key":"project","kind":"record","path":"project.json"},
        {"key":"session","kind":"record","path":"session.json"},
    ]})
    assert cli(sender, "source", "grant", "selected", "local_checkpoint", "--path", str(staging), "--consent")["status"] == "granted"
    run = ("local", "run", "--source", "selected")
    first = cli(sender,*run,code=1)
    assert first["archive"]["status"] == "partial" and first["created"] == 3
    assert first["errors"][0]["code"] == "missing"
    upload.write_bytes(upload_v1)
    resumed = cli(sender,*run)
    assert (resumed["created"],resumed["unchanged"]) == (1,3)
    assert cli(sender,*run)["unchanged"] == 4
    assert cli(sender,"local","status")["sources"][0]["last_archive_success"]
    week=cli(sender,*run,"--mode","weekly")
    assert week["governance"]["status"] == "not_run" and week["execution"]["scheduler"] == "not_verified"
    print("PASS: scoped archive, partial import, source recovery, receipts and separate cloud governance", flush=True)

    raw = {**session,"base_revision":1,"source": {
        "provider":"synthetic","kind":"observed_messages","locator":"demo:observed"},
        "data":{"title":"Synthetic raw checkpoint","messages":[{"id":"line-1","role":"user",
                                                             "text":"SYNTHETIC DO NOT TRANSFER"}]}}
    save(staging / "explicit-raw.json",raw)
    import_raw = ("import","--input",str(staging/"explicit-raw.json"),"--consent")
    assert cli(sender,*import_raw,code=2)["code"] == "permission_denied"
    assert cli(sender,*import_raw,"--allow-raw")["revision"] == 2
    delta = {**session,"base_revision":2,"data":{"title":"Synthetic progress","append":{
        "verification":["Checked synthetic output"],"file_refs":[{"asset_id":"user-upload","version":1}]}}}
    save(staging/"session.json",delta)
    upload.write_bytes(upload_v2)
    updated = cli(sender,*run)
    assert updated["updated"] == 2 and cli(sender,*run)["unchanged"] == 4
    view = ("session","show","calibration-session")
    assert cli(sender,*view,"--layer","L0")["title"] == "Synthetic progress"
    assert cli(sender,*view,"--layer","L1")["summary"]
    assert cli(sender,*view,"--layer","L2")["checkpoint"]["verification"][-1] == "Checked synthetic output"
    assert cli(sender,*view,"--layer","L3","--consent")["raw_revision"] == 2
    assert cli(sender,"asset","check","user-upload","--version","1")["data"]["sha256"] == hashlib.sha256(upload_v1).hexdigest()
    assert len(list((sender/"blobs").iterdir())) == 3
    upload.unlink()
    assert cli(sender,*run,code=1)["errors"][0]["code"] == "missing"
    assert cli(sender,"asset","check","user-upload")["availability"]["status"] == "available"
    upload.write_bytes(upload_v2)
    assert cli(sender,*run)["unchanged"] == 4
    print("PASS: L0–L3, L2 checkpoint increment, both origins, pinned versions and original source disappearance", flush=True)

    pack = ("transfer","pack","--project","greenhouse-demo","--consent")
    assert cli(sender,*pack,code=2)["code"] == "permission_denied"
    cli(sender,"config","set","handoff","on")
    cli(receiver,"config","set","handoff","on")
    context_only=cli(sender,*pack)
    handoff_path=share(context_only,transport)
    assert cli(receiver,"transfer","receive","--input",str(handoff_path),code=2)["code"] == "permission_denied"
    assert cli(receiver,"transfer","receive","--input",str(handoff_path),"--consent")["status"] == "received"
    received=cli(receiver,"transfer","inspect",context_only["id"],"--consent")["context"]
    assert all(ref["recipient_status"] == "not_transferred" for ref in received["files"])
    assert cli(receiver,"transfer","file",context_only["id"],"user-upload@1","--consent",code=2)["code"] == "permission_denied"
    archive=cli(sender,*pack,"--asset","user-upload@1","--asset","agent-output@1")
    mirrored=share(archive,transport)
    receive = ("transfer","receive","--input",str(mirrored),"--consent")
    assert cli(receiver,*receive)["status"] == "received"
    assert cli(receiver,*receive)["status"] == "unchanged"
    fetched=cli(receiver,"transfer","inspect",archive["id"],"--consent")["context"]
    assert fetched["project"]["data"]["state"] == "active" and fetched["sessions"][0]["checkpoint"]["next_actions"]
    assert "SYNTHETIC DO NOT TRANSFER" not in json.dumps(fetched)
    actual={(item["id"],item["version"]):item["recipient_status"] for item in fetched["files"]}
    assert actual[("user-upload",1)] == actual[("agent-output",1)] == "available"
    assert actual[("user-upload",2)] == "not_transferred"
    for key,expected in (("user-upload@1",upload_v1),("agent-output@1",generated.read_bytes())):
        file = Path(cli(receiver,"transfer","file",archive["id"],key,"--consent")["path"])
        assert file.is_relative_to(receiver) and file.read_bytes() == expected
    print("PASS: recipient grants, default context-only package, selected file SHA-256 and bytes in an independent Vault", flush=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="hub-v22-deployment-") as directory:
        verify(Path(directory).resolve())
