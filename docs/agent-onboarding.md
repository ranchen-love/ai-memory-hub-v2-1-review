# Agent onboarding: create a user's own AI Memory Hub
**Purpose:** an agent-assisted first-time setup protocol for a *new owner's* memory Workspace and Vault. This is **not** a built-in universal one-click deployer, and merely reading a repository does not grant access to the user's accounts or private files.
## 0. Read the operating rules
Read [workspace guide](workspace.md), [AGENTS.md](../AGENTS.md), [workspace instructions](workspace.md), [supported adapters](adapters.md), [memory governance](../workflows/memory-lifecycle.md), and [privacy boundaries](../core/boundaries.md). Treat unsupported provider actions as unavailable, not implicitly authorized.
## 1. Inventory real capabilities
Before changing anything, check whether the agent actually has access to:
| Capability | Evidence required |
| --- | --- |
| Repository read | Source files opened at a known revision |
| GitHub repository create/write | An authorized connector or CLI able to create a **Private** repository in the owner's selected account |
| Local program execution | Python 3.11+, trusted local storage, working CLI |
| File input | User-selected real files or directories readable as bytes |
| Current AI conversation/memory | Actual provider-approved export, API or scoped connector that returns the data |
| Other AI providers | Separate authorization and actual export/connector coverage |
| Ongoing automation | An explicitly installed authorized scheduler and inspectable execution receipts |
If one capability is missing, finish safe available tasks and report it as `unavailable`, `not_authorized`, or `not_verified`. Do not repeatedly interrupt independent low-risk engineering steps.
## 2. Separate consent from technical ability
For a requested first-time setup, the agent may inspect documentation, prepare a new safe workspace, and run synthetic verification within its granted environment. Before executing any high-impact or sensitive action, obtain explicit permission for the named destination and scope.
Specifically require separate approval for a new remote repository or its visibility/ownership; real conversation or file collection (especially L3, health, financial or third-party data); Git pushes/PR merges; sharing with any recipient; installing persistent schedules; deletion or overwrite.
A generic request to "set up my memory" **does not mean consent to permanently record all personal data in Git history**. Never request that secrets be pasted into source files, issues, logs or commit messages.
## 3. Initialize a Workspace and Vault
From a trusted checkout on a Python 3.11+ host, use **new paths outside the distribution repository**:
```sh
python -m pip install .
ai-memory-hub workspace init --path ../my-hub
ai-memory-hub workspace check --path ../my-hub
```
This creates a personal Workspace at `../my-hub` and a separate local Vault at `../my-hub-vault`. All life fields start unknown; there are zero granted sources and no installed scheduled task. Inspect `AGENTS.md`, the core index, memory, project, session and life archive modules; record the Vault binding and check results. Never force initialization over pre-existing directories.
## 4. Optional owner-approved private GitHub repository
Only if the owner selected the account/name and granted repository creation and write access:
- Create a *new Private* repository and verify the resulting real URL and visibility. Never infer permission from the generic AI Memory Hub source URL.
- The generated Workspace has a deliberately deny-all `.gitignore`. Do **not** bulk-force-add its contents to the Git index.
- Create a **separate reviewable projection** containing only approved non-sensitive indexes, stable rules, project checkpoints, accepted facts, and references to Vault IDs/file versions. Review changes before each remote push.
- Default exclusions include the Vault/SQLite data, original L3 transcripts, sensitive personal records, raw attachments, secrets, and local `config/workspace.json` bindings.
- A Private repository is *not* end-to-end encryption; Git history and downstream access retain old submitted data. Prefer local storage for raw or sensitive material.
The core engine has no universal `repo create` or `repo publish` command. If external GitHub write tooling is unavailable, report the remote portion as blocked rather than fabricating success.
## 5. Organize only authorized, available source material
Record actual source, provider, selected scope, time coverage, authority, evidence status, and whether content is a local byte stream, external link, session export or user report.
- **Sessions:** L0 indexes, L1 provided summaries, L2 evidence-linked structured checkpoints (goals, decisions, rejected options and next actions), optional separately authorized L3 visible source messages.
- **Memory:** distinguish fact, preference, rule, inference and open questions. Submit candidates with real evidence. Approval and activation are separate operations; unresolved information does not become an accepted fact.
- **Projects:** preserve verified goals, constraints, decisions, outcomes, file versions and next actions; record unavailable or unverified details explicitly.
- **Assets:** archive approved actual bytes with SHA-256, source, version and links to sessions/projects. An external URL alone does not mean its bytes were archived.
- **Life archive:** map evidenced data into 12 categories, 52 subdomains and 134 registered fields. Keep unsupported fields `unknown`.
Only supported, explicitly granted local sources can be imported by the existing adapters. The agent may prepare normalized inputs from records it can really access but cannot pretend to extract invisible provider memories or every chat/attachment merely because it is the user's AI.
[Adapters and supported formats](adapters.md) · [Lifecycle](../workflows/memory-lifecycle.md)
## 6. Produce an owner-facing completion and missing-information report
Always deliver a report with:
| Area | Required evidence |
| --- | --- |
| Runtime | Available tools/permissions, installed engine and workspace version |
| Local setup | Actual Workspace and Vault paths, check output, safe defaults |
| GitHub | Whether the Private repository was actually created; owner, URL, push/PR evidence, or blocker |
| Source coverage | Authorized source list, time range, created/updated/unchanged/failed items |
| Sessions/assets | Real L0/L1/L2/L3 coverage, missing raw messages, file version/checksum availability |
| Memory | Candidate, duplicate, conflict, pending review, accepted, revoked and superseded status |
| Life archive | Unknown categories and fields; ranked questions for owner to answer |
| Privacy | What stays local, what awaits approval, actual authorized recipient scopes |
| Sync | Five switches, read grants, last completed archive, per-Agent version state and scheduler proof |
| Next owner actions | Missing account connections, approvals, exports, files, evidence, monitoring preferences |
Use `completed`, `partial`, `blocked`, `not_requested`, and `not_verified` honestly. Do not announce remote publication or provider access without evidence.
## 7. Explain how synchronization actually works
The ordinary preset begins with `weekly=on`, `full=on`, `event=off`, `daily=off` and `handoff=off`. They are **policy switches**, not OS scheduled jobs.
Source grants, job installation, completed import receipts, remote Git commits and each receiving Agent's `detected_sha` / `synced_sha` are distinct facts. Verify each separately. Use `local status` for local evidence and [the shared-memory read/confirm protocol](../integrations/memory-bootstrap.md) for a recipient. Do not call a changed snapshot synchronized until all necessary scopes have been re-read and confirmed.
Close with a clear explanation of stored data locations, what has and has not been sent to Git, how to run a manual check, whether recurring jobs were actually installed, and how to back up and restore local data.
## 8. Scope of current implementation
The existing product supplies a tested Workspace/Vault engine, format validators, revision-aware candidate lifecycle, partial source import, asset bytes, L0–L3 views and explicit shared-memory acknowledgments. **It does not include a platform-independent end-to-end orchestration program** for creating a remote repository, extracting all provider memories/chats, safely projecting selected materials to Git and installing durable schedules. Such steps are conditional on the agent's real tools, user approvals and any separately implemented integrations. Treat this guide as an executable-workflow specification, not a claim of completed universal automation.
