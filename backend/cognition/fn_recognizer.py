"""이름 있는 프로그램 인식 — 실행 관문에서 들어온 다문장 code 가 이미 이름(alias)이 있는 관용구·함수와
같은 **모양**이면 봉투가 "이 프로그램은 [fn:이름] 이다" 라고 말한다(docs/OUTPUT_RETYPING_HANDOFF.md §2c, 2026-09-06).

왜: 09-05 처방(이름 먼저 회상·자동 작명·호출 보상)은 가르침이었고 05시 주행 `[fn:]` 호출은 0 이었다 — 모델이
회상 본문을 그대로 다시 치면(15.6K자) 그 자리에서 기계가 이름을 짚어 준다(관문 한 겹). 이름이 없으면 원문 코퍼스
(`ibl_code_corpus`, 해시 키)의 누계로 "같은 프로그램을 N번째 치고 있다 — 증류가 작명한다" 고 말한다.

모양(shape) = 문자열 리터럴·숫자·변수 이름을 자리표로 접은 code. 슬롯 값만 다른 두 프로그램은 같은 모양이다.
어휘 이름을 코드에 넣지 않는다 — 모양 비교는 문자열 정규화만.
"""
import hashlib
import re
import sqlite3
import time
from typing import Dict, Optional

_STR_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_NUM_RE = re.compile(r'(?<![\w$])-?\d+(?:\.\d+)?')
_VAR_RE = re.compile(r'\$\{?[^\W\d]\w*\}?')
_WS_RE = re.compile(r'\s+')
_CACHE: Dict[str, object] = {"t": 0.0, "shapes": {}}
_CACHE_TTL_S = 60


def statements(code: str) -> list:
    return [l for l in (code or "").split("\n") if l.strip() and not l.strip().startswith("#")]


def shape(code: str) -> str:
    """슬롯 값을 접은 모양 — 리터럴 → \"\", 숫자 → 0, $변수 → $_, 공백 정규화."""
    s = _STR_RE.sub('""', code or "")
    s = _NUM_RE.sub("0", s)
    s = _VAR_RE.sub("$_", s)
    return _WS_RE.sub(" ", s).strip()


def _aliased_shapes() -> Dict[str, str]:
    """이름 있는 다문장 용례의 {모양: alias} — 60초 캐시(이름 있는 용례는 수십 개 규모)."""
    if _CACHE["shapes"] and time.time() - float(_CACHE["t"]) < _CACHE_TTL_S:
        return _CACHE["shapes"]  # type: ignore[return-value]
    m: Dict[str, str] = {}
    programs = []
    try:
        from ibl_usage_db import IBLUsageDB
        for alias, code in IBLUsageDB().aliased_examples():
            if code and len(statements(code)) >= 2:
                m.setdefault(shape(code), alias)
                programs.append((alias, code))
    except Exception:
        pass
    _CACHE.update(t=time.time(), shapes=m, programs=programs)
    return m


def _aliased_programs() -> list:
    """이름 있는 다문장 용례의 [(alias, code)] — _aliased_shapes 와 같은 캐시."""
    _aliased_shapes()
    return list(_CACHE.get("programs") or [])


def variant_of(code: str) -> Optional[Dict[str, object]]:
    """들어온 다문장 code 가 이름 있는 관용구의 **변형**인가 — 문장 서명(머리 열·인자 키 부분집합·op)의
    순서 보존 부분열로 절반 이상(최소 2문장)이 겹치면 {alias, hit, total, missed}.

    2026-09-07 ep2952 재진단: 실행자는 `[fn:유튜브팁보고서작성]` 을 expand 로 열어 본 뒤 본문을 손으로
    베껴 *변형*(검색어 2→5, limit 45→70, 원장 필터 탈락)을 쳤다 — 모양(shape) 정확 일치 층은 슬롯 값만
    다른 재타이핑만 잡으므로 이 부류가 통째로 샜다(09-06 이후 2,501 문장에 fn 0). 접지 관문과 같은 자
    (ibl_idiom._sentence_matches)로 문장 단위로 대조한다 — 어휘 이름을 코드에 넣지 않는다."""
    try:
        from ibl_idiom import _sig, _blank_slots, _sentence_matches, _statements_of
        csigs = [_sig(_blank_slots(st)) for st in _statements_of(code)]
    except Exception:
        return None
    if len(csigs) < 2:
        return None
    best = None
    for alias, pcode in _aliased_programs():
        try:
            psigs = [_sig(_blank_slots(st)) for st in _statements_of(pcode)]
        except Exception:
            continue
        if len(psigs) < 2:
            continue
        pos, hit, missed = 0, 0, []
        for idx, ps in enumerate(psigs, 1):
            j = next((k for k in range(pos, len(csigs)) if _sentence_matches(ps, csigs[k])), None)
            if j is None:
                missed.append(idx)
                continue
            hit += 1
            pos = j + 1
        need = max(2, (len(psigs) + 1) // 2)
        if hit >= need and (best is None or hit > best["hit"]):
            best = {"alias": alias, "hit": hit, "total": len(psigs), "missed": missed}
    return best


def corpus_stats(code: str) -> Optional[Dict[str, int]]:
    """원문 코퍼스(ibl_code_corpus)의 누계 — 없으면 None."""
    try:
        from boot_paths import get_base_path
        sha = hashlib.sha256((code or "").encode("utf-8", "replace")).hexdigest()
        con = sqlite3.connect(str(get_base_path() / "data" / "world_pulse.db"), timeout=2)
        try:
            row = con.execute("SELECT seen_count, success_count FROM ibl_code_corpus WHERE code_sha256=?",
                              (sha,)).fetchone()
        finally:
            con.close()
        return {"seen_count": int(row[0]), "success_count": int(row[1])} if row else None
    except Exception:
        return None


def fn_hint_for(code: str) -> Optional[Dict[str, object]]:
    """다문장 프로그램이 이름 있는 모양이면 {alias, note}, 이름은 없지만 코퍼스에 되풀이면 {seen, note}, 아니면 None."""
    if len(statements(code)) < 2 or "[fn:" in (code or "") or "[def:" in (code or ""):
        return None
    alias = _aliased_shapes().get(shape(code))
    if alias:
        return {"alias": alias,
                "note": (f"이 프로그램은 [fn:{alias}]{{슬롯…}} 과 같은 모양입니다 — 다음부터 이름으로 부르세요"
                         f"(본문 {len(code)}자 재타이핑). 슬롯 이름은 [self:memory]{{op: \"recall\", expand: \"{alias}\"}} 로.")}
    v = variant_of(code)
    if v:
        return {"alias": v["alias"], "variant": True, "hit": v["hit"], "total": v["total"],
                "note": (f"이 프로그램은 [fn:{v['alias']}] 의 변형입니다 — 문장 {v['hit']}/{v['total']} 이 같은 서명"
                         f"(달라진 정의 문장: {', '.join(map(str, v['missed'])) or '없음'}). 슬롯 값만 다르면 이름으로 부르고, "
                         f"문장이 달라야 하면 expand 로 정의를 열어 [def: {v['alias']}] 로 고친 뒤 부르세요 — "
                         f"본문을 새로 치면 이름·성공/실패 귀속이 끊기고 다음 호가 또 처음부터 조립합니다.")}
    st = corpus_stats(code)
    if st and st["seen_count"] >= 2 and st["success_count"] >= 1:
        return {"seen": st["seen_count"],
                "note": (f"같은 프로그램을 {st['seen_count'] + 1}번째 치고 있습니다(원문 코퍼스) — 성공하면 증류가 "
                         f"이름을 붙이고, 이름이 생기면 [fn:이름]{{슬롯}} 한 줄로 부릅니다.")}
    return None
