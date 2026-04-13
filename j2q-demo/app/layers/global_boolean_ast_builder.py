from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {}


def build_global_boolean_ast(expansion_output: Any) -> dict[str, Any]:
    expansion = _as_dict(expansion_output)

    must_sentences: list[dict[str, Any]] = []
    nice_sentences: list[dict[str, Any]] = []
    unresolved_sentence_ids: list[int] = []

    for sentence in expansion.get("sentence_tool_expansions", []):
        sentence_id = sentence.get("sentence_id")
        tool_groups = sentence.get("tool_groups", [])

        if not tool_groups:
            if isinstance(sentence_id, int):
                unresolved_sentence_ids.append(sentence_id)
            continue

        sentence_node = {
            "type": "group",
            "level": "sentence",
            "sentence_id": sentence_id,
            "operator": "AND",
            "children": [
                {
                    "type": "term_group",
                    "tool_code": group.get("tool_code", ""),
                    "category": group.get("category", ""),
                    "terms_operator": group.get("terms_operator", "OR"),
                    "terms": group.get("terms", []),
                }
                for group in tool_groups
            ],
        }

        section = sentence.get("section")
        if section == "must":
            must_sentences.append(sentence_node)
        elif section == "nice":
            nice_sentences.append(sentence_node)

    section_nodes: list[dict[str, Any]] = []
    if must_sentences:
        section_nodes.append(
            {
                "type": "group",
                "level": "section",
                "section": "must",
                "operator": "AND",
                "children": must_sentences,
            }
        )
    if nice_sentences:
        section_nodes.append(
            {
                "type": "group",
                "level": "section",
                "section": "nice",
                "operator": "OR",
                "children": nice_sentences,
            }
        )

    return {
        "jd_id": expansion.get("jd_id", ""),
        "j2q_model": expansion.get("j2q_model", ""),
        "global_boolean_ast": {
            "type": "group",
            "level": "global",
            "operator": "AND",
            "children": section_nodes,
        },
        "unresolved_sentence_ids": unresolved_sentence_ids,
    }
