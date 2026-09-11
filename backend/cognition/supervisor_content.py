"""Content approval is bound to actual artifact bytes and observed source passages."""
import json
import re
from pathlib import Path
from supervision_store import digest

FACETS = ("meaning", "sources", "counts")


class ContentIssue(str):
    """Keep the public error string while exposing a bounded evidence repair path."""
    def __new__(cls, message, *, kind="content", evidence_id=None, quote=None):
        obj = super().__new__(cls, message)
        obj.kind, obj.evidence_id, obj.quote = kind, evidence_id, quote
        return obj


CONTRACT = """content_artifacts의 각 파일은 content_checks로 검수한다.
첫 검수에서는 파일 본문을 evidence 도구로 끝까지 읽는다. 재검수의 content_changes에는
이미 읽은 동일 구간과 실제 변경 구간이 구분되어 있다. 새 구간·의존 주장을 검토하고
필요한 문맥만 추가로 읽는다. 원천은 기존 도구 결과를 먼저 재사용한다.
각 파일의 {path,hash,meaning,sources,counts}를 반환한다. 세 항목은 각각
{status:"passed|not_applicable",reason,evidence:[{id,quote}]}이다.
meaning: 제목·요약·결론의 주체, 측정량(수준/증가율), 단위, 기간, 인과, 미확인 한계가
본문 및 원천과 같은지 대조한다. sources: 핵심 주장 원문, 발행 기관·날짜·링크 귀속을 확인한다.
counts: 최종 채택·검증된 항목을 기준으로 중복 사건과 미확인 항목을 제외해 재집계하고
본문 분류와 숫자가 일치하는지 확인한다. 수집 당시 후보 수를 최종 사건 수로 쓰지 않는다.
counts가 passed이면 calculations:[{id,items_path:"items",where:{필드:값},
identity:["사건 식별 필드"],expected:정수}]도 낸다. id는 최종 행 JSON의 증거 ID이며
items_path는 그 안의 행 목록 경로다. where의 필드는 모두 존재해야 한다.
동일 사건의 여러 보도는 같은 식별자를 쓴다. 날짜 미확인 등 제외 조건은 where에 반영한다.
하네스가 해당 원문에서 필터·유일성·계수를 다시 계산한다.
passed에는 실제 읽은 증거 ID와 정확한 발췌를 남긴다. sources의 근거는 산출물 자신이 아닌
독립 원천이어야 한다. 산술·집계는 table 연산이나 기존 검증 도구로 계산한다.
execute 결과의 evidence.id는 함께 받은 page의 정확한 원문 ID다. 이 ID와 실제 문장을 인용한다.
사건에 보이는 다른 원문 ID를 인용하려면 evidence로 해당 구간을 먼저 읽는다.
해당 내용이 전혀 없는 경우만 not_applicable과 이유를 쓴다. 증거 부족은 해당 없음이 아니다.
발견한 불일치는 한번에 REWORK로 반환한다. coverage만 확인하고 내용을 승인할 수 없다.
"""


def reconcile(store, calculations):
    from common.field_path import walk_path, MISSING
    from common.value_semantics import values_equal, relation_identity
    if not isinstance(calculations, list) or not calculations:
        return False
    for calc in calculations:
        try:
            raw = store.read_evidence(calc["id"], 0, None)["text"]
            if not store.evidence_fully_read(calc["id"]):
                return False
            data = json.loads(raw)
            rows = walk_path(data, calc.get("items_path", "items"))
            where, keys = calc.get("where", {}), calc.get("identity", [])
            if (not isinstance(rows, list) or not isinstance(where, dict)
                    or not isinstance(keys, list) or not keys
                    or type(calc.get("expected")) is not int):
                return False
            identities = set()
            for row in rows:
                values = {k: walk_path(row, k) for k in set(where) | set(keys)}
                if any(v is MISSING or v is None for v in values.values()):
                    return False
                if all(values_equal(values[k], v) for k, v in where.items()):
                    identities.add(tuple(relation_identity(values[k]) for k in keys))
            if len(identities) != calc["expected"]:
                return False
        except (KeyError, ValueError, TypeError, OSError):
            return False
    return True


def discover(controller, response, tool_calls):
    paths = set(re.findall(r"(?<![\w:])((?:/|outputs/)[^\n`\"'<>]*?\.(?:md|txt|html))(?=[\s)`\"'<>]|$)", response or ""))
    for call in tool_calls or []:
        if not isinstance(call, dict) or call.get("is_error") or call.get("success") is False:
            continue
        name = call.get("name") or call.get("tool_name") or ""
        inp = call.get("input") or {}
        if name.rsplit("__", 1)[-1] in {"Write", "Edit", "write_file"}:
            paths.update(inp[k] for k in ("path", "file_path") if isinstance(inp.get(k), str))
    artifacts = []
    for name in sorted(paths):
        path = Path(name)
        if not path.is_absolute():
            path = Path(controller.project_path) / path
        if path.suffix.lower() not in {".md", ".txt", ".html"} or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        ref = controller.store.evidence(content)
        artifacts.append({"path": str(path.resolve()), "hash": digest(content),
                          "evidence_id": ref["id"], "chars": len(content)})
    return artifacts


def validate(controller, decision):
    if decision.get("status") != "APPROVED":
        return None
    checks = decision.get("content_checks", [])
    if not isinstance(checks, list):
        return "content_checks가 목록이 아닙니다"
    for artifact in controller.content_artifacts:
        check = next((c for c in checks if isinstance(c, dict) and c.get("path") == artifact["path"]), {})
        if check.get("hash") != artifact["hash"]:
            return f"내용 검수의 파일 지문 누락·불일치: {artifact['path']}"
        try:
            if digest(Path(artifact["path"]).read_text(encoding="utf-8")) != artifact["hash"]:
                return "내용 검수 중 산출물이 바뀌었습니다"
        except OSError:
            return "내용 검수 중 산출물을 읽을 수 없습니다"
        if not controller.store.evidence_fully_read(artifact["evidence_id"]):
            return "산출물 본문의 미검수 범위가 남았습니다"
        for facet in FACETS:
            value = check.get(facet, {})
            if not isinstance(value, dict) or not str(value.get("reason") or "").strip():
                return f"내용 검수 누락: {facet}"
            if value.get("status") == "not_applicable":
                continue
            if value.get("status") != "passed" or not value.get("evidence"):
                return f"내용 검수 근거 부족: {facet}"
            if facet == "counts" and not reconcile(controller.store, value.get("calculations")):
                return "최종 행의 검증·중복 제거 후 계수가 승인 숫자와 일치하지 않습니다"
            for ref in value["evidence"]:
                if not isinstance(ref, dict):
                    return "내용 검수 발췌 형식 오류"
                key, quote = ref.get("id"), ref.get("quote")
                if facet == "sources" and key in {artifact["hash"], controller.store.manifest()["hash"]}:
                    return "출처 검수는 산출물 자신의 재인용으로 통과할 수 없습니다"
                if not controller.store.evidence_quote_read(key, quote):
                    return ContentIssue(
                        f"내용 검수 발췌가 실제로 읽은 원문과 일치하지 않습니다: "
                        f"{facet}, evidence={key}, path={artifact['path']}. "
                        "해당 증거의 발췌 구간을 evidence로 읽고 ID·원문을 확인하세요.",
                        kind="citation", evidence_id=key, quote=quote)
    return None
