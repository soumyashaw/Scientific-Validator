# Limitations

- CSV inference is conservative and scans metadata before validation. CSV has
  no native dtype or multidimensional array metadata.
- JSON Lines supports top-level object fields. Ragged arrays are reported as
  object dtype and shape mismatch rather than padded or coerced.
- NPZ archives are opened with NumPy and pickle disabled. Compressed members may
  still be decompressed in memory by NumPy.
- Exact global uniqueness and duplicate-row rate use memory proportional to the
  number of distinct values. Use `--max-exact-values` as a hard planning policy.
- Dataset row count is the sum of reader-declared leading dimensions. It does
  not prove that partitions represent independent observations.
- Statistical rules currently cover invalid fraction and category coverage;
  they do not detect arbitrary distribution shift.
- Contract-safe readers are built in only for CSV, JSON Lines, and NPZ.
  Parquet, HDF5, and ROOT are roadmap items.
- Readers validate top-level structure but cannot detect every form of physical
  media corruption that remains parseable.
- SciValid reports issues and never repairs input data.
- Passing validation means the declared contract passed. It is not evidence of
  scientific correctness, causal validity, or absence of bias.

