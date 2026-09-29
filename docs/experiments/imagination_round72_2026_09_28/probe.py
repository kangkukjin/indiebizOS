"""72회차: 가계부·원장 업무 — 조회→집계→조건 판단 25과제 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 self:finance·self:ledger·table:reduce·join·since·judge·compute 를
사용자의 실제 가계부(재무기록 원장, 결제 알림 수거분) 위에서 조합한다: 월 합계·전월 대비·
결제수단/분류별 합계·예산 초과 판정·취소 짝짓기·새 결제 감시·월말 결산 기록.
라이브 탐침 = 모델 경로(agent_id·task_id IT72_*). 모든 요청 edition 2·project_id 컨텐츠·origin training.
★사용자 금융 원장은 읽기만. 재무 쓰기(save·ingest)는 check 만. 쓰기가 필요한 원장 과제는
  스크래치 JSON(outputs/IT72_*)과 검침 스트림(IT72_*)에만 쓰고 끝에 지운다.
★원장에 쓸 수밖에 없는 결함 재현(T13 절단·T14 주체 자동 등록)은 INDIEBIZ_USERDATA 를 임시
  디렉터리로 돌린 격리 프로세스에서 패키지 핸들러를 직접 불러 재현한다(라이브 DB 무접촉).
사용: .venv/bin/python probe.py before|after
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
FIN_DB = BASE / 'data/finance/finance_records.db'
SINCE_DB = BASE / 'data/table_since.db'
AGENT = {'agent_id': 'IT72_probe', 'task_id': 'IT72_task'}
LEDGER = '~workspace/outputs/IT72_budget.json'
CLOSING = '~workspace/outputs/IT72_closing.json'
LOG = []


def post(route, payload):
    proc = subprocess.run(['curl', '-sS', '--max-time', '240', f'http://127.0.0.1:8765/ibl/{route}',
                           '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                          input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠',
                   origin='training', **AGENT, **extra)
    response = post('execute', payload)
    LOG.append({'request': payload, 'response': {k: v for k, v in response.items()
                                                 if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}})
    return response


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def issues_text(r):
    return json.dumps([{k: i.get(k) for k in ('code', 'message', 'hint')} for i in r.get('issues') or []],
                      ensure_ascii=False)


def db(sql, *args):
    """사용자 재무 원장 읽기 전용(기대값 계산용)."""
    con = sqlite3.connect(f'file:{FIN_DB}?mode=ro', uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def month_sum(month, tx='expense'):
    return db("select coalesce(sum(amount),0) from transactions where deleted_at is null and tx_type=? "
              "and occurred_at like ?", tx, f'{month}%')[0][0]


Q_SEP = '[self:finance]{op:"query", query_type:"지출", month:"2026-09"}'


def t01():
    """이번 달(9월) 카드값 합계 얼마야? — 지출 조회 >> reduce."""
    r = ex(f'return {Q_SEP} >> [table:reduce]{{init:0, step:"acc + amount", as:"합계"}}')
    v = (r.get('value') or {}).get('value')
    return v == month_sum('2026-09'), f"value={v} db={month_sum('2026-09')}"


def t02():
    """9월 지출 중 큰 것 5건을 날짜·가맹점·금액만."""
    r = ex(f'$t = {Q_SEP}\nreturn $t.items >> [table:sort]{{by:"amount", descending:true}} >> [table:take]{{n:5}}'
           ' >> [table:select]{columns:["date","counterparty","amount"]}')
    v = r.get('value') or []
    amounts = [x.get('amount') for x in v]
    return len(v) == 5 and amounts == sorted(amounts, reverse=True), f"amounts={amounts}"


def t03():
    """가맹점별 9월 지출 합계 상위 5곳 — 같은 가맹점은 한 줄로 모여야 한다."""
    r = ex(f'$g = {Q_SEP} >> [table:groupby]{{by:"counterparty", agg:{{합계:["sum","amount"], 건수:["count"]}}}}\n'
           'return $g.items >> [table:sort]{by:"합계", descending:true} >> [table:take]{n:8}')
    v = r.get('value') or []
    keys = [x.get('counterparty') for x in v]
    residue = [k for k in keys if any(t in (k or '') for t in ('인센티브', '이용금액', '총 보유', '입니다', '출금되었'))]
    empty = [k for k in keys if not k]
    return bool(v) and not residue and not empty, f"keys={keys}"


def t04():
    """9월 순지출(지출 − 인센티브 수입)을 한 번에."""
    r = ex('$둘 = [self:finance]{op:"query", query_type:"지출", month:"2026-09"}'
           ' & [self:finance]{op:"query", query_type:"수입", month:"2026-09"}\n'
           '$합 = $둘 >> [table:each]{ $it >> [table:reduce]{init:0, step:"acc + amount"} }\n'
           'return {지출:$합[0].value, 수입:$합[1].value, 순지출:$합[0].value - $합[1].value}')
    v = r.get('value') or {}
    want = month_sum('2026-09') - month_sum('2026-09', 'income')
    return v.get('순지출') == want, f"value={v} want={want}"


def t05():
    """지난달보다 이번 달 지출이 몇 % 늘었어?"""
    r = ex('$a = [self:finance]{op:"query", query_type:"지출", month:"2026-08"} >> [table:reduce]{init:0, step:"acc + amount"}\n'
           f'$b = {Q_SEP} >> [table:reduce]{{init:0, step:"acc + amount"}}\n'
           'return {전월:$a.value, 이번달:$b.value, 증감률:round(($b.value - $a.value) / $a.value * 100, 1)}')
    v = r.get('value') or {}
    a, b = month_sum('2026-08'), month_sum('2026-09')
    return v.get('증감률') == round((b - a) / a * 100, 1), f"value={v}"


def t06():
    """최근 90일 월별 지출 추이."""
    r = ex('$w = [self:finance]{op:"query", query_type:"지출", days:90}\n'
           '$g = $w.items >> [table:compute]{set:($r)=>{월:$r.date[0:7]}} >> [table:groupby]{by:"월", agg:{합계:["sum","amount"]}}\n'
           'return $g.items >> [table:sort]{by:"월"}')
    v = r.get('value') or []
    got = {x.get('월'): x.get('합계') for x in v}
    return got.get('2026-09') == month_sum('2026-09') and got.get('2026-08') == month_sum('2026-08'), f"value={got}"


def t07():
    """이번 달 예산 100만원 — 넘었으면 얼마 넘었는지 한 줄로."""
    r = ex(f'$s = {Q_SEP} >> [table:reduce]{{init:0, step:"acc + amount"}}\n'
           '[if: $s.value > 1000000] { return f"예산 초과: ${$s.value - 1000000}원" } [else] { return f"남은 예산 ${1000000 - $s.value}원" }')
    v = r.get('value')
    return isinstance(v, str) and v.startswith('예산 초과'), f"value={v}"


def t08():
    """예산을 넘으면 나에게 알림(check만 — 발신은 검수)."""
    r = ex(f'$s = {Q_SEP} >> [table:reduce]{{init:0, step:"acc + amount"}}\n'
           '[if: $s.value > 1000000] { [self:notify_user]{message: f"이달 예산 초과: ${$s.value}원"} }', check=True)
    return r.get('status') in ('valid', 'incomplete') and not codes(r), f"status={r.get('status')} issues={codes(r)}"


def t09():
    """9월 식비만 얼마 썼어? — category:"식비" 는 선언된 인자다. 조용히 전체를 내면 안 된다."""
    r = ex('$t = [self:finance]{op:"query", query_type:"지출", month:"2026-09", category:"식비"}\n'
           '$c = $t.items >> [table:each]{ $it.category }\n'
           'return {n:len($t.items), total:$t.total, cats:unique($c)}')
    r2 = ex('$t = [self:finance]{op:"query", month:"2026-09", category:"식비"}\n'
            'return {n:len($t.items), msg:get($t,"message",""), text:get($t,"text","")}')
    v, v2 = r.get('value') or {}, r2.get('value') or {}
    all_rows = len(db("select 1 from transactions where deleted_at is null and tx_type='expense' and occurred_at like '2026-09%'"))
    silent_all = r.get('success') and v.get('n') == all_rows and '식비' not in (v.get('cats') or [])
    return not silent_all, f"with_type={v} | category_only={v2}"


def t10():
    """이번 달 중 최근 7일 지출 — month 와 days 를 같이 주면 둘 다 반영되거나 충돌을 말해야 한다."""
    r = ex('$t = [self:finance]{op:"query", query_type:"지출", month:"2026-09", days:7}\n'
           '$d = $t.items >> [table:each]{ $it.date }\n'
           'return {n:len($t.items), oldest:sorted($d)[0]}')
    v = r.get('value') or {}
    body = json.dumps(r, ensure_ascii=False)
    honest = ('days' in (r.get('error') or '')) or ('무시' in body and 'days' in body)
    return (v.get('oldest') or '') >= '2026-09-21' or honest, f"value={v} warn={r.get('warnings')}"


def t11():
    """어제 김밥천국에서 12,000원 점심 — 가맹점·날짜까지 기록(check만)."""
    r = ex('[self:finance]{op:"save", kind:"지출", amount:12000, category:"식비", counterparty:"김밥천국", date:"2026-09-27"}',
           check=True)
    return r.get('status') in ('valid', 'incomplete') and not codes(r), f"status={r.get('status')} issues={issues_text(r)}"


def t12():
    """문자 한 줄로 가계부 적재 — ingest text(check만)."""
    r = ex('[self:finance]{op:"ingest", text:"어제 점심 김밥천국 12000원, 저녁 택시 8500원"}', check=True)
    return r.get('status') in ('valid', 'incomplete') and not codes(r), f"status={r.get('status')} issues={issues_text(r)}"


ISOLATED = r'''
import json, os, sys, tempfile, sqlite3, shutil
tmp = tempfile.mkdtemp(prefix='IT72_fin_')
os.environ['INDIEBIZ_USERDATA'] = tmp
sys.path.insert(0, '/Users/kangkukjin/Desktop/AI/indiebizOS/data/packages/installed/tools/finance-record')
import finance_storage as st
assert st.DB_PATH.startswith(tmp), st.DB_PATH
import handler
class C: tool_name = 'finance_op'
def call(**kw): return json.loads(handler.execute(kw, C()))
out = {}
try:
    if sys.argv[1] == 'limit':
        for i in range(250):
            st.save_transaction('expense', 1000, occurred_at='2026-09-%02d' % (1 + i % 28))
        r = call(op='query', query_type='지출', month='2026-09')
        s = call(op='query', query_type='summary', month='2026-09')
        out = {'count': r.get('count'), 'total': r.get('total'), 'truncated': r.get('truncated'),
               'summary': s.get('text', '').splitlines()[2:3],
               'db': sqlite3.connect(st.DB_PATH).execute('select count(*), sum(amount) from transactions').fetchone()}
    elif sys.argv[1] == 'owner':
        call(op='save', kind='지출', amount=1000)
        before = [o['name'] for o in st.list_owners()]
        r = call(op='query', query_type='지출', owner='회사', month='2026-09')
        out = {'before': before, 'after': [o['name'] for o in st.list_owners()],
               'count': r.get('count'), 'message': r.get('message') or r.get('text')}
finally:
    shutil.rmtree(tmp)
print(json.dumps(out, ensure_ascii=False))
'''


def isolated(case):
    proc = subprocess.run([str(BASE / '.venv/bin/python'), '-c', ISOLATED, case], cwd=BASE,
                          text=True, capture_output=True, timeout=300)
    line = [x for x in proc.stdout.splitlines() if x.startswith('{')]
    return json.loads(line[-1]) if line else {'stderr': proc.stderr[-400:]}


def t13():
    """(격리) 거래가 250건인 달의 지출 합계 — 조회 합계가 요약 합계와 같거나 잘렸다고 말해야 한다."""
    o = isolated('limit')
    r = ex('[self:finance]{op:"query", query_type:"지출", month:"2026-09", limit:500}', check=True)
    ok = o.get('total') == 250000 or o.get('truncated') is True
    return ok, json.dumps(o, ensure_ascii=False) + f" | limit_check={codes(r)}"


def t14():
    """(격리) 회사 장부 조회(owner:"회사", 아직 없는 주체) — 조회가 주체를 만들지 않고 모르는 주체라고 말해야 한다."""
    o = isolated('owner')
    return o.get('after') == o.get('before'), json.dumps(o, ensure_ascii=False)


def t15():
    """분류별 월 예산표를 원장에 두고(스크래치) 식비 예산만 꺼내 본다."""
    w = ex(f'[self:ledger]{{op:"upsert", path:"{LEDGER}", target:"budgets", key:"category", items:['
           '{category:"식비", budget:300000},{category:"카페간식", budget:50000},{category:"통신구독", budget:60000},'
           '{category:"의료", budget:50000},{category:"하나카드", budget:500000},{category:"청주페이", budget:400000}]}')
    r = ex(f'return [self:ledger]{{op:"select", path:"{LEDGER}", target:"budgets", where:{{category:"식비"}}}}')
    items = (r.get('value') or {}).get('items') or []
    return (w.get('value') or {}).get('success') is True and items == [{'category': '식비', 'budget': 300000}], f"items={items}"


def t16():
    """결제수단별 예산(원장) 대비 9월 사용액 — 넘은 수단만 초과액과 함께."""
    r = ex(f'$예산 = [self:ledger]{{op:"select", path:"{LEDGER}", target:"budgets"}}\n'
           f'$쓴돈 = {Q_SEP} >> [table:groupby]{{by:"source", agg:{{사용:["sum","amount"]}}}}\n'
           '$쓴 = $쓴돈.items >> [table:compute]{set:($r)=>{category:$r.source}}\n'
           '$j = [table:join]{left:$쓴, right:$예산.items, on:"category"}\n'
           'return $j.items >> [table:compute]{set:($r)=>{초과:$r.사용 - $r.budget}} >> [table:filter]{where:($r)=>$r.초과 > 0}'
           ' >> [table:select]{columns:["source","사용","budget","초과"]}')
    v = r.get('value') or []
    return [x.get('source') for x in v] == ['하나카드'], f"value={v} error={r.get('error')}"


def t17():
    """분류가 비어 있는 결제들을 AI 로 분류해 분류별 합계를 내고, 분류 예산을 넘은 것만."""
    r = ex(f'$t = {Q_SEP}\n'
           '$행 = $t.items >> [table:filter]{where:($r)=>$r.amount > 0} >> [table:select]{columns:["counterparty","summary","amount"]}\n'
           '$판 = $행 >> [table:judge]{instruction:"이 결제의 소비 분류는?", type:"choice", criteria:'
           '{식비:"식당·음식점·배달", 카페간식:"카페·빵집·과일·편의점 간식", 통신구독:"통신요금·구독·앱스토어·클라우드", '
           '의료:"병원·약국", 기타:"그 밖이나 판단 불가"}}\n'
           '$g = $판.items >> [table:compute]{set:($r)=>{category:get($r,"judgment_result_value","미판정")}}'
           ' >> [table:groupby]{by:"category", agg:{사용:["sum","amount"]}}\n'
           f'$예산 = [self:ledger]{{op:"select", path:"{LEDGER}", target:"budgets"}}\n'
           '$j = [table:join]{left:$g.items, right:$예산.items, on:"category"}\n'
           'return {분류:$g.items, 초과:$j.items >> [table:filter]{where:($r)=>$r.사용 > $r.budget}}')
    v = r.get('value') or {}
    cats = [x.get('category') for x in v.get('분류') or []]
    return r.get('success') is True and len([c for c in cats if c not in (None, '미판정')]) >= 2, \
        f"분류={v.get('분류')} 초과={v.get('초과')} error={r.get('error')} issues={codes(r)}"


def t18():
    """9월 취소·환불 건마다 원래 결제를 짝지어 보여줘."""
    r = ex(f'$t = {Q_SEP}\n'
           '$neg = $t.items >> [table:filter]{where:($r)=>$r.amount < 0} >> [table:compute]{set:($r)=>{금액:abs($r.amount)}}\n'
           '$pos = $t.items >> [table:filter]{where:($r)=>$r.amount > 0} >> [table:compute]{set:($r)=>{금액:$r.amount}}\n'
           '$j = [table:join]{left:$neg, right:$pos, on:"금액", how:"left"}\n'
           'return $j.items >> [table:select]{columns:["date","금액","date_2","record_id_2"]}')
    v = r.get('value') or []
    return bool(v) and all(x.get('record_id_2') for x in v), f"value={v}"


def t19():
    """새 결제가 들어오면 알려줄 감시 — 첫 실행은 기준선, 두 번째는 새 것 0건(검침 스트림 스크래치)."""
    code = f'return {Q_SEP} >> [table:since]{{key:"IT72_지출감시", by:"record_id"}}'
    a, b = ex(code), ex(code)
    va, vb = a.get('value') or {}, b.get('value') or {}
    return (a.get('success') and b.get('success') and va.get('items') == [] and vb.get('items') == []), \
        f"first={ {k: va.get(k) for k in ('count', 'note', 'message')} } second={ {k: vb.get(k) for k in ('count', 'note', 'message')} }"


def t20():
    """매달 1일 아침 9시에 전월 지출 요약을 알림으로(예약 check만)."""
    r = ex('[self:manage_events]{op:"create", title:"IT72_월간지출보고", date:"2026-10-01", time:"09:00", repeat:"monthly",'
           ' do:"[self:finance]{op:\\"query\\", query_type:\\"summary\\"} >> [self:notify_user]{message:\\"지출 요약\\"}"}',
           check=True)
    return r.get('status') in ('valid', 'incomplete') and not codes(r), f"status={r.get('status')} issues={codes(r)}"


def t21():
    """지출 기록이 없는 달(1월)도 예산 판정이 멈추지 않고 '지출 없음'을 말한다."""
    r = ex('$s = [self:finance]{op:"query", query_type:"지출", month:"2026-01"} >> [table:reduce]{init:0, step:"acc + amount"}\n'
           '[if: $s.value == 0] { return "지출 없음" } [else] { return f"${$s.value}원" }')
    return r.get('value') == '지출 없음', f"value={r.get('value')} error={r.get('error')}"


def t22():
    """월말 결산(9월 지출·수입·순액)을 결산 원장에 적고(12개월 롤링, 스크래치) 되읽는다."""
    w = ex('$e = [self:finance]{op:"query", query_type:"지출", month:"2026-09"} >> [table:reduce]{init:0, step:"acc + amount"}\n'
           '$in = [self:finance]{op:"query", query_type:"수입", month:"2026-09"} >> [table:reduce]{init:0, step:"acc + amount"}\n'
           f'[self:ledger]{{op:"upsert", path:"{CLOSING}", target:"months", key:"month",'
           ' item:{month:"2026-09", 지출:$e.value, 수입:$in.value, 순액:$in.value - $e.value}, max_items:12}')
    r = ex(f'return [self:ledger]{{op:"select", path:"{CLOSING}", target:"months", where:{{month:"2026-09"}}}}')
    items = (r.get('value') or {}).get('items') or []
    want = month_sum('2026-09', 'income') - month_sum('2026-09')
    return w.get('success') is True and len(items) == 1 and items[0].get('순액') == want, f"items={items} write_err={w.get('error')}"


def t23():
    """이번 달 요약에서 상위 가맹점을 금액 큰 순으로 — 요약 행에 숫자 금액이 있어야 한다."""
    r = ex('$s = [self:finance]{op:"query", query_type:"summary", month:"2026-09"}\n'
           'return $s.items >> [table:sort]{by:"amount", descending:true} >> [table:take]{n:3}')
    return r.get('success') is True, f"error={r.get('error')} warnings={[w.get('message') for w in r.get('warnings') or []]}"


def t24():
    """9월 실제 소비 합계 — 카드 대금 출금(이미 쓴 카드값의 청구 결제)이 지출에 또 들어가면 안 된다."""
    r = ex(f'$t = {Q_SEP}\n'
           'return $t.items >> [table:filter]{where:($r)=>$r.amount > 300000}'
           ' >> [table:select]{columns:["record_id","date","counterparty","amount","source","summary"]}')
    v = r.get('value') or []
    frag = [x for x in v if (x.get('counterparty') or '').strip() in ('입니다.', '이 출금되었습니다.')]
    return not frag, f"large={v}"


def t25():
    """교재(코퍼스 4787) '이번 달 지출 카테고리별 합계' 원문을 현재 문법으로 — 거절이면 고칠 방향을 말해야 한다."""
    r = ex('[self:finance]{op: "query", query_type: "지출", days: 30} >> [table:groupby]{by: "category", agg: {합계: ["sum", "amount"]}}'
           ' >> [table:sort]{by: "합계", desc: true}', check=True)
    t = issues_text(r)
    return r.get('status') in ('valid', 'incomplete') or ('descending' in t and '.items' in t), f"status={r.get('status')} issues={t}"


TASKS = [globals()[f't{i:02d}'] for i in range(1, 26)]


def cleanup():
    for path in (BASE / 'outputs').glob('IT72_*'):
        path.unlink()
    con = sqlite3.connect(SINCE_DB)
    con.execute("delete from since_seen where stream like 'IT72_%'")
    # 75회차 B75-6 수리 뒤 빈 첫 관측도 초기화 표지(since_streams)를 남긴다 — 표지까지 지워야 다음 탐침이 첫 검침이다.
    con.execute("delete from since_streams where stream like 'IT72_%'")
    con.commit()
    con.close()


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
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:300])
    cleanup()
    passed = sum(r['ok'] for r in rows)
    print(f'{passed}/{len(rows)}')
    (HERE / f'{phase}.json').write_text(json.dumps({'passed': passed, 'total': len(rows), 'rows': rows, 'log': LOG},
                                                   ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
