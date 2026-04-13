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


def build_sentence_index(sentence_split_output: dict[str, Any]) -> dict[int, dict[str, str]]:
    return {
        unit["sentence_id"]: {
            "sentence": unit.get("sentence", ""),
            "section": unit.get("section", ""),
        }
        for unit in sentence_split_output.get("sentence_units", [])
        if isinstance(unit.get("sentence_id"), int)
    }


def build_sentence_to_taxonomy_index(top1_output: dict[str, Any]) -> dict[int, int | None]:
    return {
        match["sentence_id"]: match.get("taxonomy_row_no")
        for match in top1_output.get("sentence_top1_matches", [])
        if isinstance(match.get("sentence_id"), int)
    }


def build_taxonomy_index(taxonomy_rows: list[dict[str, Any]]) -> dict[int, str]:
    return {
        row["No"]: row.get("task_doc", "")
        for row in taxonomy_rows
        if isinstance(row.get("No"), int)
    }


def build_sentence_taxonomy_pairs(
    sentence_split_output: dict[str, Any],
    sentence_to_taxonomy_index: dict[int, int | None],
    taxonomy_index: dict[int, str],
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []

    for unit in sentence_split_output.get("sentence_units", []):
        sentence_id = unit.get("sentence_id")
        taxonomy_row_no = sentence_to_taxonomy_index.get(sentence_id) if isinstance(sentence_id, int) else None
        task_doc = taxonomy_index.get(taxonomy_row_no) if taxonomy_row_no is not None else None

        pairs.append(
            {
                "sentence_id": sentence_id,
                "sentence": unit.get("sentence", ""),
                "section": unit.get("section", ""),
                "taxonomy_row_no": taxonomy_row_no,
                "task_doc": task_doc,
            }
        )

    return pairs


def _normalize_sql_term(term: str) -> str:
    return term.strip().lower().replace("'", "''")


def _indent(text: str, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else line for line in text.splitlines())


def compile_ast_to_sql(global_boolean_ast: dict[str, Any]) -> str:
    def compile_node(node: dict[str, Any]) -> str:
        node_type = node.get("type")

        if node_type == "term_group":
            terms = node.get("terms") or []
            valid_terms = [_normalize_sql_term(str(term)) for term in terms if _normalize_sql_term(str(term))]
            if not valid_terms:
                return ""

            join_op = str(node.get("terms_operator", "OR")).upper()
            join_op = "AND" if join_op == "AND" else "OR"
            lines = [f"LOWER(tool_text) LIKE '%{term}%'" for term in valid_terms]
            body = f"\n{join_op}\n".join(lines)
            return f"(\n{_indent(body)}\n)"

        if node_type == "group":
            children = node.get("children") or []
            compiled_children: list[str] = []
            for child in children:
                compiled = compile_node(child)
                if compiled:
                    compiled_children.append(compiled)

            if not compiled_children:
                return ""

            join_op = str(node.get("operator", "AND")).upper()
            join_op = "OR" if join_op == "OR" else "AND"
            body = f"\n{join_op}\n".join(compiled_children)
            return f"(\n{_indent(body)}\n)"

        return ""

    sql = compile_node(global_boolean_ast)
    return sql if sql else "1=1"


def build_clause_trace(
    global_boolean_ast: dict[str, Any],
    sentence_index: dict[int, dict[str, str]],
    sentence_to_taxonomy_index: dict[int, int | None],
    taxonomy_index: dict[int, str],
) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], section: str | None, sentence_id: int | None) -> None:
        node_type = node.get("type")

        if node_type == "group":
            level = node.get("level")
            next_section = section
            next_sentence_id = sentence_id

            if level == "section":
                next_section = str(node.get("section", ""))
            elif level == "sentence":
                raw_sentence_id = node.get("sentence_id")
                next_sentence_id = raw_sentence_id if isinstance(raw_sentence_id, int) else None

            for child in node.get("children") or []:
                if isinstance(child, dict):
                    walk(child, next_section, next_sentence_id)
            return

        if node_type == "term_group":
            terms = node.get("terms") or []
            if not terms or sentence_id is None:
                return

            sentence_meta = sentence_index.get(sentence_id, {})
            taxonomy_row_no = sentence_to_taxonomy_index.get(sentence_id)
            task_doc = taxonomy_index.get(taxonomy_row_no) if taxonomy_row_no is not None else None

            traces.append(
                {
                    "section": section or sentence_meta.get("section", ""),
                    "sentence_id": sentence_id,
                    "sentence": sentence_meta.get("sentence", ""),
                    "taxonomy_row_no": taxonomy_row_no,
                    "task_doc": task_doc,
                    "tool_code": node.get("tool_code", ""),
                    "terms_operator": node.get("terms_operator", "OR"),
                    "terms": terms,
                }
            )

    walk(global_boolean_ast, None, None)
    return traces


def assemble_final_response(
    jd_id: str,
    j2q_model: str,
    sql_where_clause: str,
    sentence_taxonomy_pairs: list[dict[str, Any]],
    clause_trace: list[dict[str, Any]],
    unresolved_sentence_ids: list[int],
) -> dict[str, Any]:
    return {
        "jd_id": jd_id,
        "j2q_model": j2q_model,
        "sql_where_clause": sql_where_clause,
        "sentence_taxonomy_pairs": sentence_taxonomy_pairs,
        "clause_trace": clause_trace,
        "unresolved_sentence_ids": unresolved_sentence_ids,
    }


def compile_sql_output(
    boolean_ast_output: Any,
    sentence_split_output: Any,
    top1_output: Any,
    taxonomy_rows: Any,
) -> dict[str, Any]:
    ast_output = _as_dict(boolean_ast_output)
    split_output = _as_dict(sentence_split_output)
    top1 = _as_dict(top1_output)
    taxonomy = _as_rows(taxonomy_rows)

    sentence_index = build_sentence_index(split_output)
    sentence_to_taxonomy_index = build_sentence_to_taxonomy_index(top1)
    taxonomy_index = build_taxonomy_index(taxonomy)

    sentence_taxonomy_pairs = build_sentence_taxonomy_pairs(
        split_output,
        sentence_to_taxonomy_index,
        taxonomy_index,
    )
    global_ast = _as_dict(ast_output.get("global_boolean_ast", {}))
    clause_trace = build_clause_trace(
        global_ast,
        sentence_index,
        sentence_to_taxonomy_index,
        taxonomy_index,
    )
    sql_where_clause = compile_ast_to_sql(global_ast)

    unresolved = ast_output.get("unresolved_sentence_ids", [])
    unresolved_sentence_ids = [sid for sid in unresolved if isinstance(sid, int)]

    return assemble_final_response(
        jd_id=str(ast_output.get("jd_id", "")),
        j2q_model=str(ast_output.get("j2q_model", "")),
        sql_where_clause=sql_where_clause,
        sentence_taxonomy_pairs=sentence_taxonomy_pairs,
        clause_trace=clause_trace,
        unresolved_sentence_ids=unresolved_sentence_ids,
    )
