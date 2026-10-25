"""Stored workflow argument validation."""
import json

def coerce_caller_params(raw) -> tuple:
    """run 의 params 를 dict 로 강제. 반환: (dict|None, 오류문|None).

    모델이 JSON *문자열*로 넘기는 경우를 관용 수용하되, 객체가 아니면
    침묵 무시 대신 정직 거절(B8 부류 재발 방지)."""
    if raw is None:
        return None, None
    if isinstance(raw, dict):
        return (raw or None), None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, None
        try:
            loaded = json.loads(s)
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return (loaded or None), None
    return None, (f"params 는 {{변수명: 값}} 객체여야 합니다 (받은 형: {type(raw).__name__}). "
                  '예: [self:workflow]{op:"run", workflow_id:"x", params:{city:"청주"}}')
