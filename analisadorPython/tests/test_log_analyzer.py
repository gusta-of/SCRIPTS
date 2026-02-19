import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.log_analyzer import (
    DEFAULT_NO_EXCEPTION_MESSAGE,
    build_keyword_pattern,
    extract_exception_blocks,
    extract_exception_blocks_from_lines,
    validate_input_path,
)


class TestLogAnalyzerCore(unittest.TestCase):
    def test_extract_exception_blocks_from_lines_with_context(self) -> None:
        lines = [
            "line 1\n",
            "line 2\n",
            "Traceback (most recent call last):\n",
            "line 4\n",
        ]

        result = extract_exception_blocks_from_lines(lines, context=1)

        self.assertEqual(result.block_count, 1)
        self.assertEqual(len(result.blocks), 1)
        self.assertIn("line 2", result.content)
        self.assertIn("Traceback", result.content)
        self.assertIn("line 4", result.content)

    def test_extract_exception_blocks_uses_fixed_10_lines_above(self) -> None:
        lines = [f"line {idx}\n" for idx in range(1, 30)]
        lines[20] = "ValueError: boom\n"

        result = extract_exception_blocks_from_lines(lines, context=2)

        self.assertEqual(result.block_count, 1)
        block_lines = result.blocks[0].splitlines()
        self.assertEqual(block_lines[0], "line 11")
        self.assertEqual(block_lines[-1], "line 23")
        self.assertEqual(len(block_lines), 13)

    def test_extract_exception_blocks_from_lines_without_matches(self) -> None:
        lines = ["ok\n", "still ok\n"]

        result = extract_exception_blocks_from_lines(lines, context=2)

        self.assertEqual(result.block_count, 0)
        self.assertEqual(result.blocks, ())
        self.assertEqual(result.content, DEFAULT_NO_EXCEPTION_MESSAGE)

    def test_extract_exception_blocks_with_custom_keywords(self) -> None:
        lines = ["ok\n", "Timeout while requesting service\n", "done\n"]

        result = extract_exception_blocks_from_lines(lines, context=1, keywords=["Timeout"])

        self.assertEqual(result.block_count, 1)
        self.assertIn("Timeout", result.content)

    def test_extract_exception_blocks_with_empty_keywords(self) -> None:
        lines = ["Error should not match when no keywords are active\n"]

        result = extract_exception_blocks_from_lines(lines, context=1, keywords=[])

        self.assertEqual(result.block_count, 0)
        self.assertEqual(result.content, DEFAULT_NO_EXCEPTION_MESSAGE)

    def test_build_keyword_pattern_is_case_insensitive(self) -> None:
        pattern = build_keyword_pattern(["timeout"])
        self.assertIsNotNone(pattern.search("TIMEOUT at gateway"))

    def test_extract_exception_blocks_from_file(self) -> None:
        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "app.log"
            file_path.write_text("start\nValueError: failed\nend\n", encoding="utf-8")

            result = extract_exception_blocks(file_path, context=0)

            self.assertEqual(result.block_count, 1)
            self.assertEqual(len(result.blocks), 1)
            self.assertIn("ValueError", result.content)

    def test_validate_input_path_missing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.log"

            is_valid, error = validate_input_path(missing)

            self.assertFalse(is_valid)
            self.assertIn("nao existe", error)

    def test_validate_input_path_rejects_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            is_valid, error = validate_input_path(Path(tmp))

            self.assertFalse(is_valid)
            self.assertIn("arquivo valido", error)

    def test_validate_input_path_max_size_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "large.log"
            file_path.write_bytes(b"a" * 4096)

            is_valid, error = validate_input_path(file_path, max_file_size_mb=0.001)

            self.assertFalse(is_valid)
            self.assertIn("limite", error)


if __name__ == "__main__":
    unittest.main()
