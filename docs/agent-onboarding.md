# Create a personal AI Memory Hub with an Agent

The V2.4 CLI previews a first-run plan, initializes an owner-only Workspace and its separate Vault, imports approved inputs and reports what happened. Repository creation and publication have their own approval steps. Read the [authorization boundaries](../core/boundaries.md) before requesting access.

## 1. Plan the setup

1. Install from an approved checkout using Python 3.11 or newer. Choose two new, non-nested directories outside all Git working trees. Their parent directories must exist. To resume a previous setup, keep the exact bound paths.
2. Copy the [empty request template](../examples/onboarding-request.json) to an owner-controlled local directory. Edit the copy and follow the [request and result schema](../schemas/onboarding.schema.json). Relative paths resolve against the request file's directory. Omit `vault` to use a sibling with the suffix `-vault`. The default sensitivity is `private`.
3. List only the local paths selected by the owner. Each item has a unique stable `id`, an `adapter`, a `path` and an `authorized` flag. Mark a selected source `authorized: true` only after the owner approves reading and archiving that source. The optional `allow_raw` flag defaults to `false`. Set it to `true` only after separate permission to store eligible visible messages in a private or restricted Vault. Leave `sources` empty for a blank first run.
4. To plan an optional GitHub repository, include `"github": {"target": "OWNER/NAME", "visibility": "private"}`. The request identifies the target. Creation and publication require further consent.

```sh
python -m pip install .
ai-memory-hub onboarding plan --request hub-request.json
```

Read the Markdown summary and `plan_digest` in the JSON. The read-only plan checks the current runtime, selected paths and capabilities, and reports unavailable inputs. It cannot acquire provider permissions. Verify the actual owner, retention, intended source coverage and all proposed writes with the user.

## 2. Apply only the approved plan

```sh
ai-memory-hub onboarding apply --request hub-request.json \
  --approve-plan APPROVED_PLAN_DIGEST --consent
ai-memory-hub onboarding report --request hub-request.json \
  --markdown /path/to/approved/workspace/first-run.md > first-run.json
```

Use the actual approved digest. The report emits JSON on standard output. Select a new file inside the bound Workspace to save Markdown, or omit `--markdown` for JSON only. If initialization is blocked, omit `--markdown` to read the failure report without a bound Workspace. Keep both reports within the local privacy boundary. Quote paths with spaces. These command blocks use POSIX line continuation. In PowerShell, put each command on one line or use the backtick continuation.
A single failed or unavailable source can leave usable partial results. For `apply` or `report`, exit 0 means completion and exit 1 means a partial, blocked or failed result with JSON details. Input and approval errors exit 2. Restore a missing path, fix the selected manifest or resolve a revision conflict, then check the plan and rerun. Review and approve a new digest when the plan changes. Rerunning the same import preserves prior revisions and reuses successful receipts. Choose a new directory if an existing one belongs to a different instance.

## 3. Prepare authorized inputs

| Adapter | Selected input |
| --- | --- |
| `normalized`, `codex_workspace`, `local_checkpoint` | A directory with `memory-hub.json` listing the relative paths of approved files, links and normalized records |
| `chatgpt_export` | An official local export ZIP with supported conversation shards, or an extracted conversation JSON file limited to the approved scope |
| `life_profile`, `life_timeline` | The individual approved JSON document following the workspace life archive schema and field registry |

An Agent can prepare a normalized manifest from material it can actually read. A platform with no accessible export or connector remains unavailable. Use an explicitly authorized local checkpoint from the user instead of attempting to scan an account. [Adapter formats and coverage](adapters.md)

For example, an approved directory of local checkpoints can use this entry in `sources`. The path is relative to the request, and raw message ingestion is off.

```json
{
  "id": "checkpoints",
  "adapter": "local_checkpoint",
  "path": "./owner-selected-intake",
  "authorized": true,
  "allow_raw": false
}
```

- **Sessions and projects.** Preserve actual metadata as L0, provided summaries as L1, and evidence-linked decisions, outcomes and next actions as L2. Store eligible L3 only with separate raw permission. The ChatGPT adapter does not synthesize missing summaries or checkpoints. Attachments need their own approved manifest entries.
- **Long-term memory.** Keep durable claims in candidates. Inspect duplicate and conflict suggestions, approve the evidence and separately activate the result. Keep inference and unsupported claims out of accepted facts. [Candidate review, approval and activation](../workflows/memory-lifecycle.md)
- **Files and links.** Use stable manifest keys and asset IDs. Mark actual user uploads `user_upload` and generated files `ai_generated`. Verify an archived file by exact revision and SHA-256. A URL remains an external reference.
- **Life archive.** Fill only evidenced typed fields in the existing 12 categories, 52 domains and 134 fields. Retain `unknown` for evidence gaps. [Field formats and lifecycle](../life-archive/README.md)

## 4. Review a separate Git projection

Use an independent output directory outside the Workspace, Vault and any Git checkout. The default preview contains only aggregate counts and a neutral 19-module scaffold. To share from a `private` Vault, prepare a local UTF-8 JSON request using the exact source IDs and current revisions. Write independent, redacted summaries and choose shareable aliases. This example uses synthetic values.

```json
{
  "format": "1.0",
  "target": "owner/example-private-repo",
  "items": [
    {
      "kind": "memory",
      "id": "verification-rule",
      "source": {"id": "accepted-local-rule", "revision": 2},
      "purpose": "reference",
      "data": {"key": "verification", "claim": "Check results before accepting them."}
    },
    {
      "kind": "project",
      "id": "instrument-review",
      "source": {"id": "local-project", "revision": 1},
      "purpose": "continuity",
      "data": {"title": "Instrument review", "summary": "A second reading is pending."}
    },
    {
      "kind": "session",
      "id": "second-reading",
      "source": {"id": "local-session", "revision": 1},
      "purpose": "navigation",
      "data": {"title": "Second reading", "project": "instrument-review"}
    }
  ]
}
```

```sh
ai-memory-hub projection preview --workspace WORKSPACE \
  --output NEW_PROJECTION
ai-memory-hub projection review --workspace WORKSPACE --input REVIEW.json
ai-memory-hub projection approve --workspace WORKSPACE --input REVIEW.json \
  --digest REVIEW_SHA256 --confirm-redacted --consent
ai-memory-hub projection preview --workspace WORKSPACE --output NEXT_PROJECTION \
  --review-digest REVIEW_SHA256 --previous NEW_PROJECTION
```

Read the review output locally. Check each source revision, purpose, redacted text and Private recipient, then record the review SHA-256 only after the owner confirms the redaction. Only accepted non-inferred memory is eligible. Resolve conflicting candidates first. Project or session checkpoints may supply a redacted `goal`, optional `decisions` and `next_actions`. A session can share a summary or L2 checkpoint only if the selected source has that layer. Its optional project alias must point to the selected project that actually owns the session.

Approved records appear in `memory/reviewed.json`, `projects/index.json` and `sessions/index.json`. Raw source IDs and evidence locators stay local. The final preview contains a separate projection SHA-256. Review that digest and file diff before publishing. Changed sources or edited redacted text require a new review. Review input and output can reveal local source identifiers, so keep both local. Automated filters catch common unsafe patterns, and the owner must verify that even ordinary prose contains no sensitive information. Credentials, local paths, L3, attachments and Vault files remain local. Existing public Vaults can still use `--select ID` and `--asset ID@REV` in a separate preview.

## 5. Create and publish to a Private GitHub repository

Use the GitHub target recorded by the Workspace's applied plan. After the owner approves the named destination and the relevant operation, use authenticated GitHub CLI access to run the corresponding command. Keep credentials in the existing authentication mechanism.

```sh
ai-memory-hub repo probe --target OWNER/NAME
ai-memory-hub repo create --workspace WORKSPACE \
  --target OWNER/NAME --consent
ai-memory-hub repo publish --workspace WORKSPACE --target OWNER/NAME \
  --repository-id VERIFIED_REPO_ID --projection REVIEWED_PROJECTION \
  --digest APPROVED_SHA256 --consent
```

The built-in create command targets the signed-in personal owner on github.com. For an organization or when `gh` is unavailable, use an authorized GitHub integration or the GitHub site. Create a new empty Private repository and verify visibility. If publishing manually, stage only the reviewed projection files in an independent Git history, verify the staged file hashes, and check the remote ref and visibility afterward. Keep manual operation receipts. The built-in publisher audits the history created by its own projection protocol and can block manually committed or otherwise altered history.

Approve the exact projection digest and destination before publication. A private review also requires the numeric `repository_id` from `repo create` or `repo probe`. Creation reserves an empty Private repository. The first approved direct publication seeds the branch with the reviewed manifest, then commits the 19-module scaffold with any reviewed records. Retry with the same digest if interrupted. If the source changed while only the manifest was published, review again and approve the new digest against that exact bootstrap commit with `--base-sha`. For other updates, use the verified `base_commit` from `repo probe`. Add `--pr` only with independent approval and a complete baseline. Keep the original Vault for verifying published private history and capture the actual repository, commit and PR receipts. A permission or tool failure leaves that stage blocked while the local deliverables remain usable.

## 6. Hand over the report and maintenance workflow

The report records observed scope, versions, outcomes and missing evidence. Leave unrequested actions unrequested, report denied sources as blocked, and label execution without proof as unverified. Supply the user with the report and the remaining approvals and data gaps.

```sh
ai-memory-hub --root VAULT local status
ai-memory-hub --root VAULT local run --source APPROVED_ID
ai-memory-hub --root VAULT asset check ASSET_ID --version REV
```

For a narrower scope or a changed path, stop any old schedule. Use `source revoke ID` to revoke the old active grant and review the new plan before authorizing the replacement. Revocation preserves already archived revisions. Resolve conflicts against the current revision and retry just the affected approved source.

Weekly and on-demand are enabled in the ordinary preset. Event, daily and handoff are disabled. Check imports and failure receipts with `local status`. A local archive run, a remote Git commit, and a receiving Agent's `detected_sha` and `synced_sha` are independent observations. Use [the per-Agent reload and confirmation workflow](../integrations/memory-bootstrap.md) for that evidence. Install any schedule separately with the owner's approval and confirm its first actual run. Follow [backup, restore and scheduler guidance](deployment.md) before upgrading, retrying failed runs or changing the Vault location.
