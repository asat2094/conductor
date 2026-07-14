"""Minimal-slice context builder for briefs.

Builds the SMALLEST context slice a maker needs (least proprietary code
egress, bounded brief). Given a file's full text + declared line ranges,
returns only those slices.

References:
  - S6/ADR-0017: Minimal slice principle
  - REQ-R4/E3: Bounded context exposure
"""


def slice_file(text: str, ranges: list[tuple[int, int]]) -> str:
    """Extract line ranges from text.

    Args:
        text: Full file text.
        ranges: List of (start_line, end_line) tuples, 1-based inclusive.
                Out-of-range clamped to file bounds.

    Returns:
        Concatenation of requested line spans, separated by "..." for
        non-contiguous spans.
    """
    # Remove trailing newline if present for consistent line counting
    text_stripped = text.rstrip("\n")
    lines = text_stripped.split("\n") if text_stripped else []

    # Clamp ranges to valid line indices
    clamped_ranges = []
    for start, end in ranges:
        # Convert to 0-based indexing
        clamped_start = max(0, start - 1)
        clamped_end = min(len(lines), end)
        if clamped_start < clamped_end:
            clamped_ranges.append((clamped_start, clamped_end))

    if not clamped_ranges:
        return ""

    # Sort by start position for correct ordering
    clamped_ranges.sort()

    # Build slices with separator for non-contiguous spans
    slices = []
    for start, end in clamped_ranges:
        # Extract lines (0-based, end is exclusive in Python slicing)
        slice_lines = lines[start:end]
        slices.append("\n".join(slice_lines))

    return "...".join(slices)


def build_slices(
    file_texts: dict[str, str],
    context_slices: list[dict],
) -> dict[str, str]:
    """Build context slices from declared file regions.

    Args:
        file_texts: {path: full_text} mapping.
        context_slices: List of {"path", "start_line", "end_line"} dicts.

    Returns:
        {path: sliced_text} dict. Only declared slices included (minimal).
        A path with no declared slice is OMITTED.
    """
    result = {}

    for slice_spec in context_slices:
        path = slice_spec["path"]
        start_line = slice_spec["start_line"]
        end_line = slice_spec["end_line"]

        if path in file_texts:
            text = file_texts[path]
            sliced = slice_file(text, [(start_line, end_line)])
            result[path] = sliced

    return result


def slice_bytes(slices_dict: dict[str, str]) -> int:
    """Count total characters across slices.

    Args:
        slices_dict: {path: sliced_text} mapping.

    Returns:
        Total character count across all slices.
    """
    return sum(len(content) for content in slices_dict.values())
