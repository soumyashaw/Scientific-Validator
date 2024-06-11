"""Common streaming reader interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+Z?)?$")


@dataclass(frozen=True)
class FieldInfo:
    name: str
    dtype: str
    shape: Tuple[int, ...]


@dataclass(frozen=True)
class ReaderMetadata:
    path: Path
    format: str
    reader: str
    fields: Dict[str, FieldInfo]
    row_count: int
    size_bytes: int
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataChunk:
    values: Dict[str, np.ndarray]
    locations: List[Any]
    start: int

    @property
    def row_count(self) -> int:
        return len(self.locations)


class DatasetReader(ABC):
    """Reader plugins expose metadata and repeatable chunk iteration."""

    format_name = ""
    extensions: Tuple[str, ...] = ()

    def __init__(self, path: Path, chunk_size: int = 50_000):
        self.path = Path(path)
        self.chunk_size = chunk_size

    @classmethod
    def can_open(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions

    @abstractmethod
    def inspect_metadata(self) -> ReaderMetadata:
        raise NotImplementedError

    def list_fields(self) -> Dict[str, FieldInfo]:
        return self.inspect_metadata().fields

    @abstractmethod
    def iterate_chunks(self, required_fields: Optional[List[str]] = None) -> Iterator[DataChunk]:
        raise NotImplementedError

    def close(self) -> None:
        """Release reader resources. Built-ins open files per operation."""

    def __enter__(self) -> "DatasetReader":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


def logical_dtype(values: np.ndarray) -> str:
    """Return stable contract-oriented dtype names."""
    dtype = values.dtype
    if dtype.kind == "b":
        return "bool"
    if dtype.kind == "i":
        return "int{}".format(dtype.itemsize * 8)
    if dtype.kind == "u":
        return "uint{}".format(dtype.itemsize * 8)
    if dtype.kind == "f":
        return "float{}".format(dtype.itemsize * 8)
    if dtype.kind in ("U", "S"):
        return "string"
    if dtype.kind == "M":
        return "datetime"
    if dtype.kind == "O":
        nonmissing = [item for item in values.flat if item is not None]
        if not nonmissing:
            return "missing"
        if all(isinstance(item, (str, np.str_)) and ISO_DATE_RE.match(str(item)) for item in nonmissing):
            return "datetime"
        if nonmissing and all(isinstance(item, (str, np.str_)) for item in nonmissing):
            return "string"
        if nonmissing and all(isinstance(item, (bool, np.bool_)) for item in nonmissing):
            return "bool"
        if nonmissing and all(isinstance(item, (int, np.integer)) and not isinstance(item, bool) for item in nonmissing):
            return "int64"
        if nonmissing and all(isinstance(item, (int, float, np.number)) and not isinstance(item, bool) for item in nonmissing):
            return "float64"
    return "object"


def values_to_array(values: List[Any]) -> np.ndarray:
    """Build a useful ndarray without hiding ragged or missing values."""
    nonmissing = [item for item in values if item is not None]
    if not nonmissing:
        result = np.empty(len(values), dtype=object)
        result[:] = values
        return result
    if any(item is None for item in values):
        result = np.empty(len(values), dtype=object)
        result[:] = values
        return result
    if values and all(isinstance(item, str) and ISO_DATE_RE.match(item) for item in values):
        try:
            return np.asarray(values, dtype="datetime64[ns]")
        except (TypeError, ValueError):
            pass
    nested = [item for item in values if isinstance(item, (list, tuple, np.ndarray))]
    if nested:
        shapes = {tuple(np.asarray(item).shape) for item in nested}
        if len(nested) != len(values) or len(shapes) != 1:
            result = np.empty(len(values), dtype=object)
            result[:] = values
            return result
    try:
        return np.asarray(values)
    except (ValueError, TypeError):
        result = np.empty(len(values), dtype=object)
        result[:] = values
        return result
