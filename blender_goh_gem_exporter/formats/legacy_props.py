from __future__ import annotations

import re


def legacy_flag_set(text: str) -> set[str]:
    flags: set[str] = set()
    for line in text.replace("\r", "\n").split("\n"):
        token = line.strip()
        if not token or "=" in token:
            continue
        flags.add(token.lower())
    return flags


def legacy_key_values(text: str) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    for line in text.replace("\r", "\n").split("\n"):
        token = line.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key:
            continue
        data.setdefault(key, []).append(value)
    return data


def parse_frame_range(text: str) -> tuple[int, int] | None:
    match = re.match(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*$", text or "")
    if not match:
        return None
    start_frame = int(match.group(1))
    end_frame = int(match.group(2))
    return (start_frame, max(start_frame, end_frame))
