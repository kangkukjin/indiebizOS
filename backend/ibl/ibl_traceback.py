# -*- coding: utf-8 -*-
"""ibl_traceback.py — IBL 실행 트레이스백 단일 소스 (2026-08-27, docs/IBL_TRACEBACK_HANDOFF.md)

파이썬 트레이스백에 해당하는 것을 IBL 문장에 준다: 실패가 어느 실행기 경계를 거쳐
왔는지(frames), 원형 오류(error), 실패 종류(error_type), 실패 프레임에 들어간 통화
요약(input), 파이썬 예외라면 그 꼬리(py_tail).

규약 — **경계 규약, 등록 목록 없음** (B48-1: 손으로 적은 목록은 반드시 샌다):
  실패 봉투가 실행기 경계(파이프→each→블록→병렬→폴백→워크플로우)를 넘을 때,
  넘는 쪽 실행기가 자기 프레임 한 칸을 **앞에** 붙인다(push_frame). 새 합성 구조는
  목록에 등록하는 게 아니라 같은 입구를 부르는 것으로 규약을 얻는다.
  부분 실패 봉투(each errors[]·branches_failed)도 같은 규약이다 — 행/가지 하나의
  실패에도 그 안의 경로가 붙는다(2026-08-27 판정: 경계 규약에 예외 없음. each 만
  빼자던 초안은 그 자체가 손 고른 면제라 기각).

모양:
  traceback = {
    frames: [{kind, …위치 필드}…],   # 바깥→안쪽. kind ∈ pipeline|parallel|fallback|each|block|workflow
    error: str,                      # 원형 오류문 — 다이어트 대상 아님(ibl_envelope 원칙)
    error_type: str,                 # tool_error|exception|syntax|binding|quality†  †품질 계약 예약(후속)
    input: {…}?,                     # 실패 프레임에 들어간 통화 요약 — summarize_result 재사용(B27-1: 판정기는 하나)
    py_tail: [str]?,                 # 예외일 때만 — 파이썬 트레이스백 꼬리
  }
안쪽(nested) 트레이스백이 있으면 그것이 진실이다 — error/error_type/input/py_tail 을
바깥이 덮지 않고 frames 만 앞에 쌓인다(파이썬 예외 전파와 같은 방향).

잎 모듈(ibl_honesty 와 같은 위상) — top-level import 없음, 순환 없음.
"""
import json
from typing import Any, Dict, Optional

ERROR_TYPES = ("tool_error", "exception", "syntax", "binding", "quality")

_ERR_MAX = 2000       # error 원형 상한 — 진단은 안 깎지만 무한정도 아니다(스필 통화 오폭 방지)
PY_TAIL_FRAMES = 4    # 파이썬 꼬리 프레임 수


def _err_str(error: Any) -> str:
    if isinstance(error, str):
        s = error
    else:
        try:
            s = json.dumps(error, ensure_ascii=False, default=str)
        except Exception:
            s = str(error)
    return s if len(s) <= _ERR_MAX else s[:_ERR_MAX] + f"…(+{len(s) - _ERR_MAX}자)"


def build_tb(error: Any, error_type: str = "tool_error",
             frame: Optional[dict] = None, nested: Optional[dict] = None,
             py_tail: Optional[list] = None) -> Dict[str, Any]:
    """트레이스백 생성/승계. nested(안쪽 봉투의 traceback)가 있으면 그 내용이 진실 —
    error 등은 안쪽 것을 유지하고 frames 만 이어받는다. frame 은 맨 앞(바깥)에 붙인다."""
    if isinstance(nested, dict) and isinstance(nested.get("frames"), list):
        tb = dict(nested)
        tb["frames"] = list(nested["frames"])
    else:
        tb = {"frames": [], "error": _err_str(error), "error_type": error_type}
        if py_tail:
            tb["py_tail"] = list(py_tail)
    if frame:
        tb["frames"].insert(0, dict(frame))
    return tb


def push_frame(tb: Any, frame: dict) -> Any:
    """경계 한 칸 통과 — 프레임을 맨 앞에. 트레이스백 모양이 아니면 그대로(방어)."""
    if isinstance(tb, dict) and isinstance(tb.get("frames"), list):
        tb["frames"].insert(0, dict(frame))
    return tb


def tb_of(result: Any) -> Optional[Dict[str, Any]]:
    """step 결과(dict 또는 JSON 문자열)에서 안쪽 traceback 을 **사본으로** 추출.

    사본인 이유: dict 결과의 traceback 을 참조로 꺼내 push_frame 하면 원 봉투
    (results[]·final_result)의 트레이스백까지 바뀐다 — 진단 기록이 스스로 오염된다.
    """
    obj = result
    if isinstance(result, str):
        s = result.lstrip()
        if not s.startswith("{"):
            return None
        try:
            obj = json.loads(s)
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    tb = obj.get("traceback")
    if not (isinstance(tb, dict) and isinstance(tb.get("frames"), list)):
        return None
    try:
        return json.loads(json.dumps(tb, ensure_ascii=False, default=str))
    except Exception:
        return None


def py_tail_of(exc: BaseException, limit: int = PY_TAIL_FRAMES) -> list:
    """예외의 파이썬 트레이스백 꼬리 — `패키지/파일.py:줄 in 함수` + 마지막 오류문.

    basename 하나는 모호해서(handler.py 가 패키지마다 있다) 마지막 두 경로 조각을 쓴다.
    """
    tail = []
    try:
        import traceback as _t
        from pathlib import PurePath
        for f in _t.extract_tb(exc.__traceback__)[-limit:]:
            p = PurePath(f.filename)
            loc = "/".join(p.parts[-2:]) if len(p.parts) >= 2 else p.name
            tail.append(f"{loc}:{f.lineno} in {f.name}")
    except Exception:
        pass
    tail.append(f"{type(exc).__name__}: {exc}")
    return tail


def attach_input(tb: Any, prev_result: Any) -> Any:
    """실패 프레임에 들어간 통화 요약(shape/count/columns/preview)을 단다.

    안쪽이 이미 달았으면 유지(안쪽이 진실 — 실패 지점에 더 가까운 입력이다).
    요약기는 ibl_envelope.summarize_result 재사용 — 판정기는 하나(B27-1).
    """
    if not (isinstance(tb, dict) and isinstance(tb.get("frames"), list)):
        return tb
    if "input" in tb:
        return tb
    if prev_result is None or (isinstance(prev_result, str) and not prev_result.strip()):
        return tb
    try:
        from ibl_envelope import summarize_result
        tb["input"] = summarize_result(prev_result)
    except Exception:
        pass
    return tb


def fold_heavy(tb: Any, seen: Dict[str, Any], at: Any) -> bool:
    """반복 실패의 무거운 상세(py_tail·input)를 동일 오류별 첫 발생에만 남긴다.

    each 40행이 같은 이유로 죽으면 40개의 동일 py_tail 이 실린다 — frames 는 행당
    수십 바이트라 전부 남기고, 무거운 부분만 접는다. 접었으면 detail_at 으로
    어디에 원형이 있는지 밝힌다(침묵 클램프 금지). 반환: 접었는가.
    """
    if not (isinstance(tb, dict) and isinstance(tb.get("frames"), list)):
        return False
    key = tb.get("error") or ""
    if key in seen:
        tb.pop("py_tail", None)
        tb.pop("input", None)
        tb["detail_at"] = seen[key]
        return True
    seen[key] = at
    return False
