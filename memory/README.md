# Memory index

The Vault is the authority for memory revisions. This directory holds optional reviewed views and workflow notes.

Use the [candidate form](../candidates/README.md) with source and an optional classification of fact, rule, preference or inference. Use `memory review` for duplicate keys and conflicts. Exact evidence, current base revision and explicit owner review govern acceptance; an inference remains labeled as such after review.

[Facts](facts.yaml) is an initially empty, replaceable local projection. Produce the reviewed projection with `workspace facts --path WORKSPACE --consent`. JSON output is also YAML-compatible. Do not put a populated projection in the product repository. Use [decisions](decisions.md), [changes](changelog.md) and [pending reviews](pending-review.md) as personal navigation.
