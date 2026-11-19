# Product README synchronization brief

This engineering change leaves the root English README and the eight files in `docs/i18n/` intact. The product writer should keep the existing root navigation and synchronize the following confirmed changes across the nine languages.

| Change | Exact path or command |
| --- | --- |
| Introduce the full workspace alongside the current engine | [Workspace installation](workspace.md), [coverage mapping](workspace-parity.md), [Agent entry](../AGENTS.md) |
| Install and initialize | `python -m pip install .`, `ai-memory-hub workspace init --path ../my-hub`, `ai-memory-hub workspace check --path ../my-hub` |
| Separate user data | Owner-only local workspace and sibling Vault by default. Optional `--vault PATH`, `--sensitivity LEVEL`. Both targets must be new and outside Git. |
| Demonstrate the consent and approval loop | `workspace init --path ../hub-demo --demo` followed by the exact [synthetic onboarding](workspace.md#synthetic-onboarding) commands. Copying fixtures leaves grants disabled until explicitly granted. |
| List meaningful owner modules | Parsed layout in the [core index](../core/INDEX.md). Include project templates, memory review, life taxonomy, evidence, bootstrap, file index and handoff. |
| Explain life archive coverage | [Taxonomy](../life-archive/taxonomy.md), [134-field registry](../life-archive/field-registry.json) and `workspace check --path WORKSPACE`. Twelve categories, 52 domains and 134 registered slots all start without evidence. |
| Describe the partial optional health extension | [Health extension](../life-archive/health/README.md) and `workspace health-check --input PATH --consent` validate de-identified aggregates. Raw health sync, backfilling and production scheduling are outside the extension. |
| Describe shared content versioning | `version snapshot`, `version check`, `version reload` and `version confirm` use an authorized local snapshot and Agent-specific receipts. Exact options in [Memory bootstrap](../integrations/memory-bootstrap.md). |
| Describe candidate governance | `candidate suggest ID --consent`, `candidate advance ID STATE --base REV --actor NAME --reason TEXT --consent` and `candidate history ID --consent`. [Lifecycle examples](../workflows/memory-lifecycle.md) include evidence attestation, approval, activation and optional manually attested PRs. |
| Describe permission and reachability | Describe the verified deployment scope and separate actual recipient file access from metadata. Retain existing scheduling, L3, platform and storage boundaries. |
| Version and compatibility | Product/engine version `2.3.0`; existing Vault record format `2.1`; new workspace format `1.0`. No existing V2.2 command is removed. |

The PR is a private review candidate. Product copy should preserve the existing availability and publication status until the repository owner approves release.
