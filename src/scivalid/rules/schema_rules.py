"""Required-field, dtype, rank, shape, and unexpected-field rules."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from ..contract import Contract, FieldContract
from ..models import Finding, Severity
from ..readers.base import ReaderMetadata


def dtype_compatible(expected: str, actual: str) -> bool:
    if actual == "missing":
        return True
    if expected == actual or expected == "object":
        return True
    if expected == "number":
        return actual.startswith(("int", "uint", "float"))
    if expected == "integer":
        return actual.startswith(("int", "uint"))
    if expected == "string":
        return actual == "string"
    try:
        return bool(np.can_cast(np.dtype(actual), np.dtype(expected), casting="safe"))
    except (TypeError, ValueError):
        return False


def _shape_error(
    field: FieldContract,
    actual: Tuple[int, ...],
    symbols: Dict[str, int],
) -> str:
    if field.shape is None:
        return ""
    if len(field.shape) != len(actual):
        return "rank {} does not match required rank {}".format(len(actual), len(field.shape))
    for position, (expected, observed) in enumerate(zip(field.shape, actual)):
        if expected is None:
            continue
        if isinstance(expected, int) and expected != observed:
            return "dimension {} is {}, expected {}".format(position, observed, expected)
        if isinstance(expected, str):
            if expected in symbols and symbols[expected] != observed:
                return "symbolic dimension {} is {}, previously {}".format(expected, observed, symbols[expected])
            symbols[expected] = observed
    return ""


def validate_schema(metadata: ReaderMetadata, contract: Contract) -> List[Finding]:
    findings: List[Finding] = []
    actual_names = set(metadata.fields)
    expected_names = set(contract.fields)
    for name, field in contract.fields.items():
        if field.required and name not in actual_names:
            findings.append(Finding(
                rule_id="schema.required.{}".format(name),
                severity=field.severity,
                dataset=contract.dataset,
                file=str(metadata.path),
                field=name,
                message="Required field is missing",
                observed="missing",
                expected="field present",
                affected_count=1,
                examined_count=1,
                suggestion="Restore the field or revise the versioned contract after review.",
                reader=metadata.reader,
            ))

    unexpected = sorted(actual_names - expected_names)
    if unexpected and contract.unexpected_fields != "allow":
        severity = Severity.WARNING if contract.unexpected_fields == "warn" else Severity.ERROR
        for name in unexpected:
            findings.append(Finding(
                rule_id="schema.unexpected.{}".format(name),
                severity=severity,
                dataset=contract.dataset,
                file=str(metadata.path),
                field=name,
                message="Unexpected field is present",
                observed=name,
                expected="declared field or unexpected_fields: allow",
                affected_count=1,
                examined_count=1,
                suggestion="Review the producer schema before accepting the new field.",
                reader=metadata.reader,
            ))

    symbols: Dict[str, int] = {}
    for name, field in contract.fields.items():
        info = metadata.fields.get(name)
        if info is None:
            continue
        if field.type and not dtype_compatible(field.type, info.dtype):
            findings.append(Finding(
                rule_id="schema.type.{}".format(name),
                severity=field.severity,
                dataset=contract.dataset,
                file=str(metadata.path),
                field=name,
                message="Field type is incompatible",
                observed=info.dtype,
                expected=field.type,
                affected_count=metadata.row_count,
                examined_count=metadata.row_count,
                suggestion="Convert the producer output explicitly; SciValid does not modify input data.",
                reader=metadata.reader,
            ))
        shape_error = _shape_error(field, info.shape, symbols)
        if shape_error:
            findings.append(Finding(
                rule_id="schema.shape.{}".format(name),
                severity=field.severity,
                dataset=contract.dataset,
                file=str(metadata.path),
                field=name,
                message="Field shape is incompatible: {}".format(shape_error),
                observed=list(info.shape),
                expected=field.shape,
                affected_count=1,
                examined_count=1,
                suggestion="Check array construction and partition feature dimensions.",
                reader=metadata.reader,
            ))

    row_counts = metadata.attributes.get("row_counts", [])
    if len(row_counts) > 1:
        findings.append(Finding(
            rule_id="schema.leading_dimension_consistent",
            severity=Severity.ERROR,
            dataset=contract.dataset,
            file=str(metadata.path),
            message="Arrays do not share a common leading dimension",
            observed=row_counts,
            expected="one shared leading dimension",
            affected_count=len(row_counts),
            examined_count=len(metadata.fields),
            suggestion="Rebuild the NPZ partition so row-aligned arrays have equal lengths.",
            reader=metadata.reader,
        ))
    return findings
