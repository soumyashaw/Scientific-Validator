"""Concise terminal rendering."""

from __future__ import annotations

from typing import List

from ..models import Report


def render_terminal(report: Report, max_findings: int = 20, fail_on_warnings: bool = False) -> str:
    summary = report.summary
    status = "FAIL" if report.has_errors or (fail_on_warnings and report.has_warnings) else "PASS"
    lines: List[str] = [
        "SciValid {} — {}".format(report.validator_version, status),
        "Dataset: {} | Files: {} | Rows: {}".format(
            report.dataset,
            report.metrics.get("files_inspected", len(report.files)),
            report.metrics.get("rows_declared", sum(item.rows for item in report.files)),
        ),
        "Findings: {} error(s), {} warning(s), {} info".format(
            summary["errors"], summary["warnings"], summary["info"]
        ),
    ]
    for finding in report.findings[:max_findings]:
        location = finding.file or report.dataset
        if finding.field:
            location += ":" + finding.field
        count = ""
        if finding.affected_count is not None:
            count = " ({} affected)".format(finding.affected_count)
        lines.append("[{}] {} {} — {}{}".format(
            finding.severity.value, finding.rule_id, location, finding.message, count
        ))
        if finding.sample_locations:
            lines.append("  samples: {}".format(finding.sample_locations))
    hidden = len(report.findings) - max_findings
    if hidden > 0:
        lines.append("... {} additional finding(s); use JSON or HTML for the full report".format(hidden))
    if not report.completed:
        lines.append("Validation was incomplete because an operational failure occurred.")
    return "\n".join(lines)
