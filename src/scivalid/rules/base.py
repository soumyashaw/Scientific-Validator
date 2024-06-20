"""Rule lifecycle and finding aggregation primitives."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np

from ..models import Finding, Severity


@dataclass
class FindingAccumulator:
    rule_id: str
    severity: Severity
    dataset: str
    file: Optional[str]
    field_name: Optional[str]
    message: str
    expected: Any
    suggestion: Optional[str]
    reader: Optional[str]
    sample_limit: int
    affected: int = 0
    examined: int = 0
    samples: List[Any] = field(default_factory=list)
    observed: Any = None

    def add(self, affected: int, examined: int, locations: Iterable[Any], observed: Any = None) -> None:
        self.affected += int(affected)
        self.examined += int(examined)
        if observed is not None:
            self.observed = observed
        for location in locations:
            if len(self.samples) >= self.sample_limit:
                break
            if location not in self.samples:
                self.samples.append(location)

    def finding(self) -> Optional[Finding]:
        if self.affected <= 0:
            return None
        return Finding(
            rule_id=self.rule_id,
            severity=self.severity,
            dataset=self.dataset,
            file=self.file,
            field=self.field_name,
            message=self.message,
            observed=self.observed,
            expected=self.expected,
            affected_count=self.affected,
            examined_count=self.examined,
            sample_locations=self.samples,
            suggestion=self.suggestion,
            reader=self.reader,
        )


class Rule(ABC):
    """Streaming rule lifecycle. Subclasses may implement only needed hooks."""

    bounded_memory = True

    def begin_dataset(self) -> None:
        pass

    def inspect_file_metadata(self, metadata: Any) -> None:
        pass

    def inspect_chunk(self, chunk: Any) -> None:
        pass

    def merge_partial_state(self, other: "Rule") -> None:
        raise NotImplementedError

    def finalize_dataset(self) -> List[Finding]:
        return []


def missing_mask(values: np.ndarray) -> np.ndarray:
    """Detect explicit missing values while keeping NaN distinct."""
    if values.dtype.kind == "M":
        return np.isnat(values)
    if values.dtype.kind != "O":
        return np.zeros(values.shape, dtype=bool)
    result = np.zeros(values.shape, dtype=bool)
    for index, item in np.ndenumerate(values):
        result[index] = item is None
    return result


def mask_samples(mask: np.ndarray, locations: List[Any], limit: int) -> List[Any]:
    samples: List[Any] = []
    if limit <= 0:
        return samples
    for index in np.argwhere(mask):
        row_index = int(index[0]) if len(index) else 0
        source = locations[row_index] if row_index < len(locations) else row_index
        if len(index) == 1:
            location: Any = source
        else:
            location = [source] + [int(item) for item in index[1:]]
        samples.append(location)
        if len(samples) >= limit:
            break
    return samples


def invalid_rows_from_mask(mask: np.ndarray, locations: List[Any]) -> Set[Any]:
    if mask.ndim == 0:
        return {locations[0]} if bool(mask) and locations else set()
    row_mask = mask if mask.ndim == 1 else np.any(mask, axis=tuple(range(1, mask.ndim)))
    return {locations[index] for index in np.flatnonzero(row_mask) if index < len(locations)}


def hashable_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return tuple(hashable_value(item) for item in value.tolist())
    if isinstance(value, list):
        return tuple(hashable_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, hashable_value(item)) for key, item in value.items()))
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        if np.isnan(value):
            return ("__scivalid_nan__",)
        if np.isposinf(value):
            return ("__scivalid_positive_infinity__",)
        if np.isneginf(value):
            return ("__scivalid_negative_infinity__",)
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


def row_values(values: np.ndarray) -> List[Any]:
    if values.ndim == 0:
        return [values.item()]
    return [hashable_value(values[index]) for index in range(values.shape[0])]
