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
            "calls": {"type": "boolean",
                      "description": "true면 id 없이 이 대화의 현재 턴과 바로 앞 턴들이 실행한 호출 목록(프로그램 input.id·결과 result.id·실패 여부)을 돌려줌. "
                                     "같은 일을 다른 자료로 반복하거나 문맥이 압축돼 앞 프로그램을 잊었을 때 조회. limit보다 길면 text 페이지와 next_read를 반환."},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT,
                      "default": DEFAULT_LIMIT, "description": "문자 수(토큰 수 아님)"},
            "path": {"type": "array", "maxItems": MAX_PATH_DEPTH,
                     "items": {"anyOf": [{"type": "string"},
                                          {"type": "integer", "minimum": 0}]},
                     "description": "result_ref.paths의 실제 키/인덱스 경로. 중첩 JSON을 해제한 값의 문자 페이지(문자열은 원문 글자, 구조는 JSON — read_scope.format). 생략=원 봉투."},
        },
        "required": [],
        "description": "code를 비우고 result_ref.read_args로 원문 조회(앞 턴 결과도 가능). calls:true는 앞서 실행한 프로그램 목록. 필요한 path만 선택하고 다음 페이지는 next_read 그대로. read_scope.complete=true는 선택 경로 전체가 이 응답에 있음을 뜻함. 문맥에 남은 본문은 재독하지 않음. 재실행 없음.",
    }
