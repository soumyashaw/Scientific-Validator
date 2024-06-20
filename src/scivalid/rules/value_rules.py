"""Streaming missing, finite, range, category, string, monotonic, and unique rules."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ..contract import Contract, FieldContract
from ..models import Finding
from ..readers.base import DataChunk, logical_dtype
from .base import (
    FindingAccumulator,
    Rule,
    hashable_value,
    invalid_rows_from_mask,
    mask_samples,
    missing_mask,
    row_values,
)
from .schema_rules import dtype_compatible


class ValueRule(Rule):
    """One fused pass over all configured field-level rules for one file."""

    def __init__(
        self,
        contract: Contract,
        file_path: str,
        reader: str,
        global_seen: Dict[str, Dict[Any, Tuple[str, Any]]],
    ):
        self.contract = contract
        self.file_path = file_path
        self.reader = reader
        self.global_seen = global_seen
        self.accumulators: Dict[str, FindingAccumulator] = {}
        self.invalid_locations: Set[Any] = set()
        self.local_seen: Dict[str, Dict[Any, Any]] = {}
        self.previous: Dict[str, Any] = {}

    def _acc(
        self,
        key: str,
        field: FieldContract,
        message: str,
        expected: Any,
        suggestion: Optional[str] = None,
    ) -> FindingAccumulator:
        if key not in self.accumulators:
            self.accumulators[key] = FindingAccumulator(
                rule_id=key,
                severity=field.severity,
                dataset=self.contract.dataset,
                file=self.file_path,
                field_name=field.name,
                message=message,
                expected=expected,
                suggestion=suggestion,
                reader=self.reader,
                sample_limit=self.contract.sample_limit,
            )
        return self.accumulators[key]

    def _observe_mask(
        self,
        accumulator: FindingAccumulator,
        mask: np.ndarray,
        locations: List[Any],
        observed: Any = None,
        examined: Optional[int] = None,
    ) -> None:
        mask = np.asarray(mask, dtype=bool)
        affected = int(np.count_nonzero(mask))
        accumulator.add(
            affected,
            int(mask.size if examined is None else examined),
            mask_samples(mask, locations, self.contract.sample_limit),
            observed,
        )
        self.invalid_locations.update(invalid_rows_from_mask(mask, locations))

    def _numeric(self, values: np.ndarray) -> Optional[np.ndarray]:
        if values.dtype.kind in ("i", "u", "f"):
            return values
        if values.dtype.kind == "O":
            try:
                converted = np.asarray([
                    np.nan if item is None else float(item) for item in values.flat
                ], dtype=float).reshape(values.shape)
                return converted
            except (TypeError, ValueError):
                return None
        return None

    def inspect_chunk(self, chunk: DataChunk) -> None:
        for name, field in self.contract.fields.items():
            if name not in chunk.values:
                continue
            values = np.asarray(chunk.values[name])
            missing = missing_mask(values)
            if field.missing == "forbid":
                acc = self._acc(
                    "missing.{}".format(name),
                    field,
                    "Missing values found",
                    "no missing values",
                    "Populate the value at the source or explicitly allow missing values.",
                )
                self._observe_mask(acc, missing, chunk.locations)

            actual_type = logical_dtype(values)
            if field.type and not dtype_compatible(field.type, actual_type):
                acc = self._acc(
                    "type.{}".format(name),
                    field,
                    "Values have an incompatible type",
                    field.type,
                    "Convert the producer output explicitly; SciValid does not coerce it.",
                )
                row_mask = np.ones(values.shape[0] if values.ndim else 1, dtype=bool)
                self._observe_mask(acc, row_mask, chunk.locations, observed=actual_type)

            numeric = self._numeric(values)
            if field.finite and numeric is not None:
                invalid = ~np.isfinite(numeric) & ~missing
                counts = {
                    "nan": int(np.count_nonzero(np.isnan(numeric))),
                    "positive_infinity": int(np.count_nonzero(np.isposinf(numeric))),
                    "negative_infinity": int(np.count_nonzero(np.isneginf(numeric))),
                }
                acc = self._acc(
                    "finite.{}".format(name),
                    field,
                    "Non-finite values found",
                    "all values finite",
                    "Repair or filter the source values before analysis.",
                )
                self._observe_mask(acc, invalid, chunk.locations, observed=counts)

            valid_numeric = numeric is not None
            if valid_numeric and field.minimum is not None:
                with np.errstate(invalid="ignore"):
                    invalid = numeric < field.minimum if field.min_inclusive else numeric <= field.minimum
                    invalid &= ~missing & np.isfinite(numeric)
                operator = ">=" if field.min_inclusive else ">"
                acc = self._acc(
                    "range.min.{}".format(name),
                    field,
                    "Values below the minimum found",
                    "{} {}".format(operator, field.minimum),
                    "Check units, calibration, and producer-side bounds.",
                )
                self._observe_mask(acc, invalid, chunk.locations)
            if valid_numeric and field.maximum is not None:
                with np.errstate(invalid="ignore"):
                    invalid = numeric > field.maximum if field.max_inclusive else numeric >= field.maximum
                    invalid &= ~missing & np.isfinite(numeric)
                operator = "<=" if field.max_inclusive else "<"
                acc = self._acc(
                    "range.max.{}".format(name),
                    field,
                    "Values above the maximum found",
                    "{} {}".format(operator, field.maximum),
                    "Check units, calibration, and producer-side bounds.",
                )
                self._observe_mask(acc, invalid, chunk.locations)

            if field.allowed is not None:
                try:
                    invalid = ~np.isin(values, field.allowed) & ~missing
                except (TypeError, ValueError):
                    invalid = np.asarray([
                        item is not None and hashable_value(item) not in set(map(hashable_value, field.allowed))
                        for item in values.flat
                    ], dtype=bool).reshape(values.shape)
                acc = self._acc(
                    "allowed.{}".format(name),
                    field,
                    "Values outside the allowed vocabulary found",
                    field.allowed,
                    "Review category spelling or update the contract deliberately.",
                )
                self._observe_mask(acc, invalid, chunk.locations)

            if field.pattern is not None:
                regex = re.compile(field.pattern)
                invalid = np.zeros(values.shape, dtype=bool)
                for index, item in np.ndenumerate(values):
                    if item is not None and not regex.fullmatch(str(item)):
                        invalid[index] = True
                acc = self._acc(
                    "pattern.{}".format(name), field, "Strings do not match the required pattern", field.pattern
                )
                self._observe_mask(acc, invalid, chunk.locations)

            if field.min_length is not None or field.max_length is not None:
                invalid = np.zeros(values.shape, dtype=bool)
                for index, item in np.ndenumerate(values):
                    if item is None:
                        continue
                    length = len(str(item))
                    if field.min_length is not None and length < field.min_length:
                        invalid[index] = True
                    if field.max_length is not None and length > field.max_length:
                        invalid[index] = True
                expected = {"min_length": field.min_length, "max_length": field.max_length}
                acc = self._acc(
                    "length.{}".format(name), field, "String lengths violate the contract", expected
                )
                self._observe_mask(acc, invalid, chunk.locations)

            if field.monotonic and values.ndim == 1:
                comparable = [(index, item) for index, item in enumerate(values.tolist()) if item is not None]
                invalid = np.zeros(values.shape, dtype=bool)
                previous = self.previous.get(name)
                for index, item in comparable:
                    if previous is not None:
                        if field.monotonic == "increasing":
                            bad = item < previous
                        elif field.monotonic == "strict_increasing":
                            bad = item <= previous
                        elif field.monotonic == "decreasing":
                            bad = item > previous
                        else:
                            bad = item >= previous
                        invalid[index] = bad
                    previous = item
                if previous is not None:
                    self.previous[name] = previous
                acc = self._acc(
                    "monotonic.{}".format(name), field, "Monotonicity violations found", field.monotonic
                )
                self._observe_mask(acc, invalid, chunk.locations)

            if field.unique:
                seen = self.local_seen.setdefault(name, {}) if field.unique == "file" else self.global_seen.setdefault(name, {})
                invalid = np.zeros(values.shape[0] if values.ndim else 1, dtype=bool)
                for index, item in enumerate(row_values(values)):
                    location = chunk.locations[index] if index < len(chunk.locations) else chunk.start + index
                    if item in seen:
                        invalid[index] = True
                    else:
                        seen[item] = (self.file_path, location) if field.unique == "global" else location
                scope = "across all files" if field.unique == "global" else "within each file"
                acc = self._acc(
                    "unique.{}".format(name),
                    field,
                    "Duplicate values found {}".format(scope),
                    "unique values {}".format(scope),
                    "Regenerate identifiers or review partition boundaries.",
                )
                self._observe_mask(acc, invalid, chunk.locations)

    def finalize_dataset(self) -> List[Finding]:
        return [item for item in (acc.finding() for acc in self.accumulators.values()) if item is not None]

