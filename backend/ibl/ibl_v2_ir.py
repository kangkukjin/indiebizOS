"""Compatibility import; the shared expression core lives in common.expression_ir."""
from common.expression_ir import *  # noqa: F401,F403
import hashlib as _hashlib
import json as _json


def digest_packed(packed):
    """pack 을 이미 거친 값의 지문. digest() 에 넘기면 포장 위에 포장을 한 번 더 입혀 값을 다시 훑는다
    (긴문장 L18-1: 도구 호출마다 인자 전체를 네 번 훑던 뿌리) — 포장된 값은 이 함수로 한 번만 직렬화한다."""
    return _hashlib.sha256(_json.dumps(packed, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
