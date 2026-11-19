import tempfile
import unittest
from pathlib import Path

from ai_memory_hub.candidates import history, step, suggestions
from ai_memory_hub.model import Conflict, Denied, HubError
from ai_memory_hub.store import Store

SOURCE = {"provider": "fixture", "kind": "user_checkpoint", "locator": "fixture:review"}
PR = "https://example.org/team/review/pull/41"


class CandidateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hub-candidate-")
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name).resolve() / "vault", initialize="private")

    def proposal(self, entry_id, claim, *, key="calibration", status="candidate", base=0,
                 classification="fact"):
        value = {"schema_version": "2.1", "kind": "memory", "id": entry_id, "base_revision": base,
                 "sensitivity": "private", "source": SOURCE, "data": {"key": key, "claim": claim,
                 "status": status, "classification": classification}}
        with self.store.transaction(write=True) as db:
            return self.store.ingest(db, value, allow_review=status != "candidate")

    def step(self, entry_id, target, base, *, consent=True, **kwargs):
        return step(self.store, entry_id, target, base=base, actor="reviewer", reason="Synthetic review decision",
                    consent=consent, **kwargs)

    def stage(self, entry_id):
        self.step(entry_id, "validated", 0, record_revision=1)
        return self.step(entry_id, "review", 1)

    def memory(self, name):
        with self.store.transaction() as db:
            return self.store.get(db, "memory", name)

    def test_validates_and_gates_activation_plus_legacy_approval(self):
        self.proposal("governed", "Synthetic fixture")
        with self.assertRaises(Conflict):
            self.step("governed", "approved", 0)
        with self.assertRaises(Conflict):
            self.step("governed", "validated", 0, record_revision=2)
        self.stage("governed")
        with self.assertRaises(Denied):
            self.step("governed", "approved", 2, consent=False, attest=True)
        with self.assertRaises(Denied):
            self.step("governed", "approved", 2)
        self.step("governed", "approved", 2, attest=True)
        self.assertEqual(self.memory("governed")["data"]["status"], "candidate")
        with self.assertRaises(Denied):
            self.proposal("governed", "Synthetic fixture", status="accepted", base=1)
        self.step("governed", "active", 3)
        self.assertEqual(self.memory("governed")["data"]["status"], "accepted")
        self.step("governed", "revoked", 4)
        self.step("governed", "archived", 5)
        self.assertEqual(self.memory("governed")["data"]["status"], "retired")
        result = history(self.store, "governed")
        self.assertEqual([event["state"] for event in result["events"]],
                         ["validated", "review", "approved", "active", "revoked", "archived"])
        self.assertEqual([item["revision"] for item in result["records"]], [1, 2, 3])
        self.proposal("legacy", "Original workflow", key="legacy", status="accepted")
        self.assertEqual(self.memory("legacy")["data"]["status"], "accepted")

    def test_duplicate_and_conflicting_peer_advice_exact_replacement(self):
        self.proposal("original", "Set the synthetic dial to eight", status="accepted")
        self.proposal("duplicate", "Set  the synthetic dial to eight", key="  CALIBRATION ")
        advice = suggestions(self.store, "duplicate")["peers"]
        self.assertEqual(advice[0]["relation"], "duplicate")
        self.stage("duplicate")
        with self.assertRaises(Conflict):
            self.step("duplicate", "approved", 2, attest=True, peers={"original": 1})
        self.step("duplicate", "rejected", 2)
        self.proposal("correction", "Set the synthetic dial to five")
        self.stage("correction")
        self.assertEqual(suggestions(self.store, "correction")["peers"][0]["relation"], "conflict")
        with self.assertRaises(Conflict):
            self.step("correction", "approved", 2, attest=True, peers={"original": 1})
        self.step("correction", "approved", 2, attest=True, peers={"original": 1}, supersede={"original": 1})
        self.step("correction", "active", 3)
        self.assertEqual(self.memory("correction")["data"]["status"], "accepted")
        self.assertEqual(self.memory("original")["data"]["status"], "retired")
        old = history(self.store, "original")["events"][0]
        self.assertEqual((old["state"], old["replacement"]), ("superseded", {"id": "correction", "revision": 2}))

    def test_stale_peer_approval_rolls_back_and_inference_cannot_activate(self):
        self.proposal("old", "Prior accepted content", status="accepted")
        self.proposal("candidate", "Replacement content")
        self.stage("candidate")
        self.step("candidate", "approved", 2, attest=True, peers={"old": 1}, supersede={"old": 1})
        self.proposal("old", "Revised externally", status="accepted", base=1)
        with self.assertRaises(Conflict):
            self.step("candidate", "active", 3)
        self.assertEqual(self.memory("candidate")["revision"], 1)
        self.assertEqual(self.memory("old")["revision"], 2)
        self.proposal("inferred", "Unverified conclusion", key="other", classification="inference")
        self.stage("inferred")
        with self.assertRaises(Denied):
            self.step("inferred", "approved", 2, attest=True)

    def test_optional_pr_attestation_and_reopen_preserve_history(self):
        self.proposal("note", "First draft")
        self.stage("note")
        self.step("note", "pending", 2)
        self.step("note", "candidate", 3)
        self.proposal("note", "Updated draft", base=1)
        self.step("note", "validated", 4, record_revision=2)
        self.step("note", "review", 5)
        self.step("note", "approved", 6, attest=True)
        with self.assertRaises(HubError):
            self.step("note", "pr-open", 7)
        self.step("note", "pr-open", 7, pr_ref=PR)
        with self.assertRaises(Conflict):
            self.step("note", "active", 8)
        self.step("note", "pr-reviewed", 8)
        self.step("note", "pr-merged", 9)
        result = self.step("note", "active", 10)
        self.assertEqual(result["pr_ref"], PR)
        self.assertEqual(self.memory("note")["revision"], 3)
