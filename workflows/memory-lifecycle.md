# Memory lifecycle

Use a stable ID and key, the original source, accurate classification and the Vault's sensitivity. Prepare a [normalized candidate envelope](../schemas/memory-candidate.schema.json) with `data.status` set to `candidate`. Store it in an authorized local file and import it with `--consent`. Candidate records remain outside the accepted facts view.

## Validate, review and activate locally

The example assumes a new proposal at record revision 1, with no matching peer. Replace the example IDs and decision reasons with the authorized ones. `--base` pins the lifecycle revision. Validation also pins the current memory record revision.

```sh
ai-memory-hub --root VAULT import --input CANDIDATE_JSON --consent
ai-memory-hub --root VAULT candidate advance ID validated --base 0 --record-revision 1 --actor reviewer --reason "Checked candidate format and source reference" --consent
ai-memory-hub --root VAULT candidate suggest ID --consent
ai-memory-hub --root VAULT candidate advance ID review --base 1 --actor reviewer --reason "Compared current peers" --consent
ai-memory-hub --root VAULT candidate advance ID approved --base 2 --actor reviewer --reason "Owner approved verified evidence" --evidence-verified --consent
ai-memory-hub --root VAULT candidate advance ID active --base 3 --actor reviewer --reason "Owner authorized activation" --consent
ai-memory-hub --root VAULT candidate history ID --consent
```

Validation checks the envelope and source structure. Reviewers must actually inspect the cited evidence and obtain the owner's approval before setting `--evidence-verified`. That flag and the actor record a local attestation. Unconfirmed claims or inferences cannot enter the new activation path. The approval stage itself leaves the Vault record as a candidate. Activation writes the accepted revision.

`candidate suggest` compares records with the same normalized stable key and returns exact peer revisions. A duplicate accepted claim should be linked or rejected. A conflicting candidate requires review. At approval pass `--ack-peer ID@REV` for every encountered peer. If an existing accepted claim must be replaced, also pass `--supersede ID@REV` for that exact revision. An activation conflicts if peers changed after approval. Approved replacements retire old revisions atomically and preserve links to the new record.

## Review options and later revisions

| Lifecycle path | Result |
| --- | --- |
| `candidate → validated → review → approved → active` | Local review and separate activation |
| `review → pending → review` | Wait for evidence or authority |
| `validated/review/pending → candidate` | Reopen the draft and import its newer revision before revalidating |
| `approved → pr-open → pr-reviewed → pr-merged → active` | Optional, manually attested external review |
| `candidate/validated/review/pending → rejected → archived` | Retain the record history without accepting it |
| `active → revoked/archived` | Retire the accepted record while retaining prior revisions |
| Replacement activates `active → superseded`, then `superseded → archived` | Preserve the superseding ID and revision in the previous record's audit |
| `approved` or a PR stage `→ review/revoked` | Reassess or withdraw stale or unauthorized approval |

For optional PR review, supply the stable HTTPS review link with `pr-open --pr-ref URL`. Then explicitly attest to the reviewed and merged states using the current lifecycle revision and decision reason. Use existing approved private channels and share only separately approved content. The CLI records the supplied reference and local decisions. It neither validates a remote PR outcome nor creates, pushes, uploads or merges anything.

Use `candidate history` for decision and record revisions. Verify active facts with `memory show ID` or `workspace facts --path WORKSPACE --consent`. The existing `memory review` and explicitly authorized `import --review-decision` continue to work for unmanaged records. Once the tracked workflow starts, direct imports cannot skip its state transitions. Replaying an envelope already stored remains idempotent.
