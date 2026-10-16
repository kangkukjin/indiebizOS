#!/usr/bin/env python3
"""공통 회원 셸을 얇은 몸에 번들한다. 승인 UI 코드는 접속한 허브에서 내려받지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
import argparse
from member_shell import member_html
from surface_assets import source_build, track_reads, asset_sources
import json
import subprocess

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "helper/member_app.html")
    parser.add_argument("--check", action="store_true")
    parser.add_argument('--inputs', action='store_true')
    parser.add_argument('--check-staged', action='store_true')
    args = parser.parse_args()
    with source_build(), track_reads() as reads:
        content = member_html()
    root = Path(__file__).resolve().parents[1]
    inputs = {asset_sources()[name].relative_to(root).as_posix() for name in reads}
    inputs.update(Path(module.__file__).relative_to(root).as_posix()
                  for module in list(sys.modules.values())
                  if getattr(module, '__file__', None) and Path(module.__file__).is_relative_to(root / 'backend/surface'))
    inputs.update({'scripts/build_member_shell.py', 'helper/member_app.html'})
    if args.inputs:
        print(json.dumps(sorted(inputs)))
        raise SystemExit(0)
    if args.check_staged:
        changed = set(subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMRD'], cwd=root, text=True).splitlines())
        if not (inputs & changed):
            raise SystemExit(0)
    if args.check or args.check_staged:
        if not args.output.exists() or args.output.read_text() != content:
            raise SystemExit("회원 셸 번들이 낡았습니다 — scripts/build_member_shell.py 실행")
        print("회원 셸 번들 일치")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
        print("회원 셸 번들 생성")
