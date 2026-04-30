from __future__ import annotations

import re


NUMBERING_RULE_SOURCE = "SOURCE"
NUMBERING_RULE_PLAIN = "PLAIN"
NUMBERING_RULE_PAD2 = "PAD2"

_NUMBER_SUFFIX_RE = re.compile(r"(\d+)$")
_BLENDER_DUPLICATE_SUFFIX_RE = re.compile(r"\.\d{3}$")


def strip_blender_duplicate_suffix(name: str) -> str:
    return _BLENDER_DUPLICATE_SUFFIX_RE.sub("", (name or "").strip())


def numbered_base_parts(base: str) -> tuple[str, int, int, bool]:
    text = (base or "part").strip() or "part"
    match = _NUMBER_SUFFIX_RE.search(text)
    if not match:
        return text, 1, 0, False
    digits = match.group(1)
    return text[: -len(digits)], int(digits), len(digits), True


def _padding_width(source_width: int, numbering_rule: str) -> int:
    rule = (numbering_rule or NUMBERING_RULE_SOURCE).upper()
    if rule == NUMBERING_RULE_PAD2:
        return max(2, source_width)
    if rule == NUMBERING_RULE_PLAIN:
        return 0
    return source_width


def numbered_identifier_for_number(base: str, number: int, numbering_rule: str = NUMBERING_RULE_SOURCE) -> str:
    prefix, _start, width, _has_suffix = numbered_base_parts(base)
    pad = _padding_width(width, numbering_rule)
    if pad:
        return f"{prefix}{max(0, number):0{pad}d}"
    return f"{prefix}{max(0, number)}"


def number_from_identifier(identifier: str, base: str, numbering: str = "increment") -> int | None:
    text = strip_blender_duplicate_suffix(identifier)
    base_text = (base or "part").strip() or "part"
    if numbering == "optional_first":
        if text.lower() == base_text.lower():
            return 0
        if not text.lower().startswith(base_text.lower()):
            return None
        suffix = text[len(base_text) :]
        return int(suffix) if suffix.isdigit() else None

    prefix, _start, _width, has_suffix = numbered_base_parts(base_text)
    if has_suffix:
        if not text.lower().startswith(prefix.lower()):
            return None
        suffix = text[len(prefix) :]
        return int(suffix) if suffix.isdigit() else None

    if text.lower() == base_text.lower():
        return 0
    if not text.lower().startswith(base_text.lower()):
        return None
    suffix = text[len(base_text) :]
    return int(suffix) if suffix.isdigit() else None


def numbered_identifier(
    base: str,
    index: int,
    auto_number: bool,
    numbering: str = "increment",
    numbering_rule: str = NUMBERING_RULE_SOURCE,
) -> str:
    text = (base or "part").strip() or "part"
    if not auto_number:
        return text

    if numbering == "optional_first":
        if index <= 0:
            return text
        pad = 2 if (numbering_rule or "").upper() == NUMBERING_RULE_PAD2 else 0
        return f"{text}{index:0{pad}d}" if pad else f"{text}{index}"

    prefix, start, width, has_suffix = numbered_base_parts(text)
    if has_suffix:
        return numbered_identifier_for_number(text, start + max(0, index), numbering_rule)
    if index <= 0:
        return text
    pad = _padding_width(width, numbering_rule)
    value = index + 1
    if pad:
        return f"{prefix}{value:0{pad}d}"
    return f"{text}{value}"


def numbered_display_name(
    base: str,
    suffix: str,
    index: int,
    auto_number: bool,
    numbering: str = "increment",
    numbering_rule: str = NUMBERING_RULE_SOURCE,
) -> str:
    return f"{numbered_identifier(base, index, auto_number, numbering, numbering_rule)}{suffix}"
