"""실행 산출물을 oracle 과 대조. 사용: verify.py <executor> <run> <out_dir> [--state state.json]"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_34회차'


def rows_by(rows, key):
    """행 목록 또는 {키: 행} 맵 — 두 모양 다 같은 사전으로 정규화한다(독립 AI 는 맵을 골랐다)."""
    if isinstance(rows, dict):
        return {k: ({**v, key: k} if isinstance(v, dict) else v) for k, v in rows.items()}
    return {r[key]: r for r in rows}


def names_of(value):
    if isinstance(value, dict):
        return sorted(value.keys())
    return sorted(x if isinstance(x, str) else (x.get('name') or x.get('file')) for x in (value or []))


def main():
    executor, run, out_dir = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
    state_path = Path(sys.argv[sys.argv.index('--state') + 1]) if '--state' in sys.argv else None
    oracle = json.load(open(OUT / 'oracle' / f'{executor}_run{run}.json'))
    result = json.load(open(out_dir / 'result.json'))
    summary = (out_dir / 'summary.md').read_text()
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'ok': bool(ok), 'detail': detail})

    run_info = result.get('run') or {}
    for k in ('processed_new', 'reprocessed', 'failed'):
        got_names = names_of(run_info.get(k))
        check(f'run.{k}', got_names == sorted(oracle['run'][k]), {'got': got_names[:12], 'exp': oracle['run'][k][:12]})
    for key, field in (('totals_by_sku', 'sku'), ('totals_by_store', 'store')):
        got = rows_by(result.get(key) or [], field)
        exp = rows_by(oracle[key], field)
        bad = [(k, f, got.get(k, {}).get(f), exp[k][f]) for k in exp for f in ('sale', 'refund', 'net', 'qty') if got.get(k, {}).get(f) != exp[k][f]]
        check(key, set(got) == set(exp) and not bad, {'missing': sorted(set(exp) - set(got))[:5], 'bad': bad[:5]})
    if 'totals_by_store_kind' in result:
        sk = result['totals_by_store_kind']
        got = ({(r['store'], r['kind']): r for r in sk} if isinstance(sk, list) else
               {tuple(k.split('/')) if '/' in k else tuple(k.split('|')): v for k, v in sk.items()})
        exp = {(r['store'], r['kind']): r for r in oracle['totals_by_store_kind']}
        check('totals_by_store_kind', set(got) == set(exp) and all(got[k]['amount'] == exp[k]['amount'] and got[k]['qty'] == exp[k]['qty'] for k in exp))
    check('files_total', result.get('files_total') == oracle['files_total'], (result.get('files_total'), oracle['files_total']))
    check('rows_total', result.get('rows_total') == oracle['rows_total'], (result.get('rows_total'), oracle['rows_total']))
    if state_path and state_path.exists():
        state = json.load(open(state_path))
        files = state.get('files') or state.get('processed') or []
        names = names_of(files)
        check('state_files', names == sorted(oracle['processed_files']), {'got': len(names), 'exp': len(oracle['processed_files']), 'extra': sorted(set(names) - set(oracle['processed_files']))[:3]})
        check('state_excludes_failed', not (set(names) & set(oracle['failed_files'])))
    for sec in ('상위', 'store', '실패'):
        check(f'summary:{sec}', sec in summary)
    if run == 3:
        check('summary_no_new', '새 파일 없음' in summary)
    top = sorted(oracle['totals_by_sku'], key=lambda r: -r['net'])[:10]
    check('summary_top10_present', all(r['sku'] in summary for r in top))
    ok = all(c['ok'] for c in checks)
    print(json.dumps({'executor': executor, 'run': run, 'all_ok': ok, 'checks': checks}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
