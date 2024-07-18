# Rule architecture

The base lifecycle is `begin_dataset`, `inspect_file_metadata`, `inspect_chunk`,
`merge_partial_state`, and `finalize_dataset`. Version 0.1.0 exposes the base
class for extension but intentionally accepts only built-in rule names in
untrusted contracts.

Built-in field checks are fused in `ValueRule` so one reader pass can evaluate
missing, finite, range, vocabulary, string, monotonicity, and uniqueness rules.
`RelationshipRule` evaluates only named operations. `DatasetState` owns mergeable
cross-chunk and cross-file state.

Streaming counters and bounded samples have memory independent of row count.
Exact uniqueness and duplicate-row state set `bounded_memory = false` in the
conceptual resource model and are disclosed in report metrics. New rules must
document which category they occupy and may never silently approximate an exact
contract.

Loading executable custom rules from a YAML file is deliberately unsupported.
A future trusted-code plugin API will require explicit local opt-in.

