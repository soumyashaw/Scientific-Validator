"""Reader discovery with built-ins plus optional Python entry points."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Dict, Optional, Type

from ..errors import ReaderError
from .base import DatasetReader


_READERS: Dict[str, Type[DatasetReader]] = {}


def register_reader(name: str, reader: Type[DatasetReader]) -> None:
    normalized = name.lower().lstrip(".")
    if not issubclass(reader, DatasetReader):
        raise TypeError("Reader must subclass DatasetReader")
    _READERS[normalized] = reader


def _load_builtins() -> None:
    if _READERS:
        return
    from .csv_reader import CSVReader
    from .jsonl_reader import JSONLReader
    from .npz_reader import NPZReader

    register_reader("csv", CSVReader)
    register_reader("jsonl", JSONLReader)
    register_reader("ndjson", JSONLReader)
    register_reader("npz", NPZReader)


def _load_plugins() -> None:
    try:
        entries = metadata.entry_points()
        if hasattr(entries, "select"):
            selected = entries.select(group="scivalid.readers")
        else:  # Python 3.8 compatibility
            selected = entries.get("scivalid.readers", [])
        for entry in selected:
            if entry.name.lower() not in _READERS:
                register_reader(entry.name, entry.load())
    except Exception:
        # A broken third-party plugin must not make built-in readers disappear.
        return


def available_readers() -> Dict[str, Type[DatasetReader]]:
    _load_builtins()
    _load_plugins()
    return dict(_READERS)


def get_reader(path: Path, format_name: Optional[str] = None) -> Type[DatasetReader]:
    readers = available_readers()
    if format_name:
        key = format_name.lower().lstrip(".")
        if key not in readers:
            raise ReaderError("No reader registered for format {!r}".format(format_name))
        return readers[key]
    for reader in dict.fromkeys(readers.values()):
        if reader.can_open(Path(path)):
            return reader
    raise ReaderError("No reader registered for {}".format(path))

