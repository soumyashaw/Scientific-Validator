# Contract reference

Contracts are YAML or JSON objects with `contract_version: 1`. Unknown keys,
unsupported versions, invalid severities, conflicting bounds, bad symbolic
dimensions, duplicate relationship IDs, and invalid checksums are rejected
before input scanning.

## Top-level keys

| Key | Meaning |
| --- | --- |
| `dataset` | Required report identity |
| `formats` | Allowed `csv`, `jsonl` or `ndjson`, and `npz` formats |
| `unexpected_fields` | `allow`, `warn`, or `error` |
| `fields` | Required mapping of field name to rules |
| `relationships` | Named cross-field rules |
| `dataset_rules` | Rules requiring file or dataset state |
| `file_rules` | Non-empty and SHA-256 checks |
| `sample_limit` | Maximum source examples per finding, 0 to 1000 |
| `metadata` | User metadata preserved in the contract hash |

## Field rules

`type` accepts fixed NumPy-style integer and floating dtypes plus `number`,
`integer`, `bool`, `string`, `datetime`, and `object`. Safe widening is accepted,
so an integer can satisfy `float64`, while narrowing from `float64` to `float32`
is reported.

`shape` checks full dataset shape. Integers are fixed dimensions, `null` or `*`
is unconstrained, and uppercase names such as `N` are symbolic dimensions that
must agree between fields. CSV fields are one-dimensional. JSON arrays can form
higher-rank fields when every row has the same nested shape. NPZ dtypes and
shapes are preserved.

Value rules are `missing`, `nullable`, `finite`, `min`, `max`, inclusive flags,
`allowed`, `pattern`, string length bounds, monotonicity, and uniqueness.
Uniqueness is `file` or `global`. NaN and positive and negative infinity are
reported separately from explicit missing values.

## Relationships

Only named built-ins are accepted. Contracts do not execute expressions.

- `less`, `less_equal`, `greater`, `greater_equal`, `equal`, and `not_equal`
  compare `left` and `right` row by row.
- `norm_components` compares `field` with the Euclidean norm of `components`
  using `tolerance` as both absolute and relative tolerance.
- `required_if` requires `required_field` when `condition_field` equals
  `condition_value`.
- `mutually_exclusive` requires at most one named Boolean flag to be true.
- `shape_equal` checks the chunk shapes of two fields.

Every field and relationship accepts `severity: info|warning|error`.

## Dataset and file rules

- `row_count` has optional `min` and `max`.
- `invalid_fraction` counts distinct rows with a field or relationship
  violation, not the number of failed checks. It defaults to warning severity.
- `consistent_schema` compares field names, dtypes, and trailing dimensions to
  the first deterministically ordered partition.
- `duplicate_row_rate` stores exact row hashes and compares the observed rate to
  `max`.
- `category_coverage` lists required observed categories by field and defaults
  to warning.
- `file_rules.nonempty` defaults to true.
- `file_rules.checksums` maps an exact path or basename to a SHA-256 digest.

The authoritative machine-readable definition is
`schemas/contract-v1.schema.json`; the Python parser also applies semantic checks
that JSON Schema cannot express conveniently.

