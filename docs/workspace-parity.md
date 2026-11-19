# Workspace coverage and boundaries

The reference architecture has nineteen root modules. The product tree carries all nineteen logical modules plus the standalone engine and packaging files. The initializer uses an explicit manifest for owner-facing templates. Developer-only source remains in the product tree.

## Root module mapping

| Reference module | General equivalent | Implementation | Verification evidence | Exclusions or differences |
| --- | --- | --- | --- | --- |
| .github | Test and review artifact workflows | Product CI on Windows and Ubuntu, plus review packaging | Both platform suites, Gitleaks and exact ZIP/Bundle checks | Developer configuration stays in source, scoped runtime jobs stay local |
| assets | [Assets](../assets/README.md), empty manifest and engine | Versioned references plus existing content-addressed Vault | Onboarding retrieves exact bytes in the independent receiver | Personal originals and temporary external content are excluded |
| candidates | [Candidate intake](../candidates/README.md), schema and demo | Revision-pinned validation, peer advice, attestation, activation and audit | Candidate lifecycle tests deny skipped review, and verify duplicates, conflicts, replacements and revocation | Existing personal candidate queues are excluded |
| collaboration | [Collaboration](../collaboration/workflows.md) | Neutral roles, validation and exact-version authorized transfer | Onboarding validates receiver access to a selected asset | Roles bind to actual scope, not an existing account |
| config | [Configuration](../config/README.md), defaults and local binding | Ordinary defaults, separate Vault identity, deny-by-default Git ignores | Blank init checks all five switches and rejects a wrong same-level Vault | Local paths, credentials, jobs and inherited grants belong to the owner |
| core | [Core index](../core/INDEX.md) and five empty policy modules | Needs-based navigation and owner-scoped instructions | Init test verifies all shipped Markdown links | Existing identity, preferences and standing rules stay in their original instance |
| docs | [Workspace installation](workspace.md) and existing product translations | Technical setup instructions and existing language layout | i18n checker validates all nine, default Chinese README and nine-language navigation validated against the V2.3 guide | Product copy belongs to the designated product writer |
| examples | Opt-in synthetic project, checkpoint and assets | Explicit fixture copy with no automatic grants | Onboarding checks zero grants, then grants and imports four items | Real chats, source files and original data are excluded |
| integrations | [Bootstrap](../integrations/memory-bootstrap.md), [capabilities](../integrations/capabilities.md) | Template/engine version plus per-Agent snapshot detection, scoped read and confirmation | Shared-version tests cover first/changed/unchanged/unknown, separate recipients, deletion and partial confirmation | Unverified live connectors, credentials and account-specific automation are excluded |
| knowledge | [Knowledge topics](../knowledge/README.md) | Topic index with evidence and repeatable verification | Blank init validates index and template links | Personal topics and organization-specific knowledge are excluded |
| life-archive | [Life archive](../life-archive/README.md) and schemas | 12 categories, 52 subdomains, 134 typed field slots, timeline and lineage | Registry tests exercise all 134 definitions through both runtime and schema; blank starts entirely unknown | Personal instances and raw extracts are excluded |
| memory | [Memory](../memory/README.md), empty projection and Vault | Evidence-backed lifecycle and legacy review, with an optional local view | Onboarding exercises both approval paths; lifecycle tests verify exact revision history | Original facts, deliberations and decisions are excluded |
| projects | [Projects](../projects/README.md) and project template | Project state, decisions, evidence, checkpoints, next work | Onboarding checks the synthetic project's state and L2 checkpoint | Personal project names, files and project history are excluded |
| schemas | Existing engine definitions plus workspace/life schemas | Protocol 2.1 plus optional classification and workspace 1.0 | Schema suite resolves shared definitions and validates fixture inputs | Private-specific descriptors are replaced by common interfaces |
| scripts | Release builder, onboarding smoke and i18n checker | CLI for owners, signed-off tooling for developer checks | Exact allowlist build and installed smoke exercise the real runtime | No instance-specific job or local machine wrapper is bundled as a default |
| sessions | [Session index](../sessions/README.md) and engine | L0–L3, revision history and optional provenance | Existing tests validate separated L3 authorization and immutable evidence | Existing transcripts and indexes with user material are excluded |
| tests | Existing suite and workspace-specific tests | Independent source and installed test entry points | Double init, denial, wrong Vault, installed packaging and transfer tested | Use only synthetic inputs |
| vendor | [Dependency boundary](../vendor/README.md) | Reference first-party engine with no duplicated vendored core | Current tree includes the module and exact ZIP rules include its documentation | Engine source is already first-party; mirroring provides no additional capability |
| workflows | [Core workflows](../workflows/memory-lifecycle.md) | Memory, sync, research, writing, quality, development and handoff | Onboarding and existing engine suites verify authority and permissions | Specialist media and weekly-report workflows remain owner extensions |

## Core submodule mapping

| Reference concept | General equivalent | Implementation | Verification evidence | Exclusions or differences |
| --- | --- | --- | --- | --- |
| Agent entry, identity, scope and policy | AGENTS.md, CLAUDE.md, GEMINI.md and core/ | Neutral shims, empty authority fields and core routing | Init checks links; blank data test | Personal policy and access require user approval |
| Fact registry, proposals and version history | memory/, candidates/ and workspace facts | Optional indexes backed by Vault approval and immutable revisions | Onboarding requires approval and retains classification | A private PR is optional; no automatic remote publication |
| Life category profiles and extensions | life-archive/profile.json, taxonomy and life schema | 12/52/134 registry, status, typed field evidence, time, sensitivity and cross-record links | All 52 domain rules and all 134 slots are tested | Owner supplies values, raw originals remain separately authorized |
| Timeline, gaps and corrections | life-archive/timeline.json, data-quality guidance and checker | Explicit date precision, coverage states, successor consistency and no cycles | Unknown baseline and invalid precision/cycle tests | Original episodes, locations and real timestamps are excluded |
| Health schema and raw-source tooling | life-archive/health/, aggregate schema and health-check | Partial, optional extension for de-identified aggregates with explicit consent | Health schema/dedupe tests and synthetic onboarding | The reference raw health pipeline, device recording, historical backfills and production jobs are outside this implementation |
| Connector routing, storage and re-read | integrations/, assets/ and existing adapters | Authorized snapshots, content SHA, scoped reread and separate recipient file access | Installed CLI confirms shared-memory reload and receives a separate project's exact file bytes | No assumed live connector or schedule |
| Research, development, documentation and handoff | workflows/ and collaboration/ | Evidence-driven portable workflows | Onboarding and existing cross-Vault tests verify core behavior | Instance-specific reporting scripts stay optional |

## Functional mapping

| Reference behavior | General equivalent | Implementation | Verification evidence | Exclusions or differences |
| --- | --- | --- | --- | --- |
| Initialize, protect and validate | workspace init/check | Owner-only non-nested roots and Vault identity binding | Workspace tests cover denial, path safety, no overwrite and wrong binding | Existing dirs are kept intact; use a new scope or deliberate recovery |
| Propose, review and approve | local run, memory review, import and workspace facts | Validate source structure, give duplicate/conflict advice, verify evidence with explicit attestation, activate and preserve audit links | Lifecycle tests cover denied promotion, stale base, stale peers, revocation, replacement and optional PR status | Remote PR evidence is operator-supplied; there is no automatic remote action |
| Project, session and assets | Existing session/project commands and manifest | Use a real project link, checkpoint and bytes | Onboarding compares bytes retrieved in an independent recipient Vault | L3 and unrelated files remain at origin |
| Life profile and timeline | workspace check | Report 52 domain statuses, missing evidence across 134 field slots and required gaps; enforce lineage and per-field scope | All registered field inputs and negative cases tested on synthetic values | Legacy unscoped notes do not fill field slots |
| Shared version detection | version snapshot/check/reload/confirm | SHA plus per-Agent read receipts, compare precise scopes and keep the last confirmed baseline | First, unchanged, changed, disconnected, partial confirmation and stale receipt tested | Explicitly transported snapshots; no automatic fetch or proof of human comprehension |
| Optional health (partial) | workspace health-check | Validate owner-supplied de-identified aggregates only | Synthetic schema and dedupe checks | No raw health ingestion, original records, backfill, or production schedule |
| Release and privacy | Current/historical allowlists, Gitleaks and packaging | Validate the distribution root, current ZIP and complete bundle | Artifact job and installed smoke run on named final SHA | Public publication and formal release need owner approval |

The product tree contains source and synthetic fixtures. An initialized workspace contains the owner's working notes and views. The separate Vault provides the durable data boundary. A public distribution does not grant access to another user's workspace or Vault.
