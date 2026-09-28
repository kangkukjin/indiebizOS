"""81회차: 미디어 제작 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 미디어 어휘(engines:tts·render·image_read·web·web_site·web_component,
self:photo·music·slide·deck·lecture, limbs:music·radio·radio_favorite, sense:radio)를 table:filter·each·groupby·
select·take·[if]·[try]·?? 와 조합. engines:remotion·newspaper 는 describe 결과 비활성("사용 가능한 액션이 아닙니다") — 제외.
도메인: 강의 슬라이드 한 장에 내 목소리 나레이션, 가족신문 사진 고르기(날짜·장소별), 사진 속 글자 읽기,
유튜브 영상용 짧은 렌더(썸네일), 블로그 글을 한 페이지 웹으로, 강의 자료 웹 컴포넌트, 분위기별 재생목록, 라디오 즐겨찾기.

모든 요청 edition 2·project_id 컨텐츠·origin training·agent_id IT81_probe·task_id IT81_task.
★부작용·비용 규칙: 산출물은 projects/컨텐츠/outputs/IT81_* 스크래치에만 — 끝에 삭제(clean). 배포·발행·업로드·재생·화면
  표시·창 열기는 check 만. TTS 는 edge(무과금) 1회, image_read(비전 AI) 1회, slide create·deck video·나레이션생성(GPU) 은
  check 만. 사진·음악 라이브러리는 읽기만.
★개인정보: 사진 경로·파일명·장소·기종, 음악 제목·아티스트·경로, 즐겨찾기 방송국은 before.json 에 모양(shape)만
  (private=True). detail 에는 건수·필드 이름·불리언·시각 차이만.
사용: .venv/bin/python probe.py baseline | run [tNN ...] | after | clean | raw '<code>' [--check] [--private] | desc node:action ...
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
AGENT = {'agent_id': 'IT81_probe', 'task_id': 'IT81_task'}
LOG = []
PULSE = BASE / 'data/world_pulse.db'
OUT = BASE / 'projects/컨텐츠/outputs'
ROOT_OUT = BASE / 'outputs'
MUSIC = BASE / 'data/music'
FILES = {
    'playlists': MUSIC / 'playlists.json',
    'music_sources': MUSIC / 'sources.json',
    'music_scan_state': MUSIC / 'scan_state.json',
    'radio_favorites': BASE / 'data/packages/installed/tools/radio/data/favorites.json',
    'web_sites': BASE / 'data/packages/installed/tools/web-builder/sites.json',
    'voices': BASE / 'data/voice/voices.json',
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
# ★반환 detail 은 before.json rows 에 그대로 저장된다 — 개인 원문·경로·이름을 담지 말 것.

def full_rows(code):
    """큰 결과 — value 는 표시 요약이라 read_result 로 전량 회수(JSON 텍스트 연결)."""
    r = ex(code, private=True)
    if not r.get('success'):
        return r, None
    ra = dict((r.get('result_ref') or {}).get('read_args') or {})
    if not ra:
        return r, r.get('value')
    ra['path'] = ['value']
    texts = []
    while True:
        rr = post('ibl/execute', dict(code='', read_result=ra, edition=2, project_id='컨텐츠', origin='training', **AGENT))
        texts.append(rr.get('text') or '')
        if not rr.get('next_read'):
            break
        ra = rr['next_read']
    return r, json.loads(''.join(texts))


def sips_local(path):
    s = subprocess.run(['sips', '-g', 'creation', path], capture_output=True, text=True).stdout
    m = re.search(r'creation:\s*(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)', s)
    return datetime(*map(int, m.groups())) if m else None


def ffprobe(path):
    p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,format_name:stream=codec_name,sample_rate,channels',
                        '-of', 'json', path], capture_output=True, text=True)
    info = json.loads(p.stdout or '{}')
    vd = subprocess.run(['ffmpeg', '-hide_banner', '-i', path, '-af', 'volumedetect', '-f', 'null', '-'],
                        capture_output=True, text=True).stderr
    mean = re.search(r'mean_volume: (-?[\d.]+) dB', vd)
    mx = re.search(r'max_volume: (-?[\d.]+) dB', vd)
    sil = subprocess.run(['ffmpeg', '-hide_banner', '-i', path, '-af', 'silencedetect=noise=-40dB:d=0.5', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    return {'format': (info.get('format') or {}).get('format_name'),
            'duration': round(float((info.get('format') or {}).get('duration') or 0), 2),
            'streams': info.get('streams'), 'mean_db': float(mean.group(1)) if mean else None,
            'max_db': float(mx.group(1)) if mx else None, 'silences': sil.count('silence_start')}


LECTURE = 'ai-sidae-jedoboda-meonjeo-pilyohan-geos'


def t01():
    """[조회] 강의 목록 → 강의마다 노트 있는 장·이미 구운 내 목소리 나레이션(narration/<slide_id>.wav) → '아직 구울 장' 집계."""
    r = ex("""
$l = [self:lecture]{op:"list"}
$rows = $l.lectures >> [table:each]{
  $d = [self:lecture]{op:"load", lecture_id:$it.lecture_id}
  $noted = $d.items >> [table:filter]{where:($r)=> len($r.speaker_note) > 0}
  [try] { $w = [self:list]{path:f"${$d.lecture_dir}/narration", pattern:"*.wav"} } [catch] { $w = [] }
  $wids = $w >> [table:compute]{set:($r)=> {slide_id:replace($r.name, ".wav", "")}}
  $need = [table:join]{left:$noted, right:$wids, on:"slide_id", how:"anti"}
  return {slides:len($d.items), noted:len($noted), baked:len($w), need:len($need.items)}
}
return {items_keys:keys($l.items[0]), lectures_keys:keys($l.lectures[0]), per:$rows}
""", private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    per = v['per']
    detail = {'items_row_keys': v['items_keys'], 'lectures_row_keys': v['lectures_keys'],
              'items_has_lecture_id': 'lecture_id' in v['items_keys'], 'lectures': len(per),
              'noted_total': sum(p['noted'] for p in per), 'baked_total': sum(p['baked'] for p in per),
              'need_total': sum(p['need'] for p in per), 'per_shape': [[p['slides'], p['noted'], p['baked'], p['need']] for p in per]}
    return detail['items_has_lecture_id'], js(detail, 900)


def t02():
    """[적용] 슬라이드 한 장 노트 앞부분을 시험 나레이션으로(edge, 무과금) → 영상용 폴더에 → 길이·무음 판정 (TTS 1회)."""
    r = ex(f"""
$d = [self:lecture]{{op:"load", lecture_id:"{LECTURE}"}}
$s = $d.items >> [table:filter]{{where:($r)=> len($r.speaker_note) > 20}} >> [table:take]{{n:1}}
$txt = $s[0].speaker_note[0:60]
$t = [engines:tts]{{text:$txt, engine:"edge", output_filename:"IT81_narr/IT81_s1.mp3"}}
return {{t:$t, chars:len($txt)}}
""", private=True)
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    t = v['t']
    m = re.search(r'TTS 생성 완료: (\S+\.mp3)', t) if isinstance(t, str) else None
    path = m.group(1) if m else None
    out = {'result_type': type(t).__name__, 'chars': v['chars'],
           'structured_path': isinstance(t, dict) and 'path' in t,
           'landed_in': (str(Path(path).parent.relative_to(BASE)) if path else None),
           'asked_dir_kept': bool(path) and Path(path).parent.name == 'IT81_narr',
           'result_text_shape': re.sub(r'/\S+', '<path>', t) if isinstance(t, str) else None}
    if path and Path(path).exists():
        out['audio'] = ffprobe(path)
    ok = out['structured_path'] and out['asked_dir_kept'] and (out.get('audio') or {}).get('duration', 0) > 1
    return ok, js(out, 1200)


def t03():
    """[조회·check] '내 목소리로' — engines:tts 의 engine 선택지에 사용자 목소리가 있나, 없으면 길을 말하나 + 나레이션생성·deck video check."""
    a = ex('[try] { $t = [engines:tts]{text:"안녕하세요", engine:"qwen3", voice:"kkj3", output_filename:"IT81_q.mp3"}\n return {ok:true} } [catch] { return {ok:false, code:$error.code, msg:$error.message} }')
    b = ex('[try] { $t = [engines:tts]{text:"안녕하세요", engine:"edge", rate:0.9, output_filename:"IT81_r.mp3"}\n return {ok:true} } [catch] { return {ok:false, code:$error.code, msg:$error.message} }')
    c1 = chk('[engines:tts]{text:"안녕하세요", engine:"qwen3", voice:"kkj3"}')
    c2 = chk(f'[self:script]{{op:"run", id:"나레이션생성", args:{{lecture_id:"{LECTURE}", voice:"kkj3"}}}}')
    c3 = chk(f'[self:deck]{{op:"video", lecture_id:"{LECTURE}", engine:"qwen3", captions:true}}')
    va, vb = val(a) or {}, val(b) or {}
    out = {'qwen3_exec': va, 'rate_number_exec': vb,
           'qwen3_msg_mentions_script': '나레이션생성' in str(va.get('msg')),
           'check_tts_qwen3': check_row(c1), 'check_script': check_row(c2), 'check_deck_video_engine_qwen3': check_row(c3),
           'stray_files': sorted(p.name for p in OUT.glob('IT81_[qr]*'))}
    ok = out['qwen3_msg_mentions_script'] and 'invalid' in (c1.get('status'), c3.get('status'))
    return ok, js(out, 1600)


def t04():
    """[조회] 가족신문 사진 고르기 — '최근 사진' 100장 중 진짜 사진(기종·위치)이 몇 장인가, 기본 호출은 성공하나."""
    d = ex('[try] { $p = [self:photo]{}\n return {ok:true, n:len($p.items)} } [catch] { return {ok:false, code:$error.code, pt:$error.partial.total, pn:len($error.partial.items)} }')
    r = ex("""
$total = null
[try] { $p = [self:photo]{kind:"photo", limit:100}
 $rows = $p.items; $failed = false } [catch] { $rows = $error.partial.items; $failed = true; $total = $error.partial.total }
$own = $rows >> [table:filter]{where:($r)=> contains($r.path, "/Desktop/AI/")}
$cam = $rows >> [table:filter]{where:($r)=> len($r.camera) > 0}
$gps = $rows >> [table:filter]{where:($r)=> has($r, "lat")}
return {n:len($rows), failed:$failed, total:$total, own_workspace:len($own), camera:len($cam), gps:len($gps)}
""", private=True)
    v = val(r) or {}
    out = {'default_call': val(d), 'recent100': v}
    return (not v.get('failed')) and v.get('camera', 0) > 0, js(out, 700)


def t05():
    """[조회] 사진 날짜별 — 위치 있는 사진 전부를 '찍은 날'로 묶기, 그날만 거르기 — taken_at 이 EXIF 현지 시각과 같은가."""
    r, rows = full_rows('$p = [self:photo]{has_gps:true, limit:400}\nreturn $p.items >> [table:select]{columns:["path","taken_at","month"]}')
    if rows is None:
        return False, f"FAIL {err(r)}"
    local = {x['path']: sips_local(x['path']) for x in rows}
    offs = {}
    for x in rows:
        e = local[x['path']]
        if e:
            k = round((e - datetime.fromisoformat(x['taken_at'][:19])).total_seconds() / 3600, 1)
            offs[str(k)] = offs.get(str(k), 0) + 1
    date_diff = sum(1 for x in rows if local[x['path']] and local[x['path']].date().isoformat() != x['taken_at'][:10])
    days = sorted({local[x['path']].date().isoformat() for x in rows
                   if local[x['path']] and local[x['path']].date().isoformat() != x['taken_at'][:10]})[:4]
    filt = []
    for i, dday in enumerate(days):
        rr, got = full_rows(f'$p = [self:photo]{{has_gps:true, start:"{dday}", end:"{dday}", limit:400}}\nreturn $p.items >> [table:select]{{columns:["path"]}}')
        got = {g['path'] for g in (got or [])}
        expect = {p for p, e in local.items() if e and e.date().isoformat() == dday}
        filt.append({'day': f'D{i}', 'expected_local': len(expect), 'returned': len(got), 'missing': len(expect - got),
                     'extra': len(got - expect)})
    out = {'rows': len(rows), 'exif_local_minus_taken_at_hours': offs, 'tz_suffix_rows': sum(1 for x in rows if len(x['taken_at']) > 19),
           'date_label_differs': date_diff, 'day_filter': filt}
    return date_diff == 0 and all(f['missing'] == 0 for f in filt), js(out, 900)


def t06():
    """[조회] 사진 장소별 — 위치 사진을 좌표 격자(0.1도)로 묶어 '장소 수'·가장 많이 찍은 곳 건수 (+ check 가 lat/lng 를 아는가)."""
    c = chk('$p = [self:photo]{has_gps:true, limit:400}\n$p.items >> [table:filter]{where:($r)=> $r.lat > 36.0}')
    r = ex("""
$p = [self:photo]{has_gps:true, limit:400}
$g = $p.items >> [table:compute]{set:($r)=> {cell:f"${round($r.lat, 1)},${round($r.lng, 1)}"}} >> [table:groupby]{by:"cell"}
$top = $g.items >> [table:sort]{by:"count", descending:true} >> [table:take]{n:3}
return {n:len($p.items), cells:len($g.items), top_counts:$top >> [table:select]{columns:["count"]}}
""", private=True)
    v = val(r) or {}
    out = {'check_lat_filter': check_row(c), 'result': v if r.get('success') else f"FAIL {err(r)}"}
    return 'UNOBSERVED_FIELD' not in (c.get('warnings') and wcodes(c) or []) and bool(r.get('success')), js(out, 800)


def t07():
    """[조회·조건] self:photo kind 값 영역 — '사진'·'photos'(자연어) vs 'image'·'audio'·'pdf'(선언 밖) — 무엇이 오나, check 는 말하나."""
    out = {}
    for k in ('사진', 'photos', 'image', 'audio', 'pdf'):
        r = ex(f"""
[try] {{ $p = [self:photo]{{kind:"{k}", limit:30}}
 $rows = $p.items; $f = false; $tot = get($p, "total", null) }} [catch] {{ $rows = $error.partial.items; $f = true; $tot = $error.partial.total }}
$ext = ($rows >> [table:compute]{{set:($r)=> {{ext:lower(split($r.path, ".")[-1])}}}} >> [table:groupby]{{by:"ext"}}).items
return {{n:len($rows), total:$tot, partial:$f, exts:$ext}}
""", private=True)
        c = chk(f'[self:photo]{{kind:"{k}", limit:30}}')
        out[k] = {'r': val(r) if r.get('success') else f"FAIL {err(r)}", 'check': check_row(c)}
    bad = [k for k in ('사진', 'photos') if (out[k]['r'] or {}).get('n') == 0 and out[k]['check']['status'] != 'invalid']
    leak = [k for k in ('audio', 'pdf') if (out[k]['r'] or {}).get('n', 0) > 0]
    out['silent_zero'] = bad
    out['non_photo_returned'] = leak
    return not bad and not leak, js(out, 1500)


def t08():
    """[적용] 사진 속 글자 읽기 — 글자를 아는 이미지를 렌더해 image_read 로 읽고 정답과 대조 (render >> each image_read, 비전 1회)."""
    html = ('<html><body style="margin:0;background:#fff"><div style="font-family:sans-serif;padding:40px">'
            '<h1 style="font-size:48px">가족신문 10월호</h1><p style="font-size:32px">청주 나들이 2026-10-03 · 참가 7명</p>'
            '<p style="font-size:28px">AI 강의 3강: 언어의 경계</p></div></body></html>')
    r = ex("""
$r = [engines:render]{html:$html, viewports:["900x400"], full_page:false, output_path:"IT81_ocr"}
$o = $r.items >> [table:each]{ [engines:image_read]{op:"read", image_path:$it.path, question:"이미지 안의 글자를 줄마다 그대로 적어 주세요."} }
return {render:$r.items[0], ocr:$o}
""", inputs={'html': html})
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    ocr = v['ocr'][0] if isinstance(v['ocr'], list) else v['ocr']
    txt = json.dumps(ocr, ensure_ascii=False)
    truth = ['가족신문 10월호', '2026-10-03', '참가 7명', '언어의 경계']
    hits = {t: (t in txt) for t in truth}
    out = {'ocr_type': type(ocr).__name__, 'ocr_keys': sorted(ocr) if isinstance(ocr, dict) else None, 'hits': hits,
           'ocr_text_head': txt[:300], 'render_path_dir': str(Path(v['render'].get('path', '') if isinstance(v['render'], dict) else '').parent)}
    return all(hits.values()), js(out, 1200)


def t09():
    """[조건] 렌더 검수 비용 계층 — 빈 화면을 렌더하면 prescreen 이 걸리고, 걸린 행은 비전 호출 없이 critic 실패 verdict 가 나오는가."""
    r = ex("""
$r = [engines:render]{html:"<html><body style='background:#fff'></body></html>", viewports:["600x300"], full_page:false, output_path:"IT81_blank"}
$v = $r.items >> [table:each]{ [engines:image_read]{op:"critic", image_path:$it.path, intent:"강의 표지", prescreen:$it.prescreen} }
return {flagged:$r.prescreen_flagged, pre:$r.items[0].prescreen, verdict:$v}
""")
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    vd = v['verdict'][0] if isinstance(v['verdict'], list) else v['verdict']
    msg = (vd or {}).get('message', '') if isinstance(vd, dict) else ''
    m = re.search(r'verdict_json: (\{.*\})', msg)
    inner = json.loads(m.group(1)) if m else {}
    out = {'flagged': v['flagged'], 'prescreen_nonempty': bool(v['pre']), 'verdict_keys': sorted(vd) if isinstance(vd, dict) else type(vd).__name__,
           'passed_field': (vd or {}).get('passed') if isinstance(vd, dict) else None,
           'verdict_json_in_message': bool(m), 'embedded': inner}
    out['passed'] = out['passed_field']; out['tier'] = (vd or {}).get('tier') if isinstance(vd, dict) else None
    return out['flagged'] == 1 and out['passed'] is False and out['tier'] == 'prescreen', js(out, 600)


def t10():
    """[적용] 블로그 최근 글을 한 페이지 웹으로 — 설명이 가르친 파이프(latest >> read >> document) 그대로, 안 되면 명시 인자로 → 렌더해 눈으로 판정."""
    c = chk('[self:blog]{op:"latest"} >> [self:read]{} >> [table:document]{format:"html", filename:"IT81_blog"}')
    r = ex("""
$l = [self:blog]{op:"latest"}
$t = [self:read]{path:$l.path}
$d = [table:document]{format:"html", filename:"IT81_blog", title:$l.title, markdown:$t.text}
$r = [engines:render]{path:$d.path, viewports:["1280x900","390x844"], output_path:"IT81_blog"}
return {pub_date:$l.pub_date, blocks:$d.blocks, doc_dir:$d.path, rows:$r.items >> [table:select]{columns:["label","width","height","path","prescreen"]}}
""")
    v = val(r) or {}
    out = {'described_pipe_check': check_row(c), 'described_pipe_issue': [i.get('message') for i in c.get('issues') or []],
           'explicit': {'ok': bool(r.get('success')), 'pub_date': v.get('pub_date'), 'blocks': v.get('blocks'),
                        'doc_dir': str(Path(v.get('doc_dir', '')).parent.relative_to(BASE)) if v.get('doc_dir') else None,
                        'png_dirs': sorted({str(Path(x['path']).parent.relative_to(BASE)) for x in v.get('rows') or []}),
                        'sizes': [[x['label'], x['width'], x['height'], x['prescreen']] for x in v.get('rows') or []]}}
    return c.get('status') != 'invalid' and bool(r.get('success')), js(out, 1000)


def t11():
    """[적용] 유튜브 영상 썸네일(1280x720) — 제목 글자 + 로컬 사진 한 장(절대경로, base_path 없이) → prescreen·눈으로 판정."""
    img = str(BASE / 'outputs/IT81_ocr.png')
    html = ('<html><body style="margin:0;width:1280px;height:720px;background:#1b2330;color:#fff;font-family:sans-serif">'
            f'<img src="{img}" style="position:absolute;right:40px;top:160px;width:520px">'
            '<h1 style="position:absolute;left:60px;top:220px;font-size:84px;width:640px">AI 강의 3강<br>언어의 경계</h1></body></html>')
    r = ex("""
$a = [engines:render]{html:$html, viewports:["1280x720"], full_page:false, output_path:"IT81_thumb"}
$b = [engines:render]{html:$html, base_path:"/", viewports:["1280x720"], full_page:false, output_path:"IT81_thumb_base"}
return {a:$a.items[0], b:$b.items[0], fa:$a.prescreen_flagged, fb:$b.prescreen_flagged}
""", inputs={'html': html})
    if not r.get('success'):
        return False, f"FAIL {err(r)}"
    v = val(r)
    out = {k: {'w': v[k]['width'], 'h': v[k]['height'], 'prescreen': v[k]['prescreen'], 'file': Path(v[k]['path']).name}
           for k in ('a', 'b')}
    out['flagged'] = [v['fa'], v['fb']]
    out['note'] = '그림 실림 여부는 훈련자가 PNG 를 열어 판정(보고서)'
    return True, js(out, 700)


def t12():
    """[적용·경로] 산출물을 한 폴더에 — 같은 요청·같은 프로젝트에서 write·document·render·tts 의 산출 위치, render path 의 방언(~workspace·상대)."""
    r = ex("""
$w = [self:write]{path:"IT81_loc.txt", content:"x"}
$d = [table:document]{title:"t", format:"html", filename:"IT81_loc", blocks:[{type:"paragraph", text:"본문"}]}
$r = [engines:render]{path:$d.path, viewports:["600x300"], output_path:"IT81_loc"}
return {w:$w.path, d:$d.path, r:$r.items[0].path}
""")
    v = val(r) or {}
    loc = {k: str(Path(p).parent.relative_to(BASE)) for k, p in v.items()} if r.get('success') else f"FAIL {err(r)}"
    dial = {}
    for name, p in (('~workspace', '~workspace/projects/컨텐츠/outputs/IT81_loc.html'),
                    ('workspace_rel', 'projects/컨텐츠/outputs/IT81_loc.html'),
                    ('project_rel', 'outputs/IT81_loc.html')):
        rr = ex(f'[try] {{ $a = [engines:render]{{path:"{p}", viewports:["600x300"], output_path:"IT81_dial"}}\n return {{ok:true}} }} [catch] {{ return {{ok:false, msg:$error.message}} }}')
        vv = val(rr) or {}
        m = str(vv.get('msg') or '')
        dial[name] = {'ok': vv.get('ok'), 'resolved_under': ('backend/' if '/indiebizOS/backend/' in m else m[:40]) if not vv.get('ok') else 'ok'}
    out = {'locations': loc, 'render_path_dialects': dial}
    same = isinstance(loc, dict) and len(set(loc.values())) == 1
    return same and all(x['ok'] for x in dial.values()), js(out, 900)


def t13():
    """[조회] 분위기별 재생목록 — 내 음악에서 '잔잔한 곡' 고르기: 장르·연도 칸 채움률, mood 인자, 검색어로."""
    c = chk('[self:music]{op:"library", mood:"잔잔"}')
    r = ex("""
$lib = [self:music]{op:"library", limit:300}
$g = ($lib.items >> [table:groupby]{by:"genre"}).items
$nog = $lib.items >> [table:filter]{where:($r)=> $r.genre == null or $r.genre == ""}
$noy = $lib.items >> [table:filter]{where:($r)=> $r.year == null or $r.year == ""}
$calm = [self:music]{q:"잔잔", limit:50}
$pn = [self:music]{q:"piano", limit:50}
return {n:len($lib.items), count:get($lib, "count", null), genres:len($g), no_genre:len($nog), no_year:len($noy),
        year_type_sample:[$lib.items[0].year], calm:len($calm.items), piano:len($pn.items)}
""", private=True)
    v = val(r) or {}
    out = {'check_mood': check_row(c), 'r': v if r.get('success') else f"FAIL {err(r)}",
           'db_total': q(MUSIC / 'library.db', 'select count(*) from tracks')[0][0],
           'db_no_genre': q(MUSIC / 'library.db', "select count(*) from tracks where genre is null or genre=''")[0][0],
           'db_year_types': q(MUSIC / 'library.db', 'select typeof(year), count(*) from tracks group by 1')}
    return bool(r.get('success')), js(out, 900)


def t14():
    """[축적] 스크래치 재생목록 IT81_잔잔 — 만들고 · 피아노 곡 3개 담고(each) · 없는 곡 담기 · 읽고 · 지운다 (playlists.json 원상 대조)."""
    before = _fstat(FILES['playlists'])
    r = ex("""
$c = [self:music]{op:"playlist_create", name:"IT81_잔잔"}
$pick = [self:music]{q:"piano", limit:3}
$adds = $pick.items >> [table:each]{ [self:music]{op:"playlist_add", name:"IT81_잔잔", path:$it.path} }
[try] { $bad = [self:music]{op:"playlist_add", name:"IT81_잔잔", path:"/없는/곡IT81.mp3"}; $badr = {ok:true, v:$bad} } [catch] { $badr = {ok:false, code:$error.code, msg:$error.message} }
[try] { $dup = [self:music]{op:"playlist_create", name:"IT81_잔잔"}; $dupr = {ok:true} } [catch] { $dupr = {ok:false, code:$error.code} }
$pl = [self:music]{op:"playlist", name:"IT81_잔잔"}
$del = [self:music]{op:"playlist_delete", name:"IT81_잔잔"}
return {picked:len($pick.items), added:len($adds), pl_n:len($pl.items), pl_keys:keys($pl), bad:$badr, dup:$dupr, del_ok:$del.success}
""", private=True)
    after = _fstat(FILES['playlists'])
    v = val(r) or {}
    bad = v.get('bad') or {}
    out = {'r': {k: v.get(k) for k in ('picked', 'added', 'pl_n', 'pl_keys', 'dup', 'del_ok')} if r.get('success') else f"FAIL {err(r)}",
           'bad_path': {'ok': bad.get('ok'), 'code': bad.get('code'), 'msg': (bad.get('msg') or '')[:120]},
           'playlists_restored': (before or {}).get('h') == (after or {}).get('h')}
    return bool(r.get('success')) and bad.get('ok') is False and out['playlists_restored'], js(out, 900)


def t15():
    """[조회] 라디오 즐겨찾기 중 한국 방송사 채널은? — 즐겨찾기 × sense:radio korean 을 station_id 로 잇기 + 재생 상태(읽기)."""
    r = ex("""
$f = [limbs:radio_favorite]{op:"list"}
$k = [sense:radio]{op:"korean"}
$st = [limbs:radio]{op:"status"}
$sid = $f.items >> [table:filter]{where:($r)=> get($r,"station_id","") != ""}
$j = [table:join]{left:$sid, right:$k.items, on:"station_id", how:"inner"}
$ks = $f.items >> [table:each]{ return join(",", keys($it)) }
return {fav:len($f.items), keysets:unique($ks), with_station_id:len($sid), korean:len($k.items), korean_keys:keys($k.items[0]),
        korean_has_stream_url:has($k.items[0], "stream_url"), joined:len($j.items), playing:$st.playing}
""", private=True)
    raw_fail = ex('$f = [limbs:radio_favorite]{op:"list"}\n$f.items >> [table:filter]{where:($r)=> $r.station_id != ""}', private=True)
    v = val(r) or {}
    out = {'r': v if r.get('success') else f"FAIL {err(r)}",
           'naive_filter': {'ok': bool(raw_fail.get('success')), 'err': err(raw_fail)[:200] if not raw_fail.get('success') else None,
                            'details': ((raw_fail.get('diagnostic') or {}).get('details'))}}
    return bool(r.get('success')) and v.get('with_station_id') == v.get('fav'), js(out, 900)


def t16():
    """[check] 소리를 내는 동사 — 라디오 켜기(이 PC)·유튜브 음악 재생·내 음악 정지·볼륨·즐겨찾기 추가/삭제 — 부작용 사전 판정."""
    pairs = [('[limbs:radio]{op:"status"}', '[limbs:radio]{op:"play", station_id:"kbs_1fm", mode:"host"}'),
             ('[limbs:music]{op:"queue"}', '[limbs:music]{op:"play", query:"잔잔한 피아노"}'),
             ('[self:music]{op:"playlists"}', '[self:music]{op:"stop"}'),
             ('[limbs:radio_favorite]{op:"list"}', '[limbs:radio_favorite]{op:"remove", name:"IT81"}'),
             ('[self:music]{op:"library", q:"x"}', '[self:music]{op:"playlist_delete", name:"IT81"}'),
             ('[engines:web_site]{op:"list"}', '[engines:web_site]{op:"remove", site_id:"IT81"}'),
             ('[self:lecture]{op:"list"}', '[self:lecture]{op:"delete", lecture_id:"IT81", confirm:true}'),
             ('[engines:web]{op:"snapshot", site_id:"IT81"}', '[engines:web]{op:"deploy", project_path:"/tmp/IT81", production:true}')]
    rows = []
    for rd, wr in pairs:
        cr, cw = chk(rd), chk(wr)
        vr = post('ibl/validate', {'code': rd})
        vw = post('ibl/validate', {'code': wr})
        rows.append({'read': rd.split('{')[0] + rd.split('op:')[1][:12], 'check_read': cr.get('effects'), 'check_write': cw.get('effects'),
                     'validate_read': vr.get('has_side_effect'), 'validate_write': vw.get('has_side_effect')})
    unknown = sum(1 for x in rows if x['check_read'] == x['check_write'])
    return unknown == 0, js({'pairs': rows, 'check_same_effects_pairs': unknown}, 2500)


def t17():
    """[조회] 강의 자료 웹 컴포넌트 고르기 — 섹션 카탈로그에서 hero 계열 · 등록 사이트 · 사이트 현황(snapshot) — items 통화로 이어지나."""
    r = ex("""
$c = [engines:web_component]{op:"catalog", kind:"sections"}
$s = [engines:web_site]{op:"list"}
$snap = [engines:web]{op:"snapshot", site_id:$s.sites[0].id}
return {cenv:keys($c), cats:keys($c.categories), hero:len($c.categories.hero.sections), senv:keys($s), sites:len($s.sites), snap:keys($snap)}
""")
    v = val(r) or {}
    cont = r.get('continuation') or {}
    out = {'r': v if r.get('success') else f"FAIL {err(r)}", 'continuation': {k: cont.get(k) for k in ('read_calls', 'state_change_possible')},
           'catalog_has_items': 'items' in (v.get('cenv') or []), 'site_list_has_items': 'items' in (v.get('senv') or [])}
    return out['catalog_has_items'] and out['site_list_has_items'], js(out, 900)


def t18():
    """[check] 강의 자료 웹사이트 만들기 → 빌드 → 배포 / 컴포넌트 설치 / 테마 — 전부 check (배포=외부 공개)."""
    cs = {
        'create_site': '[engines:web]{op:"create", target:"site", name:"IT81_lecture", template:"landing"}',
        'create_page_sections': '[engines:web]{op:"create", target:"page", project_path:"/tmp/IT81", page_name:"lec3", sections:[{id:"hero-simple", params:{title:"3강"}}]}',
        'build_then_deploy': '$b = [engines:web]{op:"build", project_path:"/tmp/IT81"}\n[if: $b.success] { [engines:web]{op:"deploy", project_path:"/tmp/IT81", production:true} }',
        'deploy_dry_run_arg': '[engines:web]{op:"deploy", project_path:"/tmp/IT81", dry_run:true}',
        'component_add': '[engines:web_component]{op:"add", component:"card", project_path:"/tmp/IT81"}',
        'fetch_file': '[engines:web_component]{op:"fetch", component:"hero", output_format:"file", project_path:"/tmp/IT81"}',
        'styles_bad_theme': '[engines:web]{op:"styles", project_path:"/tmp/IT81", theme:"없는테마"}',
    }
    out = {k: check_row(chk(c)) for k, c in cs.items()}
    return True, js(out, 1600)


def t19():
    """[시간] 매일 아침 7시 라디오 켜기 / 매주 일요일 이번 주 사진으로 가족신문 초안 알림 — trigger check."""
    c1 = chk("return [self:trigger]{op:\"create\", name:\"IT81_아침라디오\", cron:\"0 7 * * *\", do:'[limbs:radio]{op:\"play\", station_id:\"kbs_1fm\", mode:\"host\"}'}")
    c2 = chk("return [self:trigger]{op:\"create\", name:\"IT81_가족사진\", cron:\"0 20 * * 0\", do:'$p = [self:photo]{has_gps:true, start:\"2026-09-27\", limit:400}; [self:notify_user]{message:f\"이번 주 사진 ${len($p.items)}장\"}'}")
    inner = chk('$p = [self:photo]{has_gps:true, start:"2026-09-27", limit:400}\n[self:notify_user]{message:f"이번 주 사진 ${len($p.items)}장"}')
    return True, js({'radio_morning': check_row(c1), 'weekly_photo': check_row(c2), 'inner': check_row(inner)}, 900)


def t20():
    """[check] 슬라이드 한 장 노트 고치기 → 그 장만 다시 굽고 → 영상 — slide note·rerender·deck video·export check (쓰기·GPU·긴 렌더)."""
    cs = {
        'note_one': f'[self:slide]{{op:"note", lecture_id:"{LECTURE}", slide_id:"s001", note:"IT81"}}',
        'note_missing_slide': f'[self:slide]{{op:"note", lecture_id:"{LECTURE}", slide_id:"s999", note:"IT81"}}',
        'create_scratch_html': '[self:slide]{op:"create", instruction:"AI 강의 3강 표지", render:"html"}',
        'deck_video_captions': f'[self:deck]{{op:"video", lecture_id:"{LECTURE}", engine:"edge", captions:true, wait:true}}',
        'deck_export_pdf_then_render': f'$e = [self:deck]{{op:"export", lecture_id:"{LECTURE}", format:"pdf"}}\n[engines:render]{{op:"pdf", path:$e.path, pages:[1]}}',
        'deck_video_bad_engine': f'[self:deck]{{op:"video", lecture_id:"{LECTURE}", engine:"qwen3"}}',
    }
    out = {k: check_row(chk(c)) for k, c in cs.items()}
    return True, js(out, 1600)


def t21():
    """[check] 코퍼스 용례 — 축 액션이 들어간 교재 용례 전수를 판본 2 check (교재 드리프트)."""
    acts = ['engines:tts', 'engines:render', 'engines:image_read', 'engines:web', 'engines:web_site', 'engines:web_component',
            'self:photo', 'self:music', 'self:slide', 'self:deck', 'limbs:music', 'limbs:radio', 'limbs:radio_favorite', 'sense:radio']
    rows = q(BASE / 'data/ibl_usage.db', 'select id, ibl_code from ibl_examples')
    by = {}
    tot = inv = 0
    codes_ = {}
    for _id, code in rows:
        hit = [a for a in acts if f'[{a}]' in (code or '')]
        if not hit:
            continue
        tot += 1
        c = chk(code if code.lstrip().startswith('#!ibl') else code)
        st = c.get('status')
        for a in hit:
            by.setdefault(a, [0, 0])
            by[a][0] += 1
            if st == 'invalid':
                by[a][1] += 1
        if st == 'invalid':
            inv += 1
            for cc in codes(c):
                codes_[cc] = codes_.get(cc, 0) + 1
    LOG.clear()
    return True, js({'examples': tot, 'invalid': inv, 'issue_codes': codes_, 'by_action[n,invalid]': by}, 1500)



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


def _tree(root, top_only=False):
    root = Path(root)
    if not root.exists():
        return None
    fs = [f for f in (root.iterdir() if top_only else root.rglob('*'))]
    return {'entries': len(fs), 'h': h(sorted((str(f.relative_to(root)), f.stat().st_size if f.is_file() else -1,
                                               int(f.stat().st_mtime)) for f in fs))}


def _names(root):
    root = Path(root)
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def stores():
    out = {k: _fstat(p) for k, p in FILES.items()}
    out['out_top'] = _tree(OUT, top_only=True)
    out['out_names'] = _names(OUT)
    out['root_out_top'] = _tree(ROOT_OUT, top_only=True)
    out['root_out_names'] = _names(ROOT_OUT)
    out['lectures_tree'] = _tree(ROOT_OUT / 'lectures')
    out['music_library'] = q(MUSIC / 'library.db', 'select count(*) from tracks')[0][0]
    out['usb_media_cache'] = _tree(BASE / 'data/usb_media_cache')
    out['ibl_examples'] = q(BASE / 'data/ibl_usage.db', 'select count(*), max(id) from ibl_examples')[0]
    out['episode_log_max'] = q(PULSE, 'select max(rowid) from episode_log')[0][0]
    out['scratch_IT81'] = sorted([p.name for p in OUT.rglob('IT81*')] + [p.name for p in ROOT_OUT.glob('IT81*')])
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


def clean():
    """스크래치 삭제 — IT81 접두 산출물만(기준선에 없던 것). 그 밖의 새 파일은 목록만 출력."""
    base = json.loads((HERE / 'baseline.json').read_text())['baseline']['stores']
    import shutil
    removed = []
    for root, before in ((OUT, set(base['out_names'])), (ROOT_OUT, set(base['root_out_names']))):
        for p in sorted(root.iterdir()):
            if p.name in before:
                continue
            if p.name.startswith('IT81'):
                (shutil.rmtree if p.is_dir() else Path.unlink)(p)
                removed.append(str(p.relative_to(BASE)))
            else:
                print('NEW (not IT81, left):', p.relative_to(BASE))
    print('removed', removed)


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
    {'baseline': baseline, 'run': run, 'after': after, 'raw': raw, 'desc': desc, 'clean': clean}[sys.argv[1]]()
