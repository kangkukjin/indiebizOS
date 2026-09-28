"""75회차: 시간·발신 문형 — 예약·트리거·캘린더 실행 이벤트·검침(since)·조건 알림·발신 (훈련 턴 · 무수정).

축 = 행동 기준에서 조합 수 0인 두 문형(시간·발신). 액션: self:schedule·self:trigger·self:manage_events·
self:time·table:since·self:notify_user·others:channel_send·others:messages·others:ask.
도메인: 매일 아침 AI 팁 보고서·매주 월요일 부동산 알림·강의 전날 준비물·가계부 월말 결산·가족 소식(check)·
주가/날씨 임계값·반복 예약 수정/일시정지/삭제·말일/윤년/자정/KST 경계·"지난번 이후 새 것만"+알림·발신 폴백.

모든 요청 edition 2·project_id 컨텐츠·origin training. 탐침 표면 = 모델 경로(agent_id·task_id IT75_*).
★예외: **발화할 수 있는 등록**(schedule 지연·스크래치 트리거/이벤트)은 agent_id 를 싣지 않는다 — 셀프 스케줄의
  소유 에이전트가 가짜 이름 `IT75_probe` 가 되면 발화가 "보이는 실행"(창 열기·LLM 턴)으로 가기 때문이다
  (system_ai_plans._execute_schedule: agent_id != "system_ai" 이면 owner_agent). 표면 기본값으로 등록하면
  소유 에이전트가 비어 등록 프로젝트에서 직접 실행된다(54회차 B54-2 수리 경로).
★등록은 원칙적으로 check 만. 등록 계약(저장 레코드·캘린더 거울)을 봐야 하는 것만 IT75_ 스크래치로 등록하고,
  발화 전에 지운다. 발화 판정은 **실제 저장 레코드를 발화 판정 함수(_should_run_task)에 넣는 격리 재현**으로 본다.
★발화 실측은 두 건(T14 지연 취소·T15 지연 이중 발화)만, 본문은 `[self:time]{}`(무해 읽기). 발화 뒤 §3-5 네 곳 되돌림.
★notify_user 실발신은 T24 한 건(자기 수신). others:* 외부 발신은 전부 check.
사용: .venv/bin/python probe.py baseline | run | after
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
SCRATCH = Path('/private/tmp/claude-501/-Users-kangkukjin-Desktop-AI/2b4c35a7-5f76-494f-b23f-ecb323501955/scratchpad/it75')
AGENT = {'agent_id': 'IT75_probe', 'task_id': 'IT75_task'}
LOG = []
PY = str(BASE / '.venv/bin/python')
PULSE = BASE / 'data/world_pulse.db'
SAIM = BASE / 'data/system_ai_memory.db'
SINCE = BASE / 'data/table_since.db'
TRIG = BASE / 'data/event_triggers.json'
CAL = BASE / 'data/calendar_events.json'
RUNLOG = BASE / 'data/backend_runtime.log'


def post(route, payload=None, method='POST'):
    args = ['curl', '-sS', '--max-time', '240', '-X', method, f'http://127.0.0.1:8765/{route}',
            '-H', 'Content-Type: application/json']
    if payload is not None:
        args += ['--data-binary', '@-']
    proc = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                          text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, surface=False, **extra):
    """surface=True 는 agent_id 없이(표면 기본값) — 발화할 수 있는 등록 전용."""
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠', origin='training',
                   **({} if surface else AGENT), **extra)
    response = post('ibl/execute', payload)
    slim = {k: v for k, v in response.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}
    LOG.append({'request': payload, 'response': slim})
    return response


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def err(r):
    e = r.get('error')
    if isinstance(e, dict):
        return json.dumps({k: e.get(k) for k in ('code', 'message', 'hint')}, ensure_ascii=False)[:500]
    if e:
        return str(e)[:500]
    return json.dumps([{k: i.get(k) for k in ('code', 'message')} for i in r.get('issues') or []],
                      ensure_ascii=False)[:500]


def val(r):
    return r.get('value')


def q(db, sql, args=()):
    con = sqlite3.connect(str(db), timeout=10)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def js(x, n=400):
    return json.dumps(x, ensure_ascii=False, default=str)[:n]


# ───────────────────────── 기준선 ─────────────────────────

def snapshot():
    notes = post('notifications?limit=100', method='GET')
    trig = json.loads(TRIG.read_text())
    cal = json.loads(CAL.read_text())
    return {
        'at': datetime.now().isoformat(timespec='seconds'),
        'notifications': [{k: n.get(k) for k in ('id', 'type', 'title', 'created_at')} for n in notes['notifications']],
        'unread': notes.get('unread_count'),
        'triggers': [{k: t.get(k) for k in ('id', 'name', 'enabled', 'run_count', 'last_run', 'last_success')}
                     for t in trig['triggers']],
        'trigger_history_len': len(trig['history']),
        'trigger_history_first': trig['history'][0]['time'] if trig['history'] else None,
        'trigger_history_last': trig['history'][-1]['time'] if trig['history'] else None,
        'events': [{k: e.get(k) for k in ('id', 'title', 'enabled', 'last_run', 'repeat')} for e in cal['events']],
        'action_health_max_id': q(PULSE, 'select max(id) from action_health')[0][0],
        'notify_log_max_id': q(PULSE, 'select max(id) from notify_log')[0][0],
        'conversations_max_id': q(SAIM, 'select max(id) from conversations')[0][0],
        'since_streams': q(SINCE, 'select count(distinct stream), count(*) from since_seen')[0],
        'since_it75_rows': q(SINCE, "select count(*) from since_seen where stream like 'IT75%'")[0][0],
        'scheduler': post('scheduler/status', method='GET'),
    }


def baseline():
    snap = snapshot()
    (SCRATCH / 'event_triggers.baseline.json').write_text(TRIG.read_text())
    (SCRATCH / 'calendar_events.baseline.json').write_text(CAL.read_text())
    (HERE / 'baseline.json').write_text(json.dumps({'baseline': snap}, ensure_ascii=False, indent=1))
    print(js({k: snap[k] for k in ('at', 'unread', 'trigger_history_len', 'action_health_max_id',
                                   'notify_log_max_id', 'conversations_max_id', 'since_streams')}, 800))
    print('notifications', len(snap['notifications']), 'triggers', len(snap['triggers']), 'events', len(snap['events']))


# ─────────────────── 격리: 발화 판정 함수에 실제 저장 레코드를 넣는다 ───────────────────

ISOLATE_SRC = r'''
import json, sys
sys.path.insert(0, "/Users/kangkukjin/Desktop/AI/indiebizOS/backend")
import boot_paths  # noqa
from datetime import datetime
from calendar_manager import CalendarManagerBase as C
cases = json.loads(sys.stdin.read())
out = []
for c in cases:
    ev = dict(c["event"])
    fired = []
    for when in c["whens"]:
        now = datetime.fromisoformat(when)
        fired.append([when, bool(C._should_run_task(C, ev, now))])
    out.append({"label": c["label"], "fired": fired})
print(json.dumps(out, ensure_ascii=False))
'''


def should_run(cases):
    """cases=[{label, event, whens}] → 각 시각에 스케줄러 틱이 그 이벤트를 발화하는가(실제 판정 함수)."""
    proc = subprocess.run([PY, '-c', ISOLATE_SRC], input=json.dumps(cases, default=str), text=True,
                          capture_output=True, check=True)
    return json.loads(proc.stdout)


def cal_event(event_id):
    for e in json.loads(CAL.read_text())['events']:
        if e['id'] == event_id:
            return e
    return None


def cal_events_by_title(prefix):
    return [e for e in json.loads(CAL.read_text())['events'] if str(e.get('title', '')).startswith(prefix)]


def drop_event(event_id):
    return ex(f'return [self:manage_events]{{op:"delete", event_id:"{event_id}"}}')


def drop_trigger(trigger_id):
    return ex(f'return [self:trigger]{{op:"delete", id:"{trigger_id}"}}')


# 월말·평일·자정 경계 표본 시각 (등록 뒤 첫 한 달)
WHENS_MONTH = ['2026-09-29T09:01', '2026-09-30T09:01', '2026-10-01T09:01', '2026-10-02T09:01',
               '2026-10-15T09:01', '2026-10-31T09:01', '2026-11-30T09:01', '2027-02-28T09:01']
WHENS_WEEK = ['2026-09-29T07:01', '2026-09-30T07:01', '2026-10-05T07:01', '2026-10-06T07:01']


# ───────────────────────── 과제 ─────────────────────────

def t01():
    """[AI 팁] 매일 아침 보고서 트리거들이 잘 돌고 있나 — 켜진 것 중 마지막 실행이 실패한 것만 이름·실행수·마지막 실행."""
    r = ex('$t = [self:trigger]{op:"list"}\n'
           'return $t.items >> [table:filter]{where:($r)=> $r.enabled == true && $r.last_success == false}'
           ' >> [table:select]{columns:["name","run_count","last_run"]}')
    v = val(r) or []
    return r.get('success') and isinstance(v, list), f"rows={js(v, 300)}"


def t02():
    """[운영] 주간 재조사 트리거(부동산)의 지난 실행 이력 — 몇 번 돌았고 이력에 몇 줄 남았나."""
    r = ex('$t = [self:trigger]{op:"list"}\n'
           '$w = $t.items >> [table:filter]{where:($r)=> $r.name == "forage_resurvey_부동산"}\n'
           '$h = [self:trigger]{op:"history", id:$w[0].id, limit:50}\n'
           'return {run_count:$w[0].run_count, history_rows:len($h.items), shown:$h.items >> [table:select]{columns:["time","success"]}}')
    v = val(r) or {}
    ok = r.get('success') and isinstance(v, dict) and v.get('history_rows') == v.get('run_count')
    # 이력 원장 전체의 점유(훈련자가 셸로 대조)
    hist = json.loads(TRIG.read_text())['history']
    share = {}
    for h in hist:
        share[h['trigger_name']] = share.get(h['trigger_name'], 0) + 1
    top = sorted(share.items(), key=lambda kv: -kv[1])[:2]
    return ok, f"value={js(v, 300)} | history_total={len(hist)} top={top} span={hist[0]['time'][:16]}~{hist[-1]['time'][:16]}"


def t03():
    """[부동산] 매주 월요일 아침 7시에 청주 전세 새 매물만 3건까지 알려줘 (트리거 + since + 조건 알림, check)."""
    do = ('$m = [sense:realty]{source:\\"naver\\", region:\\"청주\\", deal:\\"lease\\"} >> [table:since]{key:\\"IT75_청주전세\\"}\\n'
          '[if: len($m.items) > 0] { [self:notify_user]{message:f\\"청주 새 전세 ${len($m.items)}건\\"} }')
    r = ex(f'return [self:trigger]{{op:"create", name:"IT75_주간전세", cron:"0 7 * * 1", do:"{do}"}}', check=True)
    inner = ex('$m = [sense:realty]{source:"naver", region:"청주", deal:"lease"} >> [table:since]{key:"IT75_청주전세"}\n'
               '[if: len($m.items) > 0] { [self:notify_user]{message:f"청주 새 전세 ${len($m.items)}건"} }', check=True)
    return r.get('status') in ('valid', 'incomplete') and inner.get('status') in ('valid', 'incomplete'), \
        f"outer={r.get('status')} {err(r)[:160]} | inner={inner.get('status')} {err(inner)[:200]}"


def t04():
    """[AI 팁] 매일 아침 9시 새 글 알림 트리거를 코퍼스 형태(`… >> [table:since] >> [self:notify_user]`)로 만들면 — 등록이 막는가, 목록 점검이 잡는가."""
    do = ('[sense:feed]{url:\\"https://news.hada.io/rss/news\\"} >> [table:since]{key:\\"IT75_하다\\"} >> '
          '[self:notify_user]{message:\\"하다뉴스 새 글\\"}')
    chk = ex(f'return [self:trigger]{{op:"create", name:"IT75_하다감시", cron:"0 9 * * *", do:"{do}"}}', check=True)
    inner = ex('[sense:feed]{url:"https://news.hada.io/rss/news"} >> [table:since]{key:"IT75_하다"} >> '
               '[self:notify_user]{message:"하다뉴스 새 글"}', check=True)
    c = ex(f'return [self:trigger]{{op:"create", name:"IT75_하다감시", cron:"0 9 * * *", do:"{do}"}}', surface=True)
    tid = ((val(c) or {}).get('trigger') or {}).get('id')
    lst = ex('$t = [self:trigger]{op:"list"}\nreturn $t.items >> [table:filter]{where:($r)=> $r.name == "IT75_하다감시"}'
             ' >> [table:select]{columns:["id","runnable","problem"]}')
    if tid:
        drop_trigger(tid)
    rows = val(lst) or []
    runnable = rows[0].get('runnable') if rows else None
    return runnable is False, (f"check_outer={chk.get('status')} inner={inner.get('status')} {codes(inner)} | "
                               f"create={c.get('success')} id={tid} | list={js(rows, 300)}")


def t05():
    """[강의] 10월 6일 강의 전날 저녁 8시에 준비물 알림 (1회 schedule, check) + 매주 화요일 강의면 매주 월요일 20시 (cron, check)."""
    a = ex('return [self:schedule]{date:"2026-10-05", time:"20:00", title:"IT75_강의준비물", '
           'do:"[self:notify_user]{message:\\"내일 강의 준비물: 노트북·HDMI·출석부\\"}"}', check=True)
    b = ex('return [self:trigger]{op:"create", name:"IT75_강의전날", cron:"0 20 * * 1", '
           'do:"[self:notify_user]{message:\\"내일 강의 준비물 챙기기\\"}"}', check=True)
    return a.get('status') in ('valid', 'incomplete') and b.get('status') in ('valid', 'incomplete'), \
        f"once={a.get('status')} {err(a)[:120]} | weekly={b.get('status')} {err(b)[:120]}"


def t06():
    """[강의] 강의 날짜 목록(시트에서 읽었다 치고)마다 '전날 20시' 알림 시각을 계산 — 날짜 산술."""
    tries = {}
    for label, code in [
        ('minus_number', '$d = "2026-10-06"\nreturn $d - 1'),
        ('fn_date_add', '$d = "2026-10-06"\nreturn date_add($d, -1)'),
        ('split_day', '$d = "2026-10-06"\n$p = split($d, "-")\nreturn f"${$p[0]}-${$p[1]}-${number($p[2]) - 1}"'),
        ('split_month_start', '$d = "2026-11-01"\n$p = split($d, "-")\nreturn f"${$p[0]}-${$p[1]}-${number($p[2]) - 1}"'),
    ]:
        r = ex(code)
        tries[label] = (r.get('success'), val(r) if r.get('success') else err(r)[:160])
    ok = tries['split_month_start'][0] and tries['split_month_start'][1] == '2026-10-31'
    return ok, js(tries, 700)


def t07():
    """[가계부] 매월 1일 00시 30분에 지난달 가계부 결산 (가이드의 매월 cron `30 0 1 * *`) — 등록 레코드와 발화 판정."""
    c = ex('return [self:trigger]{op:"create", name:"IT75_월초결산", cron:"30 0 1 * *", '
           'do:"[self:time]{}"}', surface=True)
    t = (val(c) or {}).get('trigger') or {}
    ev = next((e for e in cal_events_by_title('[IBL] IT75_월초결산')), None)
    iso = should_run([{'label': 'cron 30 0 1', 'event': {**(ev or {}), 'last_run': None},
                       'whens': [w.replace('09:01', '00:31') for w in WHENS_MONTH]}]) if ev else []
    if t.get('id'):
        drop_trigger(t['id'])
    fired = [w for w, f in (iso[0]['fired'] if iso else []) if f]
    ok = bool(ev) and all(w[8:10] == '01' for w in fired)
    return ok, (f"config={js(t.get('config'))} event={js({k: (ev or {}).get(k) for k in ('repeat','date','day','time')})} "
                f"fires_on={[w[:10] for w in fired]}")


def t08():
    """[가계부] 매월 말일 밤 9시 월말 결산 — cron `0 21 31 * *` / `0 21 L * *` / `0 21 28-31 * *` + 캘린더 date 형(10-31)."""
    forms = {}
    for cron in ('0 21 31 * *', '0 21 L * *', '0 21 28-31 * *'):
        r = ex(f'return [self:trigger]{{op:"create", name:"IT75_월말", cron:"{cron}", do:"[self:time]{{}}"}}', check=True)
        forms[cron] = (r.get('status'), err(r)[:140])
    # 캘린더 date 형 — 10월 31일 기준 매월 (등록 없이 판정만: manage_events create 가 저장하는 모양)
    ev = {'id': 'x', 'title': 'IT75', 'date': '2026-10-31', 'repeat': 'monthly', 'time': '21:00',
          'action': 'run_pipeline', 'enabled': True, 'created_at': '2026-09-28T23:00:00'}
    iso = should_run([{'label': 'monthly date 10-31', 'event': ev,
                       'whens': ['2026-10-31T21:01', '2026-11-30T21:01', '2026-12-31T21:01', '2027-02-28T21:01']}])
    fired = iso[0]['fired']
    ok = all(s in ('valid', 'incomplete') for s, _ in forms.values())
    return ok, f"cron={js(forms, 600)} | date_form_fired={fired}"


def t09():
    """[가계부] `[self:schedule]{repeat:"monthly", time}` — 날짜 없이 '매월 9시'라고만 하면 (등록 계약 + 발화 판정)."""
    r = ex('return [self:schedule]{repeat:"monthly", time:"09:00", title:"IT75_매월", do:"[self:time]{}"}', surface=True)
    eid = (val(r) or {}).get('event_id')
    ev = cal_event(eid) if eid else None
    iso = should_run([{'label': 'schedule monthly', 'event': ev, 'whens': WHENS_MONTH}]) if ev else []
    if eid:
        drop_event(eid)
    fired = [w[:10] for w, f in (iso[0]['fired'] if iso else []) if f]
    return len(fired) <= 1, f"resp={js(val(r), 200)} event={js({k: (ev or {}).get(k) for k in ('repeat','date','day','time')})} fires_on={fired}"


def t10():
    """[부동산] 매주 월요일 7시 실거래 변화 알림을 schedule 로 — weekdays 를 빠뜨림 / 이름으로 줌 / 숫자로 줌."""
    out = {}
    for label, wd in (('none', ''), ('names', ', weekdays:["mon"]'), ('ints', ', weekdays:[0]')):
        r = ex(f'return [self:schedule]{{repeat:"weekly", time:"07:00", title:"IT75_주간_{label}"{wd}, do:"[self:time]{{}}"}}',
               surface=True)
        eid = (val(r) or {}).get('event_id')
        ev = cal_event(eid) if eid else None
        iso = should_run([{'label': label, 'event': ev, 'whens': WHENS_WEEK}]) if ev else []
        if eid:
            drop_event(eid)
        out[label] = {'success': r.get('success'), 'msg': (val(r) or {}).get('message') or err(r)[:120],
                      'weekdays': (ev or {}).get('weekdays'),
                      'fires': [w[:10] for w, f in (iso[0]['fired'] if iso else []) if f]}
    ok = all(v['fires'] == ['2026-10-05'] or not v['success'] for v in out.values())
    return ok, js(out, 800)


def t11():
    """[가족] 결혼기념일(12-13) 전날 아침 9시 매년 알림 — manage_events(date 형) · schedule(date 형) · trigger cron."""
    whens = ['2026-12-12T09:01', '2027-12-12T09:01', '2026-12-13T09:01']
    out = {}
    m = ex('return [self:manage_events]{op:"create", title:"IT75_기념일전날", date:"2026-12-12", time:"09:00", '
           'repeat:"yearly", do:"[self:time]{}"}', surface=True)
    ev = ((val(m) or {}).get('event') or {})
    if ev.get('id'):
        out['manage_events'] = should_run([{'label': 'me', 'event': cal_event(ev['id']), 'whens': whens}])[0]['fired']
        drop_event(ev['id'])
    s = ex('return [self:schedule]{repeat:"yearly", date:"2026-12-12", time:"09:00", title:"IT75_기념일전날_s", '
           'do:"[self:time]{}"}', surface=True)
    sid = (val(s) or {}).get('event_id')
    if sid:
        out['schedule'] = should_run([{'label': 's', 'event': cal_event(sid), 'whens': whens}])[0]['fired']
        drop_event(sid)
    c = ex('return [self:trigger]{op:"create", name:"IT75_기념일전날_t", cron:"0 9 12 12 *", do:"[self:time]{}"}',
           surface=True)
    tid = ((val(c) or {}).get('trigger') or {}).get('id')
    tev = next(iter(cal_events_by_title('[IBL] IT75_기념일전날_t')), None)
    if tev:
        out['trigger'] = should_run([{'label': 't', 'event': tev, 'whens': whens}])[0]['fired']
    if tid:
        drop_trigger(tid)
    ok = all(v[0][1] and v[1][1] and not v[2][1] for v in out.values()) and len(out) == 3
    return ok, js(out, 700)


def t12():
    """[가족] '매일'·'평일' 을 한국어나 틀린 낱말로 주면 — schedule repeat 값 검증."""
    out = {}
    for rep in ('매일', 'weekday', 'once'):
        r = ex(f'return [self:schedule]{{repeat:"{rep}", time:"09:00", date:"2026-10-01", title:"IT75_rep_{rep}", '
               'do:"[self:time]{}"}', surface=True)
        eid = (val(r) or {}).get('event_id')
        ev = cal_event(eid) if eid else None
        iso = should_run([{'label': rep, 'event': ev, 'whens': ['2026-10-01T09:01', '2026-10-02T09:01']}]) if ev else []
        if eid:
            drop_event(eid)
        out[rep] = {'success': r.get('success'), 'msg': (val(r) or {}).get('message') or err(r)[:120],
                    'stored_repeat': (ev or {}).get('repeat'), 'fires': iso[0]['fired'] if iso else None}
    trig = ex('return [self:trigger]{op:"create", name:"IT75_rep", config:{repeat:"매일", time:"09:00"}, do:"[self:time]{}"}',
              check=True)
    ok = all((not v['success']) or any(f for _, f in (v['fires'] or [])) for v in out.values())
    return ok, js(out, 700) + f" | trigger_config_check={trig.get('status')} {err(trig)[:120]}"


def t13():
    """[경계] 지금 시각·요일·시간대 (KST) — 자정 넘김·윤년 판단의 재료."""
    r = ex('$a = [self:time]{}\n$b = [self:time]{format:"%A %Z %z"}\n$c = [self:time]{format:"%Y-%m-%d"}\n'
           'return {now:$a, dow_tz:$b, today:$c}')
    feb = ex('return [self:schedule]{date:"2026-02-29", time:"09:00", do:"[self:time]{}"}', check=True)
    feb_run = ex('return [self:schedule]{date:"2027-02-29", time:"09:00", title:"IT75_윤년", do:"[self:time]{}"}',
                 surface=True)
    v = val(r) or {}
    return r.get('success'), f"value={js(v, 200)} | feb29_check={feb.get('status')} | 2027-02-29 run={err(feb_run)[:160] if not feb_run.get('success') else js(val(feb_run))}"


def t14():
    """[강의] 5분 뒤 알림을 예약했다가 취소 — schedule 지연(event_id 반환) → manage_events delete → 발화하나 (발화 실측, 본문 [self:time])."""
    start = datetime.now()
    r = ex('return [self:schedule]{seconds:40, title:"IT75_취소", do:"[self:time]{}"}', surface=True)
    eid = (val(r) or {}).get('event_id')
    d = drop_event(eid) if eid else {}
    gone = cal_event(eid) is None if eid else None
    time.sleep(55)
    lines = [ln for ln in RUNLOG.read_text(errors='replace').splitlines()[-400:]
             if '타이머 만료' in ln and 'self:time' in ln]
    notes = [n for n in post('notifications?limit=30', method='GET')['notifications']
             if 'IT75_취소' in (n.get('message') or '')]
    ah = q(PULSE, "select id, timestamp, source, channel from action_health where node='self' and action='time' and timestamp >= ? and source != 'training'",
           (start.isoformat(),))
    fired = bool(notes) or bool(ah)
    return (not fired), (f"sched={js(val(r), 160)} delete={d.get('success')} event_gone={gone} | after55s: "
                         f"timer_log={len(lines)} notes={[n['title'] for n in notes]} action_health_nontraining={ah}")


def t15():
    """[AI 팁] 2분 뒤 한 번만 실행 예약 — 스케줄러 틱이 먼저 오는 분에도 한 번만 도는가 (지연 이중 발화, 발화 실측)."""
    # 틱 위상 = 스케줄러가 찍은 가장 최근 last_run 의 초
    last = max((e.get('last_run') or '' for e in json.loads(CAL.read_text())['events']), default='')
    phase = datetime.fromisoformat(last).second + datetime.fromisoformat(last).microsecond / 1e6 if last else 0
    now = datetime.now()
    # 타이머가 '다음다음 분의 틱 위상 + 8초'에 오도록 — 그 분의 틱이 먼저 이벤트를 본다
    target = (now.replace(second=0, microsecond=0) + timedelta(minutes=2)) + timedelta(seconds=min(phase + 8, 59))
    secs = int((target - now).total_seconds())
    start = datetime.now()
    r = ex(f'return [self:schedule]{{seconds:{secs}, title:"IT75_이중", do:"[self:time]{{}}"}}', surface=True)
    eid = (val(r) or {}).get('event_id')
    ev0 = cal_event(eid) if eid else None
    time.sleep(max(0, (target - datetime.now()).total_seconds()) + 20)
    ev1 = cal_event(eid) if eid else None
    notes = [n for n in post('notifications?limit=30', method='GET')['notifications']
             if 'IT75_이중' in (n.get('message') or '')]
    ah = q(PULSE, "select id, timestamp, source, channel from action_health where node='self' and action='time' and timestamp >= ? and source != 'training'",
           (start.isoformat(),))
    if eid:
        drop_event(eid)
    runs = len(ah)
    return runs == 1, (f"phase={phase:.1f}s secs={secs} target={target.time()} event_time={(ev0 or {}).get('time')} | "
                       f"runs(action_health)={ah} notes={[n['title'] for n in notes]} event_after={js({k: (ev1 or {}).get(k) for k in ('enabled','last_run')})}")


def t16():
    """[AI 팁] 매일 아침 보고서 알림 잠깐 끄기 → 다시 켜기 → 9시에서 10시로 → 삭제 (스크래치 트리거, 캘린더 거울 동기)."""
    c = ex('return [self:trigger]{op:"create", name:"IT75_아침팁", cron:"0 9 * * *", do:"[self:time]{}"}', surface=True)
    tid = ((val(c) or {}).get('trigger') or {}).get('id')
    steps = {}
    for op, extra in (('disable', ''), ('enable', ''), ('update', ', cron:"0 10 * * *"')):
        r = ex(f'return [self:trigger]{{op:"{op}", id:"{tid}"{extra}}}')
        ev = next(iter(cal_events_by_title('[IBL] IT75_아침팁')), {})
        steps[op] = (r.get('success'), ev.get('enabled'), ev.get('time'), len(cal_events_by_title('[IBL] IT75_아침팁')))
    drop_trigger(tid)
    steps['delete'] = len(cal_events_by_title('[IBL] IT75_아침팁'))
    ok = steps['disable'][1] is False and steps['enable'][1] is True and steps['update'][2] == '10:00' \
        and steps['update'][3] == 1 and steps['delete'] == 0
    return ok, js(steps, 400)


def t17():
    """[강의] 예약해 둔 강의 준비물 알림을 저녁 9시로 옮기고 문구도 바꾸기 — schedule 로 만든 것을 manage_events update 로."""
    r = ex('return [self:schedule]{date:"2026-10-05", time:"20:00", title:"IT75_준비물", do:"[self:time]{}"}', surface=True)
    eid = (val(r) or {}).get('event_id')
    u = ex(f'return [self:manage_events]{{op:"update", event_id:"{eid}", time:"21:00", do:"[self:time]{{format:\\"%H\\"}}"}}')
    ev = cal_event(eid) or {}
    lst = ex('$e = [self:manage_events]{op:"list", year:2026, month:10}\n'
             'return $e.items >> [table:filter]{where:($r)=> contains($r.title, "IT75_준비물")} >> [table:select]{columns:["title","date","time"]}')
    drop_event(eid)
    ok = u.get('success') and ev.get('time') == '21:00' and 'format' in str((ev.get('action_params') or {}).get('pipeline'))
    return ok, f"update={u.get('success')} stored={js({k: ev.get(k) for k in ('date','time','action')})} pipeline={js((ev.get('action_params') or {}).get('pipeline'), 120)} list={js(val(lst), 200)}"


def t18():
    """[정보센터] 지난번 이후 새 글만 — 있을 때만 알림 (since 두 번, 판본 2 조건 형태; 알림은 check 가지)."""
    rows1 = '[{id:"a", title:"첫 글"},{id:"b", title:"둘째 글"}]'
    rows2 = '[{id:"a", title:"첫 글"},{id:"b", title:"둘째 글"},{id:"c", title:"새 글"}]'
    body = ('$n = $rows >> [table:since]{key:"IT75_피드"}\n'
            '[if: len($n.items) > 0] { return {alert:true, n:len($n.items), titles:$n.items >> [table:select]{columns:["title"]}} } '
            '[else] { return {alert:false, note:get($n, "note", "")} }')
    a = ex(f'$rows = {rows1}\n' + body)
    b = ex(f'$rows = {rows2}\n' + body)
    c = ex(f'$rows = {rows2}\n' + body)
    va, vb, vc = val(a) or {}, val(b) or {}, val(c) or {}
    ok = va.get('alert') is False and vb.get('n') == 1 and vc.get('alert') is False
    return ok, f"1st={js(va, 160)} | 2nd={js(vb, 200)} | 3rd={js(vc, 160)}"


def t19():
    """[정보센터] 새 글 알림 보내다 실패하면 — 다음 검침에 그 글이 다시 '새 것'으로 오나 (since 뒤 단계 실패)."""
    ex('$rows = [{id:"a"}]\nreturn $rows >> [table:since]{key:"IT75_유실"}')          # 기준선
    fail = ex('$rows = [{id:"a"},{id:"b", title:"중요 공지"}]\n'
              '$n = $rows >> [table:since]{key:"IT75_유실"}\n'
              '[if: len($n.items) > 0] { $x = [self:read]{path:"/nonexistent/IT75/발송실패_흉내.txt"} }\n'
              'return len($n.items)')
    again = ex('$rows = [{id:"a"},{id:"b", title:"중요 공지"}]\n'
               '$n = $rows >> [table:since]{key:"IT75_유실"}\nreturn len($n.items)')
    peek = ex('$rows = [{id:"a"},{id:"b"},{id:"c", title:"또 다른 공지"}]\n'
              '$n = $rows >> [table:since]{key:"IT75_유실", peek:true}\n'
              '[if: len($n.items) > 0] { $x = [self:read]{path:"/nonexistent/IT75/발송실패_흉내.txt"} }\n'
              'return len($n.items)')
    again2 = ex('$rows = [{id:"a"},{id:"b"},{id:"c"}]\n$n = $rows >> [table:since]{key:"IT75_유실"}\nreturn len($n.items)')
    return val(again) == 1, (f"fail_step={fail.get('success')} {err(fail)[:100]} | next_run_new={val(again)} | "
                             f"peek_then_fail={peek.get('success')} → next_run_new={val(again2)}")


def t20():
    """[부동산] 아직 매물이 0건인 동네를 감시 시작 — 첫 매물이 나오면 알려주나 (빈 첫 검침)."""
    a = ex('$rows = []\n$n = $rows >> [table:since]{key:"IT75_빈동네", by:"id"}\nreturn {n:len($n.items), seeded:get($n,"seeded",null), note:get($n,"note","")}')
    b = ex('$rows = [{id:"m1", title:"첫 매물"}]\n$n = $rows >> [table:since]{key:"IT75_빈동네", by:"id"}\n'
           'return {n:len($n.items), seeded:get($n,"seeded",null), note:get($n,"note","")}')
    vb = val(b) or {}
    return vb.get('n') == 1, f"empty_first={js(val(a) or err(a), 200)} | first_listing={js(vb or err(b), 200)}"


def t21():
    """[투자] 삼성전자가 20만원 넘으면 알려줘 — 조건 알림 (조회 실측. ★조건이 실제로 충족돼(270,000원) 알림 가지가 탔다 —
    이것이 회차의 자기 수신 1건이고 알림함에서 삭제했다. 재실행하면 두 번째 발신이 되므로 --with-notify 없이는 check 로 돈다)."""
    if '--with-notify' not in sys.argv:
        r = ex('$q = [sense:stock]{op:"quote", ticker:"005930"}\n$p = $q.items[0].current_price\n'
               '[if: $p > 200000] { [self:notify_user]{message:f"삼성전자 ${$p}원 — 20만원 돌파"}; return "알림" } '
               '[else] { return f"조건 미충족 ${$p}" }', check=True)
        return r.get('status') in ('valid', 'incomplete'), f"check={r.get('status')} (실측 기록: value=\"알림\", 알림 제목 '삼성전자 270000.0원 — 20만원 돌파' — 삭제함)"
    r = ex('$q = [sense:stock]{op:"quote", ticker:"005930"}\n$p = $q.items[0].current_price\n'
           '[if: $p > 200000] { [self:notify_user]{message:f"삼성전자 ${$p}원 — 20만원 돌파"}; return "알림" } '
           '[else] { return f"조건 미충족 ${$p}" }')
    return r.get('success'), f"value={js(val(r), 160)} {'' if r.get('success') else err(r)}"


def t22():
    """[가족·발신] 가족신문 새 판 나오면 엄마에게 메일 + 실패하면 나에게 알림 (check만) · 가이드 형태 `channel:'gmail', to:'me'`."""
    a = ex('$r = [others:channel_send]{channel_type:"email", to:"엄마", subject:"가족신문 새 판", body:"이번 주 가족신문이 나왔어요"}'
           ' ?? [self:notify_user]{message:"엄마에게 가족신문 메일 실패"}\nreturn $r', check=True)
    b = ex('return [others:channel_send]{channel:"gmail", to:"me", subject:"오늘의 AI 뉴스", body:"본문"}', check=True)
    c = ex('return [sense:search]{source:"gnews", query:"AI"} >> [others:channel_send]{channel:"gmail", to:"me", subject:"오늘의 AI 뉴스"}',
           check=True)
    d = ex('return [others:ask]{to:"폰", message:"오늘 걸음 수 알려줘"}', check=True)
    return a.get('status') in ('valid', 'incomplete'), (f"fallback={a.get('status')} {err(a)[:100]} | guide_form={b.get('status')} {err(b)[:100]} | "
                                                        f"guide_pipe={c.get('status')} {codes(c)} | ask={d.get('status')} {err(d)[:80]}")


def t23():
    """[가족] 가족에게서 온 안 읽은 메시지가 있으면 몇 건인지 (inbox 읽기 → filter, 이름 미수록)."""
    r = ex('$m = [others:messages]{op:"inbox"}\n'
           '$u = $m.items >> [table:filter]{where:($r)=> get($r, "unread", 0) > 0}\n'
           'return {conversations:len($m.items), unread_threads:len($u)}')
    return r.get('success'), f"value={js(val(r), 160)} {'' if r.get('success') else err(r)}"


def t24():
    """[발신] 오늘 점검 끝났다고 나에게 알림 — ★check 로 강등: 회차의 자기 수신 1건은 T21(조건 충족, 270,000원)이 이미 썼다."""
    r = ex('return [self:notify_user]{message:"IT75 상상훈련 점검 알림", title:"IT75 점검"}', check=True)
    return r.get('status') in ('valid', 'incomplete'), f"check={r.get('status')} {err(r)[:120]}"


TASKS = [globals()[f't{i:02d}'] for i in range(1, 25)]


def run():
    only = [a for a in sys.argv[2:] if a.startswith('t')]
    rows = []
    for task in TASKS:
        if only and task.__name__ not in only:
            continue
        try:
            ok, detail = task()
        except Exception as exc:  # 탐침의 실패도 기록한다
            ok, detail = False, f'probe error: {type(exc).__name__}: {exc}'
        rows.append({'task': task.__name__, 'intent': task.__doc__, 'ok': bool(ok), 'detail': detail})
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:700], flush=True)
    passed = sum(r['ok'] for r in rows)
    print(f'{passed}/{len(rows)}')
    name = 'before.json' if not only else f"partial_{'_'.join(only)}.json"
    (HERE / name).write_text(json.dumps({'passed': passed, 'total': len(rows), 'rows': rows, 'log': LOG},
                                        ensure_ascii=False, indent=1))


def after():
    base = json.loads((HERE / 'baseline.json').read_text())
    b = base['baseline']
    a = snapshot()
    diff = {
        'notifications_added': [n for n in a['notifications'] if n['id'] not in {x['id'] for x in b['notifications']}],
        'notifications_removed': [n for n in b['notifications'] if n['id'] not in {x['id'] for x in a['notifications']}],
        'triggers_added': [t for t in a['triggers'] if t['id'] not in {x['id'] for x in b['triggers']}],
        'triggers_removed': [t for t in b['triggers'] if t['id'] not in {x['id'] for x in a['triggers']}],
        'events_added': [e for e in a['events'] if e['id'] not in {x['id'] for x in b['events']}],
        'events_removed': [e for e in b['events'] if e['id'] not in {x['id'] for x in a['events']}],
        'it75_trigger_history_rows': sum(1 for h in json.loads(TRIG.read_text())['history'] if 'IT75' in h.get('trigger_name', '')),
        'since_it75_rows': a['since_it75_rows'],
        'conversations_new': q(SAIM, 'select id, role, substr(content,1,60) from conversations where id > ?', (b['conversations_max_id'],)),
        'action_health_by_source': q(PULSE, 'select source, coalesce(channel,""), count(*) from action_health where id > ? group by 1, 2',
                                     (b['action_health_max_id'],)),
        'notify_log_new': q(PULSE, 'select id, title, emitter, source from notify_log where id > ?', (b['notify_log_max_id'],)),
    }
    base['after'] = {'snapshot': {k: a[k] for k in ('at', 'unread', 'trigger_history_len', 'action_health_max_id',
                                                     'notify_log_max_id', 'conversations_max_id', 'since_streams')},
                     'diff': diff}
    (HERE / 'baseline.json').write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(json.dumps(diff, ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == '__main__':
    {'baseline': baseline, 'run': run, 'after': after}[sys.argv[1]]()
