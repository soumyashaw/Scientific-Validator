"""Chunked CSV reader with conservative scalar type inference."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import numpy as np

from ..errors import ReaderError
from .base import DataChunk, DatasetReader, FieldInfo, ReaderMetadata, logical_dtype, values_to_array


MISSING_TOKENS = {""}


def _parse_scalar(value: Optional[str]) -> Any:
    if value is None or value.strip().lower() in MISSING_TOKENS:
        return None
    stripped = value.strip()
    lower = stripped.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return value


class CSVReader(DatasetReader):
    format_name = "csv"
    extensions = (".csv",)

    def _read_header(self) -> List[str]:
        try:
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ReaderError("Cannot read CSV {}: {}".format(self.path, exc))
        if not header:
            return []
        if len(set(header)) != len(header):
            raise ReaderError("CSV contains duplicate column names")
        if any(not name for name in header):
            raise ReaderError("CSV contains an empty column name")
        return header

    def inspect_metadata(self) -> ReaderMetadata:
        header = self._read_header()
        sample_values: Dict[str, List[Any]] = {name: [] for name in header}
        row_count = 0
        try:
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if None in row:
                        raise ReaderError("CSV row has more values than the header")
                    row_count += 1
                    if row_count <= min(self.chunk_size, 10_000):
                        for name in header:
                            sample_values[name].append(_parse_scalar(row.get(name)))
        except ReaderError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ReaderError("Cannot parse CSV {}: {}".format(self.path, exc))
        fields = {}
        for name in header:
            array = values_to_array(sample_values[name])
            fields[name] = FieldInfo(name, logical_dtype(array), (row_count,))
        return ReaderMetadata(
            path=self.path,
            format=self.format_name,
            reader=self.__class__.__name__,
            fields=fields,
            row_count=row_count,
            size_bytes=self.path.stat().st_size,
        )

    def iterate_chunks(self, required_fields: Optional[List[str]] = None) -> Iterator[DataChunk]:
        header = self._read_header()
        selected = header if required_fields is None else [name for name in header if name in required_fields]
        columns: Dict[str, List[Any]] = {name: [] for name in selected}
        locations: List[int] = []
        start = 0
        try:
            with self.path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for index, row in enumerate(reader):
                    if None in row:
                        raise ReaderError("CSV row {} has more values than the header".format(index + 2))
                    locations.append(index)
                    for name in selected:
                        columns[name].append(_parse_scalar(row.get(name)))
                    if len(locations) >= self.chunk_size:
                        yield DataChunk(
                            values={name: values_to_array(values) for name, values in columns.items()},
                            locations=locations,
                            start=start,
                        )
                        start += len(locations)
                        columns = {name: [] for name in selected}
                        locations = []
                if locations:
                    yield DataChunk(
                        values={name: values_to_array(values) for name, values in columns.items()},
                        locations=locations,
                        start=start,
                    )
        except ReaderError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ReaderError("Cannot parse CSV {}: {}".format(self.path, exc))
