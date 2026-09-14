#!/usr/bin/env python3
"""공통 회원 셸을 얇은 몸에 번들한다. 승인 UI 코드는 접속한 허브에서 내려받지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
import argparse
from member_shell import member_html

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "helper/member_app.html")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = member_html()
    if args.check:
        if not args.output.exists() or args.output.read_text() != content:
            raise SystemExit("회원 셸 번들이 낡았습니다 — scripts/build_member_shell.py 실행")
        print("회원 셸 번들 일치")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
        print("회원 셸 번들 생성")
