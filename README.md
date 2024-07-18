# SciValid

SciValid is a command-line and Python validator for scientific datasets. It
checks files against explicit, reviewable contracts before analysis begins. The
0.1.0 release supports CSV, JSON Lines, and NumPy NPZ through one reader
interface, chunked field checks, named cross-field relationships, exact global
uniqueness, cross-file schema checks, and terminal, JSON, and HTML reports.

SciValid checks structural and contract validity. It does **not** decide whether
data or a scientific conclusion is true. Distribution or coverage deviations
are warnings unless the contract explicitly assigns error severity.

## Quick start

Python 3.8 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

scivalid check examples/particle_events/invalid \
  --contract examples/particle_events/contract.yaml \
  --report-json build/particle-report.json \
  --report-html build/particle-report.html
```

The command exits with status 1 because the example intentionally contains a
missing field, NaN, a negative energy, an unknown category, reversed times, a
non-numeric value, an ID duplicated across files, and inconsistent partition
schemas. Its abbreviated terminal output is:

```text
SciValid 0.1.0 — FAIL
Dataset: particle-events | Files: 3 | Rows: 6
Findings: 10 error(s), 1 warning(s), 0 info
[WARNING] dataset.invalid_fraction particle-events — Fraction of rows with value or relationship violations is too high (4 affected)
[ERROR] schema.required.end_time .../missing-column.csv:end_time — Required field is missing (1 affected)
[ERROR] finite.energy_gev .../part-01.csv:energy_gev — Non-finite values found (1 affected)
```

Open [the generated HTML report](build/particle-report.html) for the full table,
or inspect the JSON report in automation. A finding looks like this:

```json
{
  "rule_id": "finite.energy_gev",
  "severity": "ERROR",
  "field": "energy_gev",
  "message": "Non-finite values found",
  "observed": {
    "nan": 1,
    "positive_infinity": 0,
    "negative_infinity": 0
  },
  "affected_count": 1,
  "examined_count": 3,
  "sample_locations": [1]
}
```

Errors represent violated hard contracts. Warnings represent non-fatal policy or
statistical concerns. INFO is available for contracts that want to record a
deviation without failing or warning. `--strict` makes warnings return exit 1.

Run the valid example to see a clean multi-file check:

```bash
scivalid check examples/particle_events/valid \
  --contract examples/particle_events/contract.yaml
```

## Contract example

```yaml
contract_version: 1
dataset: particle-events
formats: [csv]
unexpected_fields: warn

fields:
  event_id:
    type: int64
    unique: global
  energy_gev:
    type: float64
    finite: true
    min: 0.0
  category:
    type: string
    allowed: [signal, background, control]

relationships:
  - id: start_before_end
    rule: less_equal
    left: start_time
    right: end_time
    severity: error

dataset_rules:
  row_count: {min: 1}
  consistent_schema: true
  invalid_fraction: {max: 0.001, severity: warning}
```

Contracts never execute arbitrary Python. The supported keys and named
relationships are documented in [the contract reference](docs/contract_reference.md)
and published as [JSON Schema](schemas/contract-v1.schema.json).

## Commands and exit codes

```bash
scivalid check DATA... --contract CONTRACT.yaml
scivalid inspect sample.npz
scivalid contract validate contract.yaml
scivalid compare-schema file-a.csv file-b.csv
```

| Code | Meaning |
| ---: | --- |
| 0 | Validation completed with no ERROR findings |
| 1 | Validation completed with ERROR findings, or warnings under `--strict` |
| 2 | Contract or command configuration is invalid |
| 3 | An operational failure prevented complete validation |
| 4 | A requested optional reader dependency is unavailable |

Warnings do not fail by default. Reports are still written when data findings
are present. A malformed or unreadable file remains in the larger run context
and produces exit 3.

## Python API

```python
from scivalid import validate

report = validate(
    paths=["data/part-*.csv"],
    contract="contract.yaml",
    chunk_size=50_000,
)

if report.has_errors:
    raise RuntimeError(report.summary)
```

`examples/workflow_gate.py` shows a complete quality gate that runs downstream
work only after a successful report. CI and workflow engines such as BatchFlow
can use either the API or the documented exit codes.

## Architecture

The contract is validated before inputs are opened. The planner resolves files
in deterministic order and asks readers for required fields. Readers expose
metadata and chunks in one common model. Field and relationship rules inspect a
chunk in a fused pass, while dataset state merges global counts and exact sets.
Every reporter renders the same canonical `Report` object.

```text
contract → planner → reader chunks → field/relationship rules → dataset state
                                                               ↓
                                      terminal ← canonical report → JSON / HTML
```

Reader plugins can be registered through the `scivalid.readers` entry-point
group. See [reader plugins](docs/reader_plugins.md) and
[rule architecture](docs/rule_plugins.md).

## Reproducibility and resource policy

- Input enumeration and finding order are deterministic.
- Reports include input paths, UTC timestamps, versions, and a SHA-256 hash of
  the normalized contract.
- Samples are bounded by `sample_limit`; counts are not truncated.
- Streaming rules use memory bounded by the chunk size.
- Exact global uniqueness and exact duplicate-row rate intentionally use memory
  proportional to distinct values. `--max-exact-values` rejects files above a
  configured policy limit rather than silently weakening a rule.
- NPZ files are opened with `allow_pickle=False`.
- SciValid never modifies source data.

See [limitations](docs/limitations.md) for format and scale boundaries.

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest
# Dependency-light fallback used during development:
PYTHONPATH=src python -m unittest discover -s tests -v
```

The tests include deliberately malformed data, boundary conditions, chunk
invariance, global duplicates, equivalent logical data across formats, and
report-schema checks when `jsonschema` is installed. Run the benchmark harness
without treating unmeasured values as claims:

```bash
PYTHONPATH=src python benchmarks/benchmark_validation.py --rows 100000
```

## Provenance

The design was informed by the data-validation learning resources listed in
[UPSTREAM.md](UPSTREAM.md). SciValid is an independent implementation; no source
code from those examples is copied. The repository keeps exact reference
commits and licensing notes so the relationship remains transparent.

## License

[MIT](LICENSE)
