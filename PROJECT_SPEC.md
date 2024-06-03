# Scientific-Validator implementation target

SciValid validates scientific datasets against explicit contracts before
analysis. It checks accessibility, schema, dtypes, shapes, numerical values,
named cross-field relationships, dataset-wide properties, and consistency
across files. It produces a canonical result for people, CI, and workflow
engines.

The project boundary is deliberate. Structural validity, contract validity, and
statistical warnings are within scope. Scientific interpretation and claims of
truth are outside the tool's authority. Automatic modification is disabled.

Version 0.1.0 is complete when CSV, JSON Lines, and NPZ share a reader
interface; contracts and reports have versioned schemas; streaming rules keep
bounded samples; global and cross-file checks work across chunks; reports and
exit codes are stable; corrupted fixtures are tested; and a workflow example
uses validation as a quality gate. The detailed behavior is documented in the
repository's contract, report, plugin, and limitation references.

