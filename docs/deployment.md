# Deploy a local archive

Use Python 3.11 or newer and an owner-only Vault on a trusted local filesystem outside every Git checkout. Choose one sensitivity level for this Vault. Install from the pinned source checkout with `python -m pip install .`, or run `python -m ai_memory_hub` from that checkout. Keep Python, the checkout revision, and the Vault path stable for unattended runs.

## Initialize and authorize an input

```sh
python -m ai_memory_hub --root ../hub-demo init --wizard
python -m ai_memory_hub --root ../hub-demo source grant demo local_checkpoint --path examples --consent
python -m ai_memory_hub --root ../hub-demo local run --source demo
python -m ai_memory_hub --root ../hub-demo local status
```

Accept the Ordinary preset for weekly and on-demand defaults. The demo contains synthetic data. For real use choose a separate owner-controlled staging directory and grant one explicit source. Copy the supplied `memory-hub.json` example into the staging directory. Give each approved input its own stable item key. Use `user_upload` for an uploaded original and `ai_generated` for a generated output. Files are kept as bytes. PDF, DOCX, XLSX, PPTX, images, source and archive files use the same workflow.

A Codex workspace can supply an explicit manifest through `codex_workspace`. The `local_checkpoint` and `normalized` adapters use the same manifest. The source remains useful when a provider has no history API. Ask the authorized agent to write an evidence-backed normalized checkpoint, preserve unknown fields, and list only files the user selected. For subsequent L2 updates use the prior `base_revision`, and supply `append` for new entries. For L3 grant `--allow-raw` separately and use visible messages from the authorized source. A ChatGPT export grant can point to an eligible downloaded ZIP with recognized root conversation JSON shards, or to one extracted conversation JSON. Attachment bytes must be authorized through a separate file or manifest grant. [Official ChatGPT export instructions](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data)

`local run --source ID` is the one-command archive entry point after setup. It runs the `full` switch by default. Add `--mode weekly` or `--mode daily` to use the corresponding gate. Local weekly runs archive the selected source and report governance as `not_run`. The standard `sync weekly` continues to provide the built-in governance checks. A source records readable/missing/denied state, the last scan outcome and its own last successful archive. The local status indicates that the CLI opened this Vault and reports scheduler verification independently. A completed manual run records its own local result.

## Operate and recover

Keep grants, source item paths and Vault paths stable. Retry the same archive command after restoring a missing source. The earlier verified revision remains in the Vault when an original source disappears. Check an exact file revision with `asset check ID --version N` and recover it with `asset copy ID --version N --consent`. Read recorded failures with `local status`. A partial or failed scan exits nonzero. Resolve revision conflicts with a new checkpoint based on the current revision. Use `source revoke ID` to stop reading that source. Stored history remains subject to the retention and backup policy you approved.

For an optional local schedule use one Windows Task Scheduler task or one POSIX user scheduler entry, after explicitly approving the service identity and paths. Use an absolute Python or installed command path, a stable working directory, the exact Vault path, and `local run --mode weekly --source ID`. Configure a single instance, retain exit codes and timestamps, and use the same tested account and grant for a manual run first. Verify the next scheduled run in the operating system and in the Hub run report. An automation service with external connectors operates under its own scopes. Local Python and Vault permissions require the local execution account.

Back up the entire stopped Vault, including the SQLite index, content-addressed blobs and any required received receipts. Store backups in a separately authorized boundary. Test restore into an owner-only location with matching OS permissions and verify asset hashes and historical revisions. To upgrade, retain the pinned source and backup, then trial the new code against a restored copy. V2.2 uses the existing 2.1 record format; older executors have no V2.2 transfer commands. For rollback restore the prior code and its matching backup. Receipt and outgoing package files also contain sensitive data and follow the same retention policy.

## Share across isolated Vaults

Enable `handoff` in the sender and recipient Vaults. Review L2 and referenced versions first. A package contains context by default. Attach only the individually approved exact versions with repeated `--asset ID@REV`.

```sh
python -m ai_memory_hub --root ../hub-demo config set handoff on
python -m ai_memory_hub --root ../hub-demo transfer pack --project greenhouse-demo --asset calibration-notes@1 --consent
python -m ai_memory_hub --root ../recipient init
python -m ai_memory_hub --root ../recipient config set handoff on
python -m ai_memory_hub --root ../recipient transfer receive --input APPROVED_COPY.zip --consent
python -m ai_memory_hub --root ../recipient transfer inspect PACKAGE_ID --consent
python -m ai_memory_hub --root ../recipient transfer file PACKAGE_ID calibration-notes@1 --consent
```

The sender's result gives a ZIP path and ID. Transfer the reviewed ZIP through a channel separately approved for that recipient and sensitivity. The ZIP uses the same confidentiality as the selected transport and storage; it is an unencrypted archive. Authenticate the sender through that channel. SHA-256 verifies bytes and package consistency. The receipt is stored without merging unrelated IDs into the recipient's session or asset index. Inspection exposes recipient states separately from sender observations. A metadata-only package shows `not_transferred`, even if the sender reported availability. The recipient retrieves attached bytes from its own Vault. Package replays are idempotent and can repair missing received blobs. L3 and external-link targets are excluded. The byte limit is 1 GiB and the package accepts at most 256 selected revisions.

For a reproducible synthetic exercise including both Vaults, run `python scripts/smoke_v22.py`.
