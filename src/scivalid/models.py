"""Canonical finding and report models shared by every reporter."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

    @classmethod
    def parse(cls, value: str) -> "Severity":
        return cls(str(value).upper())


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    message: str
    dataset: str
    file: Optional[str] = None
    field: Optional[str] = None
    observed: Any = None
    expected: Any = None
    affected_count: Optional[int] = None
    examined_count: Optional[int] = None
    sample_locations: List[Any] = dc_field(default_factory=list)
    suggestion: Optional[str] = None
    reader: Optional[str] = None
    validator_version: str = "0.1.0"

    def sort_key(self) -> tuple:
        severity_order = {
            Severity.ERROR: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2,
        }
        return (
            str(self.file or ""),
            severity_order[self.severity],
            self.rule_id,
            str(self.field or ""),
            str(self.sample_locations[:1]),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return {key: value for key, value in data.items() if value is not None}


@dataclass
class FileSummary:
    path: str
    format: str
    reader: str
    size_bytes: int
    rows: int = 0
    fields: List[str] = dc_field(default_factory=list)
    sha256: Optional[str] = None
    completed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass
class Report:
    dataset: str
    contract_hash: str
    started_at: str
    completed_at: str = ""
    report_version: int = 1
    validator_version: str = "0.1.0"
    inputs: List[str] = dc_field(default_factory=list)
    files: List[FileSummary] = dc_field(default_factory=list)
    findings: List[Finding] = dc_field(default_factory=list)
    metrics: Dict[str, Any] = dc_field(default_factory=dict)
    completed: bool = True

    @property
    def has_errors(self) -> bool:
        return any(item.severity == Severity.ERROR for item in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(item.severity == Severity.WARNING for item in self.findings)

    @property
    def summary(self) -> Dict[str, int]:
        counts = {"errors": 0, "warnings": 0, "info": 0, "findings": len(self.findings)}
        for item in self.findings:
            if item.severity == Severity.ERROR:
                counts["errors"] += 1
            elif item.severity == Severity.WARNING:
                counts["warnings"] += 1
            else:
                counts["info"] += 1
        return counts

    def sort_findings(self) -> None:
        self.findings.sort(key=lambda item: item.sort_key())

    def to_dict(self) -> Dict[str, Any]:
        self.sort_findings()
        return {
            "report_version": self.report_version,
            "validator_version": self.validator_version,
            "dataset": self.dataset,
            "contract_hash": self.contract_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "completed": self.completed,
            "inputs": list(self.inputs),
            "files": [item.to_dict() for item in self.files],
            "summary": self.summary,
            "metrics": self.metrics,
            "findings": [item.to_dict() for item in self.findings],
        }
