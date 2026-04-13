from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

_SYSTEM_INSTRUCTION = """You are a semantic matching engine for a JD-to-query pipeline.

Your task is to map each input sentence to the single closest taxonomy row.

Important:
For each sentence, you must choose only from that sentence's provided taxonomy_candidates.
Do not use any taxonomy_row_no outside the candidates for that sentence.

Selection priority:
1. Respect explicit tool-code hints implied by the provided candidate list.
2. Then choose the semantically closest task_doc for the sentence.normalized_text.
3. If no candidate is meaningfully related, return null.

Rules:
1. For every input sentence, output exactly one result object.
2. The number of items in sentence_top1_matches must be exactly equal to the number of input sentence items.
3. Preserve input sentence order.
4. Each result object must contain:
   - sentence_id
   - section
   - taxonomy_row_no
5. taxonomy_row_no must be one of the provided candidate No values for that sentence, or null.
6. If multiple candidates seem equally good, choose the smaller No.
7. Do not explain your reasoning.
8. Do not return scores.
9. Do not return multiple candidates for one sentence.
10. Output valid JSON only.
11. Do not wrap the output in markdown fences."""

_LOGGER = logging.getLogger(__name__)
_ENV_CACHE: dict[str, str] | None = None


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


def _load_dotenv_cache() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE

    env_map: dict[str, str] = {}
    env_path = Path(".env")
    if env_path.exists():
        bare_key_candidate: str | None = None
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                if bare_key_candidate is None:
                    bare_key_candidate = line.strip().strip("'").strip('"')
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                env_map[key] = value
        if "GEMINI_API_KEY" not in env_map and bare_key_candidate:
            env_map["GEMINI_API_KEY"] = bare_key_candidate

    _ENV_CACHE = env_map
    return _ENV_CACHE


def _get_config_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    return _load_dotenv_cache().get(name, default)


def _normalize_match_text(text: str) -> str:
    return text.strip().lower()


def _build_tool_code_term_index(tool_master_data: list[dict[str, Any]]) -> list[tuple[str, str]]:
    index: list[tuple[str, str]] = []
    for row in tool_master_data:
        for group in row.get("tool_groups", []):
            tool_code = str(group.get("tool_code", ""))
            for term in group.get("terms", []):
                normalized = _normalize_match_text(str(term))
                if normalized and tool_code:
                    index.append((tool_code, normalized))
    return index


def _matched_tool_codes(sentence_normalized_text: str, tool_code_term_index: list[tuple[str, str]]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    haystack = _normalize_match_text(sentence_normalized_text)
    for tool_code, term in tool_code_term_index:
        if term in haystack and tool_code not in seen:
            seen.add(tool_code)
            found.append(tool_code)
    return found


def _candidate_taxonomy_for_sentence(
    sentence_text: str,
    tool_master_data: list[dict[str, Any]],
    taxonomy_retrieval_data: list[dict[str, Any]],
    tool_code_term_index: list[tuple[str, str]],
) -> tuple[list[str], list[dict[str, Any]]]:
    matched_codes = _matched_tool_codes(sentence_text, tool_code_term_index)

    if matched_codes:
        matched_set = set(matched_codes)
        filtered_rows = [
            row
            for row in tool_master_data
            if any(str(group.get("tool_code", "")) in matched_set for group in row.get("tool_groups", []))
        ]
        candidates = [{"No": row.get("No"), "task_doc": row.get("task_doc", "")} for row in filtered_rows]
    else:
        candidates = [{"No": row.get("No"), "task_doc": row.get("task_doc", "")} for row in taxonomy_retrieval_data]

    dedup: dict[int, dict[str, Any]] = {}
    for item in candidates:
        no = item.get("No")
        task_doc = item.get("task_doc", "")
        if isinstance(no, int) and no not in dedup:
            dedup[no] = {"No": no, "task_doc": task_doc}

    ordered_candidates = [dedup[no] for no in sorted(dedup.keys())]
    return matched_codes, ordered_candidates


def _build_sentence_candidate_taxonomy(
    sentence_split_output: dict[str, Any],
    tool_master_data: list[dict[str, Any]],
    taxonomy_retrieval_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index = _build_tool_code_term_index(tool_master_data)
    payload_items: list[dict[str, Any]] = []

    for unit in sentence_split_output.get("sentence_units", []):
        matched_codes, candidates = _candidate_taxonomy_for_sentence(
            str(unit.get("normalized_text", "")),
            tool_master_data,
            taxonomy_retrieval_data,
            index,
        )
        payload_items.append(
            {
                "sentence_id": unit.get("sentence_id"),
                "section": unit.get("section"),
                "normalized_text": unit.get("normalized_text"),
                "matched_tool_codes": matched_codes,
                "taxonomy_candidates": candidates,
            }
        )

    return payload_items


def _build_fallback_matches(sentence_split_output: dict[str, Any]) -> dict[str, Any]:
    matches = [
        {
            "sentence_id": unit.get("sentence_id"),
            "section": unit.get("section"),
            "taxonomy_row_no": None,
        }
        for unit in sentence_split_output.get("sentence_units", [])
    ]
    return {
        "jd_id": sentence_split_output.get("jd_id", ""),
        "j2q_model": sentence_split_output.get("j2q_model", ""),
        "sentence_top1_matches": matches,
    }


def _build_user_prompt(
    sentence_split_output: dict[str, Any],
    sentence_candidate_taxonomy: list[dict[str, Any]],
) -> str:
    payload = {
        "jd_id": sentence_split_output.get("jd_id", ""),
        "j2q_model": sentence_split_output.get("j2q_model", ""),
        "sentence_candidate_taxonomy": sentence_candidate_taxonomy,
    }

    return (
        "Match each sentence to the single closest taxonomy row.\n\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Return JSON with:\n"
        "- the same jd_id\n"
        "- the same j2q_model\n"
        "- sentence_top1_matches containing exactly one item for each input sentence item\n"
        "- sentence_top1_matches length must equal input sentence item count\n"
        "- result order must match input sentence order\n\n"
        "Return format:\n"
        "{\n"
        "  \"jd_id\": \"<jd_id>\",\n"
        "  \"j2q_model\": \"<j2q_model>\",\n"
        "  \"sentence_top1_matches\": [\n"
        "    {\n"
        "      \"sentence_id\": 1,\n"
        "      \"section\": \"must\",\n"
        "      \"taxonomy_row_no\": 20\n"
        "    }\n"
        "  ]\n"
        "}"
    )


def _extract_text_response(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(response, "candidates", None)
    if not candidates:
        return ""

    first = candidates[0]
    content = getattr(first, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if not parts:
        return ""

    chunks: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str):
            chunks.append(part_text)
    return "".join(chunks)


def _call_gemini_once(
    sentence_split_output: dict[str, Any],
    sentence_candidate_taxonomy: list[dict[str, Any]],
) -> dict[str, Any] | None:
    api_key = _get_config_value("GEMINI_API_KEY")
    if not api_key:
        _LOGGER.warning("GEMINI_API_KEY is not set (env or .env). Top1 Match falls back to taxonomy_row_no=null.")
        return None

    model_name = _get_config_value("GEMINI_MODEL", "gemini-2.5-flash-lite")
    timeout_seconds = float(_get_config_value("GEMINI_TIMEOUT_SECONDS", "15") or "15")
    prompt = _build_user_prompt(sentence_split_output, sentence_candidate_taxonomy)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    system_instruction=_SYSTEM_INSTRUCTION,
                ),
            )
            response = future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        _LOGGER.warning(
            "Gemini call timed out after %.1fs. Top1 Match falls back to taxonomy_row_no=null.",
            timeout_seconds,
        )
        return None
    except Exception as exc:
        _LOGGER.warning("Gemini call failed. Top1 Match falls back to taxonomy_row_no=null. error=%s", exc)
        return None

    raw_text = _extract_text_response(response).strip()
    if not raw_text:
        _LOGGER.warning("Gemini returned empty text. Top1 Match falls back to taxonomy_row_no=null.")
        return None

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        _LOGGER.warning("Gemini returned invalid JSON. Top1 Match falls back to taxonomy_row_no=null. error=%s", exc)
        return None

    return parsed if isinstance(parsed, dict) else None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _validated_matches(
    sentence_split_output: dict[str, Any],
    sentence_candidate_taxonomy: list[dict[str, Any]],
    raw_output: dict[str, Any] | None,
) -> dict[str, Any]:
    fallback = _build_fallback_matches(sentence_split_output)
    if raw_output is None:
        return fallback

    raw_matches = raw_output.get("sentence_top1_matches")
    sentence_units = sentence_split_output.get("sentence_units", [])
    if not isinstance(raw_matches, list) or len(raw_matches) != len(sentence_units):
        return fallback

    normalized_matches: list[dict[str, Any]] = []

    for index, unit in enumerate(sentence_units):
        item = raw_matches[index]
        allowed_candidate_nos = {
            candidate.get("No")
            for candidate in sentence_candidate_taxonomy[index].get("taxonomy_candidates", [])
            if isinstance(candidate, dict) and isinstance(candidate.get("No"), int)
        }

        taxonomy_row_no: int | None = None

        if isinstance(item, dict):
            input_sentence_id = _coerce_int(item.get("sentence_id"))
            input_section = item.get("section")
            input_taxonomy_row_no = _coerce_int(item.get("taxonomy_row_no"))

            if input_sentence_id == unit.get("sentence_id") and input_section == unit.get("section"):
                if input_taxonomy_row_no is None:
                    taxonomy_row_no = None
                elif input_taxonomy_row_no in allowed_candidate_nos:
                    taxonomy_row_no = input_taxonomy_row_no

        normalized_matches.append(
            {
                "sentence_id": unit.get("sentence_id"),
                "section": unit.get("section"),
                "taxonomy_row_no": taxonomy_row_no,
            }
        )

    return {
        "jd_id": sentence_split_output.get("jd_id", ""),
        "j2q_model": sentence_split_output.get("j2q_model", ""),
        "sentence_top1_matches": normalized_matches,
    }


def build_sentence_top1_matches(
    sentence_split_output: Any,
    taxonomy_retrieval_data: Any,
    tool_master_data: Any,
) -> dict[str, Any]:
    split = _as_dict(sentence_split_output)
    taxonomy_rows = _as_rows(taxonomy_retrieval_data)
    tool_rows = _as_rows(tool_master_data)

    sentence_candidate_taxonomy = _build_sentence_candidate_taxonomy(
        split,
        tool_rows,
        taxonomy_rows,
    )
    raw_output = _call_gemini_once(split, sentence_candidate_taxonomy)
    return _validated_matches(split, sentence_candidate_taxonomy, raw_output)
