import json
import tempfile
import unittest
from pathlib import Path

from scivalid.engine import validate


ROOT = Path(__file__).resolve().parents[2]


class SchemaAndGoldenTests(unittest.TestCase):
    def test_normalized_report_matches_reviewed_golden(self):
        raw_contract = {
            "contract_version": 1,
            "dataset": "golden-data",
            "formats": ["csv"],
            "fields": {"value": {"type": "float64", "min": 0.0}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("value\n1.0\n-1.0\n", encoding="utf-8")
            actual = validate([path], raw_contract).to_dict()
        projection = {
            "report_version": actual["report_version"],
            "validator_version": actual["validator_version"],
            "dataset": actual["dataset"],
            "completed": actual["completed"],
            "summary": actual["summary"],
            "findings": [{
                key: finding[key]
                for key in (
                    "rule_id", "severity", "field", "affected_count", "examined_count", "sample_locations"
                )
            } for finding in actual["findings"]],
        }
        expected = json.loads((ROOT / "tests/golden/invalid-report.json").read_text(encoding="utf-8"))
        self.assertEqual(projection, expected)

    def test_published_json_schemas_accept_examples_when_jsonschema_is_installed(self):
        try:
            import jsonschema
            import yaml
        except ImportError:
            self.skipTest("jsonschema is an optional development dependency")
        contract_payload = yaml.safe_load(
            (ROOT / "examples/particle_events/contract.yaml").read_text(encoding="utf-8")
        )
        contract_schema = json.loads((ROOT / "schemas/contract-v1.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(contract_payload, contract_schema)

        report = validate(
            [ROOT / "examples/particle_events/valid"],
            ROOT / "examples/particle_events/contract.yaml",
        )
        report_schema = json.loads((ROOT / "schemas/report-v1.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(report.to_dict(), report_schema)


if __name__ == "__main__":
    unittest.main()

