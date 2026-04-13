from __future__ import annotations

import re
from typing import Any


_ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "vs.",
    "etc.",
)
_DOT_TOKEN = "<DOT>"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


def _protect_abbreviations(text: str) -> str:
    protected = text
    for abbr in _ABBREVIATIONS:
        pattern = re.compile(re.escape(abbr), re.IGNORECASE)
        protected = pattern.sub(lambda m: m.group(0).replace(".", _DOT_TOKEN), protected)
    return protected


def _unprotect_abbreviations(text: str) -> str:
    return text.replace(_DOT_TOKEN, ".")


def split_section_text(text: str) -> list[str]:
    fragments: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        working_line = _protect_abbreviations(line)
        current: list[str] = []

        for index, char in enumerate(working_line):
            current.append(char)
            if char in ".!?":
                next_char = working_line[index + 1] if index + 1 < len(working_line) else ""
                if not next_char or next_char.isspace():
                    fragment = _unprotect_abbreviations("".join(current)).strip()
                    if fragment:
                        fragments.append(fragment)
                    current = []

        tail = _unprotect_abbreviations("".join(current)).strip()
        if tail:
            fragments.append(tail)

    return fragments


def normalize_text(text: str) -> str:
    normalized = text.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[.!?]+$", "", normalized).strip()
    return normalized


def build_sentence_units(request: Any) -> dict[str, Any]:
    req = _as_dict(request)
    sentence_units: list[dict[str, Any]] = []
    sentence_id = 1

    for section in req.get("sections", []):
        section_name = str(section.get("section_name", ""))
        text = str(section.get("text", ""))
        for sentence_text in split_section_text(text):
            sentence_units.append(
                {
                    "sentence_id": sentence_id,
                    "sentence": sentence_text,
                    "section": section_name,
                    "normalized_text": normalize_text(sentence_text),
                }
            )
            sentence_id += 1

    return {
        "jd_id": req.get("jd_id", ""),
        "j2q_model": req.get("j2q_model", ""),
        "sentence_units": sentence_units,
    }
