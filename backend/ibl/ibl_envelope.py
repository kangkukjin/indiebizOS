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


def _clamp_names(names, out: Dict[str, Any], field: str) -> list:
    """이름 목록을 KEYS_MAX 로 자르되 **잘랐다고 신고한다**(침묵 클램프 금지).

    `keys`·`columns` 는 모델이 다음 step 의 필드 이름을 고를 때 보는 눈이다. 조용히
    잘리면 "그 열이 없다"로 오판한다 — 정렬이 ASCII→한글 순이라 **한글 열과 방금
    compute 로 만든 파생 열이 가장 먼저 사라지므로** 하필 제일 중요한 열이 없는 것처럼
    보인다(F18-1 실측: 14키 중 `층`·`평당가만원` 소실, 행 1건이어도 재현).
    어느 열이 '방금 만든 것'인지는 봉투가 알 수 없으므로 고르지 않고 **절단을 밝힌다**.
    """
    names = list(names)
    if len(names) > KEYS_MAX:
        out[f"{field}_truncated"] = len(names) - KEYS_MAX
        out[f"{field}_total"] = len(names)
        return names[:KEYS_MAX]
    return names


def _compact(obj: Any, cap: int) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s if len(s) <= cap else s[:cap] + f"…(+{len(s) - cap}자)"


def _derived_items(obj: Dict[str, Any]):
    """이 봉투가 통화를 나르는가 — **파이프 이음매와 같은 판정기**에게 묻는다 (B27-1, 27회차).

    두 결정이 각각 옳았는데 교차에서 거짓이 났다:
      · 2026-08-05 D13 — `results[]` 는 **원형** 유지(토큰 중복 0), 통화 파생은 파이프
        이음매(`_to_prev_currency` → `derive_items`)에서만. 그때는 모델이 원형 JSON 을
        직접 봤으므로 `columns/rows` 를 보고 표인 줄 알았다.
      · 2026-08-22 M1 — 이 파일이 `results[]` 를 shape/keys 한 단어 *판정*으로 접었다.
    접고 나서는 모델이 원형 대신 **판정**을 읽는데, 그 판정을 내리는 자(`obj.get("items")`)가
    이음매의 판정기와 달랐다. 실측(2026-08-23, 27회차 실측 119 step 중 11):
        [self:body]{…} >> [table:select]{columns: ["파일","영역"]}
        step2 → shape: "effect" · keys 에 items 없음   ← 같은 step 의 final_result 엔 items 2행
    `groupby`·`select`·`union`(= table 형으로 방출하는 변환자 전부)이 매번 이 거짓을 맞는다.
    비용은 틀린 데이터가 아니라 **틀린 진단**이다 — "effect"(통화 종착)를 읽은 모델은 그 자리에서
    통화가 죽은 줄 알고 `>> [table:*]` 를 잇지 않는다. 이 저장소가 반복해 봉해 온 부류다.

    ★파생본은 **판정에만** 쓰고 봉투에 싣지 않는다 — shape/count/columns 만 갱신한다.
    derive_items 를 `_route_handler` 에 두지 않은 이유(파생본이 모델 결과에 실려 토큰 중복)는
    그대로 지켜진다. 요약은 요약 크기 그대로다.
    반환: items 리스트 또는 None(통화 아님 — 효과·스칼라는 그대로 effect/dict).
    """
    try:
        from common.currency import derive_items
        d = derive_items(dict(obj))
    except Exception:
        return None                      # 판정기가 없으면 옛 판정 유지(새 실패 경로 0)
    it = d.get("items") if isinstance(d, dict) else None
    return it if isinstance(it, list) else None


def _parse_obj(raw: Any) -> Any:
    """JSON 문자열이면 파싱, 아니면 그대로."""
    if isinstance(raw, str):
        t = raw.strip()
        if t[:1] in "{[":
            try:
                return json.loads(t)
            except Exception:
                return raw
    return raw


def classify_currency(raw: Any):
    """(shape, obj, items|None, derived) — 통화 모양 판정의 **단일 지점** (B27-1: 판정기는 하나).

    소비자 둘: summarize_result(봉투 다이어트, M1)와 action_health 런타임 실측
    (2026-08-24 — 면제 액션의 측정 사각을 실사용 기록으로 닫는다). 판정기가 갈라지면
    요약과 건강 기록이 서로를 반박한다 — B27-1 이 봉했던 바로 그 부류.
    shape ∈ {error, items, message, effect, dict, list, text}. derived 는 items 가
    봉투 직방출이 아니라 이음매 판정기(derive_items — 표 형 등)에서 파생됐다는 표지.
    """
    obj = _parse_obj(raw)
    if isinstance(obj, dict):
        if obj.get("success") is False or ("error" in obj and not obj.get("success")):
            return "error", obj, None, False
        items = obj.get("items")
        derived = False
        if not isinstance(items, list):
            # 통화 판정기는 하나여야 한다 (B27-1) — 이음매가 items 를 파생해 줄 봉투를
            # 여기가 "effect" 라 부르면, 이 판정이 이음매를 반박하는 셈이 된다.
            items = _derived_items(obj)
            derived = items is not None
        if isinstance(items, list):
            return "items", obj, items, derived
        msg = obj.get("message")
        if isinstance(msg, str) and msg.strip():
            return "message", obj, None, False
        return ("effect" if obj.get("success") is True else "dict"), obj, None, False
    if isinstance(obj, list):
        return "list", obj, None, False
    return "text", obj, None, False


def shape_of(raw: Any) -> str:
    """결과 하나의 통화 모양 한 단어 — 런타임 건강 기록용 경량 진입점."""
    return classify_currency(raw)[0]


def summarize_result(raw: Any) -> Dict[str, Any]:
    """step 결과 하나(대개 JSON 문자열)의 요약 — shape/count/bytes/preview/keys."""
    s = raw if isinstance(raw, str) else _compact(raw, 10 ** 9)
    out: Dict[str, Any] = {"bytes": len(s)}
    shape, obj, items, _derived = classify_currency(raw)
    if isinstance(obj, dict):
        keys = sorted(k for k in obj.keys() if isinstance(k, str) and not k.startswith("_"))
        out["keys"] = _clamp_names(keys, out, "keys")
        # 부분 실패(each 의 errors[])는 진단 정보다 — 다이어트 대상이 아니다.
        # 옛 요약은 이 배열을 통째로 접으면서 message 의 "errors 참조"만 남겨, 다문장
        # 프로그램에서 어느 행이 왜 실패했는지 회수 불능이었다(2026-08-28 팁 보고서
        # 완성 프로그램 실측 — 자막 실패 영상의 정체가 봉투에서 사라졌다).
        errs = obj.get("errors")
        if isinstance(errs, list) and errs:
            out["error_count"] = obj.get("error_count") or len(errs)
            out["errors_digest"] = [_compact(e, 300) for e in errs[:3]]
            if len(errs) > 3:
                out["errors_digest_truncated"] = len(errs) - 3
    if shape == "error":
        out["shape"] = "error"
        out["error"] = obj.get("error") or obj.get("message")   # 원형 — 진단은 다이어트 밖
        return out
    if shape == "items":
        out["shape"] = "items"
        out["count"] = len(items)
        # 스필 참조 봉투 — items:[] 는 0건이 아니라 **외부화**다(2026-08-29 실측:
        # 자막 283행이 스필됐는데 요약이 count:0 이라 "0건 실패"로 오독됐다 — 다음
        # step 은 참조를 투명 해소해 283행을 정상 수신). ref 의 실측 계수·경로를 싣는다.
        if isinstance(obj, dict) and (obj.get("_spilled") or obj.get("spilled")):
            _ref = obj.get("ref")
            if isinstance(_ref, dict) and not items:
                if isinstance(_ref.get("count"), int):
                    out["count"] = _ref["count"]
                out["spilled"] = True
                if isinstance(_ref.get("path"), str):
                    out["spill_path"] = _ref["path"]
        if _derived:
            # keys 엔 items 가 없는데 shape 은 items — 왜인지 밝힌다(표 형 방출).
            out["items_derived"] = True
        if items:
            first = items[0]
            if isinstance(first, dict):
                out["columns"] = _clamp_names(
                    sorted(str(k) for k in first.keys()), out, "columns")
            out["preview"] = _compact(first, PREVIEW_ITEM_CHARS)
        msg = obj.get("message")
        if isinstance(msg, str) and msg.strip():
            out["message"] = msg if len(msg) <= PREVIEW_CHARS else msg[:PREVIEW_CHARS] + "…"
        return out
    if shape == "message":
        out["shape"] = "message"
        msg = obj.get("message")
        out["preview"] = msg if len(msg) <= PREVIEW_CHARS else msg[:PREVIEW_CHARS] + "…"
        return out
    if shape in ("effect", "dict"):
        out["shape"] = shape
        # 작은 효과 봉투(path·size 따위)는 통째로 — 요약이 원형보다 클 이유가 없다
        if len(s) <= PREVIEW_ITEM_CHARS:
            out["preview"] = s
        return out
    if shape == "list":
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
    """파이프 봉투의 results[] 를 요약으로. 봉투가 아니거나 verbose 면 원형.

    ★거대 필드는 꼬리로 (2026-08-28): 에피소드 로그는 봉투 직렬화의 꼬리를 절단한다.
    종전엔 results·final_result 가 가운데 있고 정직 표지(warning·traceback·statements_failed·
    criteria_steps·_fallback_used…)가 dict 에 나중에 붙어 **표지 전부가 절단 구간에**
    떨어졌다 — 08-28 실측: 트레이스백 프레임·품질 판정이 로그에서 확인 불능이었다.
    JSON 키 순서는 소비자 계약이 아니므로(파서는 이름으로 읽는다) 여기 한 이음매의
    재배열로 모든 생산자(성공·실패·중단 봉투)의 표지가 절단 생존이 된다."""
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
    for k in ("results", "final_result"):
        if k in out:
            out[k] = out.pop(k)          # 재삽입 = 직렬화 순서상 맨 뒤로
    return out
