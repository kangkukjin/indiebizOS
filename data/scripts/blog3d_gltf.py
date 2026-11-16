"""소원마당(3D 마을 블로그) glTF 건물 작업 묶음 — 만들기·압축/검사·게시판 등록·검증(2026-11-16).
stdin JSON 하나, stdout JSON 하나(registered-json/1). 실제 일은 outputs/3d-blog/scripts/ 의 파일이 한다(이 파일은 이어 주는 자리).
op:
  build    {source, out?}            Blender 배경 실행으로 source(견본 이름 polygon13|shell|vault 또는 .blend/.obj/.fbx/.gltf/.glb 경로)를 glb 로 내보낸 뒤 pack 까지.
                                     out 생략 시 outputs/3d-blog/.cache/wish_models/<이름>.glb
  pack     {input, out}              weld·dedup·prune·meshopt 압축 → glTF-Validator → 집 게시판 관문(크기·삼각형·바깥 파일)
  register {glb, name, base?, apply?, remove?, title?, architect?, maker?, url?, license?, tool?, note?, rot?, yard?(목록), fence?, ground?}
                                     apply 가 true 여야 실제로 올린다(기본 dry-run). 같은 이름·모델·출처면 재사용. remove 는 이 스크립트가 남긴 열쇠의 집만 지운다.
  verify   {base?, name?, build?}    순수 검사(check_wish_model.mjs) + 화면·API 검사(verify_wish_model.py). build=true 는 터에 짓는다 — 로컬 격리 Worker 에서만.
  snapshot {}                        고치기 전에 지금의 src/wish 를 .cache/oldwish/wish 로 떠 둔다(기존 집 대조의 기준).
  checks   {}                        소원 집 순수 검사 전부(check_wish_*.mjs) — 기준 사본이 있으면 기존 레시피의 정규화 글자·도형 불변까지 대조.
  lines    {base?, name?}            선 도구·5층 화면 검사(verify_wish_lines.py) — 터에 짓는다, 로컬 격리 Worker 전용.
  make     {script}                  레시피 모음 만들기(scripts/make_*.mjs, 예 make_seung_plans.mjs → design/seung_plans.json). ★ make_seung_houses.mjs 는 20칸 판 시절 기록이라 다시 돌리지 않는다
  architecture {collection?, apply?, base?} 모음(design/*.json)의 집을 게시판에 등록 — 같은 이름·같은 레시피는 재사용, 다시 받아 대조, 터 불변 확인. apply 없으면 dry-run
  board_check {names, plot?, base?}  게시판 항목이 운영에서 보이는지(둘러보기·미리보기·펼치기, 데스크톱·모바일). plot 을 주면 그 터에 지어 본 뒤 원래 집으로 되돌림
                                     (되돌림 확인은 관문 글자 비교 — 옛 판 글자로 저장된 집은 다시 저장되며 36칸 글자로 바뀐다, 같은 집)
  architecture 의 base 가 운영이 아니면(로컬 격리 Worker) 열쇠·기록을 measure/architecture/*.local.json 에 따로 둔다
  lines_live {base?, remove?}        운영 사이트 선·다층 확인(verify_lines_live.py) — 시험 항목 '선 부재 견본'을 게시판에 한 번만 저장(재사용), 터는 건드리지 않음. remove=true 는 그 항목만 지움.
결과: {ok, op, ...각 단계 보고, operation_outcome:{status, message}}"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'outputs/3d-blog'
VENV_PY = Path(__file__).resolve().parents[2] / '.venv/bin/python3'
NODE = '/opt/homebrew/opt/node@24/bin/node' if Path('/opt/homebrew/opt/node@24/bin/node').exists() else 'node'
BLENDER = '/opt/homebrew/bin/blender' if Path('/opt/homebrew/bin/blender').exists() else 'blender'
LIVE = 'https://blog3d.kangkukjin.workers.dev'


def out(ok, msg, **extra):
    print(json.dumps({'ok': ok, **extra, 'operation_outcome': {'status': 'passed' if ok else 'failed', 'message': msg}}, ensure_ascii=False))
    sys.exit(0)


def run(cmd, timeout=600):
    p = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def last_json(text):
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try: return json.loads(line)
            except Exception: pass
    return None


def pack(inp, dst):
    code, so, se = run([NODE, 'scripts/wish_gltf_pack.mjs', inp, dst], 300)
    rep = last_json(so) or {'ok': False, 'error': (se or so)[-400:]}
    return code == 0 and rep.get('ok'), rep


args = json.loads(sys.stdin.read() or '{}')
op = args.get('op', 'verify')
if op == 'pack':
    if not args.get('input') or not args.get('out'): out(False, 'input·out 이 필요합니다.', op=op)
    ok, rep = pack(args['input'], args['out'])
    out(bool(ok), '압축·검사 통과' if ok else rep.get('error', '실패'), op=op, report=rep)
if op == 'build':
    src = args.get('source', '')
    if not src: out(False, 'source 가 필요합니다(polygon13|shell|vault 또는 모델 파일 경로).', op=op)
    stem = Path(src).stem if Path(src).suffix else src
    dst = Path(args.get('out') or ROOT / '.cache/wish_models' / f'{stem}.glb').resolve(); raw = dst.with_suffix('.raw.glb')
    dst.parent.mkdir(parents=True, exist_ok=True)
    code, so, se = run([BLENDER, '-b', '--python', 'scripts/blender/wish_model.py', '--', raw, src], 600)
    if code != 0 or 'WROTE' not in so: out(False, 'Blender 내보내기 실패', op=op, stderr=(se or so)[-600:])
    ok, rep = pack(raw, dst)
    out(bool(ok), f'만들기·압축·검사 통과: {dst}' if ok else rep.get('error', '실패'), op=op, glb=str(dst), report=rep)
if op == 'register':
    if not args.get('glb') or not args.get('name'): out(False, 'glb·name 이 필요합니다.', op=op)
    cmd = [sys.executable, 'scripts/wish_gltf_register.py', args['glb'], '--name', args['name'], '--base', args.get('base', LIVE), '--rot', str(args.get('rot', 0))]
    for k in ['title', 'architect', 'maker', 'url', 'license', 'tool', 'note', 'fence', 'ground']:
        if args.get(k): cmd += ['--' + k, str(args[k])]
    if args.get('yard'): cmd += ['--yard', ','.join(args['yard'])]
    if args.get('apply'): cmd.append('--apply')
    if args.get('remove'): cmd.append('--remove')
    code, so, se = run(cmd, 300)
    rep = last_json(so) or {'ok': False, 'error': (se or so)[-400:]}
    out(code == 0 and bool(rep.get('ok')), (rep.get('operation_outcome') or {}).get('message', rep.get('error', '')), op=op, report={k: v for k, v in rep.items() if k != 'operation_outcome'})
if op == 'verify':
    base = args.get('base', LIVE); name = args.get('name', 'verify')
    code1, so1, se1 = run([NODE, 'scripts/check_wish_model.mjs'], 300)
    pure = last_json(so1) or {'checks': 0, 'failures': -1, 'error': se1[-300:]}
    cmd = [VENV_PY if VENV_PY.exists() else sys.executable, 'scripts/verify_wish_model.py', base, name] + (['--build'] if args.get('build') else [])
    code2, so2, se2 = run(cmd, 900)
    live = last_json(so2) or {'ok': False, 'error': (se2 or so2)[-400:]}
    ok = code1 == 0 and code2 == 0 and bool(live.get('ok'))
    out(ok, f"순수 {pure.get('checks')}건 중 실패 {pure.get('failures')} · 화면/API {live.get('passed')}/{live.get('total')}", op=op, pure=pure,
        browser={k: v for k, v in live.items() if k != 'operation_outcome'}, record=str(ROOT / 'measure/gltf' / f'{name}.json'))
if op == 'snapshot':
    import shutil
    dst = ROOT / '.cache/oldwish/wish'
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(ROOT / 'src/wish', dst)
    out(True, f'기준 사본: {dst}', op=op, path=str(dst))
if op == 'checks':
    rows = []
    for f in sorted((ROOT / 'scripts').glob('check_wish_*.mjs')):
        code, so, se = run([NODE, f'scripts/{f.name}'], 900)
        rows.append({'file': f.name, 'ok': code == 0, 'tail': (so.strip().splitlines() or [''])[-1][:200], 'error': '' if code == 0 else (se or so)[-300:]})
    bad = [r['file'] for r in rows if not r['ok']]
    out(not bad, f"{len(rows) - len(bad)}/{len(rows)} 통과" + (f" — 실패: {', '.join(bad)}" if bad else ''), op=op, items=rows)
if op == 'lines':
    code, so, se = run([VENV_PY if VENV_PY.exists() else sys.executable, 'scripts/verify_wish_lines.py', args.get('base', 'http://localhost:8799'), args.get('name', 'lines')], 900)
    rep = last_json(so) or {'ok': False, 'error': (se or so)[-400:]}
    out(code == 0 and bool(rep.get('ok')), (rep.get('operation_outcome') or {}).get('message', rep.get('error', '')), op=op, report={k: v for k, v in rep.items() if k != 'operation_outcome'})
if op == 'make':
    sc = args.get('script', '')
    if not sc.startswith('make_') or not sc.endswith('.mjs') or '/' in sc or not (ROOT / 'scripts' / sc).exists(): out(False, 'scripts/make_*.mjs 파일 이름이 필요합니다.', op=op)
    code, so, se = run([NODE, f'scripts/{sc}'], 300)
    out(code == 0, '만들기 완료' if code == 0 else (se or so)[-400:], op=op, summary=(so.strip().splitlines() or [''])[-1][:3000])
if op == 'architecture':
    col = args.get('collection', 'architecture_collection.json')
    if '/' in col or not (ROOT / 'design' / col).exists(): out(False, f'design/{col} 이 없습니다.', op=op)
    cmd = [sys.executable, 'scripts/register_architecture_collection.py', '--collection', col, '--base', args.get('base', LIVE)] + (['--apply'] if args.get('apply') else [])
    code, so, se = run(cmd, 900)
    rows = [json.loads(l) for l in so.splitlines() if l.startswith('{')]
    out(code == 0, ('등록·확인 완료' if args.get('apply') else 'dry-run(apply 없음)') if code == 0 else (se or so)[-400:], op=op, items=rows)
if op == 'board_check':
    names = args.get('names') or []
    if isinstance(names, list): names = ','.join(names)
    if not names: out(False, 'names 가 필요합니다.', op=op)
    cmd = [VENV_PY if VENV_PY.exists() else sys.executable, 'scripts/verify_board_entries_live.py', '--names', names, '--base', args.get('base', LIVE), '--tag', args.get('tag', 'board')] + (['--plot', str(args['plot'])] if args.get('plot') is not None else [])
    code, so, se = run(cmd, 1500)
    rep = last_json(so) or {'ok': False, 'error': (se or so)[-400:]}
    out(code == 0 and bool(rep.get('ok')), (rep.get('operation_outcome') or {}).get('message', rep.get('error', '')), op=op, report={k: v for k, v in rep.items() if k != 'operation_outcome'})
if op == 'lines_live':
    cmd = [VENV_PY if VENV_PY.exists() else sys.executable, 'scripts/verify_lines_live.py', args.get('base', LIVE)] + (['--remove'] if args.get('remove') else [])
    code, so, se = run(cmd, 900)
    rep = last_json(so) or {'ok': False, 'error': (se or so)[-400:]}
    out(code == 0 and bool(rep.get('ok')), (rep.get('operation_outcome') or {}).get('message', f"status {rep.get('status')}" if 'status' in rep else rep.get('error', '')), op=op, report={k: v for k, v in rep.items() if k != 'operation_outcome'})
out(False, f'모르는 op: {op}', op=op)
