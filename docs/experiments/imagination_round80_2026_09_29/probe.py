"""80회차: 이웃·게시판·발행 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 소통·공개면 어휘(others:feed·board·follow·nostr·publish·messages·channel_read·neighbor·
agents·delegate·ask·bulletin·portal·showcase·family_news, self:blog·webapp, sense:feed)를 table:filter·each·join·take·
sort 와 [if]·[try]·?? 로 조합.
도메인: 가족신문 이번 호 준비, IndieNet 이웃 소식 읽기·최근 글, 게시판에서 내 글에 달린 반응, 블로그 최근 글·RSS 대조,
쇼케이스·포털 진열 준비(check), 여러 채널 받은 메시지 중 안 읽은 것, 에이전트 위임(check), 발행 전 미리보기·검수,
발행 실패 폴백(check).

모든 요청 edition 2·project_id 컨텐츠·origin training·agent_id IT80_probe·task_id IT80_task.
★부작용 규칙: 읽기(feed·board list·follow list·nostr profile·messages inbox·neighbor list·blog posts/stats·webapp list/status·
  bulletin status/detail·portal portals/status/display 목록·showcase status/basket_list·family_news status/uploads/comments·
  agents·sense:feed)만 실행한다. 게시·발행·팔로우·위임·질문·발신·등록·진열 변경은 전부 check 만.
★개인정보: 이웃·가족·메시지·게시판 글·포털 회원·공개 주소(slug=입장 열쇠)는 before.json 에 모양(shape)만 남긴다
  (private=True). detail 문자열에는 건수·필드 이름·불리언만 싣는다.
사용: .venv/bin/python probe.py baseline | run [tNN ...] | after | raw '<code>' [--check] [--private] | desc node:action ...
"""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
AGENT = {'agent_id': 'IT80_probe', 'task_id': 'IT80_task'}
LOG = []
PULSE = BASE / 'data/world_pulse.db'
BIZ = BASE / 'data/business.db'
INDIENET = Path.home() / '.indiebiz/indienet'
BLOGDB = BASE / 'data/packages/installed/tools/blog/data/blog_insight.db'
FILES = {
    'portal_state': BASE / 'data/portal_state.json',
    'showcase_state': BASE / 'data/showcase_state.json',
    'bulletin_state': BASE / 'data/bulletin/state.json',
    'webapps_manual': BASE / 'data/webapps.json',
    'indienet_settings': INDIENET / 'settings.json',
    'indienet_identity': INDIENET / 'identity.json',
}


def post(route, payload=None, method='POST'):
    args = ['curl', '-sS', '--max-time', '280', '-X', method, f'http://127.0.0.1:8765/{route}',
            '-H', 'Content-Type: application/json']
    if payload is not None:
        args += ['--data-binary', '@-']
    proc = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                          text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, private=False, **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠', origin='training',
                   **AGENT, **extra)
    response = post('ibl/execute', payload)
    slim = {k: v for k, v in response.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}
    LOG.append({'request': payload, 'response': slim, 'private': private})
    return response


def chk(code):
    return ex(code, check=True)


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def wcodes(r):
    return [w.get('code') for w in r.get('warnings') or []]


def err(r):
    e = r.get('error')
    if isinstance(e, dict):
        return json.dumps({k: e.get(k) for k in ('code', 'message', 'hint')}, ensure_ascii=False)[:500]
    if e:
        return str(e)[:500]
    d = r.get('diagnostic')
    if isinstance(d, dict):
        return json.dumps({k: d.get(k) for k in ('code', 'message')}, ensure_ascii=False)[:500]
    return json.dumps([{k: i.get(k) for k in ('code', 'message')} for i in r.get('issues') or []],
                      ensure_ascii=False)[:500]


def val(r):
    return r.get('value')


def js(x, n=400):
    return json.dumps(x, ensure_ascii=False, default=str)[:n]


def q(db, sql, args=()):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=10)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def h(s):
    return hashlib.sha256(str(s).encode()).hexdigest()[:10]


def shape(x, depth=0):
    if isinstance(x, dict):
        if depth > 3:
            return {'_dict_keys': sorted(x)[:40]}
        return {k: shape(v, depth + 1) for k, v in list(x.items())[:50]}
    if isinstance(x, list):
        return {'_list_len': len(x), 'first': shape(x[0], depth + 1) if x else None}
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return '<num>'
    if isinstance(x, str):
        return f'<str len={len(x)}>'
    return x


def mask_log():
    for e in LOG:
        if not e.pop('private', False):
            continue
        r = e['response']
        e['response'] = {k: (shape(v) if k in ('value', 'result', 'partial', 'partial_preview', 'partial_wire', 'data',
                                                'diagnostic', 'error_detail', 'text', 'error', 'continuation', 'result_ref',
                                                'stdout') else v)
                         for k, v in r.items()}
        e['request'] = {k: (v if k != 'inputs' else shape(v)) for k, v in e['request'].items()}


def check_row(r):
    return {'status': r.get('status'), 'effects': r.get('effects'), 'issues': codes(r), 'warnings': wcodes(r)}


def keys_of(rows):
    ks = set()
    for x in rows or []:
        if isinstance(x, dict):
            ks |= set(x)
    return sorted(ks)


# ───────────────────────── 과제 ─────────────────────────
# ★반환 detail 은 before.json rows 에 그대로 저장된다 — 개인 원문·주소·이름을 담지 말 것.


def t01():
    """[조회] 가족신문 이번 호 준비 — 판 목록·초안 여부·가족이 보낸 새 사진(다음 판 후보)·방명록 수."""
    r = ex("""
$s = [others:family_news]{op:"status"}
$u = [others:family_news]{op:"uploads"}
$c = [others:family_news]{op:"comments"}
$pending = $u.items >> [table:filter]{where:($r)=> contains($r.meta, "다음 신문 후보")}
return {editions:len($s.items), drafts:len($s.drafts), published:len($s.published), uploads:len($u.items),
        pending:len($pending), comments:len($c.items), uploads_new:$s.paper.uploads_new,
        row_keys:(keys($s.items[0]) ?? []), msg:$s.message}
""", private=True)
    v = val(r) or {}
    if not r.get('success'):
        # 판이 0이면 $s.items[0] 이 실패할 수 있다 — 그 경우 행 키 없이 다시
        r = ex("""
$s = [others:family_news]{op:"status"}
$u = [others:family_news]{op:"uploads"}
$c = [others:family_news]{op:"comments"}
$pending = $u.items >> [table:filter]{where:($r)=> contains($r.meta, "다음 신문 후보")}
return {editions:len($s.items), drafts:len($s.drafts), published:len($s.published), uploads:len($u.items),
        pending:len($pending), comments:len($c.items), uploads_new:$s.paper.uploads_new, has_msg:len($s.message) > 0,
        paper_keys:keys($s.paper)}
""", private=True)
        v = val(r) or {}
    safe = {k: v.get(k) for k in ('editions', 'drafts', 'published', 'uploads', 'pending', 'comments', 'uploads_new',
                                  'row_keys', 'paper_keys', 'has_msg')}
    return bool(r.get('success')), (f"{js(safe, 500)}" if r.get('success') else f"FAIL {err(r)}")


def t02():
    """[조회] IndieNet 이웃 소식 — 기본 보드 글을 읽고 '최근 5개' — take 5 가 최신 5개인가, 시간 칸은 비교 가능한가."""
    r = ex("""
$f = [others:feed]{op:"read", limit:30}
$top5 = $f.items >> [table:take]{n:5}
return {f:$f, top5:$top5}
""", private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    items = v['f'].get('items') or []
    times = [i.get('time') for i in items]
    fmt_ok = all(re.fullmatch(r'\d\d/\d\d \d\d:\d\d', t or '') for t in times)
    # 순서: 캐시 원장의 created_at 으로 판정(시간 문자열엔 연도가 없다)
    ids = [i.get('id') for i in items]
    ts = {}
    if ids:
        marks = ','.join('?' * len(ids))
        ts = dict(q(INDIENET / 'posts.db', f'select id, created_at from posts where id in ({marks})', ids))
    seq = [ts.get(i) for i in ids if ts.get(i)]
    asc = seq == sorted(seq)
    years = sorted({datetime.fromtimestamp(t).year for t in seq})
    top5_ts = [ts.get(i.get('id')) for i in v['top5'] if ts.get(i.get('id'))]
    newest5 = sorted(seq, reverse=True)[:5]
    detail = {'n': len(items), 'keys': keys_of(items), 'hashtag_echo': v['f'].get('hashtag') is not None,
              'time_fmt_MMDD': fmt_ok, 'order_ascending(oldest_first)': asc, 'years_spanned': years,
              'take5_is_newest5': sorted(top5_ts) == sorted(newest5), 'take5_overlap_newest5': len(set(top5_ts) & set(newest5))}
    return detail['take5_is_newest5'], js(detail, 700)


def t03():
    """[조회] 같은 피드를 세 갈래(기본 보드·팔로우 타임라인·내 글)로 — 갈래마다 순서가 같은가, 시간으로 '이번 주'를 거를 수 있는가."""
    p = ex('return [others:nostr]{op:"profile"}', private=True)
    npub = (val(p) or {}).get('npub') or ''
    out = {'profile_ok': bool(p.get('success')), 'profile_keys': sorted((val(p) or {}).keys())}
    a = ex(f'return [others:feed]{{op:"read", author:"{npub}", limit:30}}', private=True)
    fo = ex('return [others:feed]{op:"read", following:true, limit:30}', private=True)
    for name, rr in (('author_me', a), ('following', fo)):
        vv = val(rr) or {}
        items = vv.get('items') or []
        ids = [i.get('id') for i in items]
        ts = {}
        if ids:
            marks = ','.join('?' * len(ids))
            ts = dict(q(INDIENET / 'posts.db', f'select id, created_at from posts where id in ({marks})', ids))
        seq = [ts.get(i) for i in ids if ts.get(i)]
        out[name] = {'ok': bool(rr.get('success')), 'n': len(items), 'cached_ts': len(seq),
                     'descending(newest_first)': seq == sorted(seq, reverse=True) if seq else None,
                     'years': sorted({datetime.fromtimestamp(t).year for t in seq}),
                     'extra_keys': sorted(set(vv) - {'items', 'count', 'message'})}
    # '이번 주 글만' — 시간 칸 문자열로 거르기 시도(연도 없음 → 해마다 같은 주가 섞인다)
    w = ex(f"""
$a = [others:feed]{{op:"read", author:"{npub}", limit:50}}
$wk = $a.items >> [table:filter]{{where:($r)=> $r.time >= "09/22" and $r.time <= "09/29 23:59"}}
return len($wk)
""", private=True)
    out['week_filter_by_time_string'] = val(w) if w.get('success') else f"FAIL {err(w)}"
    # 캐시에서 같은 필터가 몇 해에 걸쳐 걸리는지(내 글 기준, 원장 created_at)
    my_hex = None
    try:
        from bech32 import bech32_decode  # noqa: F401
    except Exception:
        pass
    out['note'] = 'author 갈래 created_at 은 posts.db 캐시에 있는 행만 대조'
    return True, js(out, 900)


def t04():
    """[조회·불가] 게시판(IndieNet)에서 내 글에 달린 반응(답글·좋아요) 모으기 — 피드 행에 답글 관계 칸이 있는가."""
    p = ex('return [others:nostr]{op:"profile"}', private=True)
    npub = (val(p) or {}).get('npub') or ''
    a = ex(f'return [others:feed]{{op:"read", author:"{npub}", limit:50}}', private=True)
    items = (val(a) or {}).get('items') or []
    my_ids = [i.get('id') for i in items if i.get('id')]
    # 캐시 원장에는 답글(e 태그)이 있다 — 내 글을 가리키는 행 수
    rows = q(INDIENET / 'posts.db', 'select id, tags from posts')
    replies_to_me = 0
    e_tag_rows = 0
    for _id, tags in rows:
        try:
            tg = json.loads(tags or '[]')
        except Exception:
            continue
        es = [t[1] for t in tg if isinstance(t, list) and len(t) >= 2 and t[0] == 'e']
        if es:
            e_tag_rows += 1
        if any(e in my_ids for e in es):
            replies_to_me += 1
    return False, js({'my_posts': len(my_ids), 'feed_item_keys': keys_of(items),
                      'cache_rows_with_e_tag': e_tag_rows, 'cache_replies_to_my_posts': replies_to_me,
                      'reply_fields_in_items': [k for k in keys_of(items) if k in ('reply_to', 'root', 'tags', 'e', 'replies', 'reactions')]}, 600)


def t05():
    """[조건] 모르는 op 값 — 커뮤니티 네 액션(feed·follow·board·nostr)이 오타 op 를 조용히 읽기로 바꾸나 (check + 실행; 코드상 전부 읽기 갈래)."""
    out = {}
    for code in ('[others:feed]{op:"reed"}', '[others:follow]{op:"lists"}', '[others:board]{op:"remove", hashtag:"it80x"}',
                 '[others:nostr]{op:"relay"}', '[others:messages]{op:"inbox_all"}', '[others:bulletin]{op:"stat"}'):
        c = chk('return ' + code)
        row = {'check': c.get('status'), 'issues': codes(c)}
        if c.get('status') != 'invalid':
            r = ex('return ' + code, private=True)
            v = val(r) if r.get('success') else None
            row['run'] = 'ok' if r.get('success') else f"FAIL {err(r)[:160]}"
            if isinstance(v, dict):
                row['value_keys'] = sorted(v)[:12]
        out[code.split(']')[0] + ']' + code.split('op:')[1].split('"')[1]] = row
    silent = [k for k, v in out.items() if v.get('run') == 'ok']
    return not silent, js(out, 1500)


def t06():
    """[적용] 선언 밖 인자의 침묵 — feed limit:0·since·count, messages inbox search (open_params 여부에 따라)."""
    base = ex('return [others:feed]{op:"read", limit:10}', private=True)
    ids0 = [i.get('id') for i in (val(base) or {}).get('items') or []]
    out = {'limit10': len(ids0)}
    r0 = ex('return [others:feed]{op:"read", limit:0}', private=True)
    out['limit0_count'] = len((val(r0) or {}).get('items') or []) if r0.get('success') else f"FAIL {err(r0)}"
    since = int(time.time()) - 86400 * 3
    c1 = chk(f'return [others:feed]{{op:"read", limit:10, since:{since}}}')
    r1 = ex(f'return [others:feed]{{op:"read", limit:10, since:{since}}}', private=True)
    ids1 = [i.get('id') for i in (val(r1) or {}).get('items') or []]
    out['since_check'] = check_row(c1)
    out['since_same_ids_as_without'] = ids1 == ids0
    c2 = chk('return [others:feed]{op:"read", count:3}')
    r2 = ex('return [others:feed]{op:"read", count:3}', private=True)
    out['count3_check'] = check_row(c2)
    out['count3_n'] = len((val(r2) or {}).get('items') or [])
    c3 = chk('return [others:messages]{op:"inbox", search:"김"}')
    out['inbox_search_check'] = check_row(c3)
    c4 = chk('return [others:publish]{title:"IT80 미리보기", content:"# 초안", dry_run:true}')
    out['publish_dry_run_check'] = check_row(c4)
    c5 = chk('return [others:feed]{op:"post", content:"IT80 초안", preview:true}')
    out['feed_post_preview_check'] = check_row(c5)
    return False, js(out, 1500)


def t07():
    """[조회·조건] 여러 채널 받은 메시지 중 안 읽은 것만 — inbox unread>0 필터, unread 의 실제 뜻 대조(원장 read-only)."""
    r = ex("""
$m = [others:messages]{op:"inbox"}
$un = $m.items >> [table:filter]{where:($r)=> $r.unread > 0}
return {all:$m.items, un:$un}
""", private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    rows = v['all']
    dm = [x for x in rows if not x.get('is_neighbor')]
    nb = [x for x in rows if x.get('is_neighbor')]
    # 원장: 미답신 수신(replied=0, is_from_user=0) — handler docstring 의 _unread 정의
    unreplied = dict(q(BIZ, 'select neighbor_id, count(*) from messages where replied=0 and is_from_user=0 and neighbor_id is not null group by 1'))
    cols = [c[1] for c in q(BIZ, 'pragma table_info(messages)')]
    match = sum(1 for x in nb if int(x.get('unread') or 0) == int(unreplied.get(x.get('id'), 0)))
    channels = sorted({x.get('channel') for x in rows})
    detail = {'conversations': len(rows), 'neighbor_rows': len(nb), 'dm_rows(non-neighbor)': len(dm),
              'unread_gt0': len(v['un']), 'dm_unread_values': sorted({x.get('unread') for x in dm}),
              'neighbor_unread_equals_unreplied_count': f"{match}/{len(nb)}",
              'messages_table_has_read_flag': any(c in cols for c in ('read', 'is_read', 'read_at', 'seen')),
              'channels': channels, 'time_fmt_sample_ok': all(re.fullmatch(r'(\d\d/\d\d \d\d:\d\d)?', x.get('time') or '') for x in rows)}
    return False, js(detail, 900)


def t08():
    """[조회] 채널 원시 수신함 — 프로젝트 에이전트(IT80_probe)로 nostr·email 최근 3건 (신원 게이트가 어떻게 답하나)."""
    out = {}
    for code in ('[others:channel_read]{channel_type:"nostr", limit:3}', '[others:channel_read]{channel_type:"email", max_results:3}'):
        r = ex('return ' + code, private=True)
        v = val(r)
        out[code.split('"')[1]] = {'success': r.get('success'), 'err': (err(r)[:220] if not r.get('success') else None),
                                   'value_keys': sorted(v)[:12] if isinstance(v, dict) else None,
                                   'count': (v or {}).get('count') if isinstance(v, dict) else None}
    return True, js(out, 900)


def t09():
    """[조회] 블로그 최근 글 5개 + 통계 — 날짜·분류가 칸으로 오나, 조회수는 있나."""
    r = ex("""
$p = [self:blog]{op:"posts", limit:5}
$st = [self:blog]{op:"stats"}
return {p:$p, st:$st}
""", private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    p, st = v['p'], v['st']
    raw = p.get('posts') or []
    detail = {'posts_raw_keys': keys_of(raw), 'items_keys': keys_of(p.get('items')), 'n': len(p.get('items') or []),
              'items_url_sample_relative': [str(i.get('url'))[:1] for i in (p.get('items') or [])][:3],
              'stats_keys': sorted(st)[:20] if isinstance(st, dict) else None,
              'view_fields': [k for k in keys_of(raw) + (sorted(st) if isinstance(st, dict) else []) if 'view' in k.lower() or '조회' in k]}
    return True, js(detail, 900)


def t10():
    """[적용] 블로그 RSS(공개 피드) 최신 10편이 내 블로그 DB에 다 들어왔나 — url·title 두 키로 anti join."""
    r = ex("""
$rss = [sense:feed]{url:"https://irepublic.tistory.com/rss", limit:10}
$db = [self:blog]{op:"posts", limit:30}
$lt = [self:blog]{op:"latest"}
$miss_url = [table:join]{left:$rss.items, right:$db.items, on:"url", how:"anti"}
$miss_title = [table:join]{left:$rss.items, right:$db.items, on:"title", how:"anti"}
return {rss:len($rss.items), db:len($db.items), miss_by_url:len($miss_url.items), miss_by_title:len($miss_title.items),
        rss_url0:$rss.items[0].url, db_url0:$db.items[0].url, latest_url:$lt.url, latest_item_url:$lt.items[0].url}
""")
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    safe = {k: v.get(k) for k in ('rss', 'db', 'miss_by_url', 'miss_by_title')}
    safe['url_forms'] = {k: re.sub(r'\d+', 'N', str(v.get(k))) for k in ('rss_url0', 'db_url0', 'latest_url', 'latest_item_url')}
    return v.get('miss_by_url') == v.get('miss_by_title'), js(safe, 700)


def t11():
    """[조건] RSS 원천 가장자리 — limit 0(선언: 빈 결과)·HTML 주소(선언: 오류)·없는 피드(404)."""
    out = {}
    for name, code in (('limit0', 'return [sense:feed]{url:"https://irepublic.tistory.com/rss", limit:0}'),
                       ('html', 'return [sense:feed]{url:"https://irepublic.tistory.com/"}'),
                       ('404', 'return [sense:feed]{url:"https://irepublic.tistory.com/no-such-feed-it80.xml"}')):
        r = ex(code)
        v = val(r)
        out[name] = {'success': r.get('success'),
                     'n': len(v.get('items') or []) if isinstance(v, dict) else None,
                     'err': err(r)[:200] if not r.get('success') else None,
                     'code': (r.get('diagnostic') or {}).get('code') if isinstance(r.get('diagnostic'), dict) else None}
    ok = out['limit0']['success'] and out['limit0']['n'] == 0 and not out['html']['success'] and not out['404']['success']
    return ok, js(out, 900)


def t12():
    """[조회·조건] 내 웹앱(공개면) 생존 실측 — 죽은 것만, 부류별 건수 (주소는 싣지 않음)."""
    r = ex("""
$s = [self:webapp]{op:"status", timeout:4}
$dead = $s.items >> [table:filter]{where:($r)=> $r.alive == false}
$unknown = $s.items >> [table:filter]{where:($r)=> $r.alive == null}
return {all:$s.items, dead:$dead, unknown:len($unknown)}
""", private=True)
    # 첫 시도 `not $r.alive` 는 "조건에는 Bool이 필요합니다"(어느 행인지 없음)로 실패했다 — alive 가 null 인 행(주소 미상)이 있다.
    first = ex('$s = [self:webapp]{op:"status", timeout:4}\nreturn $s.items >> [table:filter]{where:($r)=> not $r.alive}', private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    from collections import Counter
    kinds = Counter(x.get('kind') for x in v['all'])
    dead_kinds = Counter(x.get('kind') for x in v['dead'])
    http = Counter(str(x.get('http')) for x in v['all'])
    return True, js({'n': len(v['all']), 'kinds': dict(kinds), 'dead': len(v['dead']), 'dead_kinds': dict(dead_kinds),
                     'alive_null': v['unknown'], 'http': dict(http), 'keys': keys_of(v['all']),
                     'first_try_not_alive': ('ok' if first.get('success') else f"FAIL {err(first)[:160]}")}, 900)


def t13():
    """[조회] 자유게시판(bulletin) 전체 — 게시판마다 detail 로 글 수·최근 7일 글 수 (detail 의 items 는 무엇인가)."""
    r = ex("""
$s = [others:bulletin]{op:"status"}
$d = $s.items >> [table:each]{ [others:bulletin]{op:"detail", board_id:$it.id} }
return {s:$s, d:$d}
""", private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    boards = v['s'].get('items') or []
    ds = v['d'] or []
    out = {'boards': len(boards), 'status_keys': keys_of(boards)}
    if ds:
        d0 = ds[0]
        out['detail_top_keys'] = sorted(d0)[:15]
        out['detail_items_is_board_row'] = keys_of(d0.get('items')) == keys_of(boards)
        out['posts_keys'] = keys_of(d0.get('posts'))
        out['posts_counts'] = [len(x.get('posts') or []) for x in ds]
        out['post_count_field'] = [b.get('post_count') for b in boards]
        allp = [p for x in ds for p in (x.get('posts') or [])]
        out['title_has_image_mark'] = sum(1 for p in allp if str(p.get('title', '')).endswith('🖼'))
        out['meta_holds_time_and_body'] = sum(1 for p in allp if ' · ' in str(p.get('meta', '')))
    return True, js(out, 900)


def t14():
    """[조회+check] 쇼케이스·포털에 올릴 항목 준비 — 읽기(폴더·바스켓·포털·진열 목록)는 실행, 담기·진열 변경은 check. 포털 상태 파일이 읽기로 바뀌나."""
    before = _fstat(FILES['portal_state'])
    r = ex("""
$sc = [others:showcase]{op:"status"}
$bk = [others:showcase]{op:"basket_list"}
$ps = [others:portal]{op:"portals"}
$dl = [others:portal]{op:"display"}
return {sc:len($sc.items), bk:len($bk.items), ps:len($ps.items), dl:len($dl.items), dl_keys:keys($dl), sc_keys:keys($sc)}
""", private=True)
    after = _fstat(FILES['portal_state'])
    out = {'read': (val(r) if r.get('success') else f"FAIL {err(r)}"),
           'portal_state_content_same': before['h'] == after['h'], 'portal_state_mtime_changed': before['mtime'] != after['mtime']}
    for name, code in (('basket_toggle', '[others:showcase]{op:"basket_toggle", basket_id:"x", folder_id:"y"}'),
                       ('showcase_add', '[others:showcase]{op:"add", path:"~/Pictures/IT80"}'),
                       ('portal_display_key', '[others:portal]{op:"display", key:"weather", set_level:"0"}'),
                       ('portal_display_list', '[others:portal]{op:"display"}'),
                       ('portal_status', '[others:portal]{op:"status"}')):
        out[name] = check_row(chk('return ' + code))
    return True, js(out, 1400)


def t15():
    """[조건] 포털 이름 오타 — 없는 포털을 지목한 읽기가 어떻게 답하나 (상태 파일 재기록 여부)."""
    before = _fstat(FILES['portal_state'])
    r = ex('return [others:portal]{op:"status", portal:"없는포털IT80"}', private=True)
    after = _fstat(FILES['portal_state'])
    return (not r.get('success')), js({'success': r.get('success'), 'err': err(r)[:260] if not r.get('success') else None,
                                        'content_same': before['h'] == after['h'], 'mtime_changed': before['mtime'] != after['mtime']}, 600)


def t16():
    """[조회] 이웃 목록 — 연락 레벨·즐겨찾기로 거르기. 행에 포털 로그인 자격(비번 해시·열쇠)이 실려 오나 (값은 싣지 않고 건수만)."""
    r = ex('return [others:neighbor]{op:"list"}', private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    rows = (val(r) or {}).get('items') or []
    cred = {}
    for k in ('portal_pw', 'portal_key', 'portal_login_id', 'warehouse_key'):
        vals = [x.get(k) for x in rows if x.get(k)]
        cred[k] = {'nonempty': len(vals),
                   'looks_masked': sum(1 for s in vals if isinstance(s, str) and ('*' in s or 'REDACT' in s.upper() or '[masked' in s)),
                   'pbkdf2_prefix': sum(1 for s in vals if isinstance(s, str) and s.startswith('pbkdf2$'))}
    # 같은 값이 실행 영수증 저장소에 남았는가 — 값 자체는 출력하지 않고 포함 여부만
    keys = [x.get('portal_key') for x in rows if x.get('portal_key') and len(str(x.get('portal_key'))) >= 16][:40]
    run_id = r.get('run_id') or (r.get('resume') or {}).get('run_id')
    hits = 0
    scanned = 0
    runs = BASE / 'data/ibl_runs'
    if keys and runs.exists():
        recent = sorted((p for p in runs.rglob('*') if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:60]
        for p in recent:
            try:
                b = p.read_text(errors='ignore')
            except Exception:
                continue
            scanned += 1
            if any(k in b for k in keys):
                hits += 1
    return False, js({'neighbors': len(rows), 'row_keys_n': len(keys_of(rows)), 'credential_columns': cred,
                      'receipt_files_scanned': scanned, 'receipt_files_containing_a_portal_key': hits,
                      'run_id_present': bool(run_id)}, 900)


def t17():
    """[조회+check] 다른 에이전트에 조사 위임 — 명부 읽기(실행) → 위임 문장 check (정확한 인자·틀린 인자·sync 결과 칸)."""
    r = ex('return [others:agents]{}', private=True)
    v = val(r) or {}
    rows = v.get('items') or []
    out = {'agents_ok': bool(r.get('success')), 'agents_n': len(rows), 'keys': keys_of(rows),
           'projects_n': len({x.get('project') for x in rows})}
    for name, code in (('delegate_ok', 'return [others:delegate]{agent_id:"컨텐츠/리서처", message:"이번 주 AI 반도체 동향 조사", mode:"sync"}'),
                       ('delegate_typo_args', 'return [others:delegate]{agent:"컨텐츠/리서처", msg:"이번 주 AI 반도체 동향 조사"}'),
                       ('delegate_no_message', 'return [others:delegate]{agent_id:"컨텐츠/리서처"}'),
                       ('delegate_sync_field', '$r = [others:delegate]{agent_id:"컨텐츠/리서처", message:"조사", mode:"sync"}\nreturn $r.response'),
                       ('delegate_bad_mode', 'return [others:delegate]{agent_id:"컨텐츠/리서처", message:"조사", mode:"sinc"}'),
                       ('ask_dry_run', 'return [others:ask]{message:"사진 폴더 용량 알려줘", dry_run:true}')):
        out[name] = check_row(chk(code))
    return True, js(out, 1600)


def t18():
    """[check] 발행 전 미리보기·검수 → 발행, 실패하면 파일로 폴백 — 문서 산출 >> publish, publish ?? write, feed post ?? notify."""
    out = {}
    for name, code in (
        ('doc_pipe_publish', '$d = [table:document]{format:"markdown", title:"IT80 이웃 소식", blocks:[{type:"paragraph", text:"본문"}]}\nreturn $d >> [others:publish]{title:"IT80 이웃 소식"}'),
        ('doc_field_publish', '$d = [table:document]{format:"markdown", title:"IT80 이웃 소식", blocks:[{type:"paragraph", text:"본문"}]}\nreturn [others:publish]{title:"IT80 이웃 소식", content:$d.markdown}'),
        ('publish_fallback_write', 'return [others:publish]{title:"IT80", content:"# 초안"} ?? [self:write]{path:"outputs/IT80_publish_fallback.md", content:"# 초안"}'),
        ('try_publish_catch', '[try] { $u = [others:publish]{title:"IT80", content:"# 초안"} } [catch] { $u = {url:null, error:$error.message} }\nreturn $u.url'),
        ('feed_post_fallback_notify', 'return [others:feed]{op:"post", content:"IT80"} ?? [self:notify_user]{message:"게시 실패"}'),
        ('family_publish', 'return [others:family_news]{op:"publish"}'),
        ('publish_url_field', '$u = [others:publish]{title:"IT80", content:"# 초안"}\nreturn $u.url'),
    ):
        out[name] = check_row(chk(code))
    return True, js(out, 1600)


def t19():
    """[check] 부작용 사전 판정 격자 — 같은 액션의 읽기 op vs 쓰기 op 가 check effects 에서 구별되나 + 옛 검수기(/ibl/validate)의 판정."""
    pairs = [
        ('feed', '[others:feed]{op:"read"}', '[others:feed]{op:"post", content:"x"}'),
        ('board', '[others:board]{op:"list"}', '[others:board]{op:"delete", hashtag:"x"}'),
        ('follow', '[others:follow]{op:"list"}', '[others:follow]{op:"add", pubkey:"npub1x"}'),
        ('nostr', '[others:nostr]{op:"profile"}', '[others:nostr]{op:"reset_identity"}'),
        ('neighbor', '[others:neighbor]{op:"list"}', '[others:neighbor]{op:"delete", id:1}'),
        ('bulletin', '[others:bulletin]{op:"status"}', '[others:bulletin]{op:"delete", board_id:"x"}'),
        ('family_news', '[others:family_news]{op:"status"}', '[others:family_news]{op:"delete", edition_id:"x", force:true}'),
        ('portal', '[others:portal]{op:"portals"}', '[others:portal]{op:"revoke", member_id:"m1"}'),
        ('showcase', '[others:showcase]{op:"status"}', '[others:showcase]{op:"basket_delete", basket_id:"x"}'),
        ('blog', '[self:blog]{op:"posts"}', '[self:blog]{op:"rebuild_index"}'),
        ('webapp', '[self:webapp]{op:"list"}', '[self:webapp]{op:"remove", name:"x"}'),
        ('messages', '[others:messages]{op:"inbox"}', '[others:channel_send]{channel_type:"email", to:"나", subject:"x", body:"y"}'),
        ('publish', '[others:agents]{}', '[others:publish]{title:"x", content:"y"}'),
        ('delegate', '[sense:feed]{url:"https://example.com/rss"}', '[others:delegate]{agent_id:"a", message:"m"}'),
    ]
    out = {}
    for name, rd, wr in pairs:
        a, b = chk('return ' + rd), chk('return ' + wr)
        va = post('ibl/validate', {'code': rd})
        vb = post('ibl/validate', {'code': wr})
        out[name] = {'read': (a.get('status'), a.get('effects')), 'write': (b.get('status'), b.get('effects')),
                     'validate_read': {k: va.get(k) for k in ('valid', 'side_effect', 'has_side_effect', 'side_effects') if k in va},
                     'validate_write': {k: vb.get(k) for k in ('valid', 'side_effect', 'has_side_effect', 'side_effects') if k in vb}}
    distinguished = [k for k, v in out.items() if v['read'][1] != v['write'][1]]
    return False, js({'distinguished_by_check': distinguished, 'grid': out}, 4000)


def t20():
    """[check] 코퍼스 용례 — 축 18액션의 교재 용례를 판본 2 check 로(상태·오류 부류)."""
    acts = ['others:feed', 'others:board', 'others:follow', 'others:nostr', 'others:publish', 'others:messages',
            'others:channel_read', 'others:neighbor', 'others:agents', 'others:delegate', 'others:ask', 'others:bulletin',
            'others:portal', 'others:showcase', 'others:family_news', 'self:blog', 'self:webapp', 'sense:feed']
    db = sqlite3.connect(f'file:{BASE / "data/ibl_usage.db"}?mode=ro', uri=True)
    ids = {}
    for a in acts:
        for i, c in db.execute("select id, ibl_code from ibl_examples where ibl_code like ?", (f'%[{a}]%',)):
            ids[i] = c
    from collections import Counter
    st, ic, wc, per = Counter(), Counter(), Counter(), Counter()
    samples = {}
    for i, c in sorted(ids.items()):
        payload = dict(code='#!ibl edition=2\n' + c, edition=2, check=True, project_id='컨텐츠', origin='training', **AGENT)
        rr = post('ibl/execute', payload)
        st[rr.get('status')] += 1
        for x in rr.get('issues') or []:
            ic[x.get('code')] += 1
            if x.get('code') not in samples:
                samples[x.get('code')] = (i, (x.get('message') or '')[:140])
        for x in rr.get('warnings') or []:
            wc[x.get('code')] += 1
        if rr.get('status') == 'invalid':
            for a in acts:
                if f'[{a}]' in c:
                    per[a] += 1
    return st.get('invalid', 0) == 0, js({'n': len(ids), 'status': dict(st), 'issues': dict(ic), 'warnings': dict(wc),
                                          'invalid_by_action': dict(per), 'samples': samples}, 2500)


def t21():
    """[조건] 실패 봉투 세 모양이 판본 2·폴백·건강 원장에 어떻게 닿나 — {error} 만(success 없음)·{success:false,message}·정상."""
    out = {}
    # ① {error:...} 만 — channel_engine 채널 해소 실패(읽기 경로): to 만 주고 channel_type 없음
    a = ex('return [others:channel_read]{to:"IT80_없는사람"}', private=True)
    out['error_only'] = {'success': a.get('success'), 'err': err(a)[:200]}
    a2 = ex('return [others:channel_read]{to:"IT80_없는사람"} ?? "폴백됨"', private=True)
    out['error_only_fallback'] = val(a2) if a2.get('success') else f"FAIL {err(a2)[:160]}"
    # ② {success:false, message:...} — items() 실패 봉투(error 칸 없음): 없는 판 상세
    b = ex('return [others:family_news]{op:"detail", edition_id:"IT80_없는판"}')
    out['success_false_message'] = {'success': b.get('success'), 'err': err(b)[:220]}
    b2 = ex('[try] { $x = [others:family_news]{op:"detail", edition_id:"IT80_없는판"} } [catch] { $x = {code:$error.code, msg:$error.message} }\nreturn $x')
    out['success_false_message_catch'] = val(b2) if b2.get('success') else f"FAIL {err(b2)[:160]}"
    c = ex('return [others:bulletin]{op:"detail", board_id:"IT80_없는게시판"}')
    out['bulletin_missing'] = {'success': c.get('success'), 'err': err(c)[:220]}
    time.sleep(1)
    rows = q(PULSE, "select node||':'||action, success, shape, substr(coalesce(error,''),1,60) from action_health where source='training' and id > ? order by id",
             (START_AH,))
    out['action_health_tail'] = [r for r in rows if r[0] in ('others:channel_read', 'others:family_news', 'others:bulletin')][-6:]
    return False, js(out, 1600)


def t22():
    """[조회·적용] 나를 팔로우한/내가 팔로우한 사람 → 이웃 승격 다리 — follow list × neighbor list × messages inbox (건수만)."""
    r = ex("""
$fo = [others:follow]{op:"list"}
$nb = [others:neighbor]{op:"list"}
$ib = [others:messages]{op:"inbox"}
$nostr_nb = $ib.items >> [table:filter]{where:($r)=> $r.channel == "nostr" and $r.is_neighbor == 1}
$peers = $ib.items >> [table:filter]{where:($r)=> $r.is_indiebiz_peer == 1}
return {follows:len($fo.items), follow_keys:keys($fo), neighbors:len($nb.items), inbox:len($ib.items),
        nostr_neighbors:len($nostr_nb), peers:len($peers)}
""", private=True)
    return bool(r.get('success')), (js({k: v for k, v in (val(r) or {}).items()}, 500) if r.get('success') else f"FAIL {err(r)}")


def t23():
    """[시간] 매주 월요일 아침, 지난 1주 이웃 소식이 있으면 나에게 요약 알림 (trigger create check — do 안 문장의 feed 시간 거르기)."""
    do = "$f = [others:feed]{op:\\\"read\\\", limit:50}; $n = len($f.items); [if: $n > 0] { [self:notify_user]{message:f\\\"이웃 소식 ${$n}건\\\"} }"
    c = chk('return [self:trigger]{op:"create", name:"IT80_이웃소식", cron:"0 8 * * 1", do:"' + do + '"}')
    c2 = chk("return [self:trigger]{op:\"create\", name:\"IT80_이웃소식\", cron:\"0 8 * * 1\", do:'$f = [others:feed]{op:\"read\", limit:50}; return len($f.items)'}")
    inner = chk('$f = [others:feed]{op:"read", limit:50}\n$n = len($f.items)\n[if: $n > 0] { [self:notify_user]{message:f"이웃 소식 ${$n}건"} }')
    return True, js({'trigger_check': check_row(c), 'trigger_check_single_quoted_do': check_row(c2), 'inner_check': check_row(inner)}, 800)


def t24():
    """[조회] 블로그 검색 — 폴더(category) 안·밖 두 번, limit·category 목록 (가이드 실무 순서)."""
    r = ex("""
$in = [self:blog]{op:"search", query:"인공지능 교육", category:"인공지능에 대한 글", limit:5}
$all = [self:blog]{op:"search", query:"인공지능 교육", limit:5}
$lst = [self:blog]{op:"search", query:"인공지능 교육", category:["인공지능에 대한 글","없는폴더IT80"], limit:5}
$bad = [self:blog]{op:"search", query:"인공지능 교육", category:"없는폴더IT80", limit:5}
return {in:len($in.items), all:len($all.items), lst:len($lst.items), bad:len($bad.items), bad_msg:get($bad, "message", null),
        in_keys:keys($in), meta0:$all.items[0].meta}
""")
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    safe = {k: v.get(k) for k in ('in', 'all', 'lst', 'bad', 'bad_msg', 'in_keys')}
    safe['meta0_shape'] = re.sub(r'[가-힣A-Za-z]+', 'W', str(v.get('meta0')))[:60]
    return v.get('bad', 0) == 0, js(safe, 700)


def t25():
    """[판본 1 대조] 저장 프로그램·스케줄 호환 판본에서 오타 op — 판본 2 는 거절(t05), 판본 1 은? + feed limit:3 이 지켜지나."""
    out = {}
    for code in ('[others:feed]{op: "reed"}', '[others:follow]{op: "lists"}', '[others:nostr]{op: "relay"}'):
        payload = dict(code=code, edition=1, project_id='컨텐츠', origin='training', **AGENT)
        rr = post('ibl/execute', payload)
        LOG.append({'request': payload, 'response': rr, 'private': True})
        res = rr.get('result') if isinstance(rr.get('result'), dict) else rr
        out[code.split('"')[1]] = {'success': rr.get('success'), 'result_keys': sorted(res)[:10] if isinstance(res, dict) else None,
                                   'warn': str(rr.get('param_warning') or (res or {}).get('param_warning') or '')[:160]}
    r3 = ex('return [others:feed]{op:"read", limit:3}', private=True)
    out['limit3_n'] = len((val(r3) or {}).get('items') or [])
    silent = [k for k, v in out.items() if isinstance(v, dict) and v.get('success')]
    return not silent, js(out, 1000)


def t00():
    return True, 'noop'


TASKS = []
START_AH = 0


def _collect():
    global TASKS
    TASKS = [globals()[n] for n in sorted(globals()) if n.startswith('t') and n[1:].isdigit() and n != 't00']


def run():
    global START_AH
    _collect()
    base = json.loads((HERE / 'baseline.json').read_text())
    START_AH = base['baseline']['action_health_max_id']
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
        except Exception as exc:
            ok, detail = False, f'probe error: {type(exc).__name__}: {exc}'
        rows[task.__name__] = {'task': task.__name__, 'intent': task.__doc__, 'ok': bool(ok), 'detail': detail,
                               'at': started}
        store['log'] = [e for e in store['log'] if e.get('task') != task.__name__]
        mask_log()
        store['log'].extend({'task': task.__name__, **e} for e in LOG)
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:2500], flush=True)
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
    r = ex(sys.argv[2], private='--private' in sys.argv, **extra)
    if '--private' in sys.argv:
        mask_log(); print(json.dumps(LOG[-1]['response'], ensure_ascii=False, indent=1)[:6000]); return
    print(json.dumps({k: v for k, v in r.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')},
                     ensure_ascii=False, indent=1, default=str)[:12000])


def _fstat(p):
    p = Path(p)
    if not p.exists():
        return None
    return {'size': p.stat().st_size, 'mtime': p.stat().st_mtime, 'h': h(p.read_bytes())}


def _tree(root):
    root = Path(root)
    if not root.exists():
        return None
    fs = [f for f in root.rglob('*') if f.is_file()]
    return {'files': len(fs), 'h': h(sorted((str(f.relative_to(root)), f.stat().st_size) for f in fs))}


def stores():
    my = q(INDIENET / 'identity.json', 'select 1') if False else None  # noqa
    out = {k: _fstat(p) for k, p in FILES.items()}
    out['bulletin_tree'] = _tree(BASE / 'data/bulletin')
    out['family_news_tree'] = _tree(BASE / 'data/family_news')
    out['biz'] = {t: q(BIZ, f'select count(*), max(id) from {t}')[0] for t in ('messages', 'neighbors', 'contacts')}
    out['posts_db'] = q(INDIENET / 'posts.db', 'select count(*), max(created_at) from posts')[0]
    out['dms_db'] = q(INDIENET / 'dms.db', 'select count(*) from dms')[0]
    out['tasks'] = {d: q(BASE / f'data/{d}', 'select count(*) from tasks')[0][0]
                    for d in ('conversation.db', 'conversations.db', 'system_ai_memory.db')}
    out['sysai_conversations'] = q(BASE / 'data/system_ai_memory.db', 'select count(*), max(rowid) from conversations')[0]
    out['blog_posts'] = q(BLOGDB, 'select count(*) from posts')[0][0] if BLOGDB.exists() else None
    out['ibl_examples'] = q(BASE / 'data/ibl_usage.db', 'select count(*), max(id) from ibl_examples')[0]
    out['episode_log_max'] = q(PULSE, 'select max(rowid) from episode_log')[0][0]
    out['scratch_IT80'] = sorted(p.name for p in (BASE / 'projects/컨텐츠/outputs').glob('IT80*'))
    return out


def snapshot():
    notes = post('notifications?limit=100', method='GET')
    return {
        'at': datetime.now().isoformat(timespec='seconds'),
        'notifications': [{k: n.get(k) for k in ('id', 'type', 'created_at')} for n in notes['notifications']],
        'action_health_max_id': q(PULSE, 'select max(id) from action_health')[0][0],
        'notify_log_max_id': q(PULSE, 'select max(id) from notify_log')[0][0],
        'stores': stores(),
    }


def baseline():
    (HERE / 'baseline.json').write_text(json.dumps({'baseline': snapshot()}, ensure_ascii=False, indent=1))
    print('baseline saved')


def after():
    base = json.loads((HERE / 'baseline.json').read_text())
    b = base['baseline']
    a = snapshot()
    norm = lambda x: json.loads(json.dumps(x))  # noqa: E731
    diff = {
        'notifications_added': [n for n in a['notifications'] if n['id'] not in {x['id'] for x in b['notifications']}],
        'action_health_by_source': q(PULSE, 'select source, coalesce(channel,""), count(*) from action_health where id > ? group by 1, 2',
                                     (b['action_health_max_id'],)),
        'action_health_training_by_action': q(PULSE, "select node||':'||action, count(*), sum(success) from action_health where id > ? and source='training' group by 1 order by 2 desc",
                                              (b['action_health_max_id'],)),
        'notify_log_new': q(PULSE, 'select id, emitter, source from notify_log where id > ?', (b['notify_log_max_id'],)),
        'stores_changed': {k: [b['stores'].get(k), norm(a['stores'].get(k))] for k in a['stores']
                           if norm(a['stores'].get(k)) != b['stores'].get(k)},
    }
    base['after'] = {'snapshot': {k: a[k] for k in ('at', 'action_health_max_id', 'notify_log_max_id')}, 'diff': diff}
    (HERE / 'baseline.json').write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(json.dumps(diff, ensure_ascii=False, indent=1, default=str)[:8000])


if __name__ == '__main__':
    {'baseline': baseline, 'run': run, 'after': after, 'raw': raw, 'desc': desc}[sys.argv[1]]()
