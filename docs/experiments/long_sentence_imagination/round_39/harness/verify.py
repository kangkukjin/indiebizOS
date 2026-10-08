"""산출물을 oracle 과 대조. 사용: verify.py <who> <mode>   (who=trainer|agent, mode=base|again|bad|dry)
base/again: docs 36 파일 sha256 == oracle expected, report 수치 일치(again 은 files_changed [] 기대)
bad: docs_bad 36 파일 sha256 == 원본(guide_07 은 손상본 그대로), report applied:false·failed=[guide_07.md]
dry: docs sha256 == 원본(실행 전 상태), report 수치는 base 와 같음"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-09_39회차'
ORACLE = json.load(open(OUT / 'oracle' / 'report.json'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_report(out_dir):
    for name in ('report.json',):
        p = out_dir / name
        if p.exists():
            return json.load(open(p))
    return None


def norm_broken(rows):
    out = set()
    for r in rows or []:
        if isinstance(r, dict):
            out.add((r.get('file'), int(r.get('line') or 0), r.get('target')))
    return out


def main():
    who, mode = sys.argv[1], sys.argv[2]
    docs = OUT / who / {'bad': 'docs_bad', 'dry': 'docs_dry'}.get(mode, 'docs')
    out_dir = OUT / who / {'base': 'out', 'again': 'out_again', 'bad': 'out_bad', 'dry': 'out_dry'}[mode]
    checks = []
    files = sorted(ORACLE['sha256_expected'])
    # 1) 파일 바이트
    if mode in ('base', 'again'):
        bad = [f for f in files if sha(docs / f) != ORACLE['sha256_expected'][f]]
        checks.append(('docs == expected (36)', not bad, bad[:5]))
    else:
        src = OUT / 'source' / 'docs'
        bad = [f for f in files if f != 'guide_07.md' and sha(docs / f) != ORACLE['sha256_source'][f]]
        if mode == 'bad':
            bad += ['guide_07.md'] if (docs / 'guide_07.md').read_bytes() != (OUT / 'trainer' / 'docs_bad' / 'guide_07.md').read_bytes() and who != 'trainer' else []
        checks.append(('docs unchanged (no writes)', not bad, bad[:5]))
    # 2) 보고
    rep = load_report(out_dir)
    checks.append(('report.json exists', rep is not None, str(out_dir)))
    checks.append(('summary.md exists', (out_dir / 'summary.md').exists(), ''))
    if rep:
        if mode == 'bad':
            checks.append(('applied false', rep.get('applied') is False, rep.get('applied')))
            failed = [x.get('file') if isinstance(x, dict) else x for x in rep.get('failed', [])]
            checks.append(('failed == [guide_07.md]', [Path(str(f)).name for f in failed] == ['guide_07.md'], failed))
        else:
            exp_changed = [] if mode == 'again' else ORACLE['files_changed']
            got_changed = sorted(Path(str(x)).name for x in rep.get('files_changed', []))
            checks.append(('files_changed', got_changed == sorted(exp_changed), (len(got_changed), len(exp_changed))))
            if mode != 'again':
                checks.append(('replacements', rep.get('replacements') == ORACLE['replacements'], (rep.get('replacements'), ORACLE['replacements'])))
                hc = rep.get('headings_changed') or []
                got_h = sorted((Path(str(h.get('file'))).name, h.get('old'), h.get('new')) for h in hc if isinstance(h, dict))
                exp_h = sorted((h['file'], h['old'], h['new']) for h in ORACLE['headings_changed'])
                checks.append(('headings_changed', got_h == exp_h, (len(got_h), len(exp_h))))
                checks.append(('anchors_remapped', rep.get('anchors_remapped') == ORACLE['anchors_remapped'], (rep.get('anchors_remapped'), ORACLE['anchors_remapped'])))
                got_b = {(Path(str(f)).name, l, t) for f, l, t in norm_broken(rep.get('broken_links'))}
                exp_b = {(b['file'], b['line'], b['target']) for b in ORACLE['broken_links']}
                checks.append(('broken_links', got_b == exp_b, {'missing': sorted(exp_b - got_b)[:5], 'extra': sorted(got_b - exp_b)[:5]}))
            else:
                checks.append(('broken_links count 5 (new anchors)', len(rep.get('broken_links') or []) == 5, len(rep.get('broken_links') or [])))
            if mode == 'dry':
                checks.append(('applied false', rep.get('applied') is False, rep.get('applied')))
            if rep.get('sha256') and mode in ('base',):
                got_sha = {Path(str(k)).name: v for k, v in rep['sha256'].items()}
                checks.append(('report sha256 == expected', all(got_sha.get(f) == ORACLE['sha256_expected'][f] for f in files), ''))
    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(('PASS' if passed else 'FAIL'), name, '' if passed else json.dumps(detail, ensure_ascii=False)[:400])
    print('RESULT', who, mode, 'ALL PASS' if ok else 'FAILED')
    (OUT / 'runs' / f'verify_{who}_{mode}.json').write_text(json.dumps({'checks': [(n, p, str(d)[:400]) for n, p, d in checks], 'ok': ok}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
