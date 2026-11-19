# Candidate intake

Start from [the candidate schema](../schemas/memory-candidate.schema.json) and [the approval path](../workflows/memory-lifecycle.md). A candidate carries a stable key, normalized claim, provenance, classification and sensitivity. Ensure the record matches the actual Vault boundary before importing.

With `workspace init --demo`, the [workspace guide](../docs/workspace.md) shows where to find the synthetic candidate. Templates contain no standing decisions on behalf of users.

Use the [executable lifecycle](../workflows/memory-lifecycle.md) to validate a pinned candidate revision, inspect exact peers, record approval and then activate. Rejected and retired records remain in revision history.
