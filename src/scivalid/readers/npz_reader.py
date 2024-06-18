"""NumPy NPZ reader with first-axis chunking and pickle disabled."""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

import numpy as np

from ..errors import ReaderError
from .base import DataChunk, DatasetReader, FieldInfo, ReaderMetadata, logical_dtype


class NPZReader(DatasetReader):
    format_name = "npz"
    extensions = (".npz",)

    def _open(self):
        try:
            return np.load(str(self.path), allow_pickle=False)
        except (OSError, ValueError, EOFError) as exc:
            raise ReaderError("Cannot open NPZ {}: {}".format(self.path, exc))

    def inspect_metadata(self) -> ReaderMetadata:
        with self._open() as archive:
            fields: Dict[str, FieldInfo] = {}
            row_counts = set()
            for name in archive.files:
                try:
                    array = archive[name]
                except ValueError as exc:
                    raise ReaderError("Cannot read array {!r}: {}".format(name, exc))
                fields[name] = FieldInfo(name, logical_dtype(array), tuple(array.shape))
                if array.ndim > 0:
                    row_counts.add(array.shape[0])
            row_count = max(row_counts) if row_counts else (1 if fields else 0)
        return ReaderMetadata(
            path=self.path,
            format=self.format_name,
            reader=self.__class__.__name__,
            fields=fields,
            row_count=row_count,
            size_bytes=self.path.stat().st_size,
            attributes={"row_counts": sorted(row_counts)},
        )

    def iterate_chunks(self, required_fields: Optional[List[str]] = None) -> Iterator[DataChunk]:
        with self._open() as archive:
            names = archive.files if required_fields is None else [name for name in archive.files if name in required_fields]
            arrays = {name: archive[name] for name in names}
            non_scalar = [array.shape[0] for array in arrays.values() if array.ndim > 0]
            total = max(non_scalar) if non_scalar else (1 if arrays else 0)
            for start in range(0, total, self.chunk_size):
                end = min(start + self.chunk_size, total)
                values = {}
                for name, array in arrays.items():
                    if array.ndim == 0:
                        values[name] = np.repeat(array.reshape(1), end - start)
                    elif array.shape[0] >= end:
                        values[name] = array[start:end]
                    else:
                        values[name] = array[start:array.shape[0]]
                yield DataChunk(values=values, locations=list(range(start, end)), start=start)
