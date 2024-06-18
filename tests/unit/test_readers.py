import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scivalid.errors import ReaderError
from scivalid.readers.csv_reader import CSVReader
from scivalid.readers.jsonl_reader import JSONLReader
from scivalid.readers.npz_reader import NPZReader


class ReaderTests(unittest.TestCase):
    def test_csv_preserves_missing_and_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("id,value\n1,2.5\n2,\n3,4.5\n", encoding="utf-8")
            reader = CSVReader(path, chunk_size=2)
            metadata = reader.inspect_metadata()
            chunks = list(reader.iterate_chunks())
            self.assertEqual(metadata.row_count, 3)
            self.assertEqual([chunk.row_count for chunk in chunks], [2, 1])
            self.assertIsNone(chunks[0].values["value"][1])

    def test_jsonl_stacks_equal_array_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.jsonl"
            path.write_text(
                '\n'.join(json.dumps({"id": index, "vector": [index, index + 1]}) for index in range(3)) + '\n',
                encoding="utf-8",
            )
            metadata = JSONLReader(path).inspect_metadata()
            chunk = next(JSONLReader(path).iterate_chunks())
            self.assertEqual(metadata.fields["vector"].shape, (3, 2))
            self.assertEqual(chunk.values["vector"].shape, (3, 2))

    def test_jsonl_rejects_non_object_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text("[1, 2, 3]\n", encoding="utf-8")
            with self.assertRaises(ReaderError):
                JSONLReader(path).inspect_metadata()

    def test_npz_preserves_dtype_shape_and_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arrays.npz"
            np.savez(path, ids=np.arange(5, dtype=np.int64), vectors=np.ones((5, 3), dtype=np.float32))
            reader = NPZReader(path, chunk_size=2)
            metadata = reader.inspect_metadata()
            chunks = list(reader.iterate_chunks())
            self.assertEqual(metadata.fields["vectors"].dtype, "float32")
            self.assertEqual(metadata.fields["vectors"].shape, (5, 3))
            self.assertEqual([chunk.row_count for chunk in chunks], [2, 2, 1])

    def test_truncated_npz_raises_reader_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.npz"
            path.write_bytes(b"not a zip archive")
            with self.assertRaises(ReaderError):
                NPZReader(path).inspect_metadata()

    def test_iso_dates_are_exposed_as_datetime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dates.csv"
            path.write_text("time\n2026-09-30\n2026-10-01\n", encoding="utf-8")
            metadata = CSVReader(path).inspect_metadata()
            self.assertEqual(metadata.fields["time"].dtype, "datetime")


if __name__ == "__main__":
    unittest.main()
