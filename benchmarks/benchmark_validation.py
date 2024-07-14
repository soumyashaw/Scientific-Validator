"""Reproducible throughput and peak-Python-memory benchmark."""

import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from scivalid import validate


CONTRACT = {
    "contract_version": 1,
    "dataset": "benchmark",
    "formats": ["csv"],
    "fields": {
        "event_id": {"type": "int64", "unique": "global"},
        "energy": {"type": "float64", "finite": True, "min": 0.0},
        "category": {"type": "string", "allowed": ["signal", "background"]},
    },
}


def run(rows: int, chunk_size: int):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.csv"
        with path.open("w", encoding="utf-8") as handle:
            handle.write("event_id,energy,category\n")
            for index in range(rows):
                category = "signal" if index % 2 else "background"
                handle.write("{},{:.6f},{}\n".format(index, index * 0.01, category))
        tracemalloc.start()
        started = time.perf_counter()
        report = validate([path], CONTRACT, chunk_size=chunk_size)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return {
        "rows": rows,
        "chunk_size": chunk_size,
        "elapsed_seconds": elapsed,
        "rows_per_second": rows / elapsed if elapsed else None,
        "peak_python_bytes": peak,
        "findings": report.summary,
        "note": "tracemalloc excludes memory allocated directly by some native libraries",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[1_000, 10_000, 50_000])
    args = parser.parse_args()
    print(json.dumps([run(args.rows, size) for size in args.chunk_sizes], indent=2))


if __name__ == "__main__":
    main()

