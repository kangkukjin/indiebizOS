"""능력 교정의 추가 실행이 현재 턴의 소유권을 따르는지 확인한다."""


def execution_available(supervisor=None):
    """추가 실행의 소유자가 현재 턴인지 확인한다. 수리 권한 유무는 기준이 아니다."""
    if getattr(supervisor, 'apply_scheduled', None):
        return False
    from task_repair import pending
    if pending():
        return False
    from repair_continuation import current
    from component_continuation import is_task
    row = current()
    # 평가·적용·활성 검사는 별도 소비자가 소유한다. 실행 단계에서는 같은 방법 선택을 허용한다.
    return (not row or is_task(row) or row.get('phase') in {
        'execution', 'repair_apply', 'repair_active', 'verify_remaining'})
