"""능력 변경의 준비·검사·조회. 쓰기는 반환 프로그램의 기존 관리 연산이 수행한다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401


def main():
    try:
        if sys.argv[1:2] in (['--check-worktree'], ['--check-files'], ['--plan-files']):
            from capability_changes import roots
            from capability_change_checks import check, changed_files
            root, _ = roots()
            explicit = sys.argv[1] != '--check-worktree'
            if explicit and not sys.argv[2:]:
                raise ValueError(sys.argv[1] + ' 뒤에 이 요청의 파일을 지정하세요.')
            if not explicit and sys.argv[2:]:
                raise ValueError('--check-worktree는 전체 변경 검사입니다. 파일 지정은 --check-files를 쓰세요.')
            planning = sys.argv[1] == '--plan-files'
            result = check(root, sys.argv[2:] if explicit else changed_files(root),
                           plan_only=planning, timeout=30 if planning else 1800)
            result['scope_source'] = 'explicit_files' if explicit else 'whole_worktree'
            result['imprint_scope'] = False
        else:
            from capability_changes import operate
            result = operate(json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('success') and result.get('ok', True) else 1
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({'success': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
