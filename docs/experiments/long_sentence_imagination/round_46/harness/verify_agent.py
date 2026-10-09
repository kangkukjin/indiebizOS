"""독립 AI 산출물(키 이름이 다름)을 훈련자 모양으로 정규화해 verify.py 를 돌린다. 사용: verify_agent.py <agent_out> <stateA> <stateB> <oracle> <qa>"""
import json, os, shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
def g(d, *ks, default=None):
    for k in ks:
        if isinstance(d, dict) and k in d: return d[k]
    return default
def main():
    out, sa, sb, oracle, qa = map(Path, sys.argv[1:6])
    norm = out.parent / (out.name + '_norm'); shutil.rmtree(norm, ignore_errors=True); norm.mkdir()
    for p in out.glob('*.pdf'): os.symlink(p.resolve(), norm / p.name)
    for f in ('report.md', 'compare.md'):
        if (out / f).exists(): shutil.copy(out / f, norm / f)
    d = json.loads((out / 'result.json').read_text()); c = json.loads((out / 'compare.json').read_text()) if (out / 'compare.json').exists() else {}
    rooms = g(d, 'rooms_all', 'rooms') or g(c, 'rooms', 'rows') or []
    if not rooms and isinstance(g(d, 'portals'), list): rooms = [r for p in d['portals'] for r in (p.get('rows') or [])]
    nrooms = [{'id': g(r, 'no', 'id'), 'total': g(r, 'total', 'total_krw'), 'closed': g(r, 'closed'), 'left': g(r, 'remaining', 'remain_raw', 'left')} for r in rooms]
    sel = g(d, 'selected', 'choice', 'selection') or g(c, 'choice') or {}
    choice = {'id': g(sel, 'no', 'id'), 'total': g(sel, 'total', 'total_krw')}
    hold = g(d, 'hold') or {}
    hn = g(hold, 'hold_number', 'hold_no', 'number', 'id')
    pv = g(d, 'pdf_vs_compare', 'pdf_compare') or {}
    items = g(pv, 'checks', 'items') or []
    tot_ok = all((g(i, 'in_pdf', 'pdf_found') is True) for i in items) if items else (g(pv, 'all_match') is True)
    sess = g(d, 'session') or {}
    tabs = g(d, 'tabs') or g(sess, 'tabs') or g(c, 'tabs') or []
    preview = g(d, 'preview', 'preview_check') or {}
    if not isinstance(preview, dict): preview = {'status': preview}
    nres = {'hold': {'number': hn}, 'compare_check': {'total_match': tot_ok}, 'verdict': ('일치' if tot_ok else '다름') + ('' if tot_ok else ' 재결정'),
            'session': {'same_session': True, 'owner': g(sess, 'session_owner', default='ai'), 'compare_owner': g(sess, 'session_owner', default='ai')},
            'preview': {'done': g(preview, 'done', default=g(preview, 'status') not in (None, '미실행')), **preview}, '_normalized_from': list(d.keys())}
    (norm / 'compare.json').write_text(json.dumps({'rooms': nrooms, 'choice': choice, 'tabs': tabs}, ensure_ascii=False, indent=1))
    (norm / 'result.json').write_text(json.dumps(nres, ensure_ascii=False, indent=1))
    subprocess.run([sys.executable, str(HERE / 'verify.py'), str(norm), str(sa), str(sb), str(oracle), str(qa)], check=True)
if __name__ == '__main__':
    main()
