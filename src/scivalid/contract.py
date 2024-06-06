"""Strict parsing and normalization for version 1 SciValid contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

import yaml

from .errors import ContractError
from .models import Severity


TOP_LEVEL_KEYS = {
    "contract_version",
    "dataset",
    "description",
    "formats",
    "unexpected_fields",
    "fields",
    "dataset_rules",
    "relationships",
    "file_rules",
    "sample_limit",
    "metadata",
}
FIELD_KEYS = {
    "type",
    "required",
    "shape",
    "finite",
    "nullable",
    "missing",
    "min",
    "max",
    "min_inclusive",
    "max_inclusive",
    "allowed",
    "pattern",
    "min_length",
    "max_length",
    "monotonic",
    "unique",
    "severity",
}
RELATIONSHIP_KEYS = {
    "id",
    "rule",
    "left",
    "right",
    "field",
    "components",
    "condition_field",
    "condition_value",
    "required_field",
    "flags",
    "tolerance",
    "severity",
}
DATASET_RULE_KEYS = {
    "row_count",
    "invalid_fraction",
    "consistent_schema",
    "duplicate_row_rate",
    "category_coverage",
}
FILE_RULE_KEYS = {"nonempty", "checksums"}
SUPPORTED_TYPES = {
    "bool",
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "float16",
    "float32",
    "float64",
    "number",
    "integer",
    "string",
    "datetime",
    "object",
}
SUPPORTED_FORMATS = {"csv", "jsonl", "ndjson", "npz"}
SUPPORTED_RELATIONSHIPS = {
    "less",
    "less_equal",
    "greater",
    "greater_equal",
    "equal",
    "not_equal",
    "norm_components",
    "required_if",
    "mutually_exclusive",
    "shape_equal",
}
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class FieldContract:
    name: str
    type: Optional[str] = None
    required: bool = True
    shape: Optional[List[Union[int, str, None]]] = None
    finite: bool = False
    nullable: bool = False
    missing: str = "forbid"
    minimum: Any = None
    maximum: Any = None
    min_inclusive: bool = True
    max_inclusive: bool = True
    allowed: Optional[List[Any]] = None
    pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    monotonic: Optional[str] = None
    unique: Optional[str] = None
    severity: Severity = Severity.ERROR


@dataclass(frozen=True)
class RelationshipContract:
    id: str
    rule: str
    config: Dict[str, Any]
    severity: Severity = Severity.ERROR


@dataclass(frozen=True)
class Contract:
    contract_version: int
    dataset: str
    formats: List[str]
    unexpected_fields: str
    fields: Dict[str, FieldContract]
    relationships: List[RelationshipContract]
    dataset_rules: Dict[str, Any]
    file_rules: Dict[str, Any]
    sample_limit: int
    metadata: Dict[str, Any]
    source: Dict[str, Any] = field(repr=False)
    hash: str = ""


def _reject_unknown(mapping: Mapping[str, Any], allowed: set, where: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ContractError("Unknown key(s) in {}: {}".format(where, ", ".join(unknown)))


def _severity(value: Any, where: str) -> Severity:
    try:
        return Severity.parse(value or "error")
    except ValueError:
        raise ContractError("Invalid severity at {}: {!r}".format(where, value))


def _parse_field(name: str, raw: Any) -> FieldContract:
    if not isinstance(raw, Mapping):
        raise ContractError("Field {!r} must be a mapping".format(name))
    _reject_unknown(raw, FIELD_KEYS, "field {!r}".format(name))
    for key in ("required", "finite", "nullable", "min_inclusive", "max_inclusive"):
        if key in raw and not isinstance(raw[key], bool):
            raise ContractError("{} for field {!r} must be a Boolean".format(key, name))
    field_type = raw.get("type")
    if field_type is not None and str(field_type).lower() not in SUPPORTED_TYPES:
        raise ContractError("Unsupported type for field {!r}: {!r}".format(name, field_type))

    shape = raw.get("shape")
    if shape is not None:
        if not isinstance(shape, list):
            raise ContractError("Shape for field {!r} must be a list".format(name))
        normalized_shape = []
        for dim in shape:
            if dim in (None, "*"):
                normalized_shape.append(None)
            elif isinstance(dim, int) and not isinstance(dim, bool) and dim >= 0:
                normalized_shape.append(dim)
            elif isinstance(dim, str) and SYMBOL_RE.match(dim):
                normalized_shape.append(dim)
            else:
                raise ContractError("Invalid shape dimension {!r} for field {!r}".format(dim, name))
        shape = normalized_shape

    minimum = raw.get("min")
    maximum = raw.get("max")
    if minimum is not None and maximum is not None:
        try:
            invalid_bounds = minimum > maximum or (
                minimum == maximum
                and (not raw.get("min_inclusive", True) or not raw.get("max_inclusive", True))
            )
        except TypeError:
            raise ContractError("Bounds for field {!r} are not comparable".format(name))
        if invalid_bounds:
            raise ContractError("Conflicting bounds for field {!r}".format(name))

    allowed = raw.get("allowed")
    if allowed is not None and not isinstance(allowed, list):
        raise ContractError("Allowed values for field {!r} must be a list".format(name))
    pattern = raw.get("pattern")
    if pattern is not None:
        try:
            re.compile(pattern)
        except (re.error, TypeError) as exc:
            raise ContractError("Invalid pattern for field {!r}: {}".format(name, exc))

    for key in ("min_length", "max_length"):
        value = raw.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ContractError("{} for field {!r} must be a non-negative integer".format(key, name))
    if (
        raw.get("min_length") is not None
        and raw.get("max_length") is not None
        and raw["min_length"] > raw["max_length"]
    ):
        raise ContractError("Conflicting length bounds for field {!r}".format(name))

    monotonic = raw.get("monotonic")
    if monotonic not in (None, "increasing", "decreasing", "strict_increasing", "strict_decreasing"):
        raise ContractError("Invalid monotonic mode for field {!r}".format(name))
    unique = raw.get("unique")
    if unique is True:
        unique = "file"
    if unique not in (None, False, "file", "global"):
        raise ContractError("Unique for field {!r} must be 'file' or 'global'".format(name))

    missing = raw.get("missing", "allow" if raw.get("nullable", False) else "forbid")
    if missing not in ("allow", "forbid"):
        raise ContractError("Missing policy for field {!r} must be 'allow' or 'forbid'".format(name))

    return FieldContract(
        name=name,
        type=str(field_type).lower() if field_type is not None else None,
        required=bool(raw.get("required", True)),
        shape=shape,
        finite=bool(raw.get("finite", False)),
        nullable=bool(raw.get("nullable", False)),
        missing=missing,
        minimum=minimum,
        maximum=maximum,
        min_inclusive=bool(raw.get("min_inclusive", True)),
        max_inclusive=bool(raw.get("max_inclusive", True)),
        allowed=allowed,
        pattern=pattern,
        min_length=raw.get("min_length"),
        max_length=raw.get("max_length"),
        monotonic=monotonic,
        unique=unique or None,
        severity=_severity(raw.get("severity"), "field {!r}".format(name)),
    )


def _parse_relationship(index: int, raw: Any, fields: Mapping[str, FieldContract]) -> RelationshipContract:
    where = "relationship {}".format(index)
    if not isinstance(raw, Mapping):
        raise ContractError("{} must be a mapping".format(where))
    _reject_unknown(raw, RELATIONSHIP_KEYS, where)
    rule = raw.get("rule")
    if rule not in SUPPORTED_RELATIONSHIPS:
        raise ContractError("Unsupported relationship rule at {}: {!r}".format(where, rule))
    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ContractError("{} requires a non-empty id".format(where))

    if rule in {"less", "less_equal", "greater", "greater_equal", "equal", "not_equal", "shape_equal"}:
        required_keys = ("left", "right")
    elif rule == "norm_components":
        required_keys = ("field", "components")
    elif rule == "required_if":
        required_keys = ("condition_field", "condition_value", "required_field")
    else:
        required_keys = ("flags",)
    for key in required_keys:
        if key not in raw:
            raise ContractError("{} requires {!r}".format(where, key))

    for key in ("left", "right", "field", "condition_field", "required_field"):
        if key in raw and not isinstance(raw[key], str):
            raise ContractError("{}.{} must be a field name".format(where, key))
    for key in ("components", "flags"):
        if key in raw and (
            not isinstance(raw[key], list)
            or not raw[key]
            or any(not isinstance(item, str) for item in raw[key])
        ):
            raise ContractError("{}.{} must be a non-empty list of field names".format(where, key))
    if "tolerance" in raw and (
        not isinstance(raw["tolerance"], (int, float))
        or isinstance(raw["tolerance"], bool)
        or raw["tolerance"] < 0
    ):
        raise ContractError("{}.tolerance must be non-negative".format(where))

    referenced = []
    for key in ("left", "right", "field", "condition_field", "required_field"):
        if key in raw:
            referenced.append(raw[key])
    referenced.extend(raw.get("components", []))
    referenced.extend(raw.get("flags", []))
    missing_fields = sorted({str(name) for name in referenced if name not in fields})
    if missing_fields:
        raise ContractError("{} references unknown field(s): {}".format(where, ", ".join(missing_fields)))

    config = {key: value for key, value in raw.items() if key not in ("id", "rule", "severity")}
    return RelationshipContract(
        id=rule_id,
        rule=rule,
        config=config,
        severity=_severity(raw.get("severity"), where),
    )


def _validate_dataset_rules(raw: Mapping[str, Any]) -> None:
    for name in ("row_count", "invalid_fraction", "duplicate_row_rate"):
        if name not in raw:
            continue
        rule = raw[name]
        if not isinstance(rule, Mapping):
            raise ContractError("dataset_rules.{} must be a mapping".format(name))
        allowed = {"min", "max", "severity"} if name == "row_count" else {"max", "severity"}
        _reject_unknown(rule, allowed, "dataset_rules.{}".format(name))
        _severity(rule.get("severity"), "dataset_rules.{}".format(name))
        if name != "row_count" and "max" not in rule:
            raise ContractError("dataset_rules.{} requires max".format(name))
        for bound in ("min", "max"):
            if bound not in rule:
                continue
            value = rule[bound]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ContractError("dataset_rules.{}.{} must be non-negative".format(name, bound))
            if name != "row_count" and value > 1:
                raise ContractError("dataset_rules.{}.max must be at most 1".format(name))
        if "min" in rule and "max" in rule and rule["min"] > rule["max"]:
            raise ContractError("dataset_rules.{} has conflicting bounds".format(name))
    if "consistent_schema" in raw:
        value = raw["consistent_schema"]
        if not isinstance(value, (bool, Mapping)):
            raise ContractError("dataset_rules.consistent_schema must be a Boolean or mapping")
        if isinstance(value, Mapping):
            _reject_unknown(value, {"severity"}, "dataset_rules.consistent_schema")
            _severity(value.get("severity"), "dataset_rules.consistent_schema")
    if "category_coverage" in raw:
        coverage = raw["category_coverage"]
        if not isinstance(coverage, Mapping):
            raise ContractError("dataset_rules.category_coverage must be a mapping")
        for name, value in coverage.items():
            if isinstance(value, list):
                continue
            if not isinstance(value, Mapping):
                raise ContractError("Category coverage for {!r} must be a list or mapping".format(name))
            _reject_unknown(value, {"required", "severity"}, "category coverage {!r}".format(name))
            if not isinstance(value.get("required"), list):
                raise ContractError("Category coverage for {!r} requires a list".format(name))
            _severity(value.get("severity"), "category coverage {!r}".format(name))


def _validate_file_rules(raw: Mapping[str, Any]) -> None:
    if "nonempty" in raw and not isinstance(raw["nonempty"], bool):
        raise ContractError("file_rules.nonempty must be a Boolean")
    if "checksums" in raw:
        checksums = raw["checksums"]
        if not isinstance(checksums, Mapping):
            raise ContractError("file_rules.checksums must be a mapping")
        for name, value in checksums.items():
            normalized = str(value).lower().replace("sha256:", "")
            if not re.fullmatch(r"[0-9a-f]{64}", normalized):
                raise ContractError("Invalid SHA-256 checksum for {!r}".format(name))


def parse_contract(raw: Mapping[str, Any]) -> Contract:
    if not isinstance(raw, Mapping):
        raise ContractError("Contract root must be a mapping")
    _reject_unknown(raw, TOP_LEVEL_KEYS, "contract")
    if raw.get("contract_version") != 1:
        raise ContractError("Only contract_version 1 is supported")
    dataset = raw.get("dataset")
    if not isinstance(dataset, str) or not dataset.strip():
        raise ContractError("Contract requires a non-empty dataset name")

    formats = raw.get("formats", ["csv", "jsonl", "npz"])
    if not isinstance(formats, list) or not formats:
        raise ContractError("formats must be a non-empty list")
    formats = [str(item).lower().lstrip(".") for item in formats]
    unknown_formats = sorted(set(formats) - SUPPORTED_FORMATS)
    if unknown_formats:
        raise ContractError("Unsupported format(s): {}".format(", ".join(unknown_formats)))
    formats = ["jsonl" if item == "ndjson" else item for item in formats]

    unexpected = raw.get("unexpected_fields", "warn")
    if unexpected not in ("allow", "warn", "error"):
        raise ContractError("unexpected_fields must be allow, warn, or error")

    raw_fields = raw.get("fields")
    if not isinstance(raw_fields, Mapping) or not raw_fields:
        raise ContractError("Contract requires at least one field")
    fields = {str(name): _parse_field(str(name), value) for name, value in raw_fields.items()}

    raw_dataset_rules = raw.get("dataset_rules", {})
    if not isinstance(raw_dataset_rules, Mapping):
        raise ContractError("dataset_rules must be a mapping")
    _reject_unknown(raw_dataset_rules, DATASET_RULE_KEYS, "dataset_rules")
    _validate_dataset_rules(raw_dataset_rules)
    raw_file_rules = raw.get("file_rules", {})
    if not isinstance(raw_file_rules, Mapping):
        raise ContractError("file_rules must be a mapping")
    _reject_unknown(raw_file_rules, FILE_RULE_KEYS, "file_rules")
    _validate_file_rules(raw_file_rules)

    raw_relationships = raw.get("relationships", [])
    if not isinstance(raw_relationships, list):
        raise ContractError("relationships must be a list")
    relationships = [
        _parse_relationship(index, item, fields)
        for index, item in enumerate(raw_relationships)
    ]
    relationship_ids = [item.id for item in relationships]
    if len(set(relationship_ids)) != len(relationship_ids):
        raise ContractError("Relationship ids must be unique")
    sample_limit = raw.get("sample_limit", 10)
    if not isinstance(sample_limit, int) or isinstance(sample_limit, bool) or sample_limit < 0 or sample_limit > 1000:
        raise ContractError("sample_limit must be an integer between 0 and 1000")

    metadata_value = raw.get("metadata", {})
    if not isinstance(metadata_value, Mapping):
        raise ContractError("metadata must be a mapping")
    try:
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ContractError("Contract contains a value that cannot be represented in JSON: {}".format(exc))
    contract_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return Contract(
        contract_version=1,
        dataset=dataset,
        formats=formats,
        unexpected_fields=unexpected,
        fields=fields,
        relationships=relationships,
        dataset_rules=dict(raw_dataset_rules),
        file_rules=dict(raw_file_rules),
        sample_limit=sample_limit,
        metadata=dict(metadata_value),
        source=dict(raw),
        hash=contract_hash,
    )


def load_contract(source: Union[str, Path, Mapping[str, Any], Contract]) -> Contract:
    if isinstance(source, Contract):
        return source
    if isinstance(source, Mapping):
        return parse_contract(source)
    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError("Cannot read contract {}: {}".format(path, exc))
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise ContractError("Cannot parse contract {}: {}".format(path, exc))
    return parse_contract(raw)
