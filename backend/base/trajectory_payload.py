"""궤적 저장 계약: JSON 객체·유한 숫자·4096자, 생략 시 작은 필드와 원문 연결 보존."""
import hashlib
import json

from logging_utils import mask_secret_data

MAX_EVENT_CHARS = 4096


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, allow_nan=False)


def encode_payload(data):
    """본문을 잘라 JSON 문법을 깨지 않는다. 작은 필드는 그대로, 생략은 명시한다."""
    # JSON의 키/값 형태로 정규화한 뒤 값에만 마스킹을 적용한다.
    safe = mask_secret_data(json.loads(_encode(data if isinstance(data, dict) else {})))
    encoded = _encode(safe)
    if len(encoded) <= MAX_EVENT_CHARS:
        return encoded
    reduced = {"truncated": True, "original_chars": len(encoded),
               "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
               "omitted_fields": len(safe)}
    # seq/store/name/count 같은 작은 값이 긴 decision/response 때문에 사라지지 않는다.
    for key, value in sorted(safe.items(), key=lambda item: (len(_encode({item[0]: item[1]})), item[0])):
        if key in reduced:
            continue
        candidate = {**reduced, key: value, "omitted_fields": reduced["omitted_fields"] - 1}
        if len(_encode(candidate)) <= MAX_EVENT_CHARS:
            reduced = candidate
    return _encode(reduced)


def ensure_payload_guards(conn):
    """기존 행은 보존하고 신규 INSERT/본문 UPDATE만 검증한다. 호출자의 트랜잭션을 따른다."""
    for operation, suffix in (("INSERT", "insert"), ("UPDATE OF data", "update")):
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS trajectory_data_{suffix}
            BEFORE {operation} ON trajectory_event
            WHEN CASE WHEN json_valid(NEW.data) THEN json_type(NEW.data) <> 'object' ELSE 1 END
            BEGIN SELECT RAISE(ABORT, 'trajectory_event.data must be a JSON object'); END""")
