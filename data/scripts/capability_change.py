"""능력 변경의 준비·검사·조회. 쓰기는 반환 프로그램의 기존 관리 연산이 수행한다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401


def main():
    try:
        if sys.argv[1:] == ['--check-worktree']:
            from capability_changes import roots
            from capability_change_checks import check, changed_files
            root, _ = roots()
            result = check(root, changed_files(root))
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
