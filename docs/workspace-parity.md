# Workspace coverage and boundaries

The reference architecture has nineteen root modules. The product tree carries all nineteen logical modules plus its own engine and packaging files. The initializer copies the owner-facing workspace from an explicit manifest, while developer files remain in the product source.

## Root mapping

| Reference module | General equivalent | Handling and evidence |
| --- | --- | --- |
| .github | Test and review artifact workflows | Product-only. Windows and Ubuntu exercises, history scan and exact release trees. |
| assets | [Assets](../assets/README.md), empty index, engine | Template and existing byte store. The onboarding smoke retrieves an exact version. Actual attachments are excluded. |
| candidates | [Candidate intake](../candidates/README.md), schema, demo | Blank intake guidance and optional synthetic candidate. The smoke covers review, explicit approval and revision history. |
| collaboration | [Collaboration](../collaboration/workflows.md) | Platform-neutral roles, verification and consent-based transfer. |
| config | [Configuration](../config/README.md) | Ordinary preset, local binding and deny-by-default ignore template. Real paths, credentials and task definitions remain local. |
| core | [Core index](../core/INDEX.md) and five empty policies | Navigation and scope are copied. Identity and standing decisions are owner-filled. |
| docs | [Workspace installation](workspace.md) and existing translated product pages | Developer validation preserves i18n layout. The initializer carries technical guides only. |
| examples | Synthetic project, structured checkpoint and bytes | The opt-in demo is copied without grants. |
| integrations | [Bootstrap](../integrations/memory-bootstrap.md), [capabilities](../integrations/capabilities.md) | Version reread and authorized fallback. Connector availability is checked in its environment. |
| knowledge | [Knowledge topics](../knowledge/README.md) | Empty index and reusable evidence template. Existing personal topics are excluded. |
| life-archive | [Life archive](../life-archive/README.md) | Twelve unknown categories, optional aggregate health checks and timeline. Source-specific raw ingestion is an optional future adapter. |
| memory | [Memory](../memory/README.md), empty facts projection, engine | Accepted objects remain in the Vault. Personal facts and previous decisions are excluded. |
| projects | [Projects](../projects/README.md), template and engine | Empty project organization and optional synthetic project. |
| schemas | Existing engine schemas plus workspace schemas | Preserve record schema 2.1. Add optional memory classification, life data and derived indexes. |
| scripts | Release files, onboarding smoke, i18n checker | Developer tools stay in source. Installed CLI implements initialization and validation. |
| sessions | [Session index](../sessions/README.md), engine | L0–L3, explicit provenance, scoped raw permission. |
| tests | Existing engine suite and workspace validation | Release verification covers installed tooling, sample import and independent Vault transfer. |
| vendor | [Dependency boundary](../vendor/README.md) | General engine source is first-party. No mirror of the engine or user data is needed. |
| workflows | [Memory](../workflows/memory-lifecycle.md), research, development, writing, sync and handoff | Shared methods; organization-specific weekly-report and media tasks remain local extensions. |

## Submodule mapping

| Reference concept | General implementation | Difference |
| --- | --- | --- |
| Agent rules, identity, communication, preferences and boundaries | `AGENTS.md`, neutral compatibility shims and `core/` | Owner fields are empty. Any future production policies require owner approval. |
| Fact registry, lifecycle proposals, decision log and version tracking | `memory/`, `candidates/`, canonical Vault revisions, `workspace check` | Local approval is the default. An expressly authorized private PR is an optional review channel. |
| Category profiles and field extensions | `life-archive/profile.json`, [twelve-category taxonomy](../life-archive/taxonomy.md), record schema | Includes provenance, status, sensitivity, timing, correction and cross-record links. Personal values are excluded. |
| Timeline, gaps and quality | `life-archive/timeline.json`, coverage checker | Unknown dates remain unknown, explicit precision and category coverage are validated. |
| Health trend structure and raw-source tooling | `health/README.md` within the life archive, aggregate schema and health-check | Optional de-identified aggregates and synthetic fixture. Device-specific import, raw archives and production schedules stay out of the default product. |
| Integration routing, version check, storage and no-connector fallback | `integrations/` and existing local CLI adapters | Manual, manifest and approved exports are first-class paths; unsupported platform access remains unverified. |
| Data quality, development, research, writing and handoff | `workflows/` and `collaboration/` | Platform-neutral workflows replace instance-specific reporting programs. |

## Functional evidence

| Function | Implementation and reproducer |
| --- | --- |
| Init, no overwrite, path safety | `workspace init` and `workspace check`. Workspace unit tests cover empty initialization, agent links, refusal in Git, overlap, symlink and ACL failures. |
| Propose, validate, review, approve, reread | `local run`, `memory review`, explicit `import --review-decision --consent`, `memory history`, then `workspace facts`. Onboarding smoke verifies denial without approval and accepted revision 2. |
| Project, checkpoint, bytes and handoff | Existing V2.2 CLI with a synthetic approved manifest. The recipient Vault retrieves the exact approved file in the onboarding smoke. |
| Privacy and release | Explicit current and historical allowlists, full-history secret scan, exact ZIP tree and self-contained Bundle. The installed smoke runs outside the checkout. |

The product tree contains source and synthetic fixtures. The workspace contains an owner's working notes and approval views. The separately protected Vault provides the durable data boundary. A public distribution does not grant access to another user's workspace or Vault.
