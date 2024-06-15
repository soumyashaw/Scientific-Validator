import json
import tempfile
import unittest
from pathlib import Path

from scivalid.models import Finding, Report, Severity
from scivalid.reporters.html_report import write_html_report
from scivalid.reporters.json_report import write_json_report


class ReportTests(unittest.TestCase):
    def _report(self):
        return Report(
            dataset="demo",
            contract_hash="sha256:" + "0" * 64,
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
            findings=[Finding(
                rule_id="range.min.x",
                severity=Severity.ERROR,
                message="bad <script>alert(1)</script>",
                dataset="demo",
                file="data.csv",
                field="x",
                affected_count=1,
                examined_count=2,
                sample_locations=[1],
            )],
        )

    def test_json_and_html_share_canonical_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "report.json"
            html_path = Path(directory) / "report.html"
            report = self._report()
            write_json_report(report, json_path)
            write_html_report(report, html_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
            self.assertEqual(payload["summary"]["errors"], 1)
            self.assertIn("range.min.x", html)
            self.assertNotIn("<script>alert", html)


if __name__ == "__main__":
    unittest.main()

