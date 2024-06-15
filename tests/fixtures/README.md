# Test fixtures

Tests create compact CSV, JSON Lines, and NPZ fixtures in temporary directories.
This keeps intentionally malformed binary inputs out of the repository while
still covering truncated NPZ data, malformed JSON, missing values, NaN,
infinities, chunk boundaries, duplicate IDs, and shape mismatches.

