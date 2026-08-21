"""ibl_envelope.py — 실행 봉투 다이어트 (2026-08-22, 프로그램급 IBL M1 / 설계 §2.5-2).

`execute_pipeline` 의 봉투 `{results: [{step, result(원형 문자열)}…], final_result}` 는 모든 step
결과를 **원형으로** 모델에게 돌려준다 — 그리고 final_result 는 마지막 step 의 사본이라 같은 내용이
두 번 실린다. 08-21 실측: 보고서류 에피소드 하나에 IBL 47회, 그 결과 전부가 컨텍스트에 쌓였다.

여기서는 **에이전트 경계**(`_execute_ibl_unified` — 인프로세스 도구·MCP 재진입·/ibl/execute 공통)
에서 `results[]` 를 step 별 *요약*(shape·count·bytes·preview)으로 접고 `final_result` 는 원형으로 둔다.
  - 실패 step 은 원형 오류문을 그대로 싣는다(어디서 왜 — 진단 정보는 다이어트 대상이 아님).
  - `verbose: true` 면 손대지 않는다(옛 모양 그대로).
  - 표면(조종실·앱·폰·웹소켓)은 이미 final_result 만 읽는다 → 무영향.
  - 봉투에 `_results_summarized: true` 표지 — MCP 브리지(_trim_for_agent)·평가자(cognitive_trace)가
    "final_result 를 지우면 안 된다"를 이 표지로 안다.
"""
import json
from typing import Any, Dict

PREVIEW_CHARS = 160          # message/text 미리보기 길이
PREVIEW_ITEM_CHARS = 300     # 첫 행(JSON) 미리보기 길이
KEYS_MAX = 12

_HINT = ("results[] 는 step 요약(shape·count·bytes·preview) — 전체 데이터는 final_result. "
         "step 원형이 필요하면 verbose: true 로 다시 실행.")


def _compact(obj: Any, cap: int) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s if len(s) <= cap else s[:cap] + f"…(+{len(s) - cap}자)"


def summarize_result(raw: Any) -> Dict[str, Any]:
    """step 결과 하나(대개 JSON 문자열)의 요약 — shape/count/bytes/preview/keys."""
    s = raw if isinstance(raw, str) else _compact(raw, 10 ** 9)
    out: Dict[str, Any] = {"bytes": len(s)}
    obj: Any = raw
    if isinstance(raw, str):
        t = raw.strip()
        if t[:1] in "{[":
            try:
                obj = json.loads(t)
            except Exception:
                obj = raw
    if isinstance(obj, dict):
        keys = sorted(k for k in obj.keys() if isinstance(k, str) and not k.startswith("_"))
        out["keys"] = keys[:KEYS_MAX]
        if obj.get("success") is False or ("error" in obj and not obj.get("success")):
            out["shape"] = "error"
            out["error"] = obj.get("error") or obj.get("message")   # 원형 — 진단은 다이어트 밖
            return out
        items = obj.get("items")
        if isinstance(items, list):
            out["shape"] = "items"
            out["count"] = len(items)
            if items:
                first = items[0]
                if isinstance(first, dict):
                    out["columns"] = sorted(str(k) for k in first.keys())[:KEYS_MAX]
                out["preview"] = _compact(first, PREVIEW_ITEM_CHARS)
            msg = obj.get("message")
            if isinstance(msg, str) and msg.strip():
                out["message"] = msg if len(msg) <= PREVIEW_CHARS else msg[:PREVIEW_CHARS] + "…"
            return out
        msg = obj.get("message")
        if isinstance(msg, str) and msg.strip():
            out["shape"] = "message"
            out["preview"] = msg if len(msg) <= PREVIEW_CHARS else msg[:PREVIEW_CHARS] + "…"
            return out
        out["shape"] = "effect" if obj.get("success") is True else "dict"
        # 작은 효과 봉투(path·size 따위)는 통째로 — 요약이 원형보다 클 이유가 없다
        if len(s) <= PREVIEW_ITEM_CHARS:
            out["preview"] = s
        return out
    if isinstance(obj, list):
        out["shape"] = "list"
        out["count"] = len(obj)
        if obj:
            out["preview"] = _compact(obj[0], PREVIEW_ITEM_CHARS)
        return out
    out["shape"] = "text"
    out["preview"] = s if len(s) <= PREVIEW_CHARS else s[:PREVIEW_CHARS] + "…"
    return out


def summarize_step(entry: Any) -> Any:
    """results[] 원소 하나 — `result` 를 요약으로 바꾼다(나머지 메타·error 는 그대로)."""
    if not isinstance(entry, dict) or "result" not in entry:
        return entry
    out = {k: v for k, v in entry.items() if k != "result"}
    out.update(summarize_result(entry.get("result")))
    return out


def diet_envelope(result: Any, verbose: bool = False) -> Any:
    """파이프 봉투의 results[] 를 요약으로. 봉투가 아니거나 verbose 면 원형."""
    if verbose or not isinstance(result, dict):
        return result
    results = result.get("results")
    if not isinstance(results, list) or not results:
        return result
    if result.get("_results_summarized"):
        return result
    out = dict(result)
    out["results"] = [summarize_step(e) for e in results]
    out["_results_summarized"] = True
    out["_hint"] = _HINT
    return out
