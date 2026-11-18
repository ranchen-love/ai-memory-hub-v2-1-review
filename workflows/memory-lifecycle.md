# Memory lifecycle

1. **Propose.** Capture a candidate in the [normalized envelope](../schemas/memory-candidate.schema.json) using a stable ID, source, sensitivity and classification.
2. **Validate and inspect.** Import the candidate with consent. Run `memory review` and compare the latest revision for duplicates, contradictory keys and source conflicts. Verify the evidence independently.
3. **Decide.** Apply the user's explicit acceptance, rejection or retirement. Use the current base revision and `import --review-decision --consent`. An inference or tentative note stays classified.
4. **Read back.** Check `memory show ID` and `memory history ID`, then reread the affected project or core notes. `workspace facts --consent` can produce an approved local projection of accepted records.
5. **Optional review channel.** An authorized private PR can carry only a separately reviewed non-sensitive proposal. Manual/local approval is the default. Do not send personal facts to the product repo.

A failed validation or a concurrent revision conflict leaves the active authoritative revision unchanged.
