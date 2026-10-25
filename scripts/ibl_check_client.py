"""검사기 공용 현행 HTTP 계약: 한 번 실행하고 원형 참조를 완전히 읽는다."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_v2_ir import unpack

def request(fields, pid, *, base="http://127.0.0.1:8765", timeout=60, on_admission=None):
    # agent_id=__self_check__ — 이 점검의 실행이 action_health 에 source='self_check' 로
    # 기록되게 한다(없으면 'usage' 로 실려 §1D 실사용 통계를 자가 점검 실패로 오염 —
    # channel_read 97% 거짓 시그널의 진범). postprocess(AI 압축)도 함께 스킵돼 점검 AI 0.
    body = json.dumps({**fields, "project_id": pid,
                       "agent_id": "__self_check__", "edition": 2}).encode()
    headers = {"Content-Type": "application/json"}
    # ★부모 자격 동반(2026-09-15) — 러너(스케줄러 잡·조종실 요청)가 쥔 실행 자격을 환경변수로
    # 물려받아 X-Runtime-Parent 로 싣는다(cli_provider._identity_headers / mcp_server 와 같은
    # 통로). 이게 없던 동안 재기동 drain(접수 중단) 중엔 이 점검의 호출이 '새 작업'으로 보여
    # 전부 503 즉시 거절됐다 — drain 은 이 잡이 끝나길 기다리면서 잡의 호출은 거절하는 셈.
    # 자식으로 실리면 drain 동안에도 접수된다(runtime_work.WorkRegistry.reserve: parent∈groups).
    _parent = os.environ.get("INDIEBIZ_RUNTIME_PARENT")
    if _parent:
        headers["X-Runtime-Parent"] = _parent
    req = urllib.request.Request(base + "/ibl/execute", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        if e.code == 503 and isinstance(payload, dict) and payload.get("executed") is False:
            if on_admission:
                on_admission(str(payload.get("detail") or raw)[:160])
        return {"_transport_error": f"HTTP {e.code}: {raw[:80]}"}
    except Exception as e:
        return {"_transport_error": str(e)}
    return out


def execute(code, pid="정보센터", *, request_page=None, timeout=60):
    """HTTP 표시 사본 대신 저장된 원형 값을 조회한다. 도구는 한 번만 실행한다."""
    call = request_page or (lambda fields, project: request(fields, project, timeout=timeout))
    result = call({"code": code}, pid)
    if not isinstance(result, dict) or result.get("success") is not True or "value_wire" in result:
        return result
    reference = result.get("result_ref") or {}
    if not isinstance(reference, dict) or not reference.get("id"):
        return {**result, "_protocol_error": "성공 응답에 원형 결과 참조가 없습니다."}
    page_request = {"id": reference["id"], "path": ["value_wire"], "offset": 0, "limit": 60000}
    chunks, offset, total = [], 0, None
    try:
        while True:
            page = call({"code": "", "read_result": page_request}, pid)
            if not isinstance(page, dict) or not isinstance(page.get("text"), str):
                raise ValueError("원형 결과 조회 실패: " + str(page)[:160])
            scope = page.get("read_scope") or {}
            if (page.get("id") != reference["id"] or page.get("path") != ["value_wire"]
                    or page.get("offset") != offset or scope.get("start") != offset
                    or scope.get("end") != offset + len(page["text"])
                    or type(page.get("chars")) is not int or page["chars"] > 4_000_000):
                raise ValueError("원형 결과 페이지의 참조·범위가 일치하지 않습니다.")
            if total is not None and total != page["chars"]:
                raise ValueError("조회 중 원형 결과 길이가 바뀌었습니다.")
            total = page["chars"]
            chunks.append(page["text"])
            offset += len(page["text"])
            if offset == total:
                if page.get("next_read") is not None:
                    raise ValueError("완료한 결과에 다음 페이지가 있습니다.")
                break
            following = page.get("next_read")
            if (not page["text"] or not isinstance(following, dict)
                    or following.get("id") != reference["id"]
                    or following.get("path") != ["value_wire"] or following.get("offset") != offset):
                raise ValueError("원형 결과 페이지가 누락됐습니다.")
            page_request = following
        return {**result, "value_wire": json.loads("".join(chunks))}
    except (ValueError, TypeError, KeyError) as exc:
        return {**result, "_protocol_error": str(exc)}


class CheckFailure(ValueError):
    """실행·전송 실패는 값의 모양 판정에 넣지 않는다."""

    def __init__(self, key, detail, result=None):
        super().__init__(f"{key}: {detail}")
        self.key, self.detail, self.result = key, detail, result or {}


def value_of(result):
    """상태와 wire를 먼저 검사한다. 해독한 업무 값의 키는 재해석하지 않는다."""
    if not isinstance(result, dict):
        raise CheckFailure("_protocol_error", "실행 응답이 Record가 아닙니다.")
    for key in ("_transport_error", "_protocol_error"):
        if key in result:
            raise CheckFailure(key, result[key], result)
    if result.get("success") is not True:
        raise CheckFailure("_execution_error", result.get("error") or result.get("issues") or "실행 실패", result)
    wire = result.get("value_wire")
    if not isinstance(wire, dict) or wire.get("protocol") not in ("ibl-value/1", "ibl-value/2"):
        raise CheckFailure("_protocol_error", "성공 응답의 value_wire가 없거나 지원하지 않는 프로토콜입니다.", result)
    try:
        return unpack(wire["data"])
    except Exception as exc:
        raise CheckFailure("_protocol_error", str(exc), result) from exc


def final_of(result):
    """출력·프로브용 뷰. 모양 판정은 value_of와 CheckFailure를 사용한다."""
    try:
        return value_of(result)
    except CheckFailure as exc:
        return {exc.key: exc.detail, "executed": exc.result.get("executed"),
                "diagnostic": exc.result.get("diagnostic")}


def item_rows(value):
    """현행 행 값: native List 또는 도구 Record의 명시적인 items 필드."""
    rows = value.get("items") if isinstance(value, dict) else value
    return rows if isinstance(rows, list) else None
