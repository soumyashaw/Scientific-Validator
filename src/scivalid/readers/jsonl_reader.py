"""Streaming JSON Lines reader for top-level object fields."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from ..errors import ReaderError
from .base import DataChunk, DatasetReader, FieldInfo, ReaderMetadata, logical_dtype, values_to_array


class JSONLReader(DatasetReader):
    format_name = "jsonl"
    extensions = (".jsonl", ".ndjson")

    def _records(self) -> Iterator[tuple]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError as exc:
                        raise ReaderError("Invalid JSON at line {}: {}".format(line_number, exc))
                    if not isinstance(record, dict):
                        raise ReaderError("JSON line {} must contain an object".format(line_number))
                    yield line_number, record
        except ReaderError:
            raise
        except (OSError, UnicodeError) as exc:
            raise ReaderError("Cannot read JSON Lines {}: {}".format(self.path, exc))

    def inspect_metadata(self) -> ReaderMetadata:
        samples: Dict[str, List[Any]] = {}
        row_count = 0
        for _, record in self._records():
            row_count += 1
            all_names = set(samples) | set(record)
            for name in all_names:
                samples.setdefault(name, [None] * (row_count - 1))
                if len(samples[name]) < min(row_count, 10_000):
                    samples[name].append(record.get(name))
        fields = {}
        for name, values in samples.items():
            array = values_to_array(values)
            full_shape = (row_count,) + tuple(array.shape[1:])
            fields[name] = FieldInfo(name, logical_dtype(array), full_shape)
        return ReaderMetadata(
            path=self.path,
            format=self.format_name,
            reader=self.__class__.__name__,
            fields=fields,
            row_count=row_count,
            size_bytes=self.path.stat().st_size,
        )

    def iterate_chunks(self, required_fields: Optional[List[str]] = None) -> Iterator[DataChunk]:
        columns: Dict[str, List[Any]] = {}
        locations: List[int] = []
        start = 0
        for line_number, record in self._records():
            selected = set(record) if required_fields is None else set(required_fields)
            for name in set(columns) | selected:
                columns.setdefault(name, [None] * len(locations))
                columns[name].append(record.get(name))
            locations.append(line_number)
            if len(locations) >= self.chunk_size:
                yield DataChunk(
                    values={name: values_to_array(values) for name, values in columns.items()},
                    locations=locations,
                    start=start,
                )
                start += len(locations)
                columns = {}
                locations = []
        if locations:
            yield DataChunk(
                values={name: values_to_array(values) for name, values in columns.items()},
                locations=locations,
                start=start,
            )

