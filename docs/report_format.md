# Report format

All reporters consume the same `Report` instance. JSON output conforms to
`schemas/report-v1.schema.json` and starts with `report_version: 1`.

Top-level provenance includes the validator version, normalized-contract
SHA-256 hash, UTC start and completion times, deterministic input list, file
summaries, completion state, summary counts, and execution metrics.

Every finding has a stable rule ID, severity, dataset, message, bounded source
locations, and validator version. File, field, observed and expected values,
counts, reader, and remediation are present when applicable. A finding count is
never truncated when its location sample reaches the configured limit.

`completed: false` means an operational error prevented a complete scan. This is
different from a complete report whose contract checks failed.

Timestamps and absolute paths are expected to vary in golden tests. Consumers
should use `report_version` and rule IDs rather than matching prose.

