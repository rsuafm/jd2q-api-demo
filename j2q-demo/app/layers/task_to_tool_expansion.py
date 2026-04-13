from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


def _as_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [_as_dict(item) for item in value]
    return []


def build_sentence_tool_expansions(
    top1_output: Any,
    tool_master_data: Any,
) -> dict[str, Any]:
    top1 = _as_dict(top1_output)
    rows = _as_rows(tool_master_data)

    tool_map = {row["No"]: row.get("tool_groups", []) for row in rows if "No" in row}
    expansions: list[dict[str, Any]] = []

    for match in top1.get("sentence_top1_matches", []):
        taxonomy_row_no = match.get("taxonomy_row_no")
        if taxonomy_row_no is None:
            tool_groups = []
        else:
            tool_groups = tool_map.get(taxonomy_row_no, [])

        expansions.append(
            {
                "sentence_id": match.get("sentence_id"),
                "section": match.get("section"),
                "taxonomy_row_no": taxonomy_row_no,
                "tool_groups": tool_groups,
            }
        )

    return {
        "jd_id": top1.get("jd_id", ""),
        "j2q_model": top1.get("j2q_model", ""),
        "sentence_tool_expansions": expansions,
    }
