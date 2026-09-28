"""69회차: 결과 참조 왕복(result_ref·read_result·inputs $ref)의 업무 조합 24과제.

축 = 09-26~28 결과 연속성 개정(e284f811 inputs $ref · 5d76eb63 read_result.input_args · 9dd15586 read_scope).
68회차는 reuse/resume만 밟았고 참조 전달은 아무도 밟지 않았다. 참조는 모델 경로에만 붙으므로
모든 요청은 agent_id·task_id(IT69_*)를 실어 호출 통로를 'agent'로 만든다(앱 통로는 원형 봉투만 받는다).
스크래치 파일은 outputs/IT69_* 에만 만들고 끝에 지운다. 발신은 check만. 모든 요청 origin=training.
사용: .venv/bin/python probe.py before|after
"""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
OUT = BASE / 'outputs'
AGENT = {'agent_id': 'IT69_probe', 'task_id': 'IT69_task'}
LOG = []


def post(route, payload):
    proc = subprocess.run(['curl', '-sS', '--max-time', '120', f'http://127.0.0.1:8765/ibl/{route}',
                           '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                          input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, *, route='execute', agent=AGENT, **extra):
    payload = dict(code=('#!ibl edition=2\n' + code) if code else '', edition=2, project_id='컨텐츠',
                   origin='training', **agent, **extra)
    response = post(route, payload)
    LOG.append({'request': payload, 'response': {k: v for k, v in response.items()
                                                 if k not in ('evidence', 'source_map', 'recordings')}})
    return response


def ref_of(r):
    return r['result_ref']['input_args']['입력']


def issues(r):
    return [i.get('code') for i in r.get('issues') or []]


def t01():
    """강의 폴더 목록을 참조로 넘겨 디렉터리 수만 센다."""
    a = ex('return [self:list]{path:"~workspace/projects"}')
    r = ex('$d = $입력 >> [table:filter]{where:($r)=>$r.is_dir}; return len($d)', inputs=a['result_ref']['input_args'])
    dirs = sum(1 for row in a['value'] if row.get('is_dir'))
    return r.get('success') is True and r.get('value') == dirs, f"value={r.get('value')} expected={dirs}"


def t02():
    """1차시·2차시 출석 결과 두 참조로 결석자를 구한다."""
    a, b = ex('return ["가","나","다"]'), ex('return ["가","다"]')
    r = ex('return difference($first, $second)', inputs={'first': ref_of(a), 'second': ref_of(b)})
    return r.get('value') == ['나'], f"value={r.get('value')}"


AREA = 'return {price: 19.9, items:[{n:"A동", v:1.1},{n:"B동", v:2.2}]}'


def t03():
    """관심 매물 결과를 input_args 그대로 넘겨 가격×3 (손실 없는 값)."""
    a = ex(AREA)
    r = ex('return $입력.price * 3', inputs=a['result_ref']['input_args'])
    return str(r.get('value')) == '59.7', f"value={r.get('value')}"


def t04():
    """매물 결과를 read_result로 확인한 뒤 그 페이지의 input_args로 가격×3."""
    a = ex(AREA)
    page = ex('', read_result=a['result_ref']['read_args'])
    r = ex('return $입력.price * 3', inputs=page['input_args'])
    return str(r.get('value')) == '59.7', f"value={r.get('value')} input_args={page.get('input_args')}"


def t05():
    """매물 두 동 면적 행만 path로 골라 합계."""
    a = ex(AREA)
    r = ex('return $입력[0].v + $입력[1].v',
           inputs={'입력': {'$ref': a['result_ref']['id'], 'path': ['value', 'items']}})
    return str(r.get('value')) == '3.3', f"value={r.get('value')}"


PAR = ('$x = [self:read]{path:"~workspace/outputs/IT69_a.txt"}.text & '
       '[self:read]{path:"~workspace/outputs/IT69_none.txt"}.text & '
       '[self:read]{path:"~workspace/outputs/IT69_b.txt"}.text; return $x')


def t06():
    """원고 셋 중 하나가 없어 실패 — 성공한 가지를 partial_reads.input_args로 이어 쓴다."""
    r = ex(PAR)
    reads = (r.get('result_ref') or {}).get('partial_reads') or []
    g = ex('return len($입력)', inputs=reads[-1]['input_args']) if reads else {}
    return g.get('value') == 1200 and [e['branch_index'] for e in reads] == [0, 2], \
        f"branches={[e['branch_index'] for e in reads]} value={g.get('value')}"


def t07():
    """부분 결과를 이어 쓴 실행은 원천 불완전을 물려받는다."""
    r = ex(PAR)
    g = ex('return len($입력)', inputs=r['result_ref']['partial_reads'][0]['input_args'])
    return g.get('success') is True and g.get('source_complete') is False, \
        f"success={g.get('success')} source_complete={g.get('source_complete')}"


def t08():
    """가계부 파일이 없으면 ?? 기본값 — 그 결과를 참조로 넘겨도 불완전 표지가 이어진다."""
    f = ex('$n=[self:read]{path:"~workspace/outputs/IT69_none.txt"} ?? {text:"기본"}; return $n.text')
    g = ex('return $입력 + "!"', inputs=f['result_ref']['input_args'])
    return g.get('value') == '기본!' and g.get('source_complete') is False, \
        f"value={g.get('value')} source_complete={g.get('source_complete')}"


def t09():
    """실패한 원고 읽기 결과를 id로 참조 — 실패 봉투가 업무 값이 되면 안 된다."""
    f = ex('$d=[self:read]{path:"~workspace/outputs/IT69_none.txt"}; return $d.text')
    g = ex('return len($입력)', inputs={'입력': {'$ref': f['result_ref']['id']}})
    ok = g.get('success') is False and g.get('executed') is False and '실패' in (g.get('error') or '')
    return ok, f"success={g.get('success')} value={g.get('value')} error={(g.get('error') or '')[:80]}"


def t10():
    """1반·2반 성적 결과를 목록으로 묶어 넘긴다."""
    a = ex('return [{n:"가", s:90},{n:"나", s:70}]')
    b = ex('return [{n:"다", s:80}]')
    g = ex('$all = $반[0] + $반[1]; return len($all)',
           inputs={'반': [{'$ref': a['result_ref']['id']}, {'$ref': b['result_ref']['id']}]})
    return g.get('value') == 3, f"value={g.get('value')} error={(g.get('error') or '')[:60]}"


def t11():
    """보고서 설정 레코드 안에 앞 결과 참조를 둔다."""
    a = ex('return [{n:"가", s:90},{n:"나", s:70}]')
    g = ex('return len($cfg.rows)', inputs={'cfg': {'rows': {'$ref': a['result_ref']['id']}, 'title': '성적'}})
    return g.get('value') == 2, f"value={g.get('value')}"


def t12():
    """수동 모드 검수(/ibl/validate)에 참조 inputs — 참조 dict를 업무 값으로 타입 검사하면 안 된다."""
    a = ex('return [{n:"가", s:90}]')
    v = ex('return $입력[0].s + 1', route='validate', inputs={'입력': {'$ref': a['result_ref']['id']}})
    bad = 'FIELD_TYPE' in issues(v)
    return not bad and (v.get('valid') or 'inputs.' in json.dumps(v, ensure_ascii=False)), \
        f"valid={v.get('valid')} issues={issues(v)} error={(v.get('error') or '')[:80]}"


def t13():
    """모델 경로 check:true 에 참조 inputs."""
    a = ex('return [{n:"가", s:90}]')
    v = ex('return $입력[0].s + 1', check=True, inputs={'입력': {'$ref': a['result_ref']['id']}})
    return v.get('status') == 'valid', f"status={v.get('status')}"


def t14():
    """다른 대화(작업)의 참조를 넘긴다 — 범위 밖임을 알려야 하고 내부 경로를 흘리면 안 된다."""
    a = ex('return ["가"]')
    other = {'agent_id': 'IT69_probe', 'task_id': 'IT69_other'}
    g = ex('return $입력', agent=other, inputs={'입력': {'$ref': a['result_ref']['id']}})
    err = g.get('error') or ''
    return g.get('executed') is False and 'Errno' not in err and '/Users/' not in err, err[:160]


def t15():
    """9만 자 가족신문 원고를 페이지로 끝까지 읽어 원문과 대조한다."""
    orig = (OUT / 'IT69_big.txt').read_text(encoding='utf-8')
    r = ex('$d=[self:read]{path:"~workspace/outputs/IT69_big.txt"}; return $d')
    args = dict(r['result_ref']['read_args'], path=['value', 'text'], limit=30000)
    buf, pages = '', 0
    while args:
        page = ex('', read_result=args)
        buf += page['text']
        args, pages = page['next_read'], pages + 1
    try:
        same = buf == orig or json.loads(buf) == orig
    except ValueError:
        same = False
    return same, f"pages={pages} chars={len(buf)}"


def t16():
    """원고 문자열 경로를 읽으면 미리보기의 total과 같은 원문 글자를 받는다(JSON 이스케이프 아님)."""
    orig = (OUT / 'IT69_big.txt').read_text(encoding='utf-8')
    r = ex('$d=[self:read]{path:"~workspace/outputs/IT69_big.txt"}; return $d')
    change = next(c for c in r['_preview']['changes'] if c['path'] == ['value', 'text'])
    page = ex('', read_result=dict(change['read_args'], limit=5000))
    total = page['read_scope']['total_chars']
    return total == change['total'] == len(orig) and page['text'] == orig[:5000], \
        f"preview_total={change['total']} read_total={total} head={page['text'][:30]!r}"


def t17():
    """input_hint대로 이름을 바꾸다 inputs 쪽을 빠뜨림 — 안내가 실제 입력 이름을 알려야 한다."""
    a = ex('return ["IT69_a.txt"]')
    r = ex('return len($목록)', inputs=a['result_ref']['input_args'])
    hint = ' '.join(i.get('hint', '') + i.get('message', '') for i in r.get('issues') or [])
    return 'UNBOUND' in issues(r) and '$입력' in hint, hint[:160]


EACH = ('$t = [table:each]{items:$입력}{ [self:read]{path:"~workspace/outputs/"+$it}.text }; '
        'return len($t[0])')


def t18():
    """원고 목록 참조로 읽은 실행을 같은 입력으로 resume."""
    a = ex('return ["IT69_a.txt","IT69_b.txt"]')
    r1 = ex(EACH, inputs=a['result_ref']['input_args'])
    r2 = ex(EACH, inputs=a['result_ref']['input_args'], resume={'run_id': r1['resume']['run_id']})
    return r2.get('resumed') is True and r2.get('value') == 900, f"resumed={r2.get('resumed')} value={r2.get('value')}"


def t19():
    """고친 프로그램을 다른 원고 목록 참조로 reuse — 겹치는 읽기만 재사용."""
    a, b = ex('return ["IT69_a.txt","IT69_b.txt"]'), ex('return ["IT69_b.txt"]')
    r1 = ex(EACH, inputs=a['result_ref']['input_args'])
    code2 = EACH.replace('return len($t[0])', 'return len($t[0]) + len($t[-1])')
    r2 = ex(code2, inputs=b['result_ref']['input_args'], reuse={'run_id': r1['resume']['run_id']})
    return r2.get('value') == 2400 and (r2.get('reuse') or {}).get('reused_calls') == 1, \
        f"value={r2.get('value')} reuse={r2.get('reuse')}"


def _roundtrip(value):
    a = ex('return $v', inputs={'v': value})
    g = ex('return $입력', inputs=a['result_ref']['input_args']) if 'input_args' in a['result_ref'] else {}
    honest = g.get('executed') is False or 'input_args' not in a['result_ref']
    return g.get('value') == value or honest, f"via_ref={json.dumps(g.get('value'), ensure_ascii=False)[:80]} error={(g.get('error') or '')[:60]}"


def t20():
    """강의실 와이파이 안내 메모를 참조로 넘겨 공지문에 넣는다 — 값이 조용히 바뀌면 안 된다."""
    return _roundtrip('와이파이 비밀번호는 cafe2026guest 입니다')


def t21():
    """주간 점검 메모의 실행 번호 문장을 참조로 넘긴다."""
    return _roundtrip('token run 96789681144447eab35805f3276ae5fa')


def t22():
    """옛 파이프 봉투(>>) 결과를 참조로 넘겨 행 수를 센다."""
    r = post('execute', dict(code='[self:list]{path:"~workspace/projects"} >> [table:take]{n:3}',
                             project_id='컨텐츠', origin='training', **AGENT))
    g = ex('return len($입력.items)', inputs={'입력': {'$ref': r['result_ref']['id']}})
    return g.get('value') == 3 and g.get('source_complete') is True, f"value={g.get('value')}"


def t23():
    """원고 둘을 each로 읽은 결과의 원소별 큰 필드 경로."""
    r = ex('$docs=[table:each]{items:["IT69_a.txt","IT69_b.txt"]}{ [self:read]{path:"~workspace/outputs/"+$it}.text }; return $docs')
    paths = [p['path'] for p in r['result_ref']['paths']]
    return paths == [['value', 0], ['value', 1]], f"paths={paths}"


def t24():
    """결석 안내를 참조 본문으로 알림 (check만)."""
    a = ex('return "나 학생 결석 안내"')
    v = ex('[self:notify_user]{message:$입력}', check=True, inputs=a['result_ref']['input_args'])
    return v.get('status') in ('valid', 'incomplete') and v.get('executed') is not True, f"status={v.get('status')}"


TASKS = [t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12,
         t13, t14, t15, t16, t17, t18, t19, t20, t21, t22, t23, t24]


def main(tag):
    text = ''.join(f'{i:04d} 가족신문 원고 줄 — "따옴표" \\ 역슬래시 및 탭\t끝\n' for i in range(2500))
    (OUT / 'IT69_big.txt').write_text(text, encoding='utf-8')
    (OUT / 'IT69_a.txt').write_text('가' * 900, encoding='utf-8')
    (OUT / 'IT69_b.txt').write_text('나' * 1200, encoding='utf-8')
    rows = []
    try:
        for task in TASKS:
            try:
                ok, note = task()
            except Exception as exc:  # 탐침 자체의 붕괴도 실패로 기록
                ok, note = False, f'probe error: {type(exc).__name__}: {exc}'
            rows.append({'id': task.__name__.upper(), 'intent': task.__doc__, 'pass': bool(ok), 'note': note})
            print(('PASS ' if ok else 'FAIL ') + task.__name__.upper() + ' ' + note)
    finally:
        for name in ('IT69_big.txt', 'IT69_a.txt', 'IT69_b.txt'):
            (OUT / name).unlink(missing_ok=True)
    passed = sum(r['pass'] for r in rows)
    print(f'{passed}/{len(rows)}')
    (HERE / f'{tag}.json').write_text(json.dumps({'summary': f'{passed}/{len(rows)}', 'tasks': rows,
                                                   'log': LOG}, ensure_ascii=False, indent=1, default=str),
                                      encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'before')
