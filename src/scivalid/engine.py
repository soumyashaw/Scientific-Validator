"""Validation execution engine and public ``validate`` function."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union

from .contract import Contract, load_contract
from .errors import ConfigurationError, OptionalDependencyError, ReaderError
from .models import FileSummary, Finding, Report, Severity
from .planner import build_plan
from .readers.registry import get_reader
from .rules.dataset_rules import DatasetState
from .rules.file_rules import validate_file
from .rules.relation_rules import RelationshipRule
from .rules.schema_rules import validate_schema
from .rules.value_rules import ValueRule


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _operational_finding(contract: Contract, path: Path, reader: Optional[str], exc: Exception) -> Finding:
    return Finding(
        rule_id="file.parseable",
        severity=Severity.ERROR,
        dataset=contract.dataset,
        file=str(path),
        message="File could not be completely inspected",
        observed=str(exc),
        expected="reader completes without an operational error",
        affected_count=1,
        examined_count=1,
        suggestion="Check whether the file is malformed, truncated, or uses an unsupported encoding.",
        reader=reader,
    )


def validate(
    paths: Iterable[Union[str, Path]],
    contract: Union[str, Path, Mapping[str, Any], Contract],
    *,
    chunk_size: int = 50_000,
    fail_fast: bool = False,
    sample_limit: Optional[int] = None,
    format_name: Optional[str] = None,
    max_exact_values: Optional[int] = None,
) -> Report:
    """Validate files against a versioned contract and return one canonical report.

    Contract validation and planning happen before any input file is opened.
    Exact global uniqueness and duplicate-row checks use memory proportional to
    the number of distinct values; ``max_exact_values`` can reject an oversized
    plan after metadata inspection.
    """
    parsed = load_contract(contract)
    if chunk_size <= 0:
        raise ConfigurationError("chunk_size must be greater than zero")
    if sample_limit is not None:
        if sample_limit < 0 or sample_limit > 1000:
            raise ConfigurationError("sample_limit must be between 0 and 1000")
        parsed = replace(parsed, sample_limit=sample_limit)
    if max_exact_values is not None and max_exact_values <= 0:
        raise ConfigurationError("max_exact_values must be greater than zero")
    plan = build_plan(paths, parsed)
    report = Report(
        dataset=parsed.dataset,
        contract_hash=parsed.hash,
        started_at=_now(),
        inputs=[str(path) for path in plan.paths],
    )
    state = DatasetState(parsed)
    fail_fast_triggered = False
    optional_dependency_failed = False
    exact_rows_planned = 0

    for path in plan.paths:
        file_findings, checksum = validate_file(path, parsed.dataset, parsed.file_rules)
        report.findings.extend(file_findings)
        if file_findings and any(item.rule_id == "file.accessible" for item in file_findings):
            report.completed = False
            if fail_fast:
                fail_fast_triggered = True
                break
            continue

        try:
            reader_type = get_reader(path, format_name)
        except ReaderError as exc:
            report.findings.append(_operational_finding(parsed, path, None, exc))
            report.completed = False
            if fail_fast:
                fail_fast_triggered = True
                break
            continue

        reader_format = reader_type.format_name
        if reader_format not in parsed.formats:
            report.findings.append(Finding(
                rule_id="file.format",
                severity=Severity.ERROR,
                dataset=parsed.dataset,
                file=str(path),
                message="Input format is not allowed by the contract",
                observed=reader_format,
                expected=parsed.formats,
                affected_count=1,
                examined_count=1,
                reader=reader_type.__name__,
            ))

        try:
            with reader_type(path, chunk_size=chunk_size) as reader:
                metadata = reader.inspect_metadata()
                if plan.exact_state_rules:
                    exact_rows_planned += metadata.row_count
                    if max_exact_values is not None and exact_rows_planned > max_exact_values:
                        raise ConfigurationError(
                            "Exact rule(s) {} require at least {} dataset rows; policy limit is {}".format(
                                ", ".join(plan.exact_state_rules), exact_rows_planned, max_exact_values
                            )
                        )
                summary = FileSummary(
                    path=str(path),
                    format=metadata.format,
                    reader=metadata.reader,
                    size_bytes=metadata.size_bytes,
                    rows=metadata.row_count,
                    fields=sorted(metadata.fields),
                    sha256=checksum,
                )
                report.files.append(summary)
                state.add_metadata(metadata)
                report.findings.extend(validate_schema(metadata, parsed))

                value_rule = ValueRule(parsed, str(path), metadata.reader, state.global_seen)
                relation_rule = RelationshipRule(parsed, str(path), metadata.reader)
                requested = None if "duplicate_row_rate" in parsed.dataset_rules else plan.required_fields
                for chunk in reader.iterate_chunks(requested):
                    value_rule.inspect_chunk(chunk)
                    relation_rule.inspect_chunk(chunk)
                    state.inspect_chunk(chunk)
                    if fail_fast and (
                        any(acc.affected for acc in value_rule.accumulators.values())
                        or any(acc.affected for acc in relation_rule.accumulators.values())
                    ):
                        fail_fast_triggered = True
                        break
                value_findings = value_rule.finalize_dataset()
                relationship_findings = relation_rule.finalize_dataset()
                report.findings.extend(value_findings)
                report.findings.extend(relationship_findings)
                state.add_invalid(str(path), value_rule.invalid_locations | relation_rule.invalid_locations)
        except ConfigurationError:
            raise
        except OptionalDependencyError as exc:
            report.findings.append(_operational_finding(parsed, path, reader_type.__name__, exc))
            report.completed = False
            optional_dependency_failed = True
        except (ReaderError, OSError, ValueError) as exc:
            report.findings.append(_operational_finding(parsed, path, reader_type.__name__, exc))
            report.completed = False
            if report.files and report.files[-1].path == str(path):
                report.files[-1].completed = False

        if fail_fast_triggered or (fail_fast and report.has_errors):
            fail_fast_triggered = True
            break

    if not fail_fast_triggered:
        report.findings.extend(state.finalize())
    else:
        report.findings.append(Finding(
            rule_id="execution.fail_fast",
            severity=Severity.INFO,
            dataset=parsed.dataset,
            message="Validation stopped after the first observed finding; dataset-wide rules were not finalized",
            expected="full scan required for dataset-wide findings",
            affected_count=0,
            examined_count=0,
        ))
    report.completed_at = _now()
    report.metrics = {
        "files_discovered": len(plan.paths),
        "files_inspected": len(report.files),
        "rows_declared": state.total_rows,
        "rows_with_violations": len(state.invalid_rows),
        "chunk_size": chunk_size,
        "sample_limit": parsed.sample_limit,
        "fail_fast_triggered": fail_fast_triggered,
        "exact_state_rules": plan.exact_state_rules,
        "exact_state_memory": "proportional to distinct values" if plan.exact_state_rules else "not used",
        "optional_dependency_failed": optional_dependency_failed,
    }
    report.sort_findings()
    return report
