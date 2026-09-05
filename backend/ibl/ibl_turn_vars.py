"""턴 범위 변수 — `$이름 = …` 로 이름 붙인 결과는 같은 턴(task_id)의 다음 execute_ibl 호출에서 그대로 보인다.

언어 개정 2026-09-06(사용자 판정 — docs/OUTPUT_RETYPING_HANDOFF.md §2a). 변수의 수명이 "프로그램 한 번"에서
"턴"으로 넓어진다. 노트북 REPL 과 같은 모형.

왜: 벽시계 ≈ 출력 토큰 ÷ v(모델 상수). 변수가 프로그램 한 번 안에서만 살면 모델은 앞 호출의 결과(지역 JSON
7K자·매물 행·필드 목록)를 다음 호출에 손으로 다시 친다(ep2890 부동산 22.8K자·ep2884 수리 112K자). 이름을
번호 핸들(`$rN`)로 주지 않는 이유: 번호는 봉투 일련번호라 뜻이 없고 해마 코퍼스에 남으면 그 프로그램이 다른
주행에서 재사용 불가가 된다. resume 파라미터로 명시하게 하지 않는 이유: 참조가 언어 밖(도구 인자)에 살고
경로 베끼기가 남고 한 호출에 하나뿐이라 `$a & $b >> [table:join]` 이 안 된다.

기판: resume_vars(부분 실패 봉투, 2026-09-06 같은 날)와 같은 스필 + 파서 `preset_vars` + 실행기 `_preset_results`.
명시판(resume:{vars_ref})은 턴을 넘는 24h 회수 자리에 그대로 남는다.

규약:
- 키 = (agent_id, task_id). task_id 없는 호출(직접 표면)은 턴 범위 **없음** — 다른 턴으로 새지 않게 침묵 폴백 금지.
- 프로그램 안 재할당이 턴 변수를 덮는다(파서가 뒤 할당으로 슬롯을 갈아 끼움 — 앞 참조는 옛 값, 뒤는 새 값).
- 명시 resume:{vars_ref} 가 같은 이름을 실으면 명시가 이긴다.
- 봉투는 `turn_vars{injected, live, too_large}` 로 정직하게 말한다. 저장소 파일은 data/spill/ 에 살아 24h GC 를 같이 탄다.
- 예약 이름(`$items $it $i $error $return $file`)은 주입하지 않는다.
"""
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

MAX_VALUE_CHARS = 4_000_000    # 이보다 큰 값은 싣지 않는다(그런 통화는 대개 이미 스필 참조) — 봉투 too_large 로 신고
MAX_STORE_CHARS = 32_000_000   # 턴 저장소 총량 — 넘치면 오래된 이름부터 덜어낸다

RESERVED = frozenset({"items", "it", "i", "error", "return", "file"})
_REF_RE = re.compile(r"\$\{?([^\W\d]\w*)")


def turn_key(agent_id: Optional[str]) -> Optional[str]:
    """(agent_id, task_id) → 저장소 키. task_id 가 없으면 None(턴 범위 없음)."""
    try:
        from thread_context import get_current_task_id
        task = get_current_task_id() or ""
    except Exception:
        task = ""
    if not task:
        return None
    return hashlib.sha256(f"{agent_id or ''}|{task}".encode("utf-8", "replace")).hexdigest()[:20]


def store_path(key: str) -> str:
    from common.spill import spill_dir
    return os.path.join(spill_dir(), f"turn_vars_{key}.json")


def load(key: Optional[str]) -> Dict[str, str]:
    if not key:
        return {}
    p = store_path(key)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save(key: Optional[str], live: Dict[str, object]) -> Tuple[List[str], List[str]]:
    """산 변수를 턴 저장소에 합친다 → (실린 이름, 크기로 뺀 이름). 재할당은 맨 뒤로(최근 순서 보존)."""
    if not key or not live:
        return [], []
    store = load(key)
    kept: List[str] = []
    skipped: List[str] = []
    for n, v in live.items():
        n = str(n)
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        if len(s) > MAX_VALUE_CHARS:
            skipped.append(n)
            continue
        store.pop(n, None)
        store[n] = s
        kept.append(n)
    while sum(len(v) for v in store.values()) > MAX_STORE_CHARS:
        old = next((n for n in store if n not in kept), None)
        if old is None:
            break
        store.pop(old)
    p = store_path(key)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)
    os.replace(tmp, p)
    return sorted(kept), sorted(skipped)


def referenced(code: str) -> List[str]:
    """code 가 참조하는 `$이름` 들(예약 이름 제외)."""
    return sorted(set(_REF_RE.findall(code or "")) - RESERVED)


def preset_for(code: str, key: Optional[str], exclude=()) -> Dict[str, str]:
    """이 code 가 참조하는 이름 중 턴 저장소에 있는 것 → {이름: 값 원형}. exclude(명시 resume 이름)는 명시가 이긴다."""
    if not key:
        return {}
    store = load(key)
    if not store:
        return {}
    ex = set(exclude or ())
    return {n: store[n] for n in referenced(code) if n in store and n not in ex}


def clear(key: Optional[str]) -> None:
    if not key:
        return
    try:
        os.remove(store_path(key))
    except OSError:
        pass
