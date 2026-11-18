# AI Memory Hub

AI Memory Hub is a local, platform-neutral CLI for personal memory candidates, conversation checkpoints, project state and file assets. Each instance has an owner-only vault. Install from a pinned release, then create one instance per audience and sensitivity class.

## Start with a synthetic demo

Use Python 3.11 or newer. From the code checkout, choose a new path outside the Git tree. Replace it with a path under your user profile for regular use.

```sh
python -m ai_memory_hub --root ../hub-demo init --wizard
python -m ai_memory_hub --root ../hub-demo source grant demo normalized --path examples --consent
python -m ai_memory_hub --root ../hub-demo sync full
python -m ai_memory_hub --root ../hub-demo session list --project greenhouse-demo
python -m ai_memory_hub --root ../hub-demo session show calibration-session --layer L2
python -m ai_memory_hub --root ../hub-demo asset check calibration-notes
python -m ai_memory_hub --root ../hub-demo asset copy calibration-notes --consent
python -m ai_memory_hub --root ../hub-demo sync status
```

Choose Ordinary or press Enter in the wizard. For unattended initialization use `init --preset ordinary`. The first sync creates four records. A retry reports four unchanged items. `asset copy` returns the path of a verified copy inside the owner-only vault. Run `asset refs calibration-notes` to trace references.

The module works directly from source without runtime dependencies. An optional package install uses `python -m pip install .` from the pinned checkout and installs the `ai-memory-hub` command. Set `AI_MEMORY_HUB_ROOT` in your shell if you use one instance often. Setup details, file versions and transfer examples are in [the user guide](docs/guide.md).

## Choose a sync preset

| Preset | Weekly review | On-demand import | Events | Daily catch-up | Project handoff |
|---|---|---|---|---|---|
| `ordinary` (default) | On | On | Off | Off | Off |
| `archive` | On | On | Off | On | Off |
| `collaboration` | On | On | On | On | On |

Use `config show`, `config preset archive` or `config set event on` after the root argument. Every optional switch is independent. The CLI reports scheduler verification separately. Use an existing authorized scheduler to invoke `sync weekly` if you need automatic execution. The recorded weekly preference is Sunday 23:00 Asia/Shanghai.

## What you can import

- A manually selected normalized JSON record with `import --input FILE --consent`.
- A grant to a local normalized inbox or Codex workspace folder with an explicit `memory-hub.json` selection.
- A locally selected ChatGPT conversation JSON export from an eligible account. Raw import requires a separate grant and accepts eligible visible text on the selected branch only.
- Any regular local file into the Vault, or a stable external URL as a reference. Link health reports declared expiry or a separately supplied observation. Local file checks validate SHA-256.

See [the protocol](docs/protocol.md), [JSON Schema](schemas/protocol.schema.json) and [platform guide](docs/adapters.md). The release uses the MIT license. See [security and storage boundaries](SECURITY.md) before using real data.
