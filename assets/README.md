# Asset references

[manifest.json](manifest.json) is an empty local index template. The live inventory is available through `asset list`. An asset is identified by ID and revision; the SHA-256 identifies exact stored bytes. The same bytes can be referenced by multiple revisions without losing provenance.

Record the origin as user upload or AI output, authorized evidence, linked project/session and exact version. Verify with `asset check ID --version N`. Use an authorized `asset copy` to retrieve bytes. Link-only entries record reference status separately from persisted Vault bytes. See [the asset and file reference definitions](../schemas/protocol.schema.json#/$defs/asset) and [authorized transfer](../collaboration/handoff-protocol.md).
