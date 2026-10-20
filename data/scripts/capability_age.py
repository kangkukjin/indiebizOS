"""구성요소 수명 원장. self:script JSON 입력 또는 --args JSON으로 호출한다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import boot_paths  # noqa: E402,F401
from capability_age import operate  # noqa: E402


def main():
    try:
        if len(sys.argv) > 1:
            if len(sys.argv) != 3 or sys.argv[1] != '--args':
                raise ValueError('사용: capability_age.py --args \'{"op":"list"}\' 또는 stdin JSON')
            args = json.loads(sys.argv[2])
        else:
            args = json.load(sys.stdin)
        if not isinstance(args, dict):
            raise ValueError('JSON 객체가 필요합니다.')
        result = operate(args)
    except (ValueError, OSError) as exc:
        result = {'success': False, 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())
