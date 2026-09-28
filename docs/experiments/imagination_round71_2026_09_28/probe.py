"""71회차: 저장 함수의 수명주기(저장·호출·개정·이행·삭제) 업무 조합 23과제.

축 = 70회차가 연 "지역 함수 분해" 다음 단계 — 교재(12_ibl_only §관용구와 저장)와 workflow.md 가
가르치는 "검증된 정의를 저장해 반복 사용, 고칠 때는 새 정의를 검사한 뒤 호출자를 전환"을 업무로
밟는다. 56~70회차 누구도 저장본의 개정·삭제·이름 공간을 밟지 않았다.
라이브 탐침 = 모델 경로(agent_id·task_id IT71_*). 스크래치 함수 = IT71_* (끝에 삭제).
이름 공간을 깨뜨릴 수 있는 과제(T18~T20)는 라이브에 쓰지 않고 임시 저장소로 격리 재현한다.
쓰기·예약은 check만. 모든 요청 origin=training.
사용: .venv/bin/python probe.py before|after
"""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
WF = BASE / 'data/workflows'
AGENT = {'agent_id': 'IT71_probe', 'task_id': 'IT71_task'}
LOG = []


def post(route, payload):
    proc = subprocess.run(['curl', '-sS', '--max-time', '180', f'http://127.0.0.1:8765/ibl/{route}',
                           '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                          input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠',
                   origin='training', **AGENT, **extra)
    response = post('execute', payload)
    LOG.append({'request': payload, 'response': {k: v for k, v in response.items()
                                                 if k not in ('evidence', 'source_map', 'recordings')}})
    return response


def text(r):
    """실패 응답에서 사람이 읽는 부분 전부(오류·진단 세부)."""
    return json.dumps({'error': r.get('error'), 'diagnostic': r.get('diagnostic'), 'issues': r.get('issues')},
                      ensure_ascii=False)


def save(code, **extra):
    fields = ''.join(f', {k}:{json.dumps(v, ensure_ascii=False)}' for k, v in extra.items())
    return ex(f'[self:workflow]{{op:"save", edition:2, code:"""{code}"""{fields}}}')


def saved_ok(r):
    return r.get('success') is True and (r.get('value') or {}).get('success') is True


GRADE = '[def:IT71_등급]($s){ [if:$s>=90]{ return "A" } [else] { return "B" } }'
GRADE2 = '[def:IT71_등급]($점수){ [if:$점수>=90]{ return "A" } [else] { return "B" } }'
SHEET = '[def:IT71_성적표]($목록){ $목록 >> [table:each]{ {점수:$it, 등급:[fn:IT71_등급]{s:$it}} } }'


def t01():
    """강의 성적 등급 함수를 저장하고 목록에서 실행 가능으로 보인다."""
    r = save(GRADE, description='강의 성적 등급(상상훈련 71 스크래치)')
    return saved_ok(r), f"success={(r.get('value') or {}).get('success')} error={r.get('error')}"


def t02():
    """저장한 등급 함수를 점수 목록 each 안에서 부른다."""
    r = ex('[95,80] >> [table:each]{ [fn:IT71_등급]{s:$it} }')
    return r.get('value') == ['A', 'B'], f"value={r.get('value')}"


def t03():
    """앱·예약이 쓰는 run 경로로 같은 함수를 이름+params로 실행."""
    r = ex('[self:workflow]{op:"run", name:"IT71_등급", params:{s:95}}')
    return (r.get('value') or {}).get('value') == 'A', f"value={(r.get('value') or {}).get('value')}"


def t04():
    """저장 함수의 계약을 describe로 조회."""
    r = ex('return 1', describe=['fn:IT71_등급'])
    c = ((r.get('descriptions') or [{}])[0].get('definition') or {}).get('callable_contract') or {}
    return c.get('required') == ['s'], f"required={c.get('required')}"


def t05():
    """등급 함수를 쓰는 성적표 함수를 저장하고 실행."""
    r = save(SHEET)
    v = ex('return [fn:IT71_성적표]{목록:[95,70]}').get('value')
    return saved_ok(r) and v == [{'점수': 95, '등급': 'A'}, {'점수': 70, '등급': 'B'}], f"value={v}"


def t06():
    """등급 함수의 인자 이름을 제자리 개정 — 저장 호출자(성적표)를 깨뜨리면 저장이 그 사실을 말해야 한다."""
    r = save(GRADE2)
    body = text(r) + json.dumps(r.get('value'), ensure_ascii=False)
    told = 'IT71_성적표' in body
    return told and not saved_ok(r), f"saved={saved_ok(r)} mentions_caller={told} error={r.get('error')}"


def t07():
    """개정 시도 뒤에도 성적표가 그대로 돈다(깨진 개정이 들어가지 않았다)."""
    r = ex('return [fn:IT71_성적표]{목록:[95]}')
    return r.get('value') == [{'점수': 95, '등급': 'A'}], f"value={r.get('value')} issues={[i.get('code') for i in r.get('issues') or []]}"


def t08():
    """교재의 이행 경로: 새 이름으로 저장 → 호출자 전환 → 옛 정의 삭제."""
    a = save(GRADE2.replace('IT71_등급', 'IT71_등급2'))
    b = save(SHEET.replace('[fn:IT71_등급]{s:$it}', '[fn:IT71_등급2]{점수:$it}'))
    c = ex('[self:workflow]{op:"delete", name:"IT71_등급"}')
    v = ex('return [fn:IT71_성적표]{목록:[70]}').get('value')
    ok = saved_ok(a) and saved_ok(b) and (c.get('value') or {}).get('success') is True and v == [{'점수': 70, '등급': 'B'}]
    return ok, f"a={saved_ok(a)} b={saved_ok(b)} delete={(c.get('value') or {}).get('success')} value={v}"


def t09():
    """쓰이고 있는 함수(등급2)를 삭제 — 호출자가 있다는 사실을 말하고 삭제하지 않는다."""
    r = ex('[self:workflow]{op:"delete", name:"IT71_등급2"}')
    body = text(r) + json.dumps(r.get('value'), ensure_ascii=False)
    exists = (WF / 'IT71_등급2.yaml').exists()
    return exists and 'IT71_성적표' in body, f"still_exists={exists} value={r.get('value')} error={r.get('error')}"


def t10():
    """세금 함수를 run 경로로 부르며 필수 인자를 빠뜨림 — 오류가 빠진 인자 이름을 말한다."""
    save('[def:IT71_세금]($금액,$세율=0.1){ return $금액 * $세율 }')
    r = ex('[self:workflow]{op:"run", name:"IT71_세금", params:{세율:0.2}}')
    return '금액' in text(r), f"error={r.get('error')}"


def t11():
    """run 경로에 없는 인자(부가세)를 줌 — 오류가 그 인자를 말한다."""
    r = ex('[self:workflow]{op:"run", name:"IT71_세금", params:{금액:1000, 부가세:true}}')
    return '부가세' in text(r), f"error={r.get('error')}"


def t12():
    """저장 안 된 보조 함수를 부르는 합계 함수를 저장 — 어떤 함수가 없는지 말한다."""
    r = save('[def:IT71_합계]($목록){ $v = $목록 >> [table:each]{ [fn:IT71_행금액]{r:$it} }; return sum($v) }')
    return not saved_ok(r) and 'IT71_행금액' in text(r), f"error={r.get('error')}"


def t13():
    """저장할 코드의 구문 오류(else를 대괄호 없이) — 저장 원문 안의 위치를 말한다."""
    r = save('[def:IT71_등급3]($s){ [if:$s>=90]{ return "A" } else { return "B" } }')
    d = json.dumps(((r.get('diagnostic') or {}).get('details') or {}), ensure_ascii=False)
    return 'SYNTAX' in d and '"line"' in d, f"code={(r.get('diagnostic') or {}).get('code')} details={d[:200]}"


def t14():
    """지역 함수로 분해한 가계부 합계 프로그램(정의 둘)을 그대로 저장 — 저장 방법을 안내한다."""
    r = save('[def:IT71_행금액]($r){ return $r.수량 * $r.단가 }\n'
             '[def:IT71_합계]($목록){ $v = $목록 >> [table:each]{ [fn:IT71_행금액]{r:$it} }; return sum($v) }')
    e = r.get('error') or ''
    return not saved_ok(r) and 'IT71_행금액' in e and '먼저' in e, f"error={e}"


def t15():
    """설명 없이 본문만 고쳐 다시 저장 — 기존 설명이 유지된다."""
    save('[def:IT71_메모]($x){ return $x }', description='부동산 메모 정리')
    save('[def:IT71_메모]($x){ return strip($x) }')
    got = ex('[self:workflow]{op:"detail", name:"IT71_메모"}').get('value') or {}
    return got.get('description') == '부동산 메모 정리', f"description={got.get('description')!r}"


def t16():
    """저장 ID와 함수 이름이 다른 할인가 함수 — 이름으로 run, 기본 인자 적용."""
    save('[def:IT71_할인]($가격,$율=0.1){ return $가격 * (1 - $율) }', workflow_id='it71-discount')
    r = ex('[self:workflow]{op:"run", name:"IT71_할인", params:{가격:1000}}')
    return (r.get('value') or {}).get('value') == 900, f"value={(r.get('value') or {}).get('value')}"


def t17():
    """workflow.md가 가르친 op:"get"으로 원문 조회 — 성공하면서 '거절됩니다' 경고를 내지 않는다."""
    r = ex('[self:workflow]{op:"get", name:"IT71_할인"}')
    v = r.get('value') or {}
    return bool(v.get('code')) and '거절' not in json.dumps(v, ensure_ascii=False), \
        f"code={bool(v.get('code'))} warning={v.get('param_warning')}"


ISOLATED = r'''
import json, sys, tempfile, pathlib
sys.path[:0] = ['.', 'ibl', 'common', 'cognition', 'datastore', 'base', 'services', 'surface']
import boot_paths, workflow_store
tmp = pathlib.Path(tempfile.mkdtemp()); workflow_store._get_workflows_path = lambda: tmp
import ibl_v2_store as s
from ibl_v2_entry import handle_request
proj = '/Users/kangkukjin/Desktop/AI/indiebizOS/projects/컨텐츠'
def run(code): return handle_request({'edition': 2, 'code': '#!ibl edition=2\n' + code}, proj)
out = {}
case = sys.argv[1]
if case == 'dup_id':
    s.action('save', {'code': '[def:IT71_배수]($x){ return $x * 2 }'}, proj)
    r = s.action('save', {'code': '[def:IT71_배수]($x){ return $x * 3 }', 'workflow_id': 'it71-v2'}, proj)
    out = {'saved': r.get('success'), 'error': r.get('error'), 'unrelated': run('return 1+1').get('value')}
elif case == 'alias':
    r = s.action('save', {'code': '[def:정렬해추리기]($x){ return $x }'}, proj)
    out = {'saved': r.get('success'), 'error': r.get('error'), 'unrelated': run('return 1+1').get('value')}
elif case == 'disk_dup':
    for wid in ('a', 'b'):
        (tmp / f'{wid}.yaml').write_text('edition: 2\nname: IT71_겹침\ncode: "[def:IT71_겹침]($x){ return $x }"\n')
    r = run('return [fn:IT71_겹침]{x:1}')
    out = {'unrelated': run('return 1+1').get('value'),
           'call_codes': [i.get('code') for i in r.get('issues') or []], 'call_error': r.get('error')}
print(json.dumps(out, ensure_ascii=False))
'''


def isolated(case):
    proc = subprocess.run([str(BASE / '.venv/bin/python'), '-c', ISOLATED, case], cwd=BASE / 'backend',
                          text=True, capture_output=True, timeout=300)
    line = [x for x in proc.stdout.splitlines() if x.startswith('{')]
    return json.loads(line[-1]) if line else {'stderr': proc.stderr[-400:]}


def t18():
    """(격리) 교재대로 '새 ID로 저장'하되 함수 이름은 그대로 — 저장이 거절되고 다른 프로그램은 계속 돈다."""
    o = isolated('dup_id')
    return o.get('saved') is False and o.get('unrelated') == 2, json.dumps(o, ensure_ascii=False)


def t19():
    """(격리) 기존 관용구와 같은 이름(정렬해추리기)으로 저장 — 거절되고 다른 프로그램은 계속 돈다."""
    o = isolated('alias')
    return o.get('saved') is False and o.get('unrelated') == 2, json.dumps(o, ensure_ascii=False)


def t20():
    """(격리) 손으로 복사해 이름이 겹친 저장본 둘 — 겹친 이름만 실패하고 다른 프로그램은 돈다."""
    o = isolated('disk_dup')
    return o.get('unrelated') == 2 and 'DUPLICATE_LIBRARY' in (o.get('call_codes') or []), json.dumps(o, ensure_ascii=False)


def t21():
    """저장한 기록 함수를 & 두 번 — 저장 함수 경유 병렬 쓰기도 충돌로 거절(check만)."""
    save('[def:IT71_기록]($c){ [self:write]{path:"~workspace/outputs/IT71_x.txt",content:$c} }')
    r = ex('[fn:IT71_기록]{c:"A반"} & [fn:IT71_기록]{c:"B반"}', check=True)
    codes = [i.get('code') for i in r.get('issues') or []]
    return 'PARALLEL_WRITE_CONFLICT' in codes, f"issues={codes}"


def t22():
    """workflow.md의 예약 실행 예시로 매일 아침 할인가 계산 예약(check만)."""
    r = ex('[self:manage_events]{op:"create",title:"IT71_계산",time:"08:00",repeat:"daily",do:"run_workflow",'
           'action_params:{workflow_id:"it71-discount",params:{가격:1000}}}', check=True)
    return r.get('status') in ('valid', 'incomplete') and not r.get('issues'), \
        f"status={r.get('status')} issues={[i.get('code') for i in r.get('issues') or []]}"


def t23():
    """저장 함수 가운데 실행 불가인 것만 골라 이름과 문제를 본다."""
    r = ex('$l=[self:workflow]{op:"list"}\n'
           'return $l.items >> [table:filter]{where:($w)=>contains($w.name,"IT71") && $w.runnable == false}')
    return isinstance(r.get('value'), list), f"value={r.get('value')} issues={[i.get('code') for i in r.get('issues') or []]}"


TASKS = [globals()[f't{i:02d}'] for i in range(1, 24)]


def cleanup():
    for path in list(WF.glob('IT71_*.yaml')) + list(WF.glob('it71-*.yaml')):
        path.unlink()
    for path in (BASE / 'outputs').glob('IT71_*'):
        path.unlink()


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'before'
    cleanup()
    rows = []
    for task in TASKS:
        try:
            ok, detail = task()
        except Exception as exc:  # 탐침의 실패도 기록한다
            ok, detail = False, f'probe error: {type(exc).__name__}: {exc}'
        rows.append({'task': task.__name__, 'intent': task.__doc__, 'ok': bool(ok), 'detail': detail})
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:240])
    cleanup()
    passed = sum(r['ok'] for r in rows)
    print(f'{passed}/{len(rows)}')
    (HERE / f'{phase}.json').write_text(json.dumps({'passed': passed, 'total': len(rows), 'rows': rows, 'log': LOG},
                                                   ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
