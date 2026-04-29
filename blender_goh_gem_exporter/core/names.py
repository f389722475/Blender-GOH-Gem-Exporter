from __future__ import annotations

import re


def numbered_identifier(base: str, index: int, auto_number: bool, numbering: str = "increment") -> str:
    text = (base or "part").strip() or "part"
    if not auto_number or index <= 0:
        return text
    match = re.search(r"(\d+)$", text)
    if match:
        digits = match.group(1)
        start = int(digits)
        next_value = start + index
        replacement = str(next_value).zfill(len(digits))
        return f"{text[:-len(digits)]}{replacement}"
    if numbering == "optional_first":
        return f"{text}{index}"
    return f"{text}{index + 1}"


def numbered_display_name(base: str, suffix: str, index: int, auto_number: bool, numbering: str = "increment") -> str:
    return f"{numbered_identifier(base, index, auto_number, numbering)}{suffix}"
