"""70회차: 지역 함수 분해·함수 계약·객체/목록 값 자리 호출의 업무 조합 24과제.

축 = 09-26~27 작성법 개정(d306852f 지역 함수 분해 · be6107a5 값 자리 호출 · 5237aefb 함수 계약).
56~69회차 누구도 "여러 함수로 나눈 한 프로그램"의 계약·병렬·효과 검사를 밟지 않았다.
모델 경로 봉투를 받도록 agent_id·task_id(IT70_*)를 싣는다. 스크래치 = outputs/IT70_* (끝에 삭제).
알림·쓰기 병렬은 check만(실행하지 않는다). 모든 요청 origin=training.
사용: .venv/bin/python probe.py before|after
"""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
OUT = BASE / 'outputs'
AGENT = {'agent_id': 'IT70_probe', 'task_id': 'IT70_task'}
GENERIC = '해당 위치의 계약과 호출 인자를 확인하세요.'
LOG = []


def post(route, payload):
    proc = subprocess.run(['curl', '-sS', '--max-time', '180', f'http://127.0.0.1:8765/ibl/{route}',
                           '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                          input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, **extra):
    payload = dict(code=('#!ibl edition=2\n' + code) if code else '', edition=2, project_id='컨텐츠',
                   origin='training', **AGENT, **extra)
    response = post('execute', payload)
    LOG.append({'request': payload, 'response': {k: v for k, v in response.items()
                                                 if k not in ('evidence', 'source_map', 'recordings')}})
    return response


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def issue(r, code):
    return next((i for i in r.get('issues') or [] if i.get('code') == code), {})


BUDGET = '''[def:금액계산]($행) { return {id:$행.id,금액:$행.수량 * $행.단가} }
[def:내역작성]($목록) { $목록 >> [table:each] { [fn:금액계산]{행:$it} } }
[def:예산검토]($목록,$예산) {
  $내역 = [fn:내역작성]{목록:$목록}
  $합계 = reduce($내역,0,($합,$행)=>$합 + $행.금액)
  return {합계:$합계,예산이내:$합계 <= $예산}
}
'''


def t01():
    """강의 교구 두 구매안(마이크·보드)을 지역 함수 셋으로 예산 판정."""
    r = ex(BUDGET + 'return {마이크안:[fn:예산검토]{목록:[{id:"m",수량:2,단가:30},{id:"s",수량:1,단가:50}],예산:100},'
                    '보드안:[fn:예산검토]{목록:[{id:"b",수량:1,단가:80}],예산:100}}')
    v = r.get('value') or {}
    ok = v.get('마이크안') == {'합계': 110, '예산이내': False} and v.get('보드안') == {'합계': 80, '예산이내': True}
    return ok, f"value={v}"


def t02():
    """출석 요약 레코드 — 필드·목록 원소의 함수 호출이 원문 순서로 채워진다."""
    r = ex('[def:표시]($반,$n){ return f"${$반}반 ${$n}명" }\n'
           'return {오전:[fn:표시]{반:"A",n:12}, 오후:[[fn:표시]{반:"B",n:9},[fn:표시]{반:"C",n:7}]}')
    return r.get('value') == {'오전': 'A반 12명', '오후': ['B반 9명', 'C반 7명']}, f"value={r.get('value')}"


def t03():
    """가족신문 원고 읽기 함수를 필드에 두고 없는 원고는 ?? 기본값."""
    (OUT / 'IT70_a.txt').write_text('가족신문 1면 원고')
    r = ex('[def:읽기]($p){ $d=[self:read]{path:$p}; return $d.text }\n'
           'return {"1면":[fn:읽기]{p:"~workspace/outputs/IT70_a.txt"}, "2면":([fn:읽기]{p:"~workspace/outputs/IT70_none.txt"} ?? "원고 없음")}')
    ok = r.get('value') == {'1면': '가족신문 1면 원고', '2면': '원고 없음'} and r.get('source_complete') is False
    return ok, f"value={r.get('value')} source_complete={r.get('source_complete')}"


CONTAINER_WRITE = ('return {첫:[self:write]{path:"~workspace/outputs/IT70_r1.txt",content:"1면"},'
                   ' 둘:[self:read]{path:"~workspace/outputs/IT70_gate.txt"}.text,'
                   ' 셋:[self:write]{path:"~workspace/outputs/IT70_r3.txt",content:"3면"}}')
STATE = {}


def t04():
    """원고 저장 레코드의 가운데 필드가 실패 — 뒤 필드의 쓰기는 실행되지 않고 앞 쓰기는 남는다."""
    for name in ('IT70_r1.txt', 'IT70_r3.txt', 'IT70_gate.txt'):
        (OUT / name).unlink(missing_ok=True)
    r = ex(CONTAINER_WRITE)
    STATE['run'] = (r.get('resume') or {}).get('run_id')
    ok = r.get('success') is False and (OUT / 'IT70_r1.txt').exists() and not (OUT / 'IT70_r3.txt').exists()
    return ok, f"success={r.get('success')} r1={(OUT / 'IT70_r1.txt').exists()} r3={(OUT / 'IT70_r3.txt').exists()}"


def t05():
    """같은 실행을 resume — 완료된 앞 쓰기는 반복하지 않는다(사람이 고친 1면 보존)."""
    (OUT / 'IT70_r1.txt').write_text('사람이 고친 1면')
    r = ex(CONTAINER_WRITE, resume={'run_id': STATE.get('run')})
    text = (OUT / 'IT70_r1.txt').read_text()
    return text == '사람이 고친 1면' and r.get('resumed') is not None, f"r1={text!r} resumed={r.get('resumed')}"


REPORT = '''[def:기록]($줄){ [self:write]{path:"~workspace/outputs/IT70_x.txt",content:$줄} }
[def:주간보고]($목록){ $m = $목록 >> [table:each]{ $it.금액 }; [fn:기록]{줄:"점검"}; return sum($m) }
return [fn:주간보고]{목록:[{금액:2}]}'''


def t06():
    """주간 가계부 보고 함수의 계약 — 중첩 함수의 쓰기가 전이 효과로 보인다."""
    r = ex(REPORT, check=True)
    fn = next((f for f in (r.get('functions') or {}).values() if f.get('name') == '주간보고'), {})
    ok = fn.get('effects') == ['write_external'] and fn.get('actions') == ['self:write']
    return ok, f"effects={fn.get('effects')} actions={fn.get('actions')}"


def t07():
    """점수 목록을 파이프로 지역 함수의 첫 인자에 넘긴다."""
    r = ex('[def:가중]($목록,$k=2){ $목록 >> [table:each]{ $it*$k } }\n[70,80] >> [fn:가중]{k:3}')
    return r.get('value') == [210, 240], f"value={r.get('value')}"


def t08():
    """방금 짠 지역 함수의 계약을 describe로 확인하며 한 번에 실행."""
    r = ex(REPORT.replace('[self:write]{path:"~workspace/outputs/IT70_x.txt",content:$줄}', 'return $줄'),
           describe=['fn:주간보고'])
    desc = (r.get('descriptions') or [{}])[0]
    contract = (desc.get('definition') or {}).get('callable_contract') or {}
    ok = r.get('executed') is not False and r.get('value') == 2 and contract.get('pipe_input') == '목록'
    return ok, f"executed={r.get('executed')} value={r.get('value')} desc={json.dumps(desc, ensure_ascii=False)[:160]}"


P = '"~workspace/outputs/IT70_p.txt"'


def conflict(code):
    r = ex(code, check=True)
    return 'PARALLEL_WRITE_CONFLICT' in codes(r), f"issues={codes(r)}"


def t09():
    """두 반 명단을 같은 파일에 & 로 동시에 쓰기(문자 경로) — 충돌 거절."""
    return conflict(f'[self:write]{{path:{P},content:"A반"}} & [self:write]{{path:{P},content:"B반"}}')


def t10():
    """같은 경로를 변수에 담아 & 로 쓰기 — 뜻이 T09와 같다."""
    return conflict(f'$경로={P}\n[self:write]{{path:$경로,content:"A반"}} & [self:write]{{path:$경로,content:"B반"}}')


def t11():
    """기본 경로가 있는 기록 함수를 & 로 두 번."""
    return conflict(f'[def:기록]($c,$p={P}){{ [self:write]{{path:$p,content:$c}} }}\n[fn:기록]{{c:"A반"}} & [fn:기록]{{c:"B반"}}')


def t12():
    """경로 변수를 기록 함수 인자로 & 두 번."""
    return conflict(f'[def:기록]($c,$p){{ [self:write]{{path:$p,content:$c}} }}\n$경로={P}\n'
                    '[fn:기록]{c:"A반",p:$경로} & [fn:기록]{c:"B반",p:$경로}')


def t13():
    """함수 본문 안의 & 가 인자로 받은 같은 경로에 쓴다."""
    return conflict(f'[def:양쪽]($p){{ [self:write]{{path:$p,content:"A반"}} & [self:write]{{path:$p,content:"B반"}} }}\n'
                    f'[fn:양쪽]{{p:{P}}}')


def t14():
    """반별 요약을 each 병렬로 만들며 모두 같은 요약 파일에 쓴다."""
    return conflict(f'["A","B","C"] >> [table:each]{{parallel:3}}{{ [self:write]{{path:{P},content:$it}} }}')


def t15():
    """반별 파일(경로가 $it에 따름)을 each 병렬로 — 충돌이 아니다(대조군)."""
    r = ex('["A","B"] >> [table:each]{parallel:2}{ [self:write]{path:f"~workspace/outputs/IT70_${$it}.txt",content:$it} }',
           check=True)
    return not r.get('issues'), f"issues={codes(r)}"


def t16():
    """서로 다른 두 파일을 & 로 — 충돌이 아니다(대조군)."""
    r = ex('[self:write]{path:"~workspace/outputs/IT70_1.txt",content:"a"} & '
           '[self:write]{path:"~workspace/outputs/IT70_2.txt",content:"b"}', check=True)
    return not r.get('issues'), f"issues={codes(r)}"


GRADE = '[def:등급]($s){ [if:$s>=90]{ return "A" } }\nreturn [95,50] >> [table:each]{ [fn:등급]{s:$it} }'


def t17():
    """성적 등급 함수에서 else를 빠뜨림 — 검사가 반환 누락 경로를 알려야 한다."""
    r = ex(GRADE, check=True)
    warned = [w for w in (r.get('warnings') or []) + (r.get('issues') or []) if 'Unit' in json.dumps(w, ensure_ascii=False)
              or '반환' in json.dumps(w, ensure_ascii=False)]
    return bool(warned), f"warnings={[w.get('code') for w in r.get('warnings') or []]} issues={codes(r)}"


def t18():
    """할인가 함수의 기본값이 앞 인자(가격)를 참조 — 안내가 기본값 규칙을 말해야 한다."""
    r = ex('[def:할인]($가격,$율=0.1,$최종=$가격*(1-$율)){ return $최종 }\nreturn [fn:할인]{가격:10000}')
    hint = issue(r, 'UNBOUND').get('hint', '')
    return '기본값' in hint, f"issues={codes(r)} hint={hint}"


def t19():
    """바깥 세율 변수를 함수가 몰래 쓴다 — 인자로 넘기라는 안내."""
    r = ex('$세율=0.1\n[def:세금]($x){ return $x*$세율 }\nreturn [fn:세금]{x:1000}')
    hint = issue(r, 'UNBOUND').get('hint', '')
    return '인자' in hint, f"issues={codes(r)} hint={hint}"


def t20():
    """누적 이자를 재귀 함수로 — 반복 도구를 안내해야 한다."""
    r = ex('[def:복리]($n,$v){ [if:$n<=0]{ return $v } [else]{ $r=[fn:복리]{n:$n-1,v:$v*1.1}; return $r } }\n'
           'return [fn:복리]{n:3,v:100}')
    i = issue(r, 'RECURSION')
    return i.get('hint', GENERIC) != GENERIC and '첫 판본' not in i.get('message', ''), \
        f"message={i.get('message')} hint={i.get('hint')}"


def t21():
    """같은 이름의 함수를 두 번 정의 — 안내가 범용 문구가 아니어야 한다."""
    r = ex('[def:요약]($x){ return 1 }\n[def:요약]($x){ return 2 }\nreturn [fn:요약]{x:0}')
    i = issue(r, 'DUPLICATE_FUNCTION')
    return bool(i) and i.get('hint', GENERIC) != GENERIC, f"hint={i.get('hint')}"


def t22():
    """병렬 쓰기 충돌의 안내가 고치는 법(순차·다른 자원)을 말한다."""
    r = ex(f'[self:write]{{path:{P},content:"A"}} & [self:write]{{path:{P},content:"B"}}', check=True)
    i = issue(r, 'PARALLEL_WRITE_CONFLICT')
    return bool(i) and i.get('hint', GENERIC) != GENERIC, f"hint={i.get('hint')}"


def t23():
    """3월·4월 가계부 합계를 월 이름 필드로 — 숫자로 시작하는 필드 이름의 안내."""
    r = ex('return {3월:120000, 4월:98000}')
    i = (r.get('issues') or [{}])[0]
    ok = r.get('value') == {'3월': 120000, '4월': 98000} or '따옴표' in (i.get('message', '') + i.get('hint', ''))
    return ok, f"value={r.get('value')} message={i.get('message')} hint={i.get('hint')}"


def t24():
    """결석 안내 알림 함수 — check만, 계약에 발신 효과가 보인다."""
    r = ex('[def:결석안내]($이름){ [self:notify_user]{message:f"${$이름} 결석"} }\n[fn:결석안내]{이름:"나"}', check=True)
    fn = next((f for f in (r.get('functions') or {}).values() if f.get('name') == '결석안내'), {})
    ok = r.get('executed') is False and fn.get('effects') not in (None, ['pure']) and 'self:notify_user' in (fn.get('actions') or [])
    return ok, f"executed={r.get('executed')} effects={fn.get('effects')} actions={fn.get('actions')}"


TASKS = [globals()[f't{i:02d}'] for i in range(1, 25)]


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else 'before'
    rows = []
    for task in TASKS:
        try:
            ok, detail = task()
        except Exception as exc:  # 탐침의 실패도 기록한다
            ok, detail = False, f'probe error: {type(exc).__name__}: {exc}'
        rows.append({'task': task.__name__, 'intent': task.__doc__, 'ok': bool(ok), 'detail': detail})
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:220])
    for path in OUT.glob('IT70_*'):
        path.unlink()
    passed = sum(r['ok'] for r in rows)
    print(f'{passed}/{len(rows)}')
    (HERE / f'{phase}.json').write_text(json.dumps({'passed': passed, 'total': len(rows), 'rows': rows, 'log': LOG},
                                                   ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
