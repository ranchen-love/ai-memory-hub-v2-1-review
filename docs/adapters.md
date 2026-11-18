# Source adapters

| Adapter | Read local input | Request provider export | File access | Provider write | Automatic trigger | Schedule execution |
|---|---|---|---|---|---|---|
| Manual CLI | Yes, explicitly selected | No | Explicit local file | No | No | No |
| Normalized manifest | Yes | No | Explicit manifest entries | No | No | No |
| Codex workspace | Yes | No | Explicit manifest entries | No | No | No |
| ChatGPT local export | Yes | No | Recognized conversation JSON members in ZIP or one JSON file | No | No | No |

Grant a directory with `source grant ID normalized --path PATH --consent` or use `codex_workspace` if it is an explicitly selected workspace. Place `memory-hub.json` there with a unique key per entry. Use paths relative to that directory. The manifest cannot select a symlink, reparse point or a parent path. You can generate the manifest and normalized records from checkpoints you can actually access. The CLI does not discover provider session databases or traverse the workspace automatically.

An eligible account can request a data export through ChatGPT settings or OpenAI's Privacy Portal. Choose the downloaded ZIP with supported root conversation shards, or select an extracted JSON with `source grant ID chatgpt_export --path PATH --consent`. The adapter understands the community-observed `mapping` / `current_node` conversation representation and uses the selected branch. This format is not an OpenAI API contract. Default import stores the title and provider reference. Include `--allow-raw` on a private/restricted grant only if the user authorized storing visible verbatim messages. This adapter imports eligible user/assistant text, skips hidden and nontext messages, and does not obtain attachments. For a different export shape or a managed workspace, follow the provider's approved export path and create normalized records manually. [Official OpenAI export instructions](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data)

An authorized integration can place an explicit event envelope under a granted directory and invoke `sync event --source ID --event event.json --consent`. Event dispatch checks the event switch, the active grant, the payload path and any previous receipt before writing. Codex documents lifecycle hooks for supported surfaces. A trusted local hook can invoke this path after the user sets up the hook, a stable instance path and the source authorization. There is no hook installation or global conversation watcher in the release. [Official hook documentation](https://learn.chatgpt.com/docs/hooks)

A connected app has the access granted by its provider and workspace. A connector for an external source is usable only after its owner has verified the connection, scopes and item permissions. This release relies on an authorized local export for ChatGPT conversations. [Official ChatGPT app permission documentation](https://help.openai.com/en/articles/20001495-managing-app-permissions-in-chatgpt)

Other providers can export manually or implement the adapter protocol if they have real scopes for reading, file access, writing or events. The core does not automatically obtain historical chats via ChatGPT connectors, request credentials or invoke provider APIs. Use an external authorized scheduler to invoke a scheduled sync. Review destination authorization before wiring a connector to any handoff.
