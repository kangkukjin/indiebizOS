"""몸 사이 스냅샷 교환 절차. 테이블·LWW·tombstone·파일의 뜻은 도메인 병합기가 소유한다."""
from collections.abc import Callable


class InvalidSyncPayload(ValueError):
    """교환 봉투의 형식 오류. 도메인 병합 중의 오류와 구별한다."""


def export_snapshot(export: Callable[[], dict]) -> dict:
    return {"success": True, "data": export()}


def merge_snapshot(payload: dict, merge: Callable[[dict], dict], export: Callable[[], dict]) -> dict:
    """옛 직접 스냅샷과 data 봉투를 모두 받는다. 실패 뒤 내보내기/성공 표명을 하지 않는다."""
    remote = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    if not isinstance(remote, dict):
        raise InvalidSyncPayload("sync 페이로드 형식 오류(dict 필요)")
    stats = merge(remote)
    return {"success": True, "stats": stats, "data": export()}
