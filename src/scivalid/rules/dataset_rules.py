"""Dataset-wide and cross-file state and final checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from ..contract import Contract
from ..models import Finding, Severity
from ..readers.base import DataChunk, ReaderMetadata
from .base import hashable_value


def _rule_config(raw: Any, default_severity: Severity) -> tuple:
    if isinstance(raw, dict):
        config = dict(raw)
        severity = Severity.parse(config.pop("severity", default_severity.value))
        return config, severity
    return {}, default_severity


@dataclass
class DatasetState:
    contract: Contract
    total_rows: int = 0
    invalid_rows: Set[Tuple[str, Any]] = field(default_factory=set)
    schemas: List[Tuple[str, Dict[str, Tuple[str, Tuple[int, ...]]]]] = field(default_factory=list)
    global_seen: Dict[str, Dict[Any, Tuple[str, Any]]] = field(default_factory=dict)
    category_values: Dict[str, Set[Any]] = field(default_factory=dict)
    duplicate_rows: int = 0
    examined_rows: int = 0
    _row_seen: Set[Any] = field(default_factory=set)

    def add_metadata(self, metadata: ReaderMetadata) -> None:
        self.total_rows += metadata.row_count
        schema = {
            name: (info.dtype, tuple(info.shape[1:]))
            for name, info in metadata.fields.items()
        }
        self.schemas.append((str(metadata.path), schema))

    def add_invalid(self, file_path: str, locations: Set[Any]) -> None:
        self.invalid_rows.update((file_path, location) for location in locations)

    def inspect_chunk(self, chunk: DataChunk) -> None:
        coverage = self.contract.dataset_rules.get("category_coverage", {})
        if isinstance(coverage, dict):
            for name in coverage:
                if name in chunk.values:
                    self.category_values.setdefault(name, set()).update(
                        hashable_value(item) for item in chunk.values[name].flat if item is not None
                    )

        if "duplicate_row_rate" in self.contract.dataset_rules:
            names = sorted(chunk.values)
            for index in range(chunk.row_count):
                row = tuple(
                    (name, hashable_value(chunk.values[name][index]))
                    for name in names
                    if chunk.values[name].ndim > 0 and index < chunk.values[name].shape[0]
                )
                if row in self._row_seen:
                    self.duplicate_rows += 1
                else:
                    self._row_seen.add(row)
                self.examined_rows += 1

    def finalize(self) -> List[Finding]:
        findings: List[Finding] = []
        row_rule = self.contract.dataset_rules.get("row_count")
        if row_rule is not None:
            config, severity = _rule_config(row_rule, Severity.ERROR)
            minimum = config.get("min")
            maximum = config.get("max")
            failed = (minimum is not None and self.total_rows < minimum) or (
                maximum is not None and self.total_rows > maximum
            )
            if failed:
                findings.append(Finding(
                    rule_id="dataset.row_count",
                    severity=severity,
                    dataset=self.contract.dataset,
                    message="Dataset row count is outside the declared range",
                    observed=self.total_rows,
                    expected={"min": minimum, "max": maximum},
                    affected_count=1,
                    examined_count=1,
                ))

        invalid_rule = self.contract.dataset_rules.get("invalid_fraction")
        if invalid_rule is not None:
            config, severity = _rule_config(invalid_rule, Severity.WARNING)
            maximum = config.get("max")
            fraction = len(self.invalid_rows) / self.total_rows if self.total_rows else 0.0
            if maximum is not None and fraction > maximum:
                findings.append(Finding(
                    rule_id="dataset.invalid_fraction",
                    severity=severity,
                    dataset=self.contract.dataset,
                    message="Fraction of rows with value or relationship violations is too high",
                    observed=fraction,
                    expected={"max": maximum},
                    affected_count=len(self.invalid_rows),
                    examined_count=self.total_rows,
                ))

        consistent = self.contract.dataset_rules.get("consistent_schema", False)
        if consistent and self.schemas:
            config, severity = _rule_config(consistent, Severity.ERROR)
            baseline_file, baseline = self.schemas[0]
            for path, schema in self.schemas[1:]:
                if schema != baseline:
                    findings.append(Finding(
                        rule_id="cross_file.consistent_schema",
                        severity=severity,
                        dataset=self.contract.dataset,
                        file=path,
                        message="Partition schema differs from the first file",
                        observed=schema,
                        expected={"file": baseline_file, "schema": baseline},
                        affected_count=1,
                        examined_count=1,
                        suggestion="Regenerate the partition with the same fields, dtypes, and feature dimensions.",
                    ))

        duplicate_rule = self.contract.dataset_rules.get("duplicate_row_rate")
        if duplicate_rule is not None:
            config, severity = _rule_config(duplicate_rule, Severity.WARNING)
            maximum = config.get("max")
            rate = self.duplicate_rows / self.examined_rows if self.examined_rows else 0.0
            if maximum is not None and rate > maximum:
                findings.append(Finding(
                    rule_id="dataset.duplicate_row_rate",
                    severity=severity,
                    dataset=self.contract.dataset,
                    message="Duplicate-row rate exceeds the declared maximum",
                    observed=rate,
                    expected={"max": maximum},
                    affected_count=self.duplicate_rows,
                    examined_count=self.examined_rows,
                ))

        coverage = self.contract.dataset_rules.get("category_coverage", {})
        if isinstance(coverage, dict):
            for name, required in coverage.items():
                if isinstance(required, dict):
                    config, severity = _rule_config(required, Severity.WARNING)
                    expected_values = set(config.get("required", []))
                else:
                    severity = Severity.WARNING
                    expected_values = set(required)
                missing = sorted(expected_values - self.category_values.get(name, set()), key=str)
                if missing:
                    findings.append(Finding(
                        rule_id="dataset.category_coverage.{}".format(name),
                        severity=severity,
                        dataset=self.contract.dataset,
                        field=name,
                        message="Required categories were not observed",
                        observed=sorted(self.category_values.get(name, set()), key=str),
                        expected=sorted(expected_values, key=str),
                        affected_count=len(missing),
                        examined_count=len(expected_values),
                    ))
        return findings
