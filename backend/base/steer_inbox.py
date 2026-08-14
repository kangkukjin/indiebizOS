"""steer_inbox.py — 턴 중 조향(steer) 인박스 (2026-08-15)

돌고 있는 에이전트에게 **멈추지 않고** 지시를 밀어 넣는 통로. 중단(cancel)이 유일한
개입 수단이던 갭의 해소 — 관측 3겹(스텝 원장·역할 기록·반복 가드) 위의 첫 조종 조각.

원리(dsh steer/inject 의 이음매 번역): 조향 메시지를 키(agent_id)별 인박스에 넣어 두면,
그 에이전트의 **다음 도구 결과**에 부록으로 실려 모델에게 도달한다 — 루프를 뜯지 않고
반복 가드와 같은 전달 채널을 쓴다. 배달 어댑터 둘(두-경로 대칭):
  ①직결 경로: system_tools.execute_tool 래퍼 (인프로세스 프로바이더 전부)
  ②클로드 코드 경로: api_ibl /ibl/execute (MCP 호출 = req.agent_id 명시된 것만 —
    앱/수동 모드의 결정론 결과를 오염시키지 않는 게이트)

한계(정직): 도구를 더 부르지 않는 턴에는 배달할 수 없다 — 미배달분은 턴 종료 시
폐기되고 로그에 남는다(다음 턴으로 새는 stale 조향 방지). 조향은 지시의 *주입*이지
보장된 *수신*이 아니다.
"""
import threading
import time
from typing import List

_inbox: dict = {}   # key(agent_id) -> [(ts, text), ...]
_lock = threading.Lock()
_MAX_PER_KEY = 5        # 키당 대기 조향 상한 (초과 시 오래된 것부터 밀어냄)
_MAX_TEXT = 2000        # 조향 1건 길이 상한
_TTL_SECONDS = 1800     # 30분 지난 조향은 배달하지 않음 (유령 방지)


def post(key: str, text: str) -> int:
    """조향 1건 접수. 반환 = 그 키의 대기 건수."""
    text = (text or "").strip()[:_MAX_TEXT]
    if not key or not text:
        return 0
    with _lock:
        q = _inbox.setdefault(key, [])
        q.append((time.time(), text))
        del q[:-_MAX_PER_KEY]
        return len(q)


def drain(key: str) -> List[str]:
    """대기 조향 전부 회수(비움). TTL 지난 것은 버린다."""
    with _lock:
        q = _inbox.pop(key, [])
    now = time.time()
    return [t for ts, t in q if now - ts <= _TTL_SECONDS]


def clear(key: str) -> int:
    """턴 종료 시 미배달분 폐기. 반환 = 폐기 건수 (0이면 조용)."""
    with _lock:
        return len(_inbox.pop(key, []))


def render(texts: List[str]) -> str:
    """배달 부록 렌더 — 반복 가드 조언과 같은 결(부록, 결과 변조 아님).
    자기예약 콘텐츠와 같은 위생: 내용은 사용자 지시로 명시(untrusted 프레이밍의 역방향 —
    이건 진짜 사용자에게서 온 것임을 표시)."""
    if not texts:
        return ""
    body = "\n".join(f"- {t}" for t in texts)
    return ("\n\n[사용자 조향] 작업이 도는 동안 사용자가 지시를 보냈습니다. "
            "지금까지의 계획보다 이 지시를 우선해 즉시 반영하세요:\n" + body)
