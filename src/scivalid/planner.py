"""Deterministic input resolution and validation-plan construction."""

from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Union

from .contract import Contract
from .errors import ConfigurationError


@dataclass(frozen=True)
class ValidationPlan:
    paths: List[Path]
    required_fields: List[str]
    exact_state_rules: List[str]


def _expand_one(value: Union[str, Path], formats: Sequence[str]) -> List[Path]:
    text = str(value)
    if any(character in text for character in "*?["):
        matches = [Path(item) for item in glob.glob(text, recursive=True)]
        return matches if matches else [Path(text)]
    path = Path(value)
    if path.is_dir():
        extensions = {"." + item for item in formats}
        extensions.add(".ndjson")
        return [item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in extensions]
    return [path]


def build_plan(paths: Iterable[Union[str, Path]], contract: Contract) -> ValidationPlan:
    if isinstance(paths, (str, Path)):
        paths = [paths]
    expanded: List[Path] = []
    for item in paths:
        expanded.extend(_expand_one(item, contract.formats))
    unique = sorted({path.expanduser().absolute() for path in expanded}, key=lambda item: str(item))
    if not unique:
        raise ConfigurationError("No input files matched")

    required = set(contract.fields)
    for relationship in contract.relationships:
        for key in ("left", "right", "field", "condition_field", "required_field"):
            if key in relationship.config:
                required.add(relationship.config[key])
        required.update(relationship.config.get("components", []))
        required.update(relationship.config.get("flags", []))
    exact = []
    if any(field.unique == "global" for field in contract.fields.values()):
        exact.append("global uniqueness")
    if "duplicate_row_rate" in contract.dataset_rules:
        exact.append("duplicate-row rate")
    return ValidationPlan(paths=unique, required_fields=sorted(required), exact_state_rules=exact)

