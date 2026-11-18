# Handoff protocol

Pick the project ID and review its session checkpoint revisions, current state, decisions, outcomes and next actions. Confirm which file versions the recipient needs and verify exact bytes.

Use `handoff --project ID --consent` for a local context snapshot. For separate environments enable the handoff switch in both Vaults and use `transfer pack --project ID`. Exact `--asset ID@REV` entries require approval. Transport the package through a channel authorized for that audience. The recipient independently consents, inspects its own availability and verifies bytes. L3 remains in the originating Vault.
