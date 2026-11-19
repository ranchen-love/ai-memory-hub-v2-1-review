# Agent entry point

## First-time owner setup
For a new owner's personal memory hub, use the executable [Agent onboarding guide](docs/agent-onboarding.md) or [简体中文版](docs/agent-onboarding.zh-CN.md).
- Prepare an owner-scoped request and run `ai-memory-hub onboarding plan`. Review the resolved paths, capabilities and scope before calling `onboarding apply` with the approved plan digest. Run `onboarding report` to record actual results and remaining gaps.
- Use only data the owner has specifically authorized and the current environment can access. Scope raw messages, private repository creation, publication, sharing and scheduled execution separately.
- The workspace denies Git tracking by default. Publish only an independently reviewed projection to the approved destination. Keep raw messages, private documents, files and Vault state local.
- Report source and time coverage, unresolved fields, verified versions, actual remote receipts, policy switches and scheduler evidence. Mark unavailable or unverified steps explicitly.

Start with [the core index](core/INDEX.md). Read only the task-relevant project, accepted memories and explicitly authorized sources. Check workspace and engine versions at the start of a new task and after a reported update. For a shared snapshot, follow the [Agent version check, reload and confirmation flow](integrations/memory-bootstrap.md) before treating detected changes as read.

1. Confirm which workspace and Vault the user authorized. A link, ID or filename is evidence of a reference. Confirm whether the bytes are readable before relying on it.
2. Separate observed evidence, user self-report, inference and open questions. Preserve revision and source when citing decisions or test results.
3. Use [the memory workflow](workflows/memory-lifecycle.md) for durable candidates. Only an explicit user approval can promote one to accepted memory.
4. Follow [the handoff protocol](collaboration/handoff-protocol.md) for another agent. Keep raw messages and unapproved files inside their authorized boundary.
5. If a connector, repository or Vault is unavailable, label the limitation and use an explicitly supplied export or checkpoint. Keep production scheduling separate from a successful manual run.
