#!/usr/bin/env python3
"""고정 문장으로 실제 IBL 엔진의 경계를 시험한다. 외부 서비스·모델 호출 없음."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import contextlib
import io
import json
import subprocess

from ibl_boundary_cases import cases, additional_cases, check, payload
from idiom_experiment_worker import run_trial
from ibl_parser import parse_with_vars


def probe(case):
    try:
        parse_with_vars(case['code'])
        syntax_ok = True
    except Exception as exc:
        return {**case, 'syntax_ok': False, 'ok': False, 'error_text': str(exc)}
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_trial(case['code'], 'dedup')['result']
    return {**case, 'syntax_ok': syntax_ok, 'ok': check(case, result),
            'runtime_success': result.get('success'), 'actual': payload(result),
            'error_text': result.get('error'), 'result': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--additional', action='store_true')
    parser.add_argument('--round2', action='store_true')
    parser.add_argument('--round3', action='store_true')
    parser.add_argument('--round4', action='store_true')
    parser.add_argument('--round5', action='store_true')
    parser.add_argument('--round6', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('기존 기록을 덮어쓰지 않습니다')
    rows = []
    selected = additional_cases() if args.additional else cases()
    if args.round2:
        from ibl_boundary_cases_round2 import cases as round2_cases
        from ibl_boundary_cases_round2 import additional_cases as round2_additional
        selected = round2_additional() if args.additional else round2_cases()
    if args.round3:
        from ibl_boundary_cases_round3 import cases as round3_cases
        selected = round3_cases()
    if args.round4:
        from ibl_boundary_cases_round4 import cases as round4_cases
        selected = round4_cases()
    if args.round5:
        from ibl_boundary_cases_round5 import cases as round5_cases
        selected = round5_cases()
    if args.round6:
        from ibl_boundary_cases_round6 import cases as round6_cases
        selected = round6_cases()
    for case in selected:
        row = probe(case)
        rows.append(row)
        print(row['id'], 'PASS' if row['ok'] else 'FAIL', flush=True)
    report = {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'cases': len(rows), 'passed': sum(r['ok'] for r in rows),
              'syntax_passed': sum(r['syntax_ok'] for r in rows), 'rows': rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print({k: v for k, v in report.items() if k != 'rows'})


if __name__ == '__main__':
    main()
