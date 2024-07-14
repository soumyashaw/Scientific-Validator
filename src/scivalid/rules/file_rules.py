"""Accessibility, non-empty, and optional checksum checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Finding, Severity


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_file(
    path: Path,
    dataset: str,
    file_rules: Dict[str, Any],
    reader_name: Optional[str] = None,
) -> tuple:
    findings: List[Finding] = []
    if not path.exists() or not path.is_file():
        findings.append(Finding(
            rule_id="file.accessible",
            severity=Severity.ERROR,
            dataset=dataset,
            file=str(path),
            message="File does not exist or is not a regular file",
            expected="existing readable file",
            affected_count=1,
            examined_count=1,
            suggestion="Check the input path and permissions.",
            reader=reader_name,
        ))
        return findings, None
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.read(1)
    except OSError as exc:
        findings.append(Finding(
            rule_id="file.accessible",
            severity=Severity.ERROR,
            dataset=dataset,
            file=str(path),
            message="File cannot be read",
            observed=str(exc),
            expected="readable file",
            affected_count=1,
            examined_count=1,
            suggestion="Check file permissions and storage availability.",
            reader=reader_name,
        ))
        return findings, None
    if file_rules.get("nonempty", True) and size == 0:
        findings.append(Finding(
            rule_id="file.nonempty",
            severity=Severity.ERROR,
            dataset=dataset,
            file=str(path),
            message="File is empty",
            observed=0,
            expected="size greater than zero bytes",
            affected_count=1,
            examined_count=1,
            reader=reader_name,
        ))

    expected_checksums = file_rules.get("checksums", {})
    expected = expected_checksums.get(str(path)) or expected_checksums.get(path.name)
    actual = None
    if expected:
        actual = sha256_file(path)
        normalized = str(expected).lower().replace("sha256:", "")
        if actual != normalized:
            findings.append(Finding(
                rule_id="file.checksum",
                severity=Severity.ERROR,
                dataset=dataset,
                file=str(path),
                message="SHA-256 checksum does not match",
                observed="sha256:" + actual,
                expected="sha256:" + normalized,
                affected_count=1,
                examined_count=1,
                suggestion="Re-transfer the file or update the manifest after reviewing the change.",
                reader=reader_name,
            ))
    return findings, actual

