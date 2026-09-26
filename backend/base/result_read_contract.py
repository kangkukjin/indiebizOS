"""저장 결과 조회의 문자 페이지 계약 — 모델 도구와 MCP가 같은 한도를 알린다."""

DEFAULT_LIMIT = 60000
MAX_LIMIT = 60000
MAX_PATH_DEPTH = 16


def is_observation_request(request):
    """계약 조회를 곁들인 실행도 실제 작업이다. 추적·반복 관문을 건너뛰지 않는다."""
    if request.get("check"):
        return True
    if request.get("code") or request.get("pipeline"):
        return False
    return request.get("describe") is not None or request.get("read_result") is not None


def read_result_schema():
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT,
                      "default": DEFAULT_LIMIT, "description": "문자 수(토큰 수 아님)"},
            "path": {"type": "array", "maxItems": MAX_PATH_DEPTH,
                     "items": {"anyOf": [{"type": "string"},
                                          {"type": "integer", "minimum": 0}]},
                     "description": "result_ref.paths의 실제 키/인덱스 경로. 중첩 JSON을 해제한 값의 문자 페이지. 생략=원 봉투."},
        },
        "required": ["id"],
        "description": "code를 비우고 result_ref.read_args로 원문 조회. 다음 페이지는 next_read 그대로. 재실행 없음.",
    }
