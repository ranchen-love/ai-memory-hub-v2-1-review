# Session checkpoints

[index.json](index.json) is an optional empty snapshot. Use `session list` to query the live Vault. L0 indexes a session, L1 summarizes it, L2 stores a structured checkpoint, and L3 is an optional archived visible transcript.

Use [the session schema](../schemas/protocol.schema.json#/$defs/session) and the project ID. Each checkpoint records goal, constraints, decisions, outcomes, verification and next actions. Append against the actual `base_revision`. Keep file version references stable. Missing L3 or evidence stays unknown. For an already authorized transcript use `session show ID --layer L3 --consent`, optionally with its revision.
