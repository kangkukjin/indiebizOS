"""78회차: 개인 기록·기억 회상 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 기억·기록 어휘(self:recent_chats·body·forage·folder_note(detail만)·memory·health·record)를
table:filter·sort·groupby·select·compute·dedup·chart·each 와 조합.
도메인: 사용자(물리학박사·뇌과학·AI 저서·강의, 활성 프로젝트 부동산·투자·컨텐츠 등) — 지난 대화 회상, 장소(폴더) 회상,
몸의 변경 이력, 건강·운동 기록과 추세, 기억 검색 결과 표·날짜순, 없는 기억의 정직성, 중복, 기록 수정·삭제, 회상+외부 조회.

모든 요청 edition 2·project_id 컨텐츠·origin training·agent_id IT78_probe·task_id IT78_task.
★개인정보: 포식 기억·대화·심층기억·건강 기록은 읽기만. before.json 에는 원문을 싣지 않는다 — 건수·키·길이·해시·날짜만(mask()).
★쓰기는 IT78_ 스크래치 업무 공간(data/record_spaces/IT78_*)에만, 끝에 삭제. 건강·기억·대화·포식 원장 쓰기 = check 만.
★해마 시딩 0 · 발신 0 · 유료 AI 최소.
사용: .venv/bin/python probe.py baseline | run [tNN ...] | after | raw '<code>' [--check] | desc node:action ...
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
AGENT = {'agent_id': 'IT78_probe', 'task_id': 'IT78_task'}
LOG = []
PULSE = BASE / 'data/world_pulse.db'
SINCE = BASE / 'data/table_since.db'
STORES = {
    'system_ai_memory': (BASE / 'data/system_ai_memory.db', ['conversations', 'messages', 'memories', 'history_checkpoints']),
    'contents_conversations': (BASE / 'projects/컨텐츠/conversations.db', ['messages', 'history_checkpoints']),
    'deep_memory_system_ai': (BASE / 'data/system_ai_state/memory_system_ai.db', ['memories', 'distill_receipts']),
    'deep_memory_contents_agent': (BASE / 'projects/컨텐츠/memory_900b7943.db', ['memories', 'distill_receipts']),
    'deep_memory_contents_sys': (BASE / 'projects/컨텐츠/memory_system_ai.db', ['memories']),
    'forage_memory': (BASE / 'data/forage_memory.db', ['forage_map', 'survey']),
    'health': (BASE / 'data/health/health_records.db', ['persons', 'measurements', 'symptoms', 'medications', 'documents']),
    'ibl_usage': (BASE / 'data/ibl_usage.db', ['ibl_examples']),
}


def post(route, payload=None, method='POST'):
    args = ['curl', '-sS', '--max-time', '280', '-X', method, f'http://127.0.0.1:8765/{route}',
            '-H', 'Content-Type: application/json']
    if payload is not None:
        args += ['--data-binary', '@-']
    proc = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                          text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠', origin='training',
                   **AGENT, **extra)
    response = post('ibl/execute', payload)
    slim = {k: v for k, v in response.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}
    LOG.append({'request': payload, 'response': slim})
    return response


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def err(r):
    e = r.get('error')
    if isinstance(e, dict):
        return json.dumps({k: e.get(k) for k in ('code', 'message', 'hint')}, ensure_ascii=False)[:600]
    if e:
        return str(e)[:600]
    return json.dumps([{k: i.get(k) for k in ('code', 'message')} for i in r.get('issues') or []],
                      ensure_ascii=False)[:600]


def val(r):
    return r.get('value')


def js(x, n=400):
    return json.dumps(x, ensure_ascii=False, default=str)[:n]


def q(db, sql, args=()):
    con = sqlite3.connect(str(db), timeout=10)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def ok_or_err(r, n=500):
    return js(val(r), n) if r.get('success') else f"FAIL {err(r)}"




def h(s):
    return hashlib.sha256(str(s).encode()).hexdigest()[:10]


def shape(x, depth=0):
    """개인 원문 없이 값의 모양만: 키·타입·길이·해시."""
    if isinstance(x, dict):
        if depth > 3:
            return {'_dict_keys': sorted(x)[:30]}
        return {k: shape(v, depth + 1) for k, v in list(x.items())[:40]}
    if isinstance(x, list):
        return {'_list_len': len(x), 'first': shape(x[0], depth + 1) if x else None}
    if isinstance(x, str):
        return f'<str len={len(x)} h={h(x)}>'
    return x


def mask_log():
    for e in LOG:
        r = e['response']
        e['response'] = {k: (shape(v) if k in ('value', 'result', 'partial', 'partial_preview', 'partial_wire', 'data', 'diagnostic', 'error_detail', 'text') else v) for k, v in r.items()}
        e['request'] = {k: (v if k != 'inputs' else shape(v)) for k, v in e['request'].items()}

# ───────────────────────── 과제 ─────────────────────────
# ★반환 detail 은 개인 원문 없이 건수·키·날짜·길이만 담는다(before.json rows 에 그대로 저장됨).

SCRATCH_LEDGER = 'projects/컨텐츠/outputs/IT78_건강원장.json'


def t01():
    """[대화 회상] 지난주에 부동산 에이전트와 무슨 얘기를 했지 — 최근 대화 30건에서 이번 주 것만 날짜·방향·길이 표로."""
    r = ex("""
$c = [self:recent_chats]{project_id:"부동산", limit:30}
$week = $c.data >> [table:filter]{where:($x)=> $x.message_time >= "2026-09-22"}
return {n:len($c.data), week:len($week), rows:($week >> [table:select]{columns:["message_time","from_agent","to_agent","content_len","truncated"]} >> [table:take]{n:5})}
""")
    d = r.get('diagnostic') or {}
    return bool(r.get('success')), (ok_or_err(r, 300) if r.get('success') else
                                    f"FAIL code={d.get('code')} kind={d.get('kind')} has_partial={d.get('has_partial')} truncation={js((d.get('details') or {}).get('truncation'), 200)}")


def t02():
    """[대화 회상 · 우회] 같은 요구를 try/catch 로 — 실패의 partial 에서 이번 주 행을 건지고, 잘린 미리보기 수를 센다."""
    r = ex("""
[try] { $c = [self:recent_chats]{project_id:"부동산", limit:30} } [catch] { $c = $error.partial }
$week = $c.data >> [table:filter]{where:($x)=> $x.message_time >= "2026-09-22"}
$cut = $week >> [table:filter]{where:($x)=> $x.truncated}
$lens = $week >> [table:each]{ $it.content_len }
return {n:len($c.data), week:len($week), cut:len($cut), max_len:max($lens), first:$week[-1].message_time, last:$week[0].message_time, row_keys:keys($c.data[0]), item_keys:keys($c.items[0])}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('week')), (js(v, 600) + f" source_complete={r.get('source_complete')}") if r.get('success') else f"FAIL {err(r)}"


def t03():
    """[대화 회상 · 필터] '지난 7일 중 전세 얘기만' — days·query 를 주면 걸러지는가(선언: params 없음·open_params)."""
    base = """
[try] { $c = [self:recent_chats]{project_id:"부동산", limit:20%s} } [catch] { $c = $error.partial }
$ids = $c.data >> [table:each]{ $it.id }
return {n:len($c.data), ids:$ids}
"""
    a = ex(base % '')
    b = ex(base % ', days:7, query:"전세"')
    c = ex(base % ', agent:"user"')
    ck = ex('return [self:recent_chats]{project_id:"부동산", limit:20, days:7, query:"전세", since:"2026-09-22"}', check=True)
    va, vb, vc = val(a) or {}, val(b) or {}, val(c) or {}
    same = va.get('ids') == vb.get('ids')
    return bool(a.get('success') and not same), (f"plain n={va.get('n')} · days+query n={vb.get('n')} same_ids={same} · agent:'user' n={vc.get('n')} same_as_plain={va.get('ids') == vc.get('ids')} · "
                                               f"check status={ck.get('status')} issues={codes(ck)} warn={[w.get('code') for w in (ck.get('warnings') or [])]}")


def t04():
    """[기억 검색 → 표·날짜순] '부동산' 관련 기억·대화 검색 결과를 출처·화자·날짜 표로, 날짜 역순."""
    r = ex("""
$m = [self:memory]{op:"search", query:"부동산", top_k:10}
$rows = $m.items >> [table:compute]{set:($x)=> {날짜:$x.provenance.recorded_at, 화자:$x.provenance.speaker, 종류:$x.provenance.status, 길이:len($x.summary)}}
$sorted = $rows >> [table:sort]{by:"날짜", descending:true}
$kl = $rows >> [table:each]{$it.종류}
return {count:$m.count, n:len($m.items), clamped:get($m,"clamped",null), msg:get($m,"message",null), kinds:unique($kl), dates:($sorted >> [table:each]{$it.날짜}), lens:($sorted >> [table:each]{$it.길이}), mem_keys:keys($m.memories[0]), trunc_marker:has($m.memories[0],"truncated") or has($m.memories[0],"content_len")}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 900)


def t05():
    """[기억 정직성] 없는 말·두 낱말 질의 — '큐비트뇌파양자구름'은 0건, 'AI 블로그'(두 낱말이 한 대화에 함께 있는 행 15, 붙은 구 0)는?"""
    r = ex("""
$a = [self:memory]{op:"search", query:"큐비트뇌파양자구름", top_k:5}
$b = [self:memory]{op:"search", query:"AI 블로그", top_k:5}
$c1 = [self:memory]{op:"search", query:"AI", top_k:5}
$c2 = [self:memory]{op:"search", query:"블로그", top_k:5}
return {nonsense:$a.count, two_words:$b.count, w1:$c1.count, w2:$c2.count, keys_empty:keys($a)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('nonsense') == 0 and v.get('two_words')), ok_or_err(r, 500) + ' · DB 대조: 두 낱말 동시 포함 15행·붙은 구 0행(컨텐츠 대화)'


def t06():
    """[기억 주인] 처음 보는 에이전트(IT78_probe)가 '내 기억 지도'를 열고 검색하면 — 없다고 말하나, 저장소가 생기나."""
    db = BASE / 'projects/컨텐츠/memory_IT78_probe.db'
    existed_before = db.exists()
    r = ex("""
$map = [self:memory]{op:"recall"}
$s = [self:memory]{op:"search", query:"가족", top_k:5, category:"사용자정보"}
return {map_keys:keys($map), nodes:len(get($map,"nodes",[])), items:len(get($map,"items",[])), msg_len:len(text(get($map,"message",""))), s_count:$s.count, s_keys:keys($s)}
""")
    return bool(r.get('success')), f"{ok_or_err(r, 500)} · memory_IT78_probe.db existed_before_task={existed_before} exists_now={db.exists()} (첫 생성=탐색 중 search, 01:49)"


def t07():
    """[시스템 AI 대화 검색 — 코드 경로 대조] 시스템 AI 의 memory search 대화 가지가 읽는 DB와 실제 대화 DB(읽기 전용 대조)."""
    sys.path.insert(0, str(BASE / 'backend'))
    sys.path.insert(0, str(BASE / 'data/packages/installed/tools/memory'))
    import importlib
    h = importlib.import_module('handler')
    word = '부동산'
    via_handler = h._search_conversations(str(BASE / 'data'), word, limit=5)
    truth = q(BASE / 'data/system_ai_memory.db', 'select count(*) from conversations where content like ?', (f'%{word}%',))[0][0]
    empty = q(BASE / 'data/conversations.db', 'select count(*) from messages')[0][0]
    return (len(via_handler) > 0), f"_search_conversations(data/) → {len(via_handler)}건 · system_ai_memory.db conversations LIKE → {truth}건 · data/conversations.db messages={empty}"


def t08():
    """[장소 회상] '부동산 프로젝트 폴더는 뭐 하던 곳이었지' — 포식 기억에서 그 폴더의 단언을 종류·경로(own/inherit)·신선도로 센다."""
    r = ex("""
$f = [self:forage]{op:"recall", locus:"/Users/kangkukjin/Desktop/AI/indiebizOS/projects/부동산"}
$kinds = $f.map >> [table:groupby]{by:"kind", agg:{n:["count"]}}
$via = $f.map >> [table:groupby]{by:"via", agg:{n:["count"]}}
return {n:$f.map_count, kinds:$kinds.items, via:$via.items, root_missing:$f.root_missing, docs_below:len($f.docs_below), has_doc:$f.doc != null}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 700)


def t09():
    """[장소 회상 · 오타] 없는 폴더(오타) — '기억 없음'이라고 하나, 조상 기억을 제 것처럼 주나."""
    r = ex("""
$f = [self:forage]{op:"recall", locus:"/Users/kangkukjin/Desktop/AI/indiebizOS/projects/부동삼"}
$own = $f.map >> [table:filter]{where:($x)=> $x.via != "inherit"}
return {n:$f.map_count, own:len($own), root_missing:$f.root_missing, doc_is_ancestor:not contains(text($f.doc), "부동삼"), locus:$f.locus}
""")
    v = val(r) or {}
    honest = v.get('root_missing') is True or v.get('n') == 0
    return bool(r.get('success') and honest), ok_or_err(r, 500)


def t10():
    """[장소 찾기 → 지명] '외장하드 영화 폴더' — query 로 후보 장소를 받고 상위 3곳을 locus 로 다시 열어 단언 수를 센다(가이드의 2단계 계약)."""
    r = ex("""
$q = [self:forage]{op:"recall", query:"외장하드 영화"}
$top = $q.places >> [table:take]{n:3}
$opened = $top >> [table:each] {
  $o = [self:forage]{op:"recall", locus:$it.place}
  return {body_name: contains($it.place, ":"), n:$o.map_count}
}
return {places:len($q.places), opened:$opened}
""")
    v = val(r) or {}
    zero = [o for o in (v.get('opened') or []) if not o.get('n')]
    return bool(r.get('success') and v.get('places') and not zero), ok_or_err(r, 600)


def t11():
    """[노트북 포식 기억] 지금 있는 노트북과 포식 기억의 노트북 몸을 대조 — 지운 노트북의 기억이 신선한 것처럼 남는가."""
    r = ex("""
$nb = [self:notebook]{op:"list"}
$names = $nb.items >> [table:each]{ join("", ["notebook:", $it.title]) }
$bodies = ["notebook:AI 동향","notebook:카파시 강의","notebook:블로그항법","notebook:온톨로지 역사","notebook:_프로브"]
$orph = difference($bodies, $names)
$open = $orph >> [table:each] {
  $o = [self:forage]{op:"recall", locus:$it}
  $fr = $o.map >> [table:filter]{where:($x)=> get($x,"freshness","") != ""}
  return {n:$o.map_count, flagged:len($fr), root_missing:$o.root_missing}
}
return {live:len($names), orphan_bodies:len($orph), open:$open}
""")
    v = val(r) or {}
    silent = [o for o in (v.get('open') or []) if o.get('n') and not o.get('flagged') and not o.get('root_missing')]
    return bool(r.get('success') and not silent), ok_or_err(r, 600)


def t12():
    """[책 몸 회상] '내 책 하네스에 대해 기억하는 것' — query 로 book 장소를 받고 locus 로 열기(같은 책이 두 몸?)."""
    r = ex("""
$q = [self:forage]{op:"recall", query:"하네스 책"}
$books = $q.places >> [table:filter]{where:($x)=> contains($x.place, "book:")}
$open = $books >> [table:each] {
  $o = [self:forage]{op:"recall", locus:$it.place}
  return {bracket: contains($it.place, "<"), n:$o.map_count}
}
return {places:len($q.places), book_places:len($books), open:$open}
""")
    v = val(r) or {}
    zero = [o for o in (v.get('open') or []) if not o.get('n')]
    return bool(r.get('success') and v.get('book_places') == 1 and not zero), ok_or_err(r, 600)


def t13():
    """[회상 + 외부] 포식 기억의 내 책 장소 이름으로 도서관(정보나루)에서 그 책을 찾는다 — 몸 이름에서 제목을 떼어 검색."""
    r = ex("""
$q = [self:forage]{op:"recall", query:"하네스 책"}
$books = $q.places >> [table:filter]{where:($x)=> contains($x.place, "book:")}
$found = $books >> [table:each] {
  $title = replace($it.place, "book:", "")
  $b = [sense:book]{title:$title, rows:3}
  return {bracket: contains($title, "<"), n:len($b.items)}
}
return $found
""")
    v = val(r)
    return bool(r.get('success') and v and all(x.get('n') for x in v)), ok_or_err(r, 400)


def t14():
    """[몸 이력] '요즘 뭐 고쳤지' — 이번 주 커밋 중 '수리'가 요지에 있는 것 최근 5개(커밋·시각·파일 수)."""
    r = ex("""
$l = [self:body]{op:"log", days:7, limit:200}
$fix = $l.items >> [table:filter]{where:($x)=> contains($x.요지, "수리")} >> [table:sort]{by:"시각", descending:true}
return {total:$l.total, n:len($l.items), truncated:$l.truncated, fix:len($fix), top:($fix >> [table:select]{columns:["커밋","시각","파일수"]} >> [table:take]{n:5})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('fix')), ok_or_err(r, 700)


def t15():
    """[몸 이력 집계] 최근 3일 파일 변화를 영역별로 세고, 미커밋 파일 수."""
    r = ex("""
$c = [self:body]{days:3, limit:1000}
$g = $c.items >> [table:groupby]{by:"영역", agg:{n:["count"]}}
$u = $c.items >> [table:filter]{where:($x)=> $x.상태 == "미커밋"}
return {n:len($c.items), total:$c.total, truncated:$c.truncated, top:($g.items >> [table:sort]{by:"n", descending:true} >> [table:take]{n:5}), uncommitted:len($u)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 600)


def t16():
    """[몸 파일 일생] 상상훈련 가이드 파일의 일생(최근 5번) + 없는 파일 경로의 정직성."""
    r = ex("""
$f = [self:body]{op:"file", path:"data/guides/imagination_training.md", limit:50}
[try] { $g = [self:body]{op:"file", path:"data/guides/IT78_없는가이드.md"}; $none = {n:len($g.items), text_len:len(text(get($g,"text","")))} } [catch] { $none = {err:$error.code} }
return {n:len($f.items), first:$f.items[-1].시각, last:$f.items[0].시각, none:$none}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 500)


def t17():
    """[실행 궤적] '방금 내가 돌린 것들' — task_id 로 궤적을 열어 사건 종류를 세고, 궤적의 source 칸을 본다(훈련은 training 이어야)."""
    r = ex("""
$t = [self:body]{op:"trajectory", task_id:"IT78_task", limit:200}
$k = $t.items >> [table:groupby]{by:"kind", agg:{n:["count"]}}
$src = $t.items >> [table:each]{ $it.source }
return {n:len($t.items), total:get($t,"total",null), kinds:$k.items, sources:unique($src)}
""")
    v = val(r) or {}
    tr = q(PULSE, "select source, count(*) from trajectory_event where task_id like 'IT7%' group by 1")
    return bool(r.get('success') and v.get('sources') == ['training']), f"{ok_or_err(r, 500)} · DB IT70~78 task 궤적 source={tr}"


def t18():
    """[건강 추세 읽기] 지난 1년 혈압 추세 — 측정 점을 날짜순으로 정렬해 첫·끝·최고 수축기와 변화(건수만 보고)."""
    r = ex("""
$h = [self:health]{op:"query", query_type:"혈압", days:365}
$pts = $h.points >> [table:sort]{by:"date"}
$vals = $pts >> [table:each]{ number($it.value) }
return {keys:keys($h), has_items:has($h,"items"), n:len($pts), table_cols:len($h.table.columns), up:$vals[-1] > $vals[0], max_ge_first: max($vals) >= $vals[0]}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 500)


def t19():
    """[건강 → 차트] 코퍼스 3683 그대로 — 혈압 조회를 차트로(판본 2). 파일이 생기면 회차 끝에 지운다."""
    r = ex("""
return [self:health]{op:"query", query_type:"혈압", days:365} >> [table:chart]{chart_type:"line", title:"IT78 혈압 추이"}
""")
    v = val(r) or {}
    return bool(r.get('success')), (js({k: v.get(k) for k in ('success', 'path', 'file', 'rows', 'points', 'message')} if isinstance(v, dict) else v, 500)
                                    if r.get('success') else f"FAIL {err(r)}")


def t20():
    """[건강 기록 · check] 오늘 혈압 128/85 기록(가이드의 systolic/diastolic 평탄형과 value 문자열형) — 쓰기는 check 만."""
    a = ex('return [self:health]{op:"save", category:"혈압", systolic:128, diastolic:85, person:"IT78_스크래치"}', check=True)
    b = ex('return [self:health]{op:"save", category:"혈압", value:"128/85", person:"IT78_스크래치"}', check=True)
    c = ex('return [self:health]{op:"delete", record_type:"measurement", record_id:1, person:"IT78_스크래치"}', check=True)
    def st(x):
        return f"{x.get('status')} issues={codes(x)} effects={x.get('effects')}"
    return (a.get('status') != 'invalid'), f"systolic형={st(a)} | value형={st(b)} | delete={st(c)}"


def t21():
    """[건강 · 오타 주체 — 사본 재현] 사람 이름을 틀리게 조회하면(읽기) — 스크래치 DB 사본에서 주체 행 증가·응답 문구."""
    import os
    sp = os.environ.get('IT78_SCRATCH')
    if not sp:
        return False, 'IT78_SCRATCH 미설정'
    proc = subprocess.run([str(BASE / '.venv/bin/python'), f'{sp}/health_repro.py', sp], capture_output=True, text=True)
    line = (proc.stdout.strip().splitlines() or ['{}'])[-1]
    d = json.loads(line)
    d['message'] = '<IT78_오타사람>의 최근 365일간 혈압 기록이 없습니다.' if d.get('message') else None
    grew = d.get('persons_after', [0])[0] > d.get('persons_before', [0])[0]
    return (not grew), js(d, 500)


LEDGER_ROWS = [
    {"id": "d1", "date": "2026-09-26", "kind": "혈압", "sys": 131, "dia": 86},
    {"id": "d2", "date": "2026-09-27", "kind": "운동", "minutes": 30, "what": "걷기"},
    {"id": "d3", "date": "2026-09-28", "kind": "혈압", "sys": 128, "dia": 85},
    {"id": "d4", "date": "2026-09-28", "kind": "운동", "minutes": 45, "what": "수영"},
    {"id": "d5", "date": "2026-09-29", "kind": "혈압", "sys": 182, "dia": 85},
]


def t22():
    """[스크래치 원장 · 기록과 추세] 오늘 운동·혈압을 원장(IT78_)에 적고 혈압 추세(최근순)·주간 운동 합계를 본다."""
    r = ex(f"""
$w = [self:ledger]{{op:"append", path:"{SCRATCH_LEDGER}", target:"log", items:$rows, enum_fields:{{kind:["혈압","운동"]}}}}
$bp = [self:ledger]{{op:"select", path:"{SCRATCH_LEDGER}", target:"log", where:{{kind:"혈압"}}}}
$trend = $bp.items >> [table:sort]{{by:"date", descending:true}} >> [table:select]{{columns:["date","sys","dia"]}}
$ex = [self:ledger]{{op:"select", path:"{SCRATCH_LEDGER}", target:"log", where:{{kind:"운동"}}}}
$mins = $ex.items >> [table:each]{{ $it.minutes }}
return {{written:get($w,"count",null), wkeys:keys($w), bp:len($bp.items), trend:$trend, exercise_min:sum($mins)}}
""", inputs={'rows': LEDGER_ROWS})
    v = val(r) or {}
    return bool(r.get('success') and v.get('bp') == 3), ok_or_err(r, 700)


def t23():
    """[스크래치 원장 · 수정과 삭제] 잘못 적은 수축기 182 → 132 로 고치고, 중복으로 적은 d4 운동 행을 지운다."""
    r = ex(f"""
$fix = [self:ledger]{{op:"upsert", path:"{SCRATCH_LEDGER}", target:"log", key:"id", item:{{id:"d5", date:"2026-09-29", kind:"혈압", sys:132, dia:85}}}}
$all = [self:ledger]{{op:"select", path:"{SCRATCH_LEDGER}", target:"log"}}
$keep = $all.items >> [table:filter]{{where:($x)=> $x.id != "d4"}}
$del = [self:ledger]{{op:"set", path:"{SCRATCH_LEDGER}", target:"log", value:$keep}}
$after = [self:ledger]{{op:"select", path:"{SCRATCH_LEDGER}", target:"log"}}
$d5 = $after.items >> [table:filter]{{where:($x)=> $x.id == "d5"}}
return {{before:len($all.items), after:len($after.items), d5_sys:$d5[0].sys, del_keys:keys($del)}}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('after') == 4 and v.get('d5_sys') == 132), ok_or_err(r, 500)


def t24():
    """[check · 코퍼스] recent_chats 용례(278 등 5건 '{}'·3823 파이프)와 forage 용례(2799 table·2800 layer)를 판본 2로."""
    a = ex('return [self:recent_chats]{}')
    b = ex('return [self:recent_chats] >> [table:take]{n: 5}', check=True)
    c = ex('return [self:forage]{op:"note", layer:"map", locus:"/Volumes/IT78/backup", kind:"identity", claim:"x"}', check=True)
    d = ex('return [self:forage]{op:"forget", id:1, table:"forage_map"}', check=True)
    da = a.get('diagnostic') or {}
    def st(x):
        w = [i.get('code') for i in (x.get('warnings') or x.get('precheck_warnings') or [])]
        return f"{x.get('status')} issues={codes(x)} warn={w}"
    return bool(a.get('success')), (f"278형 실행 success={a.get('success')} code={da.get('code')} | 3823={st(b)} | 2800 layer={st(c)} | 2799 table={st(d)}")


def t00():
    """(탐색) 원천 모양 확인 — 과제 아님."""
    return True, 'noop'


TASKS = []


def _collect():
    global TASKS
    TASKS = [globals()[n] for n in sorted(globals()) if n.startswith('t') and n[1:].isdigit() and n != 't00']


def run():
    _collect()
    only = [a for a in sys.argv[2:] if a.startswith('t')]
    path = HERE / 'before.json'
    store = json.loads(path.read_text()) if path.exists() else {'rows': [], 'log': []}
    rows = {r['task']: r for r in store['rows']}
    for task in TASKS:
        if only and task.__name__ not in only:
            continue
        LOG.clear()
        started = datetime.now().isoformat(timespec='seconds')
        try:
            ok, detail = task()
        except Exception as exc:  # 탐침의 실패도 기록한다
            ok, detail = False, f'probe error: {type(exc).__name__}: {exc}'
        rows[task.__name__] = {'task': task.__name__, 'intent': task.__doc__, 'ok': bool(ok), 'detail': detail,
                               'at': started}
        store['log'] = [e for e in store['log'] if e.get('task') != task.__name__]
        mask_log()
        store['log'].extend({'task': task.__name__, **e} for e in LOG)
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:1500], flush=True)
    store['rows'] = [rows[k] for k in sorted(rows)]
    store['passed'] = sum(r['ok'] for r in store['rows'])
    store['total'] = len(store['rows'])
    path.write_text(json.dumps(store, ensure_ascii=False, indent=1))
    print(f"{store['passed']}/{store['total']}")


def desc():
    r = post('ibl/execute', dict(code='', edition=2, describe=sys.argv[2:], project_id='컨텐츠', origin='training', **AGENT))
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str)[:20000])


def raw():
    extra = {}
    if '--check' in sys.argv:
        extra['check'] = True
    r = ex(sys.argv[2], **extra)
    print(json.dumps({k: v for k, v in r.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')},
                     ensure_ascii=False, indent=1, default=str)[:12000])


def _tree_stat(root):
    root = Path(root)
    if not root.exists():
        return None
    files = [f for f in root.rglob('*') if f.is_file()]
    return {'files': len(files), 'max_mtime': max((f.stat().st_mtime for f in files), default=0)}


def stores():
    out = {}
    for name, (db, tables) in STORES.items():
        row = {'mtime': db.stat().st_mtime if db.exists() else None}
        for t in tables:
            try:
                row[t] = q(db, f'select count(*), coalesce(max(rowid),0) from {t}')[0]
            except Exception as exc:
                row[t] = f'ERR {exc}'
        out[name] = row
    out['forage_surveys'] = _tree_stat(BASE / 'data/forage_surveys')
    out['memory_tree_system_ai'] = _tree_stat(BASE / 'data/system_ai_state/memory_tree_system_ai')
    out['recall_index'] = _tree_stat(BASE / 'data/recall_index')
    out['record_spaces'] = _tree_stat(BASE / 'data/record_spaces')
    out['storage_scans'] = _tree_stat(BASE / 'data/packages/installed/tools/storage_scans') or _tree_stat(BASE / 'data/packages/storage_scans')
    out['episode_log_max'] = q(PULSE, 'select max(rowid) from episode_log')[0][0]
    return out


def snapshot():
    notes = post('notifications?limit=100', method='GET')
    return {
        'at': datetime.now().isoformat(timespec='seconds'),
        'notifications': [{k: n.get(k) for k in ('id', 'type', 'created_at')} for n in notes['notifications']],
        'action_health_max_id': q(PULSE, 'select max(id) from action_health')[0][0],
        'notify_log_max_id': q(PULSE, 'select max(id) from notify_log')[0][0],
        'since_streams': q(SINCE, 'select count(distinct stream), count(*) from since_seen')[0],
        'stores': stores(),
    }


def baseline():
    (HERE / 'baseline.json').write_text(json.dumps({'baseline': snapshot()}, ensure_ascii=False, indent=1))
    print('baseline saved')


def after():
    base = json.loads((HERE / 'baseline.json').read_text())
    b = base['baseline']
    a = snapshot()
    diff = {
        'notifications_added': [n for n in a['notifications'] if n['id'] not in {x['id'] for x in b['notifications']}],
        'action_health_by_source': q(PULSE, 'select source, coalesce(channel,""), count(*) from action_health where id > ? group by 1, 2',
                                     (b['action_health_max_id'],)),
        'action_health_training_by_action': q(PULSE, "select node||':'||action, count(*), sum(success) from action_health where id > ? and source='training' group by 1 order by 2 desc",
                                              (b['action_health_max_id'],)),
        'notify_log_new': q(PULSE, 'select id, emitter, source from notify_log where id > ?', (b['notify_log_max_id'],)),
        'since_streams': a['since_streams'],
        'stores_before': b['stores'],
        'stores_after': a['stores'],
        'stores_changed': {k: [b['stores'].get(k), json.loads(json.dumps(a['stores'].get(k)))] for k in a['stores'] if json.loads(json.dumps(a['stores'].get(k))) != b['stores'].get(k)},
    }
    base['after'] = {'snapshot': {k: a[k] for k in ('at', 'action_health_max_id', 'notify_log_max_id')}, 'diff': diff}
    (HERE / 'baseline.json').write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(json.dumps(diff, ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == '__main__':
    {'baseline': baseline, 'run': run, 'after': after, 'raw': raw, 'desc': desc}[sys.argv[1]]()
