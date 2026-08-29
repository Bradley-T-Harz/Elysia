import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import memory_manager


class TestMemoryManager(unittest.TestCase):
    def test_normalize_preview_truncates_long_text(self):
        text = "word " * 50

        result = memory_manager.normalize_preview(text, limit=40)

        self.assertLessEqual(len(result), 40)
        self.assertTrue(result.endswith("..."))

    def test_get_recent_session_memory_handles_missing_directory(self):
        temp_dir = Path(tempfile.mkdtemp())
        shutil.rmtree(temp_dir)

        with patch.object(memory_manager, "SESSIONS_DIR", temp_dir):
            result = memory_manager.get_recent_session_memory()

        self.assertEqual(result, [])

    def test_get_recent_session_memory_returns_expected_shape_sorted_and_bounded(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            (temp_dir / "2026-03-12_runtime-session.md").write_text(
                "# Runtime Session Note\noldest entry\n",
                encoding="utf-8",
            )
            (temp_dir / "2026-03-13_runtime-session.md").write_text(
                "# Runtime Session Note\nolder entry\n",
                encoding="utf-8",
            )
            (temp_dir / "2026-03-14_runtime-session.md").write_text(
                "# Runtime Session Note\nnewer entry\n",
                encoding="utf-8",
            )
            (temp_dir / "2026-03-15_runtime-session.md").write_text(
                "# Runtime Session Note\nnewest entry\n",
                encoding="utf-8",
            )

            with patch.object(memory_manager, "SESSIONS_DIR", temp_dir):
                result = memory_manager.get_recent_session_memory(limit=3)

            self.assertEqual(len(result), 3)

            self.assertEqual(
                [item["title"] for item in result],
                [
                    "2026-03-15_runtime-session.md",
                    "2026-03-14_runtime-session.md",
                    "2026-03-13_runtime-session.md",
                ],
            )

            for item in result:
                self.assertEqual(item["source"], "session_journal")
                self.assertTrue(item["path"].endswith(item["title"]))
                self.assertIsInstance(item["preview"], str)
                self.assertGreater(len(item["preview"]), 0)

        finally:
            shutil.rmtree(temp_dir)

    def test_get_recent_session_memory_can_exclude_paths(self):
        temp_dir = Path(tempfile.mkdtemp())

        try:
            newest = temp_dir / "2026-03-15_runtime-session.md"
            older = temp_dir / "2026-03-14_runtime-session.md"

            newest.write_text(
                "# Runtime Session Note\nnewest entry\n",
                encoding="utf-8",
            )
            older.write_text(
                "# Runtime Session Note\nolder entry\n",
                encoding="utf-8",
            )

            with patch.object(memory_manager, "SESSIONS_DIR", temp_dir):
                result = memory_manager.get_recent_session_memory(
                    limit=3,
                    exclude_paths=[str(newest)],
                )

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["title"], "2026-03-14_runtime-session.md")

        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()

