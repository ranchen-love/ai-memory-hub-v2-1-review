# Optional health summary

Use [the aggregate schema](../../schemas/health-summary.schema.json) for explicitly selected de-identified aggregate summaries. This feature verifies structure, dates, units labels and duplicate entries. It does not interpret medical results or access device exports.

Try `workspace health-check --input demo-inbox/synthetic.json --consent` after [initializing the optional demo](../../docs/workspace.md#synthetic-onboarding). The command writes no imported observations. If a real summary is approved for storage, use a separately authorized Vault asset. Keep raw records, exports, personal identifiers and devices out of this template.
