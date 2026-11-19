# Agent entry point

## First-time owner setup
If the user wants to **create their own personal memory hub** from this distribution, follow [the Agent onboarding and completion protocol](docs/agent-onboarding.md) or [简体中文版](docs/agent-onboarding.zh-CN.md) before claiming any setup or migration succeeded.
- Discover actual GitHub write tools, local execution rights and provider-data coverage. Reading this repository cannot grant access to another account's private memory.
- Initialize a new local Workspace and separate Vault when authorized; run synthetic checks before touching real material.
- Private GitHub repository creation, collecting real conversations and files, pushing any projection, sharing data and installing schedules require explicit owner approval for that destination and scope.
- The generated Workspace ignores everything in Git by default. Never force-add the entire Workspace or Vault, L3 raw history, sensitive facts, or secrets. Use only separately reviewed projections.
- Finish with evidence of completed actions, version and source coverage, unresolved fields, user questions, actual remote commits (if any), five policy switches, and scheduler/run receipts. Label unavailable or unverified steps plainly.

Start with [the core index](core/INDEX.md). Read only the task-relevant project, accepted memories and explicitly authorized sources. Check workspace and engine versions at the start of a new task and after a reported update. For a shared snapshot, follow the [Agent version check, reload and confirmation flow](integrations/memory-bootstrap.md) before treating detected changes as read.

1. Confirm which workspace and Vault the user authorized. A link, ID or filename is evidence of a reference. Confirm whether the bytes are readable before relying on it.
2. Separate observed evidence, user self-report, inference and open questions. Preserve revision and source when citing decisions or test results.
3. Use [the memory workflow](workflows/memory-lifecycle.md) for durable candidates. Only an explicit user approval can promote one to accepted memory.
4. Follow [the handoff protocol](collaboration/handoff-protocol.md) for another agent. Keep raw messages and unapproved files inside their authorized boundary.
5. If a connector, repository or Vault is unavailable, label the limitation and use an explicitly supplied export or checkpoint. Keep production scheduling separate from a successful manual run.
