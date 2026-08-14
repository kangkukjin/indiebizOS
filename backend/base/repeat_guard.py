"""repeat_guard.py — 반복 호출 가드 공용 코어 (2026-08-14, 두-경로 대칭 감사 2탄)

동일 (신원, 시그니처) 연속 호출을 세어 임계치(3/5/8)에서 점증 조언 문자열을 돌려준다.
차단·변조 없음(조언뿐) · 오류 결과도 카운트(거부를 두들기는 게 바로 끊을 루프) ·
다른 호출이 오면 리셋. dsh repeat-tool-reminder 의미론의 IBL판.

어댑터 둘이 이 코어를 공유한다 (정책 표류 방지 — 렌더러 "공용 코어+두 어댑터" 선례):
  ①직결 경로: system_tools.execute_tool 래퍼 (인프로세스 프로바이더 전부)
  ②클로드 코드 경로: mcp_server.execute_ibl (MCP 에이전트 경계)
두 경로는 서로 다른 목을 지나므로 이중 카운트 없음(/ibl/execute 는 execute_tool 미경유).

턴 경계 리셋은 하지 않는다 — 연속-동일 호출은 턴을 건너도 루프 신호이고, 다른 호출이
오면 어차피 리셋되며, 조언-전용이라 오탐 비용이 낮다(사용자가 턴마다 같은 호출을
정확히 3회 요구하는 드문 경우만 조언 한 줄).
"""
import threading

THRESHOLDS = (3, 5, 8)
_chains: dict = {}   # key -> [signature, count]
_CHAIN_CAP = 256
_lock = threading.Lock()


def advise(key: str, signature: str) -> str:
    """호출 1건을 체인에 반영하고, 임계치면 조언 문자열을(아니면 "") 돌려준다."""
    with _lock:
        chain = _chains.get(key)
        if chain and chain[0] == signature:
            chain[1] += 1
        else:
            if key not in _chains and len(_chains) >= _CHAIN_CAP:
                _chains.pop(next(iter(_chains)))
            _chains[key] = chain = [signature, 1]
        n = chain[1]
    if n == THRESHOLDS[0]:
        return ("\n\n[반복 감지] 같은 도구 호출을 같은 인자로 연속 3회 실행했습니다. "
                "직전 결과를 다시 읽고, 접근이나 파라미터를 바꾸거나 결론을 내리세요.")
    if n in THRESHOLDS[1:]:
        return (f"\n\n[반복 감지] 같은 호출 연속 {n}회째입니다: "
                f"{signature[:200]}{'…' if len(signature) > 200 else ''}\n"
                "같은 호출의 반복은 같은 결과를 냅니다. 다른 액션·다른 인자를 쓰거나, "
                "지금까지의 결과로 결론을 내리세요.")
    return ""


def reset_all():
    """테스트 전용 — 체인 전체 초기화."""
    with _lock:
        _chains.clear()
