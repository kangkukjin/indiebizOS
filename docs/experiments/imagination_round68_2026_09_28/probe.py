"""68회차: 고친 프로그램의 증분 재실행(reuse)·재개(resume)·관측 필드 경고의 업무 조합 20과제.

축 = 09-26~27 증분 실행 개정(e284f811·81b0d410·5237aefb). 56~67회차가 밟지 않은 밭.
스크래치 파일은 outputs/IT68_* 에만 만들고 끝에 지운다. 발신·예약은 check만. 모든 요청 origin=training.
사용: .venv/bin/python probe.py before   (결과 = before.json)
"""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
OUT = BASE / 'outputs'
F = {k: str(OUT / f'IT68_{k}.txt') for k in ('memo', 'a', 'b', 'c', 'new', 'ledger')}
DB = 'path:"~workspace/data/world_pulse.db"'
LOG = []


def ex(code, *, check=False, project='컨텐츠', **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id=project,
                   origin='training', check=check, **extra)
    proc = subprocess.run(['curl', '-sS', '--max-time', '120', 'http://127.0.0.1:8765/ibl/execute',
                           '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                          input=json.dumps(payload), text=True, capture_output=True, check=True)
    response = json.loads(proc.stdout)
    result = response.get('result', response)
    LOG.append({'request': payload, 'response': {k: v for k, v in result.items()
                                                 if k not in ('evidence', 'source_map', 'recordings')}})
    return result


def recover(run_id):
    proc = subprocess.run(['curl', '-sS', '-X', 'POST', 'http://127.0.0.1:8765/ibl/recover',
                           '-H', 'Content-Type: application/json',
                           '-d', json.dumps({'run_id': run_id, 'project_id': '컨텐츠'})],
                          text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def rid(r):
    return (r.get('resume') or {}).get('run_id')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def read(path):
    return f'[self:read]{{path:"{path}"}}'


def hint(r):
    return (r.get('diagnostic') or {}).get('hint', '')


def reused(r):
    return (r.get('reuse') or {}).get('reused_calls')


def warns(r):
    return [w.get('code') for w in r.get('warnings', [])]


SYNTAX_HINT = '표시된 구문 경계를 수정'


# 각 과제: (id, 의도, 실행 함수 → (통과 여부, 요지))
def t01():
    """강의 자료 폴더 목록을 읽고 요약 문구만 고쳐 다시 — 목록 읽기 재사용."""
    r1 = ex('$d=[self:list]{path:"~workspace/projects"}; return len($d)')
    r2 = ex('$d=[self:list]{path:"~workspace/projects"}; return f"폴더 ${len($d)}개"', reuse={'run_id': rid(r1)})
    return reused(r2) == 1 and r2['value'] == f"폴더 {r1['value']}개", f"reused={reused(r2)} value={r2.get('value')}"


def t02():
    """가족신문 원고 2편을 읽은 뒤 1편을 앞에 추가하고 문장부호를 고쳐 재실행 — each 원소별 재사용."""
    for k, t in (('a', '가'), ('b', '나'), ('c', '다')):
        write(F[k], t)
    r1 = ex(f'return ["{F["a"]}","{F["b"]}"] >> [table:each]{{ $x=[self:read]{{path:$it}}; return $x.text }}')
    r2 = ex(f'return ["{F["c"]}","{F["a"]}","{F["b"]}"] >> [table:each]{{ $x=[self:read]{{path:$it}}; return $x.text+"." }}',
            reuse={'run_id': rid(r1)})
    return reused(r2) == 2 and r2['value'] == ['다.', '가.', '나.'], f"reused={reused(r2)} value={r2.get('value')}"


def t03():
    """부동산 메모를 새로 쓴 뒤 다시 읽기 — 쓰기 뒤 읽기는 재사용 금지."""
    write(F['memo'], 'A')
    r1 = ex(f'$t={read(F["memo"])}; return $t.text')
    r2 = ex(f'[self:write]{{path:"{F["memo"]}",content:"C"}}; $t={read(F["memo"])}; return $t.text',
            reuse={'run_id': rid(r1)})
    return r2.get('value') == 'C' and reused(r2) == 0, f"value={r2.get('value')} reused={reused(r2)}"


def t04():
    """메모 기록 함수를 부른 뒤 읽기 — 함수 안 쓰기도 장벽."""
    write(F['memo'], 'A')
    r1 = ex(f'$t={read(F["memo"])}; return $t.text')
    r2 = ex(f'[def:기록]($s) {{ [self:write]{{path:"{F["memo"]}",content:$s}} }}\n[fn:기록]{{s:"F"}}\n'
            f'$t={read(F["memo"])}; return $t.text', reuse={'run_id': rid(r1)})
    return r2.get('value') == 'F' and reused(r2) == 0, f"value={r2.get('value')} reused={reused(r2)}"


def t05():
    """메모 쓰기와 읽기를 병렬 가지로 — 병렬 쓰기도 장벽."""
    write(F['memo'], 'A')
    r1 = ex(f'$t={read(F["memo"])}; return $t.text')
    r2 = ex(f'$x=[self:write]{{path:"{F["memo"]}",content:"P"}} & {read(F["memo"])}; return $x[1].text',
            reuse={'run_id': rid(r1)})
    return reused(r2) == 0, f"value={r2.get('value')} reused={reused(r2)}"


def t06():
    """쓰지 않은 조건 가지 — 실행되지 않은 쓰기는 장벽이 아니다."""
    write(F['memo'], 'A')
    r1 = ex(f'$t={read(F["memo"])}; return $t.text')
    r2 = ex(f'[if:false] {{ [self:write]{{path:"{F["memo"]}",content:"D"}} }}\n$t={read(F["memo"])}; return $t.text+"?"',
            reuse={'run_id': rid(r1)})
    return r2.get('value') == 'A?' and reused(r2) == 1, f"value={r2.get('value')} reused={reused(r2)}"


def t07():
    """가계부 월 파일이 없으면 기본 문구로 — ?? 복구 성공의 실행 상태."""
    Path(F['new']).unlink(missing_ok=True)
    r = ex(f'$n={read(F["new"])} ?? {{text:"이번 달 기록 없음"}}; return $n.text')
    ok = r.get('success') is True and r.get('run_status') == 'completed'
    return ok, f"success={r.get('success')} run_status={r.get('run_status')} source_complete={r.get('source_complete')}"


def t08():
    """강의 출석 파일 읽기 실패를 try/catch로 안내 — 복구 성공의 실행 상태."""
    r = ex(f'$m="?"\n[try] {{ $x={read(F["new"])}; $m=$x.text }} [catch] {{ $m="출석 파일을 찾지 못했습니다" }}\nreturn $m')
    ok = r.get('success') is True and r.get('run_status') == 'completed'
    return ok, f"success={r.get('success')} run_status={r.get('run_status')} value={r.get('value')}"


def t09():
    """연결이 끊겼다고 가정하고 T07 실행을 recover로 조회."""
    r = ex(f'$n={read(F["new"])} ?? {{text:"이번 달 기록 없음"}}; return $n.text')
    s = recover(rid(r))
    ok = s.get('status') == 'completed'
    return ok, f"status={s.get('status')} resumable={s.get('resumable')} ended_at={'있음' if s.get('ended_at') else '없음'} reason={s.get('reason')}"


def t10():
    """원고 파일이 없어 실패 → 파일을 만든 뒤 고친 프로그램을 reuse — 실패 영수증은 재사용 안 함."""
    Path(F['new']).unlink(missing_ok=True)
    write(F['a'], '가')
    r1 = ex(f'$a={read(F["a"])}; $n={read(F["new"])}; return [$a.text,$n.text]')
    write(F['new'], '새')
    r2 = ex(f'$a={read(F["a"])}; $n={read(F["new"])}; return [$a.text,$n.text,"완"]', reuse={'run_id': rid(r1)})
    return r2.get('value') == ['가', '새', '완'] and reused(r2) == 1, f"value={r2.get('value')} reused={reused(r2)}"


def t11():
    """고친 코드에 resume을 실음(흔한 실수) — 거절 문구가 올바른 다음 행동을 가리키는가."""
    r1 = ex(f'$a={read(F["a"])}; return $a.text')
    r2 = ex(f'$a={read(F["a"])}; return $a.text+"!"', resume={'run_id': rid(r1)})
    code = (r2.get('diagnostic') or {}).get('code')
    return code == 'RESUME_CHANGED' and SYNTAX_HINT not in hint(r2), f"code={code} hint={hint(r2)}"


def t12():
    """음악 프로젝트에서 컨텐츠 프로젝트 실행 핸들로 reuse — 문맥 밖 핸들 거절 문구."""
    r1 = ex(f'$a={read(F["a"])}; return $a.text')
    r2 = ex(f'$a={read(F["a"])}; return $a.text', reuse={'run_id': rid(r1)}, project='음악')
    code = (r2.get('diagnostic') or {}).get('code')
    return code == 'REUSE_NOT_FOUND' and SYNTAX_HINT not in hint(r2), f"code={code} hint={hint(r2)}"


def t13():
    """resume과 reuse를 함께 — 인자 거절 문구."""
    r1 = ex(f'$a={read(F["a"])}; return $a.text')
    r2 = ex(f'$a={read(F["a"])}; return 1', reuse={'run_id': rid(r1)}, resume={'run_id': rid(r1)})
    code = (r2.get('diagnostic') or {}).get('code')
    return code == 'REUSE_ARGUMENT' and SYNTAX_HINT not in hint(r2), f"code={code} hint={hint(r2)}"


def t14():
    """발송 전 check에 없는 실행 핸들을 reuse로 — check가 핸들을 보는가."""
    r = ex(f'$a={read(F["a"])}; return $a.text', check=True, reuse={'run_id': '0' * 32})
    return r.get('status') != 'valid' or bool(r.get('warnings')), f"status={r.get('status')} warnings={warns(r)}"


def t15():
    """주간 보고서 '작성 시각' 줄만 고쳐 재실행 — 시계 읽기의 재사용."""
    r1 = ex('return [self:time]{}')
    time.sleep(61)
    r2 = ex('$t=[self:time]{}; return f"작성: ${$t}"', reuse={'run_id': rid(r1)})
    ok = reused(r2) == 0
    return ok, f"1차={r1.get('value')} 61초 뒤 재실행={r2.get('value')} reused={reused(r2)}"


def t16():
    """가계부 원장 파일에 한 줄 덧붙이기 → 형식만 고쳐 reuse 재실행 — 앞 실행이 쓴 줄의 운명."""
    write(F['ledger'], '09-01 식비 12000\n')
    prog = lambda line: (f'$old={read(F["ledger"])}; $new=$old.text + "{line}\\n"; '
                         f'[self:write]{{path:"{F["ledger"]}",content:$new}}; $chk={read(F["ledger"])}; return $chk.text')
    r1 = ex(prog('09-02 교통 3000'))
    hinted = bool((r1.get('continuation') or {}).get('reuse_args'))
    r2 = ex(prog('09-03 식비 8000'), reuse={'run_id': rid(r1)})
    now = Path(F['ledger']).read_text(encoding='utf-8')
    ok = '09-02 교통 3000' in now or bool(r2.get('warnings') or r2.get('reuse', {}).get('stale'))
    return ok, f"1차 continuation 권유={hinted} 재실행 reused={reused(r2)} 파일={now!r}"


def t17():
    """프로젝트 폴더 이름 오타 — 직접 접근·each·함수는 관측 경고."""
    L = '$d=[self:list]{path:"~workspace/projects"}; '
    got = {k: warns(ex(L + c, check=True)) for k, c in (
        ('직접', 'return $d[0].nmae'), ('each', 'return $d >> [table:each]{ return $it.nmae }'),
        ('함수', '[def:이름]($r) { return $r.nmae }\nreturn [fn:이름]{r:$d[0]}'))}
    return all(v == ['UNOBSERVED_FIELD'] for v in got.values()), json.dumps(got, ensure_ascii=False)


def t18():
    """같은 오타를 filter·sort·select·take 뒤 each에서 — 관측 경고의 전파."""
    L = '$d=[self:list]{path:"~workspace/projects"}; '
    got = {k: warns(ex(L + c, check=True)) for k, c in (
        ('filter 콜백', '$f=$d >> [table:filter]{where:($r)=>$r.nmae=="음악"}; return len($f)'),
        ('sort by', 'return $d >> [table:sort]{by:"nmae"}'),
        ('select columns', 'return $d >> [table:select]{columns:["nmae"]}'),
        ('take 뒤 each', 'return $d >> [table:take]{n:1} >> [table:each]{ return $it.nmae }'))}
    return all(v == ['UNOBSERVED_FIELD'] for v in got.values()), json.dumps(got, ensure_ascii=False)


def t19():
    """훈련 기록 원장에서 최근 3건만 보기 — sqlite limit 인자(작성자가 정한 선택)."""
    r = ex(f'$r=[sense:sqlite]{{{DB}, query:"select source from action_health order by rowid desc", limit:3}}; return len($r.items)')
    code = (r.get('diagnostic') or {}).get('code')
    return r.get('success') is True and r.get('value') == 3, f"success={r.get('success')} code={code} run_status={r.get('run_status')}"


def t20():
    """원장 조회 행을 $q[0]으로 인덱싱(흔한 실수) — 거절 문구가 고칠 방향을 가리키는가."""
    r = ex(f'$q=[sense:sqlite]{{{DB}, query:"select count(*) as n from action_health"}}; return $q[0].n')
    h = ' '.join(i.get('hint', '') for i in r.get('issues', []))
    return '.items나 .value를 붙이지 말고' not in h, f"hint={h}"


def t21():
    """실행기억 원장의 FTS 표 한 행 보기 — BLOB 열."""
    r = ex('$r=[sense:sqlite]{path:"~workspace/data/ibl_usage.db", query:"select * from ibl_examples_fts_docsize", limit:1}; return len($r.items)')
    return r.get('success') is True, f"success={r.get('success')} error={r.get('error')}"


def t22():
    """재사용한 실행을 다시 reuse (사슬) — 고친 프로그램의 두 번째 수정."""
    r1 = ex(f'$a={read(F["a"])}; return $a.text')
    r2 = ex(f'$a={read(F["a"])}; return $a.text+"1"', reuse={'run_id': rid(r1)})
    r3 = ex(f'$a={read(F["a"])}; return $a.text+"2"', reuse={'run_id': rid(r2)})
    return reused(r3) == 1 and r3.get('value') == '가2', f"value={r3.get('value')} reused={reused(r3)}"


def t23():
    """결석 안내 메일 (check만)."""
    r = ex('$결석=difference(["가","나"],["가"]); '
           '[others:channel_send]{channel_type:"email",to:"나",subject:"결석 안내",body:join(", ",$결석)}', check=True)
    return r.get('status') in ('valid', 'incomplete') and not r.get('issues'), f"status={r.get('status')}"


def t24():
    """매일 아침 지출 요약 예약 (check만)."""
    r = ex('$do="#!ibl edition=2\\n[self:time]{}"; [self:schedule]{repeat:"daily",time:"08:00",do:$do}', check=True)
    return r.get('status') in ('valid', 'incomplete') and not r.get('issues'), f"status={r.get('status')}"


TASKS = [t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12,
         t13, t14, t15, t16, t17, t18, t19, t20, t21, t22, t23, t24]


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'before'
    rows = []
    try:
        for task in TASKS:
            start = len(LOG)
            try:
                ok, summary = task()
            except Exception as exc:  # 탐침 자체의 실패는 실패로 적는다
                ok, summary = False, f'probe error: {exc!r}'
            rows.append({'task': task.__name__, 'intent': task.__doc__, 'passed': ok,
                         'summary': summary, 'calls': LOG[start:]})
            print(task.__name__, 'PASS' if ok else 'FAIL', summary[:300], flush=True)
    finally:
        for p in F.values():
            Path(p).unlink(missing_ok=True)
        (HERE / f'{phase}.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('SUMMARY', sum(r['passed'] for r in rows), '/', len(rows))


if __name__ == '__main__':
    main()
