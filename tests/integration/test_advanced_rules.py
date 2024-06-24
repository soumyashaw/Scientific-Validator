import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scivalid.engine import validate


class AdvancedRuleTests(unittest.TestCase):
    def test_string_monotonic_unique_and_upper_bound_rules(self):
        raw_contract = {
            "contract_version": 1,
            "dataset": "advanced-values",
            "formats": ["csv"],
            "fields": {
                "id": {"type": "int64", "unique": "file"},
                "score": {"type": "float64", "min": 0, "max": 10, "monotonic": "increasing"},
                "label": {
                    "type": "string", "allowed": ["AA", "BB"], "pattern": "[A-Z]{2}",
                    "min_length": 2, "max_length": 2,
                },
                "optional": {"type": "string", "missing": "allow"},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text(
                "id,score,label,optional\n1,1,AA,\n1,12,C,hello\n2,10,ZZ,world\n",
                encoding="utf-8",
            )
            report = validate([path], raw_contract, chunk_size=1)
        ids = {item.rule_id for item in report.findings}
        self.assertTrue({
            "unique.id", "range.max.score", "monotonic.score", "allowed.label",
            "pattern.label", "length.label",
        }.issubset(ids))
        self.assertNotIn("missing.optional", ids)

    def test_all_named_relationship_families(self):
        fields = {
            name: {"type": "number"}
            for name in ("left", "right", "norm", "x", "y")
        }
        fields.update({
            "condition": {"type": "string"},
            "detail": {"type": "string", "missing": "allow"},
            "flag_a": {"type": "bool"},
            "flag_b": {"type": "bool"},
            "vec2": {"type": "number"},
            "vec3": {"type": "number"},
        })
        raw_contract = {
            "contract_version": 1,
            "dataset": "relationships",
            "formats": ["jsonl"],
            "fields": fields,
            "relationships": [
                {"id": "lt", "rule": "less", "left": "left", "right": "right"},
                {"id": "gt", "rule": "greater", "left": "left", "right": "right"},
                {"id": "ge", "rule": "greater_equal", "left": "left", "right": "right"},
                {"id": "eq", "rule": "equal", "left": "left", "right": "right"},
                {"id": "ne", "rule": "not_equal", "left": "left", "right": "right"},
                {"id": "norm", "rule": "norm_components", "field": "norm", "components": ["x", "y"]},
                {
                    "id": "detail_required", "rule": "required_if", "condition_field": "condition",
                    "condition_value": "signal", "required_field": "detail",
                },
                {"id": "exclusive", "rule": "mutually_exclusive", "flags": ["flag_a", "flag_b"]},
                {"id": "same_shape", "rule": "shape_equal", "left": "vec2", "right": "vec3"},
            ],
        }
        records = [
            {
                "left": 2, "right": 1, "norm": 5, "x": 3, "y": 4,
                "condition": "signal", "detail": None, "flag_a": True, "flag_b": True,
                "vec2": [1, 2], "vec3": [1, 2, 3],
            },
            {
                "left": 1, "right": 1, "norm": 10, "x": 0, "y": 1,
                "condition": "background", "detail": None, "flag_a": False, "flag_b": False,
                "vec2": [3, 4], "vec3": [4, 5, 6],
            },
            {
                "left": 0, "right": 1, "norm": 1, "x": 0, "y": 1,
                "condition": "background", "detail": "ok", "flag_a": False, "flag_b": False,
                "vec2": [5, 6], "vec3": [7, 8, 9],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
            report = validate([path], raw_contract)
        ids = {item.rule_id for item in report.findings}
        for expected in (
            "relationship.lt", "relationship.gt", "relationship.ge", "relationship.eq", "relationship.ne",
            "relationship.norm", "relationship.detail_required", "relationship.exclusive",
            "relationship.same_shape",
        ):
            self.assertIn(expected, ids)

    def test_dataset_rules_and_checksum(self):
        raw_contract = {
            "contract_version": 1,
            "dataset": "dataset-rules",
            "formats": ["csv"],
            "file_rules": {"checksums": {"data.csv": "0" * 64}},
            "fields": {"category": {"type": "string"}, "value": {"type": "int64"}},
            "dataset_rules": {
                "row_count": {"max": 1},
                "duplicate_row_rate": {"max": 0.1},
                "category_coverage": {"category": ["signal", "control"]},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("category,value\nsignal,1\nsignal,1\n", encoding="utf-8")
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            report = validate([path], raw_contract)
        ids = {item.rule_id for item in report.findings}
        self.assertTrue({
            "file.checksum", "dataset.row_count", "dataset.duplicate_row_rate",
            "dataset.category_coverage.category",
        }.issubset(ids))
        self.assertEqual(report.files[0].sha256, actual_hash)

    def test_symbolic_shape_and_npz_leading_dimension_mismatch(self):
        raw_contract = {
            "contract_version": 1,
            "dataset": "shapes",
            "formats": ["npz"],
            "fields": {
                "a": {"type": "float32", "shape": ["N", 3]},
                "b": {"type": "float32", "shape": ["N", 3]},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arrays.npz"
            np.savez(path, a=np.ones((2, 3), dtype=np.float32), b=np.ones((3, 3), dtype=np.float32))
            report = validate([path], raw_contract)
        ids = {item.rule_id for item in report.findings}
        self.assertIn("schema.shape.b", ids)
        self.assertIn("schema.leading_dimension_consistent", ids)
        print(ids)

if __name__ == "__main__":
    unittest.main()
