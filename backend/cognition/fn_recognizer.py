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
    try:
        from ibl_usage_db import IBLUsageDB
        for alias, code in IBLUsageDB().aliased_examples():
            if code and len(statements(code)) >= 2:
                m.setdefault(shape(code), alias)
    except Exception:
        pass
    _CACHE.update(t=time.time(), shapes=m)
    return m


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
    st = corpus_stats(code)
    if st and st["seen_count"] >= 2 and st["success_count"] >= 1:
        return {"seen": st["seen_count"],
                "note": (f"같은 프로그램을 {st['seen_count'] + 1}번째 치고 있습니다(원문 코퍼스) — 성공하면 증류가 "
                         f"이름을 붙이고, 이름이 생기면 [fn:이름]{{슬롯}} 한 줄로 부릅니다.")}
    return None
