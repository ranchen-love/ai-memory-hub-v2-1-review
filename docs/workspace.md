# Initialize a personal memory workspace

The distribution includes neutral instructions, templates and a local engine. The installer copies only the approved template files into a new owner-only workspace. A separate owner-only Vault stores durable records, raw messages and file bytes. Choose local paths outside Git that have trusted existing parents.

```sh
python -m pip install .
ai-memory-hub workspace init --path ../my-hub
ai-memory-hub workspace check --path ../my-hub
```

By default the Vault is a sibling named `my-hub-vault` and the sensitivity is private. To choose a separate existing parent or sensitivity, use `--vault PATH --sensitivity LEVEL`. Both targets must be new, on the local boundary, and outside each other. Keep the same version of the engine and a protected backup of both directories. A second init refuses to replace profiles or existing notes. If an interrupted initialization left a directory, inspect it before any recovery and choose new paths for another run. The installed CLI works from outside this source checkout. You can use `python -m ai_memory_hub` if the installed command is unavailable.

Start at [AGENTS.md](../AGENTS.md) inside the new workspace and follow the [core index](../core/INDEX.md). The binding in `config/workspace.json` pins the local Vault identity and directory. Restore the matching Vault and workspace backups as a pair. A safe empty workspace authorizes no sources, stores no records and installs no scheduler. Ordinary sync defaults are weekly and on demand only.

## Synthetic onboarding

Start with a separate new pair for the example:

```sh
ai-memory-hub workspace init --path ../hub-demo --demo
ai-memory-hub --root ../hub-demo-vault source grant sample normalized --path ../hub-demo/demo-inbox --consent
ai-memory-hub --root ../hub-demo-vault local run --source sample
ai-memory-hub --root ../hub-demo-vault memory review
ai-memory-hub --root ../hub-demo-vault project list
ai-memory-hub --root ../hub-demo-vault session list
ai-memory-hub --root ../hub-demo-vault asset check calibration-notes
ai-memory-hub --root ../hub-demo-vault config set handoff on
ai-memory-hub --root ../hub-demo-vault handoff --project greenhouse-demo --consent
```

The demo generates an evidence-backed synthetic candidate, project, L2 checkpoint and file manifest in `demo-inbox`. Imported records use the Vault's configured sensitivity. A second local run keeps unchanged revisions. To practice acceptance, use the actual candidate ID from the manifest's memory envelope. Copy that envelope, set `base_revision` to its current revision and change its status to `accepted` after review. Import the copy using `--review-decision --consent`. The local facts projection includes only accepted records and never pushes them to Git.

```sh
ai-memory-hub workspace facts --path ../hub-demo --consent
ai-memory-hub workspace health-check --input ../hub-demo/demo-inbox/synthetic.json --consent
```

For offline cross-agent transfer, enable handoff on both Vaults and follow [deployment and exact-version transfer](deployment.md). Review any selected files and obtain recipient authorization before transporting the ZIP. The receiver verifies its own byte availability. L3 requires its own archive and read consent and stays at the origin.

## Customize and maintain

- Use the [memory governance](../workflows/memory-lifecycle.md), [project template](../projects/TEMPLATE.md) and [life archive](../life-archive/README.md) as local, owner-approved inputs.
- `workspace check` displays versions and the Vault's settings, tests workspace navigation and summarizes coverage. Unknown profile categories remain unknown.
- Check `local status` for read grants, last successful archive and production scheduling evidence. [Bootstrap](../integrations/memory-bootstrap.md) describes fallback when a new Agent lacks access.
- Stop executors before backup. Protect both snapshots, record hashes, trial upgrades with copies and verify the Vault binding if moving a workspace. Keep the matching prior engine and backup for rollback. The new workspace format adds no required field to existing 2.2 Vault records.
- Keep actual workspaces and Vaults outside the product repo. An explicitly approved private repository can host a separately reviewed, non-sensitive projection. The generated workspace's Git ignore rules exclude all data by default.
