"""Named, non-executable cross-field relationship rules."""

from __future__ import annotations

from typing import Any, Dict, List, Set

import numpy as np

from ..contract import Contract, RelationshipContract
from ..models import Finding
from ..readers.base import DataChunk
from .base import FindingAccumulator, Rule, invalid_rows_from_mask, mask_samples, missing_mask


class RelationshipRule(Rule):
    def __init__(self, contract: Contract, file_path: str, reader: str):
        self.contract = contract
        self.file_path = file_path
        self.reader = reader
        self.accumulators: Dict[str, FindingAccumulator] = {}
        self.invalid_locations: Set[Any] = set()

    def _acc(self, relationship: RelationshipContract, message: str, expected: Any) -> FindingAccumulator:
        if relationship.id not in self.accumulators:
            self.accumulators[relationship.id] = FindingAccumulator(
                rule_id="relationship.{}".format(relationship.id),
                severity=relationship.severity,
                dataset=self.contract.dataset,
                file=self.file_path,
                field_name=None,
                message=message,
                expected=expected,
                suggestion="Review the related source fields; SciValid will not alter them.",
                reader=self.reader,
                sample_limit=self.contract.sample_limit,
            )
        return self.accumulators[relationship.id]

    def _observe(self, acc: FindingAccumulator, mask: np.ndarray, chunk: DataChunk, observed: Any = None) -> None:
        mask = np.asarray(mask, dtype=bool)
        if mask.ndim > 1:
            mask = np.any(mask, axis=tuple(range(1, mask.ndim)))
        acc.add(
            int(np.count_nonzero(mask)),
            int(mask.size),
            mask_samples(mask, chunk.locations, self.contract.sample_limit),
            observed,
        )
        self.invalid_locations.update(invalid_rows_from_mask(mask, chunk.locations))

    def inspect_chunk(self, chunk: DataChunk) -> None:
        for relationship in self.contract.relationships:
            config = relationship.config
            rule = relationship.rule
            if rule in {"less", "less_equal", "greater", "greater_equal", "equal", "not_equal"}:
                if config["left"] not in chunk.values or config["right"] not in chunk.values:
                    continue
                left = np.asarray(chunk.values[config["left"]])
                right = np.asarray(chunk.values[config["right"]])
                length = min(left.shape[0], right.shape[0])
                left, right = left[:length], right[:length]
                try:
                    if rule == "less":
                        valid = left < right
                        symbol = "<"
                    elif rule == "less_equal":
                        valid = left <= right
                        symbol = "<="
                    elif rule == "greater":
                        valid = left > right
                        symbol = ">"
                    elif rule == "greater_equal":
                        valid = left >= right
                        symbol = ">="
                    elif rule == "equal":
                        valid = left == right
                        symbol = "=="
                    else:
                        valid = left != right
                        symbol = "!="
                except (TypeError, ValueError):
                    valid = np.zeros(length, dtype=bool)
                    symbol = rule
                missing = missing_mask(left) | missing_mask(right)
                invalid = ~np.asarray(valid, dtype=bool) & ~missing
                acc = self._acc(
                    relationship,
                    "Cross-field relationship failed",
                    "{} {} {}".format(config["left"], symbol, config["right"]),
                )
                self._observe(acc, invalid, chunk)
            elif rule == "norm_components":
                names = list(config["components"])
                if config["field"] not in chunk.values or any(name not in chunk.values for name in names):
                    continue
                target = np.asarray(chunk.values[config["field"]], dtype=float)
                components = [np.asarray(chunk.values[name], dtype=float) for name in names]
                norm = np.sqrt(sum(component * component for component in components))
                tolerance = float(config.get("tolerance", 1e-6))
                invalid = ~np.isclose(target, norm, rtol=tolerance, atol=tolerance, equal_nan=False)
                acc = self._acc(
                    relationship,
                    "Vector norm does not agree with its components",
                    {"components": names, "tolerance": tolerance},
                )
                self._observe(acc, invalid, chunk)
            elif rule == "required_if":
                condition_name = config["condition_field"]
                required_name = config["required_field"]
                if condition_name not in chunk.values or required_name not in chunk.values:
                    continue
                condition = np.asarray(chunk.values[condition_name]) == config["condition_value"]
                invalid = condition & missing_mask(np.asarray(chunk.values[required_name]))
                acc = self._acc(
                    relationship,
                    "Conditionally required value is missing",
                    "{} required when {} == {!r}".format(required_name, condition_name, config["condition_value"]),
                )
                self._observe(acc, invalid, chunk)
            elif rule == "mutually_exclusive":
                names = list(config["flags"])
                if any(name not in chunk.values for name in names):
                    continue
                total = sum(np.asarray(chunk.values[name], dtype=bool).astype(int) for name in names)
                invalid = total > 1
                acc = self._acc(
                    relationship,
                    "Mutually exclusive flags are simultaneously true",
                    {"at_most_one_true": names},
                )
                self._observe(acc, invalid, chunk)
            elif rule == "shape_equal":
                if config["left"] not in chunk.values or config["right"] not in chunk.values:
                    continue
                left_shape = np.asarray(chunk.values[config["left"]]).shape
                right_shape = np.asarray(chunk.values[config["right"]]).shape
                invalid = np.asarray([left_shape != right_shape], dtype=bool)
                acc = self._acc(
                    relationship,
                    "Field shapes are not equal",
                    {"left": config["left"], "right": config["right"]},
                )
                self._observe(acc, invalid, chunk, observed={"left": left_shape, "right": right_shape})

    def finalize_dataset(self) -> List[Finding]:
        return [item for item in (acc.finding() for acc in self.accumulators.values()) if item is not None]

