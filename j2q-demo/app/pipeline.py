from __future__ import annotations

import json
from pathlib import Path

from app.layers.compile_sql import compile_sql_output
from app.layers.global_boolean_ast_builder import build_global_boolean_ast
from app.layers.sentence_split import build_sentence_units
from app.layers.task_to_tool_expansion import build_sentence_tool_expansions
from app.layers.top1_match import build_sentence_top1_matches
from typing import Any


def _load_json_rows(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def run_pipeline(request: dict[str, Any]) -> dict[str, Any]:
    taxonomy_rows = _load_json_rows(str(request.get("taxonomy_retrieval_json_path", "")))
    tool_master_rows = _load_json_rows(str(request.get("tool_master_json_path", "")))

    sentence_split_output = build_sentence_units(request)
    top1_output = build_sentence_top1_matches(sentence_split_output, taxonomy_rows, tool_master_rows)
    expansion_output = build_sentence_tool_expansions(top1_output, tool_master_rows)
    boolean_ast_output = build_global_boolean_ast(expansion_output)

    return compile_sql_output(
        boolean_ast_output,
        sentence_split_output,
        top1_output,
        taxonomy_rows,
    )
