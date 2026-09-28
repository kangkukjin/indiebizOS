"""73회차: 문서·표·차트 산출 — 조회·집계 결과를 사람이 볼 산출물로 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 table:chart·document·spreadsheet·structure·rename·flatten,
self:sheet·document·output·slide·deck 을 사용자 도메인(가계부 월간 보고·강의 성적표/출석·
가족신문·부동산 메모·투자 보고서) 위에서 조합한다.
라이브 탐침 = 모델 경로(agent_id·task_id IT73_*). 모든 요청 edition 2·project_id 컨텐츠·origin training.
★사용자 금융 원장은 읽기만(query). 산출 파일은 outputs/IT73_* 에만 쓰고 앞뒤로 지운다.
★발신·표시(self:output·others:publish)·슬라이드/덱(사용자 강의 저장소에 쓰는 것)은 check 만.
★시각 산출물은 탐침이 파일 존재·내용 기계 대조까지만 한다 — 그림의 제목·축·값·한글은 훈련자가
  직접 열어 본 판정을 보고서에 적는다(탐침 PASS 는 "파일이 생겼다"보다 좁은 기계 대조일 뿐).
사용: .venv/bin/python probe.py before|after
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
OUT = BASE / 'outputs'
PROJ_OUT = BASE / 'projects/컨텐츠/outputs'
FIN_DB = BASE / 'data/finance/finance_records.db'
AGENT = {'agent_id': 'IT73_probe', 'task_id': 'IT73_task'}
W = '~workspace/outputs/'
LOG = []
PY = str(BASE / '.venv/bin/python')


def post(route, payload):
    proc = subprocess.run(['curl', '-sS', '--max-time', '240', f'http://127.0.0.1:8765/ibl/{route}',
                           '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                          input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠',
                   origin='training', **AGENT, **extra)
    response = post('execute', payload)
    slim = {k: v for k, v in response.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}
    val = slim.get('value')
    if isinstance(val, dict) and isinstance(val.get('html'), str):   # 응답 원장 비대 방지(HTML 본문은 파일에 있음)
        slim['value'] = {**val, 'html': f"<{len(val['html'])} chars>"}
    LOG.append({'request': payload, 'response': slim})
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


def pyrun(src):
    """스크래치 산출물 되읽기(python-docx·pptx·fitz·openpyxl) — 탐침 자신의 파일만 읽는다."""
    p = subprocess.run([PY, '-c', src], text=True, capture_output=True, timeout=120)
    line = [x for x in p.stdout.splitlines() if x.startswith('{') or x.startswith('[')]
    return json.loads(line[-1]) if line else {'stderr': p.stderr[-400:]}


def png_ok(path):
    p = Path(path or '')
    return p.is_file() and p.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n' and p.stat().st_size > 5000


Q_SEP = '[self:finance]{op:"query", query_type:"지출", month:"2026-09"}'
SRC_SUMS = f'$t = {Q_SEP}\n$g = $t.items >> [table:groupby]{{by:"source", agg:{{합계:["sum","amount"]}}}}\n'


def by_source():
    return dict(db("select source, sum(amount) from transactions where deleted_at is null and tx_type='expense' "
                   "and occurred_at like '2026-09%' group by source"))


def t01():
    """9월 결제수단별 지출을 막대그래프로 — 교재·코퍼스(4789·4110)의 파이프 형태 `… >> [table:chart]`."""
    r = ex(SRC_SUMS + f'return $g.items >> [table:chart]{{chart_type:"bar", title:"9월 결제수단별 지출", path:"{W}IT73_t01.png"}}')
    return r.get('success') is True and png_ok(OUT / 'IT73_t01.png'), f"status={r.get('status')} issues={issues_text(r)}"


def t02():
    """같은 막대그래프를 표형 table 인자로 — 값·라벨이 원장 합계와 같아야 한다(그림은 훈련자가 직접 확인)."""
    r = ex(SRC_SUMS + '$rows = $g.items >> [table:each]{ [$it.source, $it.합계] }\n'
           f'$c = [table:chart]{{chart_type:"bar", title:"9월 결제수단별 지출", table:{{columns:["결제수단","합계"], rows:$rows}}, path:"{W}IT73_t02.png"}}\n'
           'return {chart:$c, rows:$rows}')
    v = r.get('value') or {}
    got = {row[0]: row[1] for row in v.get('rows') or []}
    path = ((v.get('chart') or {}).get('data') or {}).get('path')
    return png_ok(path) and got == by_source(), f"path={path} rows={got} db={by_source()}"


def t03():
    """최근 석 달 월별 지출·수입을 두 선으로 — 한 차트에 두 시리즈·범례(그림 확인)."""
    r = ex('$월들 = ["2026-07","2026-08","2026-09"]\n'
           '$rows = $월들 >> [table:each]{\n'
           '  $e = [self:finance]{op:"query", query_type:"지출", month:$it} >> [table:reduce]{init:0, step:"acc + amount"}\n'
           '  $n = [self:finance]{op:"query", query_type:"수입", month:$it} >> [table:reduce]{init:0, step:"acc + amount"}\n'
           '  [$it, $e.value, $n.value]\n}\n'
           f'$c = [table:chart]{{chart_type:"line", title:"월별 지출·수입", table:{{columns:["월","지출","수입"], rows:$rows}}, path:"{W}IT73_t03.png"}}\n'
           'return {chart:$c, rows:$rows}')
    v = r.get('value') or {}
    path = ((v.get('chart') or {}).get('data') or {}).get('path')
    summ = (v.get('chart') or {}).get('summary') or ''
    return png_ok(path) and '2개 시리즈' in summ, f"rows={v.get('rows')} summary={summ[:60]!r} error={r.get('error')}"


def t04():
    """가맹점별 금액 막대 — 선언된 x·y 인자로 어느 열을 쓸지 지정한다(원 행 그대로)."""
    r = ex(f'$t = {Q_SEP}\n'
           f'return [table:chart]{{chart_type:"bar", title:"가맹점별 9월 지출", data:$t.items, x:"counterparty", y:"amount", path:"{W}IT73_t04.png"}}')
    v = r.get('value') or {}
    summ = v.get('summary') or ''
    # 정답: 한 시리즈(amount), 라벨=가맹점. x·y 를 무시하면 첫 열이 라벨·나머지 전부가 시리즈가 된다.
    import re
    m = re.search(r'(\d+)개 시리즈', summ)
    return r.get('success') is True and m and m.group(1) == '1', f"summary={summ[:80]!r}"


def t05():
    """9월 가계부 월간 보고서(HTML) — 합계 문장·큰 지출 5건 표·메모 목록."""
    r = ex(f'$t = {Q_SEP}\n'
           '$s = $t.items >> [table:reduce]{init:0, step:"acc + amount"}\n'
           '$top = $t.items >> [table:sort]{by:"amount", descending:true} >> [table:take]{n:5}\n'
           '$rows = $top >> [table:each]{ [$it.date, $it.counterparty, $it.amount] }\n'
           '$blocks = [{type:"heading", level:2, text:"요약"}, {type:"paragraph", text:f"9월 지출 합계는 ${$s.value}원입니다."},'
           ' {type:"heading", level:2, text:"큰 지출 5건"}, {type:"table", columns:["날짜","가맹점","금액"], rows:$rows},'
           ' {type:"list", items:["카드 대금 출금 행 확인 필요", "분류 미기재 29건"]}]\n'
           f'return [table:document]{{title:"2026년 9월 가계부", meta:"결제 알림 수거분 기준", blocks:$blocks, filename:"{W}IT73_t05"}}')
    v = r.get('value') or {}
    html = Path(v.get('path') or '/nonexistent').read_text() if v.get('path') else ''
    total = db("select sum(amount) from transactions where deleted_at is null and tx_type='expense' and occurred_at like '2026-09%'")[0][0]
    want = f'합계는 {int(total)}원'
    ok = want in html and html.count('<tr>') == 6 and '결제 알림 수거분 기준' in html
    return ok, f"path={v.get('path')} rows_tr={html.count('<tr>')} total_in={want in html} meta_in={'결제 알림 수거분 기준' in html}"


def t06():
    """보고서를 PDF로 — 막대그래프를 그림으로 넣고, 만든 PDF 를 되읽어 제목·그림을 확인."""
    r = ex(SRC_SUMS + '$rows = $g.items >> [table:each]{ [$it.source, $it.합계] }\n'
           f'$c = [table:chart]{{chart_type:"bar", title:"결제수단별", table:{{columns:["결제수단","합계"], rows:$rows}}, path:"{W}IT73_t06.png"}}\n'
           '$d = [table:document]{title:"9월 가계부 보고서", format:"pdf", blocks:[{type:"paragraph", text:"결제수단별 지출은 아래와 같다."},'
           f' {{type:"image", src:$c.data.path, caption:"그림 1. 결제수단별 지출"}}], filename:"{W}IT73_t06_report"}}\n'
           '$back = [self:read]{path:$d.path}\n'
           'return {doc:$d, text:$back.text}')
    v = r.get('value') or {}
    path = (v.get('doc') or {}).get('path')
    info = pyrun(f"import fitz,json;d=fitz.open({path!r});print(json.dumps({{'pages':len(d),'images':[[i[2],i[3]] for p in d for i in p.get_images()],'text':''.join(p.get_text() for p in d)[:300]}},ensure_ascii=False))") if path else {}
    # 그림이 실렸는지는 개수가 아니라 크기로 본다 — 깨진 그림 아이콘도 PDF 안의 그림 1개로 세어진다(훈련자 육안 확인).
    ok = bool(path) and any(w >= 300 for w, h in info.get('images') or []) and '9월 가계부 보고서' in (info.get('text') or '')
    return ok, f"path={path} pdf={info} read_text={str(v.get('text'))[:80]!r} error={r.get('error')}"


def t07():
    """차트 두 장을 한 문서에 그림으로 — 교재 as:"images" 형태(차트 결과 행을 그대로)."""
    base = (SRC_SUMS + '$rows = $g.items >> [table:each]{ [$it.source, $it.합계] }\n'
            f'$c1 = [table:chart]{{chart_type:"bar", title:"막대", table:{{columns:["결제수단","합계"], rows:$rows}}, path:"{W}IT73_t07a.png"}}\n'
            f'$c2 = [table:chart]{{chart_type:"pie", title:"비율", table:{{columns:["결제수단","합계"], rows:$rows}}, path:"{W}IT73_t07b.png"}}\n')
    r = ex(base + f'return [table:document]{{title:"결제수단 차트", items:[$c1, $c2], as:"images", filename:"{W}IT73_t07"}}')
    r2 = ex(base + '$행 = [$c1, $c2] >> [table:compute]{set:($r)=>{path:$r.data.path, caption:$r.summary}}\n'
            f'return [table:document]{{title:"결제수단 차트", items:$행, as:"images", src_field:"path", caption_field:"caption", filename:"{W}IT73_t07w"}}')
    return r.get('success') is True, f"direct_error={r.get('error')} | workaround_success={r2.get('success')} path={(r2.get('value') or {}).get('path')}"


def t08():
    """5만원 넘는 9월 지출만 엑셀로 — 코퍼스 4790 의 현재 문법판(파이프·items 인자 두 형태, check)."""
    r = ex(f'$t = {Q_SEP}\n$t.items >> [table:filter]{{where:($r)=>$r.amount > 50000}} >> [table:spreadsheet]{{path:"{W}IT73_t08.xlsx"}}', check=True)
    r2 = ex(f'$t = {Q_SEP}\n[table:spreadsheet]{{path:"{W}IT73_t08.xlsx", items:$t.items >> [table:filter]{{where:($r)=>$r.amount > 50000}}}}', check=True)
    ok = all(x.get('status') in ('valid', 'incomplete') and not codes(x) for x in (r, r2))
    return ok, f"pipe={r.get('status')} {codes(r)} | items_arg={r2.get('status')} {codes(r2)}"


def t09():
    """8월·9월 지출을 월별 시트로 한 엑셀에 — sheets:{8월:…, 9월:…} 에 조회 행을 그대로."""
    r = ex('$a = [self:finance]{op:"query", query_type:"지출", month:"2026-08"}\n'
           f'$b = {Q_SEP}\n'
           f'return [table:spreadsheet]{{path:"{W}IT73_t09.xlsx", sheets:{{"8월":$a.items, "9월":$b.items}}}}')
    info = pyrun("import openpyxl,json;wb=openpyxl.load_workbook(%r);print(json.dumps({ws.title:[ws.max_column, str(ws['A1'].value)[:70]] for ws in wb},ensure_ascii=False))"
                 % str(OUT / 'IT73_t09.xlsx')) if (OUT / 'IT73_t09.xlsx').exists() else {}
    stringified = any(str(v[1]).startswith('{') for v in info.values()) if isinstance(info, dict) else False
    ok = r.get('success') is not True or not stringified
    return ok, f"success={r.get('success')} sheets={info} value={json.dumps(r.get('value'), ensure_ascii=False)[:120]}"


GRADES = ('$성적 = [{이름:"김민수", 중간:78.5, 기말:88, 출석:15},{이름:"이서연", 중간:92, 기말:95.5, 출석:16},'
          '{이름:"박지훈", 중간:65, 기말:70.25, 출석:12},{이름:"정하늘", 중간:88, 기말:84, 출석:16}]\n'
          '$점 = $성적 >> [table:compute]{set:($r)=>{총점:$r.중간*0.4 + $r.기말*0.6}}\n'
          '$등 = $점 >> [table:each]{\n'
          '  [if: $it.총점 >= 90] { return {**$it, 등급:"A"} }\n'
          '  [if: $it.총점 >= 80] { return {**$it, 등급:"B"} }\n'
          '  return {**$it, 등급:"C"}\n}\n'
          '$표 = $등 >> [table:sort]{by:"총점", descending:true}\n')


def t10():
    """강의 성적표 — 총점·등급을 계산해 총점 순 엑셀로 만들고 되읽어 숫자로 남았는지 확인."""
    r = ex(GRADES + '$rows = $표 >> [table:each]{ [$it.이름, $it.중간, $it.기말, $it.출석, $it.총점, $it.등급] }\n'
           f'$x = [table:spreadsheet]{{path:"{W}IT73_grade.xlsx", headers:["이름","중간","기말","출석","총점","등급"], rows:$rows, sheet_name:"성적"}}\n'
           '$back = [self:read]{path:$x.path}\n'
           'return {x:$x, rows:$back.data.table.rows}')
    rows = (r.get('value') or {}).get('rows') or []
    ok = [x[0] for x in rows] == ['이서연', '정하늘', '김민수', '박지훈'] and rows[0][4] == 94.1 and rows[0][5] == 'A' \
        and all(isinstance(x[4], (int, float)) for x in rows)
    return ok, f"rows={rows} error={r.get('error')}"


def t11():
    """성적표에서 B등급 학생만 찾기 — 방금 만든 파일을 만든 이름(~workspace/…) 그대로 self:sheet 로.

    같은 토큰 경로를 다른 읽기 표면에도 넣어 본다(되읽기 census)."""
    r = ex(f'return [self:sheet]{{op:"find", path:"{W}IT73_grade.xlsx", where:{{등급:"B"}}}}')
    r_abs = ex(f'return [self:sheet]{{op:"find", path:"{OUT}/IT73_grade.xlsx", where:{{등급:"B"}}}}')
    names = [x.get('이름') for x in ((r.get('value') or {}).get('items') or [])]
    census = {}
    for key, code in (('read_xlsx', f'[self:read]{{path:"{W}IT73_grade.xlsx"}}'),
                      ('read_pdf', f'[self:read]{{path:"{W}IT73_t06_report.pdf"}}'),
                      ('read_html', f'[self:read]{{path:"{W}IT73_t05.html"}}'),
                      ('sheet_range', f'[self:sheet]{{op:"range", path:"{W}IT73_grade.xlsx", range:"A1:B2"}}')):
        rr = ex(code)
        census[key] = 'ok' if rr.get('success') else ('not_found' if '찾을 수 없' in (rr.get('error') or '') else (rr.get('error') or '')[:60])
    abs_names = [x.get('이름') for x in ((r_abs.get('value') or {}).get('items') or [])]
    return sorted(names) == ['김민수', '정하늘'], f"token_error={(r.get('error') or '')[:110]} | abs={abs_names} | census={census}"


def t12():
    """전학생 추가(수식 총점)와 박지훈 출석 정정 — self:sheet append·update 후 되읽기."""
    p = f'{OUT}/IT73_grade.xlsx'
    r = ex(f'$ap = [self:sheet]{{op:"append", path:"{p}", items:[{{이름:"최유진", 중간:81, 기말:79.5, 출석:14, 총점:"=B6*0.4+C6*0.6", 등급:"C"}}]}}\n'
           f'$up = [self:sheet]{{op:"update", path:"{p}", where:{{이름:"박지훈"}}, set:{{출석:13}}}}\n'
           f'$all = [self:sheet]{{op:"find", path:"{p}"}}\n'
           'return {ap:$ap, up:$up, all:$all.items}')
    rows = (r.get('value') or {}).get('all') or []
    park = [x for x in rows if x.get('이름') == '박지훈']
    ok = len(rows) == 5 and park and park[0].get('출석') == 13 and rows[-1].get('이름') == '최유진'
    return ok, f"n={len(rows)} park={park} last={rows[-1] if rows else None} error={r.get('error')}"


def t13():
    """등급 분포 막대그래프 — groupby 결과를 표형으로 넘긴다(그림 확인)."""
    r = ex(GRADES + '$g = $표 >> [table:groupby]{by:"등급", agg:{인원:["count"]}}\n'
           '$rows = $g.items >> [table:sort]{by:"등급"} >> [table:each]{ [$it.등급, $it.인원] }\n'
           f'$c = [table:chart]{{chart_type:"bar", title:"AI 개론 등급 분포", table:{{columns:["등급","인원"], rows:$rows}}, path:"{W}IT73_t13.png"}}\n'
           'return {c:$c, rows:$rows}')
    v = r.get('value') or {}
    path = ((v.get('c') or {}).get('data') or {}).get('path')
    return png_ok(path) and v.get('rows') == [['A', 1], ['B', 2], ['C', 1]], f"rows={v.get('rows')} path={path}"


def t14():
    """이번 달 차트가 비었을 때 — 지출 없는 달(1월) 차트는 0행이라고 말해야 한다."""
    r = ex('$t = [self:finance]{op:"query", query_type:"지출", month:"2026-01"}\n'
           '$rows = $t.items >> [table:each]{ [$it.date, $it.amount] }\n'
           f'return [table:chart]{{chart_type:"line", title:"1월 지출", table:{{columns:["날짜","금액"], rows:$rows}}, path:"{W}IT73_t14.png"}}')
    err = r.get('error') or json.dumps(r.get('value'), ensure_ascii=False)
    return (r.get('success') is not True and '0행' in err) and not (OUT / 'IT73_t14.png').exists(), f"success={r.get('success')} msg={err[:120]}"


def t15():
    """출석 요약 워드 문서 — 부제(학기·기준 주차)까지 들어가야 한다. 만든 뒤 self:document 로 되읽기."""
    r = ex('$출석 = [{이름:"김민수", 출석:15, 결석:1},{이름:"이서연", 출석:16, 결석:0},{이름:"박지훈", 출석:12, 결석:4}]\n'
           '$rows = $출석 >> [table:each]{ [$it.이름, $it.출석, $it.결석] }\n'
           '$위험 = $출석 >> [table:filter]{where:($r)=>$r.결석 >= 3} >> [table:each]{ $it.이름 }\n'
           f'$d = [table:document]{{title:"AI 개론 출석 요약", meta:"2026년 2학기 · 16주차 기준", format:"docx", filename:"{W}IT73_t15",'
           ' blocks:[{type:"heading", level:2, text:"요약"}, {type:"paragraph", text:f\'결석 3회 이상: ${join(", ", $위험)}\'},'
           ' {type:"table", columns:["이름","출석","결석"], rows:$rows}]}\n'
           '$insp = [self:document]{op:"inspect", path:$d.path}\n'
           'return $insp.items >> [table:each]{ $it.text }')
    texts = r.get('value') or []
    return any('16주차' in (t or '') for t in texts) and '결석 3회 이상: 박지훈' in texts, f"texts={texts[:5]} error={r.get('error')}"


def t16():
    """출석 문서의 문구를 변경 추적으로 고쳐 새 파일에 — 해시 조회 → edit → 새 파일 되읽기."""
    r = ex(f'$insp = [self:document]{{op:"inspect", path:"{OUT}/IT73_t15.docx"}}\n'
           '$p = $insp.items >> [table:filter]{where:($r)=>contains($r.text, "결석 3회")} >> [table:take]{n:1}\n'
           f'$e = [self:document]{{op:"edit", path:"{OUT}/IT73_t15.docx", expected_sha256:$insp.sha256, output:"{OUT}/IT73_t16.docx",'
           ' edits:[{block_id:$p[0].block_id, old_string:"결석 3회 이상", new_string:"면담 대상(결석 3회 이상)", comment:"면담 일정 추가"}]}\n'
           f'$back = [self:read]{{path:"{OUT}/IT73_t16.docx"}}\n'
           'return {e:$e, text:$back.text}')
    v = r.get('value') or {}
    tok = {k: ('ok' if x.get('success') else (x.get('error') or '')[:70]) for k, x in (
        ('read_docx', ex(f'[self:read]{{path:"{W}IT73_t16.docx"}}')),
        ('document_inspect', ex(f'[self:document]{{op:"inspect", path:"{W}IT73_t16.docx"}}')))}
    return '면담 대상' in (v.get('text') or ''), f"text={str(v.get('text'))[:120]!r} error={r.get('error')} | token_reads={tok}"


def t17():
    """가족신문 10월호 — 기사 카드 3건을 신문 테마 그림(PNG)으로(그림 확인)."""
    r = ex('$기사 = [{title:"할머니 칠순 잔치", meta:"가족 행사 · 10월 3일", summary:"오송 한정식집에서 온 가족이 모였다."},'
           '{title:"막내 첫 걸음마", meta:"육아 · 9월 20일", summary:"거실에서 다섯 걸음을 걸었다."},'
           '{title:"가을 캠핑 계획", meta:"여행 · 10월", summary:"속리산 자연휴양림 예약 완료."}]\n'
           f'return [table:document]{{title:"우리집 신문 10월호", meta:"2026년 10월 · 제12호", theme:"newspaper", items:$기사, format:"png", filename:"{W}IT73_t17"}}')
    path = (r.get('value') or {}).get('path')
    return png_ok(path), f"path={path} error={r.get('error')}"


def t18():
    """부동산 매물 메모 — 영문 키를 한글 열로 바꿔 문서 표와 엑셀로(단지별 평균 호가 포함)."""
    r = ex('$매물 = [{apt:"가경자이", area:84, price:52000, floor:12},{apt:"가경자이", area:59, price:39000, floor:5},'
           '{apt:"복대두산위브", area:84, price:47000, floor:20}]\n'
           '$한 = $매물 >> [table:rename]{map:{apt:"단지", area:"전용면적", price:"호가_만원", floor:"층"}}\n'
           '$평균 = $한.items >> [table:groupby]{by:"단지", agg:{평균호가:["avg","호가_만원"], 건수:["count"]}}\n'
           '$평균2 = $평균 >> [table:rename]{map:{평균호가:"평균호가_만원"}}\n'
           f'$d = [table:document]{{title:"청주 흥덕 매물 메모", items:$한.items, filename:"{W}IT73_t18"}}\n'
           '$rows = $평균2.items >> [table:each]{ [$it.단지, $it.평균호가_만원, $it.건수] }\n'
           f'$x = [table:spreadsheet]{{path:"{W}IT73_t18.xlsx", headers:["단지","평균호가_만원","건수"], rows:$rows}}\n'
           'return {d:$d.path, x:$x.path, rows:$rows}')
    v = r.get('value') or {}
    html = Path(v['d']).read_text() if v.get('d') else ''
    ok = '<th>단지</th>' in html and '<th>호가_만원</th>' in html and v.get('rows') == [['가경자이', 45500, 2], ['복대두산위브', 47000, 1]]
    return ok, f"rows={v.get('rows')} th_ok={'<th>단지</th>' in html} error={r.get('error')}"


def t19():
    """강의별 수강생 명단(중첩)을 한 줄에 한 명씩 펼쳐 엑셀로."""
    r = ex('$반 = [{강의:"AI 개론", 학생:[{이름:"김민수"},{이름:"이서연"}]},{강의:"데이터 윤리", 학생:[{이름:"박지훈"}]},{강의:"특강", 학생:[]}]\n'
           '$펼 = $반 >> [table:flatten]{field:"학생", keep:["강의"]}\n'
           '$rows = $펼.items >> [table:each]{ [$it.강의, $it.이름] }\n'
           f'$x = [table:spreadsheet]{{path:"{W}IT73_t19.xlsx", headers:["강의","이름"], rows:$rows}}\n'
           'return {rows:$rows, x:$x.path, dropped:get($펼,"rows_dropped",null)}')
    v = r.get('value') or {}
    return v.get('rows') == [['AI 개론', '김민수'], ['AI 개론', '이서연'], ['데이터 윤리', '박지훈']], f"value={v} error={r.get('error')}"


MEMO = ('오늘 AI 개론 7주차. 주제는 트랜스포머의 어텐션. 출석 28명 중 25명. 질문이 많았던 부분: 멀티헤드가 왜 필요한가, 위치 인코딩. '
        '다음 주 중간고사 범위는 1~7주차. 과제 2는 10월 10일 마감. 박지훈 학생 3회 결석이라 면담 필요.')


def t20():
    """강의 메모를 강의 일지 문서로 — structure 로 정리해 HTML 로(교재의 파이프 형태는 check 로 함께)."""
    pipe = ex(f'"{MEMO}" >> [table:structure]{{instruction:"강의 일지"}} >> [table:document]{{format:"html"}}', check=True)
    r = ex(f'$s = [table:structure]{{content:"{MEMO}", instruction:"강의 일지: 요약·출석·다음 할 일 3섹션"}}\n'
           f'return [table:document]{{title:$s.title, blocks:$s.blocks, filename:"{W}IT73_t20"}}')
    v = r.get('value') or {}
    html = Path(v['path']).read_text() if v.get('path') else ''
    ok = r.get('success') is True and '25' in html and '10월 10일' in html
    return ok, f"pipe_form={pipe.get('status')} {codes(pipe)} | explicit blocks={v.get('blocks')} has_facts={'25' in html and '10월 10일' in html}"


def t21():
    """삼성전자 한 달 주가를 캔들차트로 — 시세 행을 data 로(그림 확인)."""
    r = ex('$h = [sense:stock]{op:"history", ticker:"삼성전자", period:"1mo"}\n'
           f'$c = [table:chart]{{chart_type:"candlestick", title:"삼성전자 최근 1개월", data:$h.items, ma_periods:[5], path:"{W}IT73_t21.png"}}\n'
           'return {c:$c, n:len($h.items), first:$h.items[0], last:$h.items[-1]}')
    v = r.get('value') or {}
    path = ((v.get('c') or {}).get('data') or {}).get('path')
    return png_ok(path), f"n={v.get('n')} first={v.get('first')} last={v.get('last')} summary={((v.get('c') or {}).get('summary') or '')[:60]!r} error={r.get('error')}"


def t22():
    """투자 보고서를 발표용 pptx 로 — 제목·부제·요점·차트 그림. 슬라이드를 되읽어 확인."""
    r = ex('$h = [sense:stock]{op:"history", ticker:"삼성전자", period:"1mo"}\n'
           '$rows = $h.items >> [table:each]{ [$it.date, $it.close] }\n'
           f'$c = [table:chart]{{chart_type:"line", title:"종가 추이", table:{{columns:["날짜","종가"], rows:$rows}}, path:"{W}IT73_t22.png"}}\n'
           '$hi = $h.items >> [table:sort]{by:"close", descending:true} >> [table:take]{n:1}\n'
           f'return [table:document]{{title:"삼성전자 월간 점검", meta:"2026년 9월 · 개인 투자 메모", format:"pptx", filename:"{W}IT73_t22",'
           ' blocks:[{type:"heading", level:2, text:"요점"}, {type:"list", items:[f"최고 종가 ${$hi[0].close}원 (${$hi[0].date})", "분할 매수 유지"]},'
           ' {type:"heading", level:2, text:"종가 추이"}, {type:"image", src:$c.data.path}]}')
    path = (r.get('value') or {}).get('path')
    info = pyrun(f"import pptx,json;p=pptx.Presentation({path!r});print(json.dumps([[s.shapes.title.text if s.shapes.title else None, [sh.shape_type for sh in s.shapes].count(13), ' | '.join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame)[:120]] for s in p.slides],ensure_ascii=False))") if path else []
    alltext = json.dumps(info, ensure_ascii=False)
    ok = bool(path) and '최고 종가' in alltext and any(s[1] >= 1 for s in info if isinstance(s, list)) and '개인 투자 메모' in alltext
    return ok, f"slides={info} error={r.get('error')}"


def t23():
    """보고서를 마크다운으로 받아 블로그 발행·클립보드·화면 표시·슬라이드로(발신·표시·슬라이드는 check)."""
    r = ex(f'$m = [table:document]{{title:"9월 가계부", format:"markdown", filename:"{W}IT73_t23", blocks:[{{type:"paragraph", text:"요약"}}]}}\n'
           'return $m.markdown')
    checks = {}
    for key, code in (('publish', '$m = [table:document]{title:"t", format:"markdown", blocks:[{type:"paragraph", text:"x"}]}\n[others:publish]{content:$m.markdown, title:"9월 가계부"}'),
                      ('clipboard', '[self:output]{op:"clipboard", content:"9월 지출 1,111,527원"}'),
                      ('gui', '[self:output]{op:"gui", content:"<b>9월</b>", format:"html"}'),
                      ('slide', '[self:slide]{op:"create", instruction:"9월 가계부 요약 한 장", render:"html"}'),
                      ('deck', '[self:deck]{op:"export", lecture_id:"IT73_none", format:"pdf"}')):
        rr = ex(code, check=True)
        checks[key] = [rr.get('status'), codes(rr)]
    md = r.get('value') or ''
    ok = isinstance(md, str) and md.startswith('# 9월 가계부') and all(v[0] in ('valid', 'incomplete') and not v[1] for v in checks.values())
    return ok, f"markdown={md[:40]!r} checks={checks}"


def t24():
    """교재대로 쓴 차트 옵션 — 다중 시리즈 series·파이 hole·산점도 trendline(target_description 의 낱말, check)."""
    out = {}
    for key, code in (('series', '[table:chart]{chart_type:"line", title:"t", series:[{name:"a", data:[{x:1,y:2}]}]}'),
                      ('hole', '[table:chart]{chart_type:"pie", title:"t", hole:0.4, data:[{label:"a",value:1}]}'),
                      ('trendline', '[table:chart]{chart_type:"scatter", title:"t", trendline:true, data:[{x:1,y:2}]}'),
                      ('ma', '[table:chart]{chart_type:"candlestick", title:"t", ma:[5], data:[]}')):
        rr = ex(code, check=True)
        out[key] = [rr.get('status'), codes(rr), [i.get('hint') for i in rr.get('issues') or []][:1]]
    return all(v[0] in ('valid', 'incomplete') and not v[1] for v in out.values()), json.dumps(out, ensure_ascii=False)


TASKS = [globals()[f't{i:02d}'] for i in range(1, 25)]


def cleanup():
    for d in (OUT, PROJ_OUT):
        for path in d.glob('IT73_*'):
            if path.is_file():
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
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:400])
    if '--keep' not in sys.argv:
        cleanup()
    passed = sum(r['ok'] for r in rows)
    print(f'{passed}/{len(rows)}')
    (HERE / f'{phase}.json').write_text(json.dumps({'passed': passed, 'total': len(rows), 'rows': rows, 'log': LOG},
                                                   ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
