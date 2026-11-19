# Agent entry point

Start with [the core index](core/INDEX.md). Read only the task-relevant project, accepted memories and explicitly authorized sources. Check workspace and engine versions at the start of a new task and after a reported update. For a shared snapshot, follow the [Agent version check, reload and confirmation flow](integrations/memory-bootstrap.md) before treating detected changes as read.

1. Confirm which workspace and Vault the user authorized. A link, ID or filename is evidence of a reference. Confirm whether the bytes are readable before relying on it.
2. Separate observed evidence, user self-report, inference and open questions. Preserve revision and source when citing decisions or test results.
3. Use [the memory workflow](workflows/memory-lifecycle.md) for durable candidates. Only an explicit user approval can promote one to accepted memory.
4. Follow [the handoff protocol](collaboration/handoff-protocol.md) for another agent. Keep raw messages and unapproved files inside their authorized boundary.
5. If a connector, repository or Vault is unavailable, label the limitation and use an explicitly supplied export or checkpoint. Keep production scheduling separate from a successful manual run.
