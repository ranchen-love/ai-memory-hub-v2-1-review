# Local configuration

`sync-defaults.json` documents the ordinary preset. The Vault settings are authoritative after initialization. Use `config show` and `config set FEATURE on|off` for changes. Source authorization, archive outcome and scheduler verification are separate.

The initializer writes `workspace.json` with the local Vault path and template version. Keep it local. The default creates no grants and installs no scheduled tasks. See [deployment](../docs/deployment.md).
