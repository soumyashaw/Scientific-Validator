import random
import tempfile
import unittest
from pathlib import Path

from scivalid.engine import validate


class ChunkInvarianceTests(unittest.TestCase):
    def test_random_in_range_values_never_fail_range_rule_and_chunking_is_invariant(self):
        generator = random.Random(7421)
        values = [generator.uniform(0.0, 10.0) for _ in range(73)]
        raw_contract = {
            "contract_version": 1,
            "dataset": "generated",
            "formats": ["csv"],
            "fields": {"value": {"type": "float64", "min": 0.0, "max": 10.0}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.csv"
            path.write_text("value\n" + "\n".join(str(value) for value in values) + "\n", encoding="utf-8")
            small = validate([path], raw_contract, chunk_size=1)
            large = validate([path], raw_contract, chunk_size=29)
            self.assertNotIn("range.min.value", [item.rule_id for item in small.findings])
            self.assertNotIn("range.max.value", [item.rule_id for item in small.findings])
            self.assertEqual(
                [(item.rule_id, item.affected_count) for item in small.findings],
                [(item.rule_id, item.affected_count) for item in large.findings],
            )


if __name__ == "__main__":
    unittest.main()

