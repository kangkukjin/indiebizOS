"""되받아쓰기 관문 — 모델이 친 내용이 *이미 있는* 내용인가를 초크포인트(execute_ibl) 한 곳에서 잰다.

일반 관문(2026-09-06, 사용자 판정 "경우마다 막을 수 없다 — 일반적으로 막아라", docs/OUTPUT_RETYPING_HANDOFF.md §6).
보고서 본문·코드 편집·원장 항목·메시지 어디서든 같은 잣대: 모델이 친 긴 문자열 인자를

  ① 이 턴의 변수 값(`$이름 = …`, ibl_turn_vars)          → "$이름 으로 가리켜라"
  ② 직전 결과 그림자(이름 없는 최근 봉투 final_result)  → "이름을 붙여 $이름 으로 가리켜라"
  ③ 대상 파일 현재 내용(그 step 의 경로 param 이 가리키는 파일) → "줄범위 edit·차분으로"

와 대조한다. 잣대는 두 가지: 그대로 겹치는 조각 글자 수(verbatim_chars — 줄·문장 단위 부분열)와
데이터 토큰(숫자·URL) 중 이미 있는 것의 비율(data_tokens). 어휘 이름은 보지 않는다 — 문자열 일치만.

결정: warn(봉투 `retyped` + 처방, 실행은 함) / refuse(대상 파일과 통째 재작성급 겹침 — 차분·줄범위 edit 이 기계적
대안이라 실행 전에 거절). 임계는 data/lifecycle_policy.yaml `retyping:` 데이터(코드에 상수 이름만).
왜 관문인가: 쓰는 쪽(모델)이 쓸지 정하면 지침은 장식이다 — 셀 수 있으면 봉투가 말하고 관문이 막는다.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_POLICY = {
    "min_param_chars": 200,
    "min_segment_chars": 40,
    "warn_verbatim_chars": 2000,
    "refuse_file_verbatim_chars": 8000,
    "warn_data_ratio": 0.5,
    "warn_data_min_tokens": 20,
    "shadow_results": 8,
    "shadow_max_chars": 1_000_000,
}
_SOURCE_CAP = 1_500_000        # 출처 한 덩이 상한(부분열 검색 비용)
_SOURCES_TOTAL_CAP = 6_000_000
_NUM_RE = re.compile(r"\d[\d,\.]{2,}")
_URL_RE = re.compile(r"https?://[^\s\"'<>\)\]]+")
_SPLIT_RE = re.compile(r"[\n\r]+|(?<=[\.。!?])\s+")

HINT = ("있는 것은 치지 말고 가리켜라 — 앞 결과·데이터 행은 `$이름`(턴 변수)으로 넘기고(문서면 "
        "`[table:document]{blocks: [{type: table|cards, items: $x}]}` 처럼 블록에 items 를 실어 기계가 렌더), "
        "파일은 줄범위 edit·`old_string/new_string` 차분으로 — 통째 재작성·본문 옮겨 적기 금지.")

_policy_cache: Dict[str, Any] = {}


def load_policy() -> Dict[str, Any]:
    if _policy_cache:
        return _policy_cache
    pol = dict(DEFAULT_POLICY)
    try:
        import yaml
        from boot_paths import get_base_path  # type: ignore
        p = os.path.join(str(get_base_path()), "data", "lifecycle_policy.yaml")
        with open(p, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        block = doc.get("retyping") or {}
        for k in DEFAULT_POLICY:
            if k in block:
                pol[k] = type(DEFAULT_POLICY[k])(block[k])
    except Exception:
        pass
    _policy_cache.update(pol)
    return _policy_cache


def data_tokens(text: str) -> set:
    toks = {m.replace(",", "") for m in _NUM_RE.findall(text or "")}
    toks |= set(_URL_RE.findall(text or ""))
    return toks


def segments(text: str, min_len: int) -> List[str]:
    out = []
    for s in _SPLIT_RE.split(text or ""):
        s = s.strip()
        if len(s) >= min_len:
            out.append(s)
    return out


def typed_strings(steps: list, min_chars: int) -> List[Tuple[str, List[str]]]:
    """(긴 문자열 인자, 그 step 의 파일 경로 후보들) 목록 — 내부 키(`_…`)는 보지 않는다."""
    found: List[Tuple[str, List[str]]] = []

    def _paths_in(obj, acc: List[str]):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).startswith("_"):
                    continue
                if isinstance(v, str) and 0 < len(v) < 1024 and ("/" in v or "\\" in v) and "\n" not in v:
                    _p = os.path.expanduser(v)
                    if os.path.isfile(_p):
                        acc.append(_p)
                else:
                    _paths_in(v, acc)
        elif isinstance(obj, list):
            for it in obj:
                _paths_in(it, acc)

    def _walk(obj, acc: List[str]):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).startswith("_"):
                    continue
                _walk(v, acc)
        elif isinstance(obj, list):
            for it in obj:
                _walk(it, acc)
        elif isinstance(obj, str) and len(obj) >= min_chars:
            acc.append(obj)

    for st in steps or []:
        if not isinstance(st, dict):
            continue
        params = st.get("params") if isinstance(st.get("params"), dict) else st
        strings: List[str] = []
        _walk(params, strings)
        if not strings:
            continue
        paths: List[str] = []
        _paths_in(params, paths)
        for s in strings:
            found.append((s, paths))
    return found


def _cap_join(values: List[str]) -> str:
    out: List[str] = []
    total = 0
    for v in reversed(values):          # 최근 것부터
        v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        v = v[:_SOURCE_CAP]
        if total + len(v) > _SOURCES_TOTAL_CAP:
            break
        out.append(v)
        total += len(v)
    return "\n".join(out)


def measure(text: str, sources: Dict[str, str], min_seg: int) -> Dict[str, Any]:
    """text 의 조각·데이터 토큰이 출처들에 얼마나 그대로 있는가. 조각은 첫 번째로 맞은 출처에 귀속."""
    verbatim: Dict[str, int] = {}
    hit_total = 0
    for seg in segments(text, min_seg):
        for label, src in sources.items():
            if src and seg in src:
                verbatim[label] = verbatim.get(label, 0) + len(seg)
                hit_total += len(seg)
                break
    toks = data_tokens(text)
    pool = set()
    for src in sources.values():
        if src:
            pool |= data_tokens(src)
    in_pool = [t for t in toks if t in pool]
    return {"chars": len(text), "verbatim": verbatim, "verbatim_chars": hit_total,
            "data_in": len(in_pool), "data_total": len(toks)}


def check_retyping(steps: list, turn_values: Optional[Dict[str, str]], shadows: Optional[List[str]],
                   policy: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """None(문제 없음) 또는 {level: warn|refuse, verbatim_chars, by_source, data_tokens, sources, message, hint}."""
    pol = policy or load_policy()
    typed = typed_strings(steps, int(pol["min_param_chars"]))
    if not typed:
        return None
    var_src = {f"${n}": (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))[:_SOURCE_CAP]
               for n, v in (turn_values or {}).items()}
    shadow_src = _cap_join(list(shadows or []))
    total_verbatim = 0
    file_verbatim = 0
    by_source: Dict[str, int] = {}
    data_in = data_total = 0
    file_cache: Dict[str, str] = {}
    for text, paths in typed:
        sources: Dict[str, str] = dict(var_src)
        if shadow_src:
            sources["직전 결과"] = shadow_src
        for p in paths:
            if p not in file_cache:
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        file_cache[p] = f.read(_SOURCE_CAP)
                except OSError:
                    file_cache[p] = ""
            if file_cache[p]:
                sources[f"파일:{os.path.basename(p)}"] = file_cache[p]
        m = measure(text, sources, int(pol["min_segment_chars"]))
        total_verbatim += m["verbatim_chars"]
        for label, n in m["verbatim"].items():
            by_source[label] = by_source.get(label, 0) + n
            if label.startswith("파일:"):
                file_verbatim += n
        data_in += m["data_in"]
        data_total += m["data_total"]
    ratio = (data_in / data_total) if data_total else 0.0
    level = None
    if file_verbatim >= int(pol["refuse_file_verbatim_chars"]):
        level = "refuse"
    elif total_verbatim >= int(pol["warn_verbatim_chars"]) or (
            data_total >= int(pol["warn_data_min_tokens"]) and ratio >= float(pol["warn_data_ratio"])):
        level = "warn"
    if level is None:
        return None
    srcs = sorted(by_source, key=lambda k: -by_source[k])
    if data_in and not srcs:
        srcs = [k for k in list(var_src) + (["직전 결과"] if shadow_src else []) if k]
    msg = (f"이미 있는 내용을 다시 쳤습니다 — 그대로 겹침 {total_verbatim}자"
           + (f"(파일과 {file_verbatim}자)" if file_verbatim else "")
           + (f", 숫자·URL {data_in}/{data_total}개가 이미 결과에 있음" if data_total else "")
           + (f" · 출처: {', '.join(srcs[:4])}" if srcs else ""))
    return {"level": level, "verbatim_chars": total_verbatim, "file_verbatim_chars": file_verbatim,
            "by_source": by_source, "data_tokens": f"{data_in}/{data_total}", "sources": srcs[:6],
            "message": msg, "hint": HINT}
