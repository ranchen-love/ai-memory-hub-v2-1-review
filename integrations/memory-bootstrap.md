# Memory bootstrap and shared version

1. Confirm the authorized workspace and Vault. Start with [AGENTS.md](../AGENTS.md) and the [core index](../core/INDEX.md).
2. Run `workspace check --path WORKSPACE` for local template and engine versions. Reread changed instructions and current record revisions.
3. For shared memory, use the version procedure below. Read the current project, permitted session layers and exact file revisions separately. Check local grants and archive coverage with `local status`.
4. Submit durable proposals through [candidate review](../workflows/memory-lifecycle.md). If access is unavailable, request an explicitly approved local snapshot or handoff and report the missing scope.

## Create and deliver an approved snapshot

From the owner's Vault, select only individually approved records. Each `--include SCOPE=ID` names one accepted memory and a stable scope. Repeat it for more records. Choose `--empty` explicitly to produce a deliberately empty snapshot. The output is a JSON file in the owner's Vault. The CLI sends nothing to a remote service. The owner reviews the selected content and transports it through a separately authorized channel. A receiver should place it in a directory they control, at a stable path. Keep raw messages, personal files and unapproved memory outside the package.

```sh
ai-memory-hub --root OWNER_VAULT version snapshot --name checkpoint-01 --include rules=memory-id --consent
```

The [snapshot schema](../schemas/shared-memory.schema.json) uses the normalized memory format and pins each record revision. The SHA-256 hashes canonical JSON. A digest identifies content, and the owner must establish the source's identity and permission through the approved channel. This works with local files supplied by any provider or a manually maintained checkout. No remote account, network monitoring or automatic sync is installed.

## Detect, read and confirm

Choose distinct IDs for each Agent. A channel pins one approved source path per Agent inside that receiving Vault. Update the file in place with an approved copy, preferably by moving a complete replacement into place. If the authorized source location changes, use a new channel and perform its first read.

```sh
ai-memory-hub --root RECEIVER_VAULT version check --channel shared --agent agent-b --snapshot APPROVED_JSON --consent
ai-memory-hub --root RECEIVER_VAULT version reload --channel shared --agent agent-b --scope rules --consent
ai-memory-hub --root RECEIVER_VAULT version confirm --channel shared --agent agent-b --sha DETECTED_SHA --receipt READ_RECEIPT --consent
```

Inspect the returned records before confirming. `reload` emits selected changed content and a one-time receipt for that Agent and SHA. Omit `--scope` to read all outstanding scopes, or repeat it to select a subset. A removed scope is returned as `null`. Complete the cycle for all changes before using cached shared instructions as current. Receipt confirmation records the Agent's explicit attestation that it reread the returned content. The engine can prove the scoped data was fetched, but cannot independently prove comprehension or the Agent's remote identity.

| Field or check result | Meaning |
| --- | --- |
| `first_check`, `changed`, `unchanged` | Comparison with the last successful detection, independent of confirmation |
| `unknown` and `availability: unavailable` | Source missing, invalid or outside the scope. Prior baselines are retained; current sync cannot be established |
| `detected_sha` | Latest successfully observed snapshot SHA |
| `synced_sha` | Last fully reread and explicitly confirmed SHA |
| `pending_reload` | A known SHA still awaits confirmation |
| `reload_scope` | Remaining scopes changed or removed since the confirmed baseline |
| `in_sync` | True only for a currently readable and fully confirmed version; unknown on an unavailable check |

Changing the source after a read invalidates its outstanding confirmation until a fresh check. A different Agent must read and confirm separately. The receiver stores local version and receipt metadata only. Snapshot application to its own facts requires the normal candidate review flow.
