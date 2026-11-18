# Workspace coverage and boundaries

The reference architecture has nineteen root modules. The product tree carries all nineteen logical modules plus the standalone engine and packaging files. The initializer uses an explicit manifest for owner-facing templates. Developer-only source remains in the product tree.

## Root module mapping

| Reference module | General equivalent | Implementation | Verification evidence | Exclusions or differences |
| --- | --- | --- | --- | --- |
| .github | Test and review artifact workflows | Product CI on Windows and Ubuntu, plus review packaging | Both platform suites, Gitleaks and exact ZIP/Bundle checks | Developer configuration stays in source, scoped runtime jobs stay local |
| assets | [Assets](../assets/README.md), empty manifest and engine | Versioned references plus existing content-addressed Vault | Onboarding retrieves exact bytes in the independent receiver | Personal originals and temporary external content are excluded |
| candidates | [Candidate intake](../candidates/README.md), schema and demo | Explicit normalized intake, evidence and owner review | Onboarding denies unapproved acceptance and preserves revision 2 | Existing personal candidate queues are excluded |
| collaboration | [Collaboration](../collaboration/workflows.md) | Neutral roles, validation and exact-version authorized transfer | Onboarding validates receiver access to a selected asset | Roles bind to actual scope, not an existing account |
| config | [Configuration](../config/README.md), defaults and local binding | Ordinary defaults, separate Vault identity, deny-by-default Git ignores | Blank init checks all five switches and rejects a wrong same-level Vault | Local paths, credentials, jobs and inherited grants belong to the owner |
| core | [Core index](../core/INDEX.md) and five empty policy modules | Needs-based navigation and owner-scoped instructions | Init test verifies all shipped Markdown links | Existing identity, preferences and standing rules stay in their original instance |
| docs | [Workspace installation](workspace.md) and existing product translations | Technical setup instructions and existing language layout | i18n checker validates all nine, product README diff is empty | Product copy belongs to the designated product writer |
| examples | Opt-in synthetic project, checkpoint and assets | Explicit fixture copy with no automatic grants | Onboarding checks zero grants, then grants and imports four items | Real chats, source files and original data are excluded |
| integrations | [Bootstrap](../integrations/memory-bootstrap.md), [capabilities](../integrations/capabilities.md) | Version check, scoped reads, explicit fallback and review flow | Onboarding compares template/engine versions, installed smoke runs off checkout | Unverified live connectors, credentials and account-specific automation are excluded |
| knowledge | [Knowledge topics](../knowledge/README.md) | Topic index with evidence and repeatable verification | Blank init validates index and template links | Personal topics and organization-specific knowledge are excluded |
| life-archive | [Life archive](../life-archive/README.md) and schemas | Twelve-category profile, timeline, lineage and optional aggregates | Workspace tests check unknown coverage, precision, cycles and level boundaries | Personal life records and device exports are excluded |
| memory | [Memory](../memory/README.md), empty projection and Vault | Evidence-backed revision workflow with optional local view | Onboarding checks empty facts, accepted projection and history | Original facts, deliberations and decisions are excluded |
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
| Life category profiles and extensions | life-archive/profile.json, taxonomy and life schema | Twelve categories, status, evidence, sensitivity, timing and cross-record keys | Coverage and schema tests | Owner supplies values, raw originals remain separately authorized |
| Timeline, gaps and corrections | life-archive/timeline.json, data-quality guidance and checker | Explicit date precision, coverage states, successor consistency and no cycles | Unknown baseline and invalid precision/cycle tests | Original episodes, locations and real timestamps are excluded |
| Health schema and raw-source tooling | life-archive/health/, aggregate schema and health-check | Opt-in de-identified aggregates with sample-only validation | Health schema/dedupe tests and synthetic onboarding | Device-specific raw imports and production schedules are excluded |
| Connector routing, storage and re-read | integrations/, assets/ and existing adapters | Explicit authorization, version comparison, fallback and actual byte checks | Installed smoke and authorized receiver byte verification | No assumed live connector or schedule |
| Research, development, documentation and handoff | workflows/ and collaboration/ | Evidence-driven portable workflows | Onboarding and existing cross-Vault tests verify core behavior | Instance-specific reporting scripts stay optional |

## Functional mapping

| Reference behavior | General equivalent | Implementation | Verification evidence | Exclusions or differences |
| --- | --- | --- | --- | --- |
| Initialize, protect and validate | workspace init/check | Owner-only non-nested roots and Vault identity binding | Workspace tests cover denial, path safety, no overwrite and wrong binding | Existing dirs are kept intact; use a new scope or deliberate recovery |
| Propose, review and approve | local run, memory review, import and workspace facts | Validate evidence, approve with explicit consent and reread the true revision | Onboarding proves unapproved acceptance denied and accepted revision 2 | No implicit remote review or publish |
| Project, session and assets | Existing session/project commands and manifest | Use a real project link, checkpoint and bytes | Onboarding compares bytes retrieved in an independent recipient Vault | L3 and unrelated files remain at origin |
| Optional archive and health | workspace check and health-check | Validate coverage, accepted lineage and de-identified aggregates | Schema and synthetic onboarding coverage | No automated raw-data adapter or original health material |
| Release and privacy | Current/historical allowlists, Gitleaks and packaging | Validate the distribution root, current ZIP and complete bundle | Artifact job and installed smoke run on named final SHA | Public publication and formal release need owner approval |

The product tree contains source and synthetic fixtures. An initialized workspace contains the owner's working notes and views. The separate Vault provides the durable data boundary. A public distribution does not grant access to another user's workspace or Vault.
