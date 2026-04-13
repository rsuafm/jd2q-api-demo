from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        return resp.getcode(), json.loads(body)


def _wait_port(host: str, port: int, timeout_sec: float = 10.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"Server did not open {host}:{port} in time")


def run_verification() -> None:
    repo = Path(__file__).resolve().parent
    host = "127.0.0.1"
    port = 8011
    url = f"http://{host}:{port}/generate"

    proc = subprocess.Popen(
        ["python3", "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_port(host, port)

        case_a = {
            "jd_id": "jd_e2e_resolved",
            "j2q_model": "v1",
            "sections": [
                {"section_name": "must", "text": "BIツールの利用経験（Power BI / Tableau）"},
                {"section_name": "nice", "text": "PythonやRでの分析経験"},
            ],
            "taxonomy_retrieval_json_path": "data/taxonomy_retrieval.json",
            "tool_master_json_path": "data/tool_master.json",
        }
        code_a, res_a = _post_json(url, case_a)

        _assert(code_a == 200, "Case A status must be 200")
        for key in [
            "jd_id",
            "j2q_model",
            "sql_where_clause",
            "sentence_taxonomy_pairs",
            "clause_trace",
            "unresolved_sentence_ids",
        ]:
            _assert(key in res_a, f"Case A missing key: {key}")

        _assert(res_a["jd_id"] == "jd_e2e_resolved", "Case A jd_id mismatch")
        _assert(isinstance(res_a["sql_where_clause"], str), "Case A sql_where_clause must be string")
        _assert(isinstance(res_a["sentence_taxonomy_pairs"], list), "Case A sentence_taxonomy_pairs must be list")
        _assert(isinstance(res_a["clause_trace"], list), "Case A clause_trace must be list")
        _assert(isinstance(res_a["unresolved_sentence_ids"], list), "Case A unresolved_sentence_ids must be list")

        pairs_a = res_a["sentence_taxonomy_pairs"]
        _assert(len(pairs_a) == 2, "Case A sentence_taxonomy_pairs must contain all sentences")
        _assert([p.get("sentence_id") for p in pairs_a] == [1, 2], "Case A sentence order must be preserved")

        for item in pairs_a:
            for key in ["sentence_id", "sentence", "section", "taxonomy_row_no", "task_doc"]:
                _assert(key in item, f"Case A pair missing key: {key}")
            _assert(item.get("task_doc") != "", "Case A task_doc must never be empty string")

        if res_a["clause_trace"]:
            for item in res_a["clause_trace"]:
                for key in [
                    "section",
                    "sentence_id",
                    "sentence",
                    "taxonomy_row_no",
                    "task_doc",
                    "tool_code",
                    "terms_operator",
                    "terms",
                ]:
                    _assert(key in item, f"Case A clause_trace item missing key: {key}")
            _assert(res_a["sql_where_clause"] != "1=1", "Case A sql_where_clause must not be 1=1 when trace exists")

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp_tool_master:
            tmp_tool_master.write("[]")
            tmp_tool_master_path = tmp_tool_master.name

        case_b = {
            "jd_id": "jd_e2e_empty",
            "j2q_model": "v1",
            "sections": [
                {"section_name": "must", "text": "zzzz_unmatched_requirement_12345"},
            ],
            "taxonomy_retrieval_json_path": "data/taxonomy_retrieval.json",
            "tool_master_json_path": tmp_tool_master_path,
        }
        code_b, res_b = _post_json(url, case_b)

        _assert(code_b == 200, "Case B status must be 200")
        _assert(res_b.get("sql_where_clause") == "1=1", "Case B sql_where_clause must be exactly 1=1")

        pairs_b = res_b.get("sentence_taxonomy_pairs")
        _assert(isinstance(pairs_b, list), "Case B sentence_taxonomy_pairs must be list")
        _assert(len(pairs_b) == 1, "Case B sentence_taxonomy_pairs length must be 1")

        first = pairs_b[0]
        _assert(first.get("sentence_id") == 1, "Case B first sentence_id must be 1")
        _assert(first.get("task_doc") != "", "Case B task_doc must never be empty string")

        taxonomy_row_no = first.get("taxonomy_row_no")
        unresolved = res_b.get("unresolved_sentence_ids", [])
        _assert(isinstance(unresolved, list), "Case B unresolved_sentence_ids must be list")
        _assert(all(isinstance(x, int) for x in unresolved), "Case B unresolved_sentence_ids must be int list")
        _assert(taxonomy_row_no is None or 1 in unresolved, "Case B taxonomy_row_no non-null should be unresolved")

        _assert(isinstance(res_b.get("clause_trace"), list), "Case B clause_trace must be list")
        _assert(res_b.get("clause_trace") == [], "Case B clause_trace should be empty for zero effective conditions")

        print("PASS: Case A")
        print("PASS: Case B")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    run_verification()
