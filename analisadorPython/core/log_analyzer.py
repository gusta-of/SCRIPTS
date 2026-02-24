"""Core logic for log parsing and input validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

MAX_FILE_SIZE_MB = 50
DEFAULT_CONTEXT = 30
DEFAULT_NO_EXCEPTION_MESSAGE = "Nenhuma excecao encontrada no log."
DEFAULT_SEPARATOR = "\n" + ("-" * 72) + "\n"
DEFAULT_KEYWORDS = ("Exception", "Error", "Traceback", "CRITICAL", "FATAL")


@dataclass(frozen=True)
class AnalysisResult:
    content: str
    block_count: int
    blocks: tuple[str, ...]


def build_keyword_pattern(keywords: list[str] | tuple[str, ...] | None = None) -> re.Pattern[str]:
    """Build a case-insensitive regex pattern from keywords."""
    source = keywords if keywords is not None else DEFAULT_KEYWORDS
    cleaned = [term.strip() for term in source if term and term.strip()]
    if not cleaned:
        # Regex that never matches.
        return re.compile(r"(?!x)x")

    unique_terms = list(dict.fromkeys(cleaned))
    combined = "|".join(re.escape(term) for term in unique_terms)
    return re.compile(combined, re.IGNORECASE)


def validate_input_path(path: Path, max_file_size_mb: float = MAX_FILE_SIZE_MB) -> tuple[bool, str]:
    """Validate path existence, file type and max size."""
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return False, "O arquivo selecionado nao existe ou esta inacessivel."

    if not resolved.is_file():
        return False, "O caminho selecionado nao e um arquivo valido."

    file_size_mb = resolved.stat().st_size / (1024 * 1024)
    if file_size_mb > max_file_size_mb:
        return False, (
            f"Este arquivo possui {file_size_mb:.1f} MB. "
            f"O limite e {max_file_size_mb:.1f} MB."
        )

    return True, ""


def extract_exception_blocks(
    file_path: Path,
    context: int = DEFAULT_CONTEXT,
    keywords: list[str] | tuple[str, ...] | None = None,
    pattern: re.Pattern[str] | None = None,
    separator: str = DEFAULT_SEPARATOR,
) -> AnalysisResult:
    """Extract sections around lines that match exception/error patterns."""
    with file_path.open("r", encoding="utf-8", errors="replace") as file_obj:
        lines = file_obj.readlines()

    return extract_exception_blocks_from_lines(
        lines,
        context=context,
        keywords=keywords,
        pattern=pattern,
        separator=separator,
    )


def extract_exception_blocks_from_lines(
    lines: list[str],
    context: int = DEFAULT_CONTEXT,
    keywords: list[str] | tuple[str, ...] | None = None,
    pattern: re.Pattern[str] | None = None,
    separator: str = DEFAULT_SEPARATOR,
) -> AnalysisResult:
    below_context = max(0, int(context))
    resolved_pattern = pattern if pattern is not None else build_keyword_pattern(keywords)
    ranges: list[tuple[int, int, list[int]]] = []
    blocks: list[str] = []

    for idx, line in enumerate(lines):
        if resolved_pattern.search(line):
            start = idx
            end = min(idx + below_context + 1, len(lines))
            if not ranges:
                ranges.append((start, end, [idx]))
                continue

            prev_start, prev_end, prev_hits = ranges[-1]
            if start < prev_end:
                merged_end = max(prev_end, end)
                ranges[-1] = (prev_start, merged_end, prev_hits + [idx])
            else:
                ranges.append((start, end, [idx]))

    for start, end, hit_indexes in ranges:
        if len(hit_indexes) == 1:
            header = f"[Linha {hit_indexes[0] + 1}]\n"
        else:
            hit_lines = ", ".join(str(pos + 1) for pos in hit_indexes)
            header = f"[Linhas {hit_lines}]\n"
        section = header + "".join(lines[start:end]).rstrip()
        blocks.append(section)

    if not blocks:
        return AnalysisResult(content=DEFAULT_NO_EXCEPTION_MESSAGE, block_count=0, blocks=())

    return AnalysisResult(content=separator.join(blocks), block_count=len(blocks), blocks=tuple(blocks))
