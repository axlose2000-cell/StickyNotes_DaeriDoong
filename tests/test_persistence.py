import tempfile
import unittest
from pathlib import Path

from persistence import atomic_write_json, read_json_file


class PersistenceTests(unittest.TestCase):
    def test_atomic_write_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "notes_data.json"
            payload = {"notes": [{"id": "1", "title": "A"}], "app_state": {"x": 1}}
            atomic_write_json(path, payload)
            loaded = read_json_file(path, {})
            self.assertEqual(loaded, payload)


if __name__ == "__main__":
    unittest.main()
