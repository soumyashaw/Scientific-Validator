import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scivalid.cli import main


class CLITests(unittest.TestCase):
    def invoke(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_contract_validate_and_inspect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.yaml"
            data = root / "data.csv"
            contract.write_text(
                "contract_version: 1\ndataset: cli\nformats: [csv]\nfields:\n  value: {type: float64}\n",
                encoding="utf-8",
            )
            data.write_text("value\n1.5\n", encoding="utf-8")
            code, output, _ = self.invoke(["contract", "validate", str(contract)])
            self.assertEqual(code, 0)
            self.assertIn("Contract is valid", output)
            code, output, _ = self.invoke(["inspect", str(data)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["row_count"], 1)

    def test_check_writes_reports_and_maps_finding_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.yaml"
            data = root / "data.csv"
            json_report = root / "report.json"
            html_report = root / "report.html"
            contract.write_text(
                "contract_version: 1\ndataset: cli\nformats: [csv]\nfields:\n  value: {type: float64, min: 0}\n",
                encoding="utf-8",
            )
            data.write_text("value\n-1\n", encoding="utf-8")
            code, output, _ = self.invoke([
                "check", str(data), "--contract", str(contract),
                "--report-json", str(json_report), "--report-html", str(html_report),
            ])
            self.assertEqual(code, 1)
            self.assertIn("FAIL", output)
            self.assertTrue(json_report.exists())
            self.assertTrue(html_report.exists())

    def test_strict_promotes_warning_to_failing_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.yaml"
            data = root / "data.csv"
            contract.write_text(
                "contract_version: 1\ndataset: cli\nformats: [csv]\nunexpected_fields: warn\nfields:\n  value: {type: float64}\n",
                encoding="utf-8",
            )
            data.write_text("value,extra\n1,note\n", encoding="utf-8")
            relaxed, _, _ = self.invoke(["check", str(data), "--contract", str(contract)])
            strict, strict_output, _ = self.invoke(["check", str(data), "--contract", str(contract), "--strict"])
            self.assertEqual(relaxed, 0)
            self.assertEqual(strict, 1)
            self.assertIn("FAIL", strict_output)

    def test_configuration_and_operational_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad_contract = root / "bad.yaml"
            bad_contract.write_text("contract_version: 2\n", encoding="utf-8")
            code, _, error = self.invoke(["contract", "validate", str(bad_contract)])
            self.assertEqual(code, 2)
            self.assertIn("Configuration error", error)

            contract = root / "contract.yaml"
            contract.write_text(
                "contract_version: 1\ndataset: cli\nformats: [csv]\nfields:\n  value: {}\n",
                encoding="utf-8",
            )
            code, output, _ = self.invoke([
                "check", str(root / "missing.csv"), "--contract", str(contract)
            ])
            self.assertEqual(code, 3)
            self.assertIn("incomplete", output)

    def test_compare_schema_equal_and_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            left = root / "left.csv"
            right = root / "right.csv"
            changed = root / "changed.csv"
            left.write_text("id,value\n1,2.0\n", encoding="utf-8")
            right.write_text("id,value\n2,3.0\n", encoding="utf-8")
            changed.write_text("id,label\n1,x\n", encoding="utf-8")
            equal, output, _ = self.invoke(["compare-schema", str(left), str(right)])
            different, changed_output, _ = self.invoke(["compare-schema", str(left), str(changed)])
            self.assertEqual(equal, 0)
            self.assertTrue(json.loads(output)["equal"])
            self.assertEqual(different, 1)
            self.assertFalse(json.loads(changed_output)["equal"])


if __name__ == "__main__":
    unittest.main()
