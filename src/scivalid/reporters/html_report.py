"""Self-contained human-review HTML report."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Union

from ..models import Report


def _escape(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(str(value))


def write_html_report(report: Report, destination: Union[str, Path]) -> None:
    rows = []
    for finding in report.findings:
        rows.append(
            "<tr class='{severity}'><td>{severity}</td><td><code>{rule}</code></td>"
            "<td>{file}</td><td>{field}</td><td>{message}</td><td>{count}</td>"
            "<td>{samples}</td></tr>".format(
                severity=finding.severity.value.lower(),
                rule=_escape(finding.rule_id),
                file=_escape(finding.file or "—"),
                field=_escape(finding.field or "—"),
                message=_escape(finding.message),
                count=_escape(finding.affected_count if finding.affected_count is not None else "—"),
                samples=_escape(finding.sample_locations or "—"),
            )
        )
    summary = report.summary
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SciValid report — {dataset}</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--ink:#18202b;--muted:#637083;--error:#b42318;--warning:#b54708;--info:#175cd3}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1200px;margin:40px auto;padding:0 20px}} h1{{margin-bottom:4px}} .meta{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:12px;margin:24px 0}}
.card{{background:var(--card);border-radius:10px;padding:18px;box-shadow:0 1px 3px #1018281a}} .value{{font-size:28px;font-weight:700}}
table{{width:100%;border-collapse:collapse;background:var(--card);box-shadow:0 1px 3px #1018281a}}
th,td{{padding:10px 12px;border-bottom:1px solid #e4e7ec;text-align:left;vertical-align:top}} th{{background:#eef1f6}}
tr.error td:first-child{{color:var(--error);font-weight:700}} tr.warning td:first-child{{color:var(--warning);font-weight:700}}
tr.info td:first-child{{color:var(--info);font-weight:700}} code{{white-space:nowrap}} .boundary{{margin-top:24px;padding:16px;border-left:4px solid var(--info);background:#eef4ff}}
@media(max-width:700px){{.cards{{grid-template-columns:1fr 1fr}} table{{display:block;overflow-x:auto}}}}
</style></head><body><main>
<h1>SciValid report</h1><div class="meta">{dataset} · validator {version} · contract {contract_hash}</div>
<div class="cards"><div class="card"><div class="value">{status}</div><div>status</div></div>
<div class="card"><div class="value">{errors}</div><div>errors</div></div>
<div class="card"><div class="value">{warnings}</div><div>warnings</div></div>
<div class="card"><div class="value">{rows_count}</div><div>rows declared</div></div></div>
<table><thead><tr><th>Severity</th><th>Rule</th><th>File</th><th>Field</th><th>Message</th><th>Affected</th><th>Samples</th></tr></thead>
<tbody>{finding_rows}</tbody></table>
<div class="boundary"><strong>Interpretation boundary.</strong> This report checks explicit structural and data contracts. It does not establish that the dataset or its scientific conclusions are true.</div>
</main></body></html>""".format(
        dataset=_escape(report.dataset),
        version=_escape(report.validator_version),
        contract_hash=_escape(report.contract_hash),
        status="FAIL" if report.has_errors or (report.metrics.get("strict") and report.has_warnings) else "PASS",
        errors=summary["errors"],
        warnings=summary["warnings"],
        rows_count=_escape(report.metrics.get("rows_declared", 0)),
        finding_rows="".join(rows) or "<tr><td colspan='7'>No findings.</td></tr>",
    )
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
