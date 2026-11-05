"""Content approval is bound to actual artifact bytes and observed source passages."""
import json
from pathlib import Path
from supervision_store import digest

def _result_value(value):
    """실행 결과의 JSON만 해석한다. 명령문·로그 속 경로는 추측하지 않는다."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _receipt_paths(value):
    """실행 반환 봉투의 파일 영수증. 원문/source/input/임의 데이터는 순회하지 않는다.

    영수증은 파일 후보의 출처일 뿐 완료 증명이 아니다. 실제 바이트·지문은
    discover가 읽고, 내용의 적합성은 기존 최종 평가가 판단한다.
    """
    value = _result_value(value)
    if isinstance(value, list):
        for item in value:
            yield from _receipt_paths(item)
    elif isinstance(value, dict):
        if (value.get("success") is False or value.get("executed") is False
                or value.get("not_executed") is True
                or value.get("exit_code") not in (None, 0)):
            return
        # path만 있는 목록/검색 행과 구분한다. src/source는 입력 자료다.
        if (any(key in value for key in ("bytes", "size", "chars", "sha256"))
                or value.get("role") == "submission"):
            if isinstance(value.get("path"), str):
                yield value["path"]
        for key in ("output_path", "output_file"):
            if isinstance(value.get(key), str):
                yield value[key]
        for key in ("value", "result", "items", "artifact", "artifacts", "stdout", "output"):
            if key in value:
                yield from _receipt_paths(value[key])


def result_paths(controller, call):
    """셸·스크립트의 실행 반환 파일을 같은 턴 원문에서 회수한다."""
    from seam_metrics import is_shell_tool

    if call.get("is_error") or call.get("success") is False:
        return []
    name = (call.get("name") or call.get("tool_name") or "").rsplit("__", 1)[-1].rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[-1]
    runtime = call.get("runtime_calls") or []
    producer = is_shell_tool(name) or name in {"exec_command", "run_shell_command", "run_script"}
    producer |= any(row.get("action") in {"self:script", "self:write", "self:edit", "self:patch"}
                    for row in runtime if isinstance(row, dict))
    if not producer:
        shown = _result_value(call.get("result"))
        return list(_receipt_paths(shown)) if isinstance(shown, dict) and shown.get("role") == "submission" else []
    shown = _result_value(call.get("result"))
    if isinstance(shown, dict):
        if (shown.get("success") is False or shown.get("executed") is False
                or shown.get("not_executed") is True):
            return []
        # 축약된 value만 보지 않고 이미 보존된 동일 실행의 원문을 읽는다.
        ref = shown.get("result_ref")
        if shown.get("edition") == 2 and isinstance(ref, dict) and ref.get("id"):
            try:
                raw = controller.store.read_evidence(ref["id"], 0, None)["text"]
                return list(_receipt_paths(raw))
            except (OSError, ValueError, KeyError):
                pass
    return list(_receipt_paths(shown))


def discover(controller, response, tool_calls, *, submitted=()):
    # Links are references; only actual write/return receipts and declared submissions
    # establish output candidates. Consumers share this collection.
    paths = set(submitted)
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        paths.update(result_paths(controller, call))
        # 계산된 경로는 코드 문자열이 아니라 실행 증거에 있다. 부분 실패 전
        # 저장된 파일도 검사하되, 읽기 대상이나 실행하지 않은 코드는 산출물로 보지 않는다.
        for invocation in call.get("runtime_calls") or []:
            if isinstance(invocation, dict) and invocation.get("action") in {"self:write", "self:edit", "self:patch"}:
                target = (invocation.get("targets") or {}).get("path")
                if isinstance(target, str):
                    paths.add(target)
        if call.get("is_error") or call.get("success") is False:
            continue
        name = call.get("name") or call.get("tool_name") or ""
        inp = call.get("input") or {}
        if not isinstance(inp, dict):
            continue
        from cognitive_trace import _FILE_WRITE_TOOL_NAMES, _FILE_PATH_INPUT_KEYS
        if name.rsplit("__", 1)[-1].rsplit('/', 1)[-1] in _FILE_WRITE_TOOL_NAMES:
            paths.update(inp[k] for k in _FILE_PATH_INPUT_KEYS if isinstance(inp.get(k), str))
    artifacts, seen = [], set()
    for name in sorted(paths):
        path = Path(name)
        if not path.is_absolute():
            path = Path(controller.project_path) / path
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        if path.suffix.lower() not in {".md", ".txt", ".html", ".json", ".csv", ".tsv", ".py", ".js", ".ts", ".tsx", ".jsx",
                                       ".css", ".yaml", ".yml", ".sh", ".sql", ".toml", ".xml", ".svg"}:
            continue
        try:
            content = path.read_bytes().decode('utf-8')
        except (OSError, UnicodeError) as exc:
            artifacts.append({"path": str(path), "error": str(exc)})
            continue
        ref = controller.store.evidence(content)
        artifacts.append({"path": str(path.resolve()), "hash": digest(content),
                          "evidence_id": ref["id"], "chars": len(content)})
    return artifacts
