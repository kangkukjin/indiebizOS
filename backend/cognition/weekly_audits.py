"""weekly_audits.py — 주간 감사 넷의 공통 정형 (2026-09-07 신설)

## 왜 있나 — 호출부가 감사 수만큼 자라던 자리
data_ownership·doc_drift·store_waste·vocab_overlap 은 모두 같은 모양이다:
주간 카덴스로 한 번 돌고, 깃발을 자기 JSON 에 쓰고, self_checks 원장에 1건을 남기고,
실패해도 유지보수 전체를 멈추지 않는다. 그 정형이 `run_maintenance_bundle` 안에
네 벌 복제돼 있었고(감사 하나당 15줄), 파일은 1500줄 규칙의 코앞(1493줄)까지 왔다 —
`fixture_sweeps`(주간 스윕 다섯)와 `component_lifecycle` 이 이미 같은 이유로 자기
정형을 가져간 자리다. **다섯 번째 감사를 넣으려다 규칙에 걸려** 이 모듈이 생겼다.

## 규율
- 경고 문구는 여기서 만들지 않는다 — 각 감사가 `error_message` 에 자기 문장을 쓴다.
  (문구를 여기 두면 감사의 사실과 호출부의 사본이 어긋난다 — 파생본에 규칙을 전개하지 말 것.)
- 감사 하나의 실패는 그 감사에서 끝난다(개별 격리). 유지보수는 계속 간다.
- 카덴스 스킵(`{"skipped": "cadence"}`)은 원장에 남기지 않는다 — 안 돈 것은 사건이 아니다.
"""
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# (결과 키, 모듈, 함수) — 순서는 실행 순서. 새 주간 감사는 여기 한 줄로 합류한다.
AUDITS: List[Tuple[str, str, str]] = [
    ("data_ownership", "data_ownership", "run_data_ownership_check"),
    ("doc_drift", "doc_drift", "run_doc_drift_check"),
    ("store_waste", "store_waste_audit", "run_store_waste_check"),
    ("vocab_overlap", "vocab_overlap_audit", "run_vocab_overlap_check"),
]


def run_weekly_audits(save_self_check) -> Dict:
    """주간 감사 넷을 돌리고 {결과 키: self_check 형식} 을 반환."""
    result: Dict = {}
    for key, module, func in AUDITS:
        try:
            mod = __import__(module, fromlist=[func])
            r = getattr(mod, func)()
            result[key] = r
            if r.get("error_message"):
                logger.warning(f"[Maintenance] {r['error_message']}")
            if r.get("node"):  # 실제 실행됨 (카덴스 스킵이 아님) — 성공/실패 무관 기록
                try:
                    save_self_check(r)
                except Exception as e:
                    logger.warning(f"[Maintenance] {key} 원장 기록 실패 (무시): {e}")
        except Exception as e:
            logger.warning(f"[Maintenance] {key} 감사 실패 (무시): {e}")
    return result
