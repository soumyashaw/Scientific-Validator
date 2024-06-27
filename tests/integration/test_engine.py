import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scivalid.engine import validate
from scivalid.errors import ConfigurationError


def contract(formats):
    return {
        "contract_version": 1,
        "dataset": "logical-data",
        "formats": formats,
        "unexpected_fields": "error",
        "sample_limit": 2,
        "fields": {
            "event_id": {"type": "int64", "unique": "global"},
            "value": {"type": "number", "finite": True, "min": 0},
            "start": {"type": "number"},
            "end": {"type": "number"},
        },
        "relationships": [{
            "id": "ordered", "rule": "less_equal", "left": "start", "right": "end"
        }],
        "dataset_rules": {
            "row_count": {"min": 1},
            "consistent_schema": True,
            "invalid_fraction": {"max": 0.1, "severity": "warning"},
        },
    }


class EngineTests(unittest.TestCase):
    def test_valid_csv_passes_across_small_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.csv"
            path.write_text("event_id,value,start,end\n1,1.0,0,1\n2,2.0,2,3\n", encoding="utf-8")
            report = validate([path], contract(["csv"]), chunk_size=1)
            self.assertTrue(report.completed)
            self.assertFalse(report.has_errors)
            self.assertEqual(report.metrics["rows_declared"], 2)

    def test_violations_are_counted_and_samples_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text(
                "event_id,value,start,end\n1,-1,2,1\n2,-2,3,2\n3,-3,4,3\n",
                encoding="utf-8",
            )
            report = validate([path], contract(["csv"]), chunk_size=1)
            findings = {item.rule_id: item for item in report.findings}
            self.assertEqual(findings["range.min.value"].affected_count, 3)
            self.assertEqual(findings["relationship.ordered"].affected_count, 3)
            self.assertEqual(len(findings["range.min.value"].sample_locations), 2)

    def test_global_uniqueness_spans_files_and_order_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.csv"
            second = Path(directory) / "b.csv"
            header = "event_id,value,start,end\n"
            first.write_text(header + "1,1,0,1\n", encoding="utf-8")
            second.write_text(header + "1,2,1,2\n", encoding="utf-8")
            report_a = validate([second, first], contract(["csv"]))
            report_b = validate([first, second], contract(["csv"]))
            keys_a = [(item.rule_id, item.file, item.field) for item in report_a.findings]
            keys_b = [(item.rule_id, item.file, item.field) for item in report_b.findings]
            self.assertEqual(keys_a, keys_b)
            self.assertIn("unique.event_id", [item.rule_id for item in report_a.findings])

    def test_csv_jsonl_equivalent_value_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "data.csv"
            jsonl_path = Path(directory) / "data.jsonl"
            csv_path.write_text("event_id,value,start,end\n1,-1,2,1\n", encoding="utf-8")
            jsonl_path.write_text(json.dumps({"event_id": 1, "value": -1, "start": 2, "end": 1}) + "\n", encoding="utf-8")
            csv_report = validate([csv_path], contract(["csv"]))
            json_report = validate([jsonl_path], contract(["jsonl"]))
            common = {"range.min.value", "relationship.ordered"}
            self.assertEqual(
                common & {item.rule_id for item in csv_report.findings},
                common & {item.rule_id for item in json_report.findings},
            )

    def test_npz_shape_and_non_finite_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.npz"
            np.savez(
                path,
                event_id=np.array([1, 2], dtype=np.int64),
                value=np.array([1.0, np.inf], dtype=np.float32),
                start=np.array([0.0, 2.0]),
                end=np.array([1.0, 1.0]),
            )
            report = validate([path], contract(["npz"]), chunk_size=1)
            ids = {item.rule_id for item in report.findings}
            self.assertIn("finite.value", ids)
            self.assertIn("relationship.ordered", ids)

    def test_malformed_file_preserves_report_context(self):
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / "a.jsonl"
            bad = Path(directory) / "b.jsonl"
            good.write_text(json.dumps({"event_id": 1, "value": 1, "start": 0, "end": 1}) + "\n", encoding="utf-8")
            bad.write_text("{broken\n", encoding="utf-8")
            report = validate([good, bad], contract(["jsonl"]))
            self.assertFalse(report.completed)
            self.assertEqual(report.metrics["files_inspected"], 1)
            self.assertIn("file.parseable", [item.rule_id for item in report.findings])

    def test_exact_resource_policy_applies_across_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.csv"
            second = Path(directory) / "b.csv"
            header = "event_id,value,start,end\n"
            first.write_text(header + "1,1,0,1\n", encoding="utf-8")
            second.write_text(header + "2,2,1,2\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                validate([first, second], contract(["csv"]), max_exact_values=1)

    def test_fail_fast_skips_dataset_wide_conclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("event_id,value,start,end\n1,-1,2,1\n2,-2,3,2\n", encoding="utf-8")
            report = validate([path], contract(["csv"]), chunk_size=1, fail_fast=True)
            ids = {item.rule_id for item in report.findings}
            self.assertIn("execution.fail_fast", ids)
            self.assertNotIn("dataset.invalid_fraction", ids)


if __name__ == "__main__":
    unittest.main()
