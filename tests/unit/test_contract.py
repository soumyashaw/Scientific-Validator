import copy
import unittest

from scivalid.contract import parse_contract
from scivalid.errors import ContractError


MINIMAL = {
    "contract_version": 1,
    "dataset": "test-data",
    "formats": ["csv"],
    "fields": {"value": {"type": "float64"}},
}


class ContractTests(unittest.TestCase):
    def test_minimal_contract_has_stable_hash(self):
        first = parse_contract(copy.deepcopy(MINIMAL))
        second = parse_contract(copy.deepcopy(MINIMAL))
        self.assertEqual(first.hash, second.hash)
        self.assertTrue(first.hash.startswith("sha256:"))

    def test_unknown_key_is_rejected(self):
        raw = copy.deepcopy(MINIMAL)
        raw["mystery"] = True
        with self.assertRaisesRegex(ContractError, "Unknown key"):
            parse_contract(raw)

    def test_unsupported_version_is_rejected(self):
        raw = copy.deepcopy(MINIMAL)
        raw["contract_version"] = 2
        with self.assertRaisesRegex(ContractError, "version 1"):
            parse_contract(raw)

    def test_invalid_severity_is_rejected_before_execution(self):
        raw = copy.deepcopy(MINIMAL)
        raw["dataset_rules"] = {"invalid_fraction": {"max": 0.1, "severity": "urgent"}}
        with self.assertRaisesRegex(ContractError, "Invalid severity"):
            parse_contract(raw)

    def test_conflicting_bounds_are_rejected(self):
        raw = copy.deepcopy(MINIMAL)
        raw["fields"]["value"].update({"min": 5, "max": 4})
        with self.assertRaisesRegex(ContractError, "Conflicting bounds"):
            parse_contract(raw)

    def test_invalid_symbolic_dimension_is_rejected(self):
        raw = copy.deepcopy(MINIMAL)
        raw["fields"]["value"]["shape"] = ["rows", 3]
        with self.assertRaisesRegex(ContractError, "Invalid shape dimension"):
            parse_contract(raw)

    def test_relationship_cannot_reference_unknown_field(self):
        raw = copy.deepcopy(MINIMAL)
        raw["relationships"] = [{
            "id": "ordered", "rule": "less_equal", "left": "value", "right": "missing"
        }]
        with self.assertRaisesRegex(ContractError, "unknown field"):
            parse_contract(raw)

    def test_string_boolean_is_rejected(self):
        raw = copy.deepcopy(MINIMAL)
        raw["fields"]["value"]["finite"] = "false"
        with self.assertRaisesRegex(ContractError, "must be a Boolean"):
            parse_contract(raw)

    def test_relationship_collections_must_be_lists(self):
        raw = copy.deepcopy(MINIMAL)
        raw["relationships"] = [{
            "id": "norm", "rule": "norm_components", "field": "value", "components": "value"
        }]
        with self.assertRaisesRegex(ContractError, "list of field names"):
            parse_contract(raw)


if __name__ == "__main__":
    unittest.main()
