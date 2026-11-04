"""검증된 공개 실행 인자의 전달. 신원·승인·전송 필드는 각 표면이 소유한다."""

EXECUTION_OPTION_FIELDS = (
    "code", "edition", "composition", "completion", "repair", "function_refs",
    "value_protocols", "inputs", "check", "code_edits", "resume", "reuse",
    "budget", "describe", "read_result",
)


def project_execution_options(values):
    """입구의 검증 뒤 호출한다. 빈 컨테이너와 내부 null/false를 보존한다."""
    result = {"code": values["code"]}
    for field in EXECUTION_OPTION_FIELDS[1:]:
        value = values.get(field)
        if field == "check":
            if value:
                result[field] = True
        elif value is not None:
            result[field] = value
    return result
