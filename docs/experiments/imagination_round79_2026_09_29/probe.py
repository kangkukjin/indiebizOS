"""79회차: 가족 나들이·생활 조회 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 위치·생활 어휘(sense:place·restaurant·navigate_route·reverse_geocode·here·weather·
performance·exhibit·stay·search_shopping·used·contest, limbs:show_map)를 table:filter·sort·select·compute·each·take·
union·dedup 과 [if]·[try]·?? 로 조합.
도메인: 사용자 생활권 청주·오송·세종 — 주말(2026-10-03 토·10-04 일) 가족 나들이: 맑은 날 고르기 → 근처 전시·공연 →
주변 맛집(후기·거리) → 이동 시간 비교, 비 오면 실내 대안, 숙소 1박 가격, 아이 선물 새것 최저가 vs 중고 시세,
근처 약국, 좌표↔주소 왕복, 원천 0건·한도, 지도 표시.

모든 요청 edition 2·project_id 컨텐츠·origin training·agent_id IT79_probe·task_id IT79_task.
★사용자 실제 위치: sense:here 결과·navigate_route 기본 출발지(선언 위치)를 쓰는 요청은 before.json 에 모양(shape)만 남긴다.
  보고서·rows detail 에도 좌표·주소를 싣지 않는다(시·구 수준까지만).
★외부 API 읽기만. 발신 0 · 해마 시딩 0 · 유료 AI 0 목표. 쓰기는 projects/컨텐츠/outputs/IT79_* 스크래치만, 끝에 삭제.
사용: .venv/bin/python probe.py baseline | run [tNN ...] | after | raw '<code>' [--check] [--private] | desc node:action ...
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
AGENT = {'agent_id': 'IT79_probe', 'task_id': 'IT79_task'}
LOG = []
PULSE = BASE / 'data/world_pulse.db'
SINCE = BASE / 'data/table_since.db'
PLACES_LEDGER = BASE / 'projects/앱모드/outputs/map/places.json'
BODY_LOCATION = BASE / 'data/body_location.json'
SCRATCH = BASE / 'projects/컨텐츠/outputs'
WEEKEND = ('2026-10-03', '2026-10-04')


def post(route, payload=None, method='POST'):
    args = ['curl', '-sS', '--max-time', '280', '-X', method, f'http://127.0.0.1:8765/{route}',
            '-H', 'Content-Type: application/json']
    if payload is not None:
        args += ['--data-binary', '@-']
    proc = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                          text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, private=False, **extra):
    """private=True: 사용자 실제 위치가 섞이는 요청 — before.json 에는 값의 모양만 남긴다."""
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠', origin='training',
                   **AGENT, **extra)
    response = post('ibl/execute', payload)
    slim = {k: v for k, v in response.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}
    LOG.append({'request': payload, 'response': slim, 'private': private})
    return response


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def warns(r):
    return [(w.get('code'), (w.get('message') or '')[:120]) for w in (r.get('warnings') or [])]


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
    """위치 원문 없이 값의 모양만: 키·타입·길이·해시."""
    if isinstance(x, dict):
        if depth > 3:
            return {'_dict_keys': sorted(x)[:30]}
        return {k: shape(v, depth + 1) for k, v in list(x.items())[:40]}
    if isinstance(x, list):
        return {'_list_len': len(x), 'first': shape(x[0], depth + 1) if x else None}
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return '<num>'
    if isinstance(x, str):
        return f'<str len={len(x)} h={h(x)}>'
    return x


def mask_log():
    for e in LOG:
        if not e.pop('private', False):
            continue
        r = e['response']
        e['response'] = {k: (shape(v) if k in ('value', 'result', 'partial', 'partial_preview', 'partial_wire', 'data',
                                                'diagnostic', 'error_detail', 'text', 'error', 'continuation', 'result_ref') else v)
                         for k, v in r.items()}
        e['request'] = {k: (v if k != 'inputs' else shape(v)) for k, v in e['request'].items()}

# ───────────────────────── 과제 ─────────────────────────
# ★반환 detail 은 before.json rows 에 그대로 저장된다 — 사용자 위치(좌표·주소)를 담지 말 것.

MUSEUM = {'x': '127.47829194581672', 'y': '36.63471250225671'}   # 청주시립미술관(전시 원천 gpsX/gpsY) — 공공 시설 좌표


def t01():
    """[조건] 이번 주말 청주 날씨 — 토·일 중 비 없는 날을 고르고, 둘 다 비면 실내(전시) 아니면 야외(관광명소) 후보."""
    r = ex("""
$w = [sense:weather]{city:"청주", days:7}
$wk = $w.items >> [table:filter]{where:($d)=> $d.date == "2026-10-03" or $d.date == "2026-10-04"}
$dry = $wk >> [table:filter]{where:($d)=> $d.precipitation_mm == 0 and not contains($d.condition, "비")}
[if: len($dry) == 0] {
  $e = [sense:exhibit]{query:"청주", rows:20}
  $plan = {mode:"실내", day:null, picks:($e.items >> [table:filter]{where:($x)=> $x.end_date >= "2026-10-03"} >> [table:take]{n:3})}
} [else] {
  $p = [sense:place]{category:"관광명소", lat:36.6424, lng:127.4890, radius:10000, limit:5}
  $plan = {mode:"야외", day:$dry[0].date, picks:($p.items >> [table:take]{n:3})}
}
$names = $plan.picks >> [table:each]{ get($it, "title", get($it, "name", null)) }
return {weekend:($wk >> [table:each]{ {d:$it.date, c:$it.condition, mm:$it.precipitation_mm} }), mode:$plan.mode, day:$plan.day, picks:$names}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('picks')), ok_or_err(r, 600)


def t02():
    """[대조] 같은 주말 날씨를 두 경로로 — 도시명 '청주' vs 청주시청 좌표(장소 검색). 토·일 최고기온 차이·해소 이름."""
    r = ex("""
$a = [sense:weather]{city:"청주", days:7}
$h = [sense:place]{query:"청주시청", limit:1}
$b = [sense:weather]{lat:$h.items[0].lat, lon:$h.items[0].lng, days:7}
$pa = $a.items >> [table:filter]{where:($d)=> $d.date >= "2026-10-03" and $d.date <= "2026-10-04"}
$pb = $b.items >> [table:filter]{where:($d)=> $d.date >= "2026-10-03" and $d.date <= "2026-10-04"}
$diff = zip($pa, $pb) >> [table:each]{ abs($it[0].max_temp - $it[1].max_temp) }
return {resolved_city:$a.resolved, resolved_coord:$b.resolved, max_diff:max($diff), a:($pa >> [table:each]{$it.max_temp}), b:($pb >> [table:each]{$it.max_temp})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('max_diff') is not None and float(str(v.get('max_diff'))) < 2.0), ok_or_err(r, 500)


def t03():
    """[조회] 이번 주말 충북 공연 — 날짜 범위만 주면(기본 status) 주말에 새로 시작하는 공연이 빠지는가. 공연예정과 대조."""
    r = ex("""
$a = [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"충북", rows:50}
$c = [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"충북", status:"공연예정", rows:50}
$kid = $c.items >> [table:filter]{where:($x)=> contains($x.title, "어린이") or contains($x.genrenm, "아동")}
return {default_n:len($a.items), default_status:$a.search_params.status, upcoming_n:len($c.items), upcoming_starts:($c.items >> [table:each]{$it.start_date}), kid_titles:($kid >> [table:each]{$it.title}), default_titles:($a.items >> [table:each]{$it.title})}
""")
    v = val(r) or {}
    missed = v.get('upcoming_n') or 0
    return bool(r.get('success') and missed == 0), (ok_or_err(r, 900) + f" · 기본값이 놓친 주말 개막 공연 {missed}건")


def t04():
    """[조회] '청주 공연' — region 에 시 이름을 주면? (코드표는 시도 17개) 충북·청주 대조."""
    r = ex("""
$a = [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"충북", rows:50}
$b = [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"청주", rows:50}
$g = [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"충북", genre:"어린이극", rows:50}
$cj = $a.items >> [table:filter]{where:($x)=> contains($x.title, "청주")}
return {chungbuk:len($a.items), chungbuk_cheongju_titled:len($cj), cheongju:len($b.items), cheongju_msg:$b.message, cheongju_region_echo:$b.search_params.region, genre_bad:len($g.items), genre_echo:$g.search_params.genre}
""")
    ck = ex('return [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"청주"}', check=True)
    v = val(r) or {}
    return bool(r.get('success') and v.get('cheongju')), ok_or_err(r, 500) + f" · check status={ck.get('status')} warn={warns(ck)}"


def t05():
    """[적용] 주말 청주 공연 ∪ 전시를 한 목록으로 — dedup(title) 뒤 같은 공연이 두 번 남는가."""
    r = ex("""
$p = [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"충북", rows:50}
$e = [sense:exhibit]{query:"청주", rows:30}
$pr = $p.items >> [table:each]{ {title:$it.title, venue:$it.fcltynm, src:"kopis"} }
$er = $e.items >> [table:each]{ {title:$it.title, venue:$it.place, src:"kcisa"} }
$u = [table:union]{inputs:[$pr, $er]} >> [table:dedup]{by:"title"}
$dup = $u.items >> [table:filter]{where:($x)=> contains($x.title, "무명의 용병사") or contains($x.title, "청주짜글이")}
return {p:len($pr), e:len($er), union_dedup:len($u.items), same_show_rows:($dup >> [table:each]{ {t:$it.title, v:$it.venue, s:$it.src} })}
""")
    v = val(r) or {}
    return bool(r.get('success') and len(v.get('same_show_rows') or []) <= 2), ok_or_err(r, 700)


def t06():
    """[적용] 주말에 열린 청주 전시·공연(전시 원천)을 지도에 — 행마다 원천 좌표(gpsX/gpsY)가 있는데 몇 개가 실리나."""
    r = ex("""
$e = [sense:exhibit]{query:"청주", rows:30}
$now = $e.items >> [table:filter]{where:($x)=> $x.end_date >= "2026-10-03" and $x.start_date <= "2026-10-04"}
$withgps = $now >> [table:filter]{where:($x)=> $x.gpsX != null}
$m = [limbs:show_map]{markers:$now, title:"주말 청주 전시·공연"}
return {rows:len($now), rows_with_source_coords:len($withgps), row_keys:keys($now[0]), markers:len($m.map_data.markers), unresolved:len(get($m,"unresolved",[])), geocoded_note:contains($m.message, "좌표 변환")}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('markers') == v.get('rows_with_source_coords')), ok_or_err(r, 500)


def t07():
    """[조회·정렬] 미술관 반경 700m 돈까스집을 가까운 순으로 — 반경 밖(전국) 행이 섞이는가."""
    r = ex(f"""
$r = [sense:restaurant]{{query:"돈까스", x:"{MUSEUM['x']}", y:"{MUSEUM['y']}", radius:700, limit:30, enrich:false}}
$rows = $r.items >> [table:each]{{ {{name:$it.name, source:$it.source, distance:get($it,"distance",null), region:split($it.address, " ")[0]}} }}
$far = $rows >> [table:filter]{{where:($x)=> $x.distance == null}}
$types = $rows >> [table:each]{{ $it.distance }}
$fr = $far >> [table:each]{{$it.region}}
return {{n:len($rows), msg:$r.message, no_distance:len($far), far_regions:unique($fr), sample_distance:$types[0]}}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('no_distance') == 0), ok_or_err(r, 600)


def t08():
    """[조회] 미술관 근처 후기 많은 맛집(블로그 근거 기본) — 이름·거리·언급수 표. 행마다 칸이 다른가, 진단이 어느 칸인지 말하나."""
    code = f"""
$r = [sense:restaurant]{{query:"맛집", x:"{MUSEUM['x']}", y:"{MUSEUM['y']}", radius:1500, limit:15}}
return $r.items >> [table:select]{{columns:["name","distance","blog_count"]}}
"""
    a = ex(code)
    d = a.get('diagnostic') or {}
    reuse = (a.get('continuation') or {}).get('reuse_args') or {}
    b = ex(f"""
$r = [sense:restaurant]{{query:"맛집", x:"{MUSEUM['x']}", y:"{MUSEUM['y']}", radius:1500, limit:15}}
$rows = $r.items >> [table:each]{{ {{name:$it.name, blog:get($it,"blog_count",null)}} }}
$unmeasured = $rows >> [table:filter]{{where:($x)=> $x.blog == null}}
return {{n:len($rows), unmeasured:len($unmeasured), naver_nationwide:($r.naver.restaurants >> [table:each]{{split($it.address, " ")[0]}}), msg:$r.message}}
""", **reuse)
    return bool(a.get('success')), (f"select: code={d.get('code')} msg={d.get('message')} details={d.get('details')} · 우회: {ok_or_err(b, 400)}")


def t09():
    """[적용·정렬] 오송역에서 주말 후보 세 곳의 자동차 소요시간 — 짧은 순, 직선거리(좌표 근사)와 도로거리 비율로 대조."""
    r = ex("""
$cands = ["청주시립미술관", "국립현대미술관 청주", "국립세종수목원"]
$rows = $cands >> [table:each]{
  $p = [sense:place]{query:$it, limit:1}
  $rt = [sense:navigate_route]{origin:"오송역", destination:$it}
  $o = $rt.map_data.origin
  $dx = ($p.items[0].lng - $o.lng) * 89.3
  $dy = ($p.items[0].lat - $o.lat) * 111.0
  return {name:$it, resolved:$rt.map_data.destination.name, min:$rt.summary.duration_min, km:$rt.summary.distance_km, straight_km:round(($dx*$dx + $dy*$dy) ** 0.5, 1)}
}
$sorted = $rows >> [table:sort]{by:"min"}
$ratio = $sorted >> [table:each]{ round($it.km / $it.straight_km, 2) }
return {order:($sorted >> [table:each]{ {n:$it.name, r:$it.resolved, min:$it.min, km:$it.km, straight:$it.straight_km} }), road_over_straight:$ratio}
""")
    v = val(r) or {}
    ratios = [float(str(x)) for x in (v.get('road_over_straight') or [])]
    return bool(r.get('success') and ratios and all(1.0 <= x <= 2.2 for x in ratios)), ok_or_err(r, 700)


def t10():
    """[대조] 대중교통 vs 자동차 — 오송역→청주시립미술관 가장 빠른 대중교통 경로·요금, 청주→세종(시 경계) 대중교통 완결 여부."""
    r = ex("""
$t = [sense:navigate_route]{mode:"transit", origin:"오송역", destination:"청주시립미술관"}
$d = [sense:navigate_route]{origin:"오송역", destination:"청주시립미술관"}
$fast = $t.items >> [table:sort]{by:"duration_min"} >> [table:take]{n:1}
$cheap = $t.items >> [table:sort]{by:"fare_krw"} >> [table:take]{n:1}
$u = [sense:navigate_route]{mode:"transit", origin:"청주시립미술관", destination:"국립세종수목원"}
return {routes:len($t.items), fastest_min:$fast[0].duration_min, fastest_fare:$fast[0].fare_krw, cheapest_fare:$cheap[0].fare_krw, drive_min:$d.summary.duration_min, cross_city_complete:$u.items[0].complete, cross_city_min:$u.items[0].duration_min}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('cross_city_complete')), ok_or_err(r, 500)


def t11():
    """[조회·비교] 세종 호텔 1박 vs 2박 가격 — price 가 1박가인가 합계인가, '1박 10만원 이하'(max_price)가 2박에서 무엇을 거르나."""
    r = ex("""
$one = [sense:stay]{region:"세종", checkin:"2026-10-10", checkout:"2026-10-11", limit:9}
$two = [sense:stay]{region:"세종", checkin:"2026-10-10", checkout:"2026-10-12", limit:9}
$sat = [sense:stay]{region:"세종", checkin:"2026-10-11", checkout:"2026-10-12", limit:9}
[try] { $cap = [sense:stay]{region:"세종", checkin:"2026-10-10", checkout:"2026-10-12", max_price:100000, limit:9}; $capfail = null } [catch] { $cap = $error.partial; $capfail = {code:$error.code, trunc:$cap.truncations} }
$pick = "초정약수 세종스파텔"
$p1 = $one.items >> [table:filter]{where:($x)=> $x.title == $pick}
$p2 = $two.items >> [table:filter]{where:($x)=> $x.title == $pick}
$p3 = $sat.items >> [table:filter]{where:($x)=> $x.title == $pick}
$capn = $cap.items >> [table:each]{ {t:$it.title, p:$it.price} }
return {pick:$pick, night1:$p1[0].price, night2:$p3[0].price, two_nights:$p2[0].price, sum_equals:($p1[0].price + $p3[0].price == $p2[0].price), two_summary:$p2[0].summary, cap_rows:$capn, cap_msg:$cap.message, cap_failure:$capfail}
""")
    v = val(r) or {}
    cap_has_pick = any(x.get('t') == '초정약수 세종스파텔' for x in (v.get('cap_rows') or []))
    return bool(r.get('success') and cap_has_pick), ok_or_err(r, 700) + f" · 1박 7.5만원꼴 숙소가 '1박 10만원 이하'에 남았나={cap_has_pick}"


def t12():
    """[조회] 세종에서 가족 호텔(4인) — region '세종' 결과에 세종 밖 숙소가 섞이나, 주소 칸이 구조로 있나."""
    r = ex("""
$s = [sense:stay]{region:"세종", checkin:"2026-10-10", checkout:"2026-10-11", personal:4, limit:9}
$rows = $s.items >> [table:each]{ {t:$it.title, meta:$it.meta, has_addr:has($it, "address"), p:$it.price} }
$out = $rows >> [table:filter]{where:($x)=> not contains($x.meta, "세종") and not contains($x.meta, "청주") and not contains($x.meta, "동 ·") }
$ha = $rows >> [table:each]{$it.has_addr}
return {n:len($rows), outside_by_meta:($out >> [table:each]{ {t:$it.t, m:$it.meta} }), structured_address:any($ha), keys:keys($s.items[0])}
""")
    v = val(r) or {}
    return bool(r.get('success') and not v.get('outside_by_meta')), ok_or_err(r, 700)


def t13():
    """[조회·비교] 아이 선물 — 닌텐도 스위치 2 새것 최저가(다나와) vs 중고 본체 시세(번개장터, 30만원 이상·본체 제목) 중앙값."""
    r = ex("""
$n = [sense:search_shopping]{query:"닌텐도 스위치 2", display:5}
$u = [sense:used]{source:"bunjang", query:"닌텐도 스위치 2", limit:30}
$new_prices = $n.items >> [table:each]{ number($it.price) }
$body = $u.items >> [table:filter]{where:($x)=> $x.price != null and $x.price >= 300000 and (contains($x.title, "스위치2") or contains($x.title, "스위치 2"))}
$bp = $body >> [table:each]{$it.price}
$up = sorted($bp)
$median = $up[len($up) // 2]
return {new_min:min($new_prices), new_price_type:$n.items[0].price, used_n:len($body), used_median:$median, ratio:round($median / min($new_prices), 2)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('used_n')), ok_or_err(r, 500)


def t14():
    """[조회] 청주에서 파는 스위치 2 중고 — 번개장터 region:'청주' vs region 없이 받은 행 중 위치 표기가 청주인 것."""
    r = ex("""
$a = [sense:used]{source:"bunjang", query:"닌텐도 스위치 2", region:"청주", limit:15}
$b = [sense:used]{source:"bunjang", query:"닌텐도 스위치 2", limit:15}
$located = $b.items >> [table:filter]{where:($x)=> len(split($x.meta, " · ")) > 1}
return {cheongju_n:len($a.items), cheongju_total:$a.total, cheongju_keys:keys($a), nationwide_n:len($b.items), nationwide_with_location:len($located)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('cheongju_n')), ok_or_err(r, 500) + ' · 코드: find_v2 최신 max(limit*2,40)건을 받아 location substring 후필터(tool_used.search_bunjang)'


def t15():
    """[조회] 우리 동네(오송읍) 당근 매물 — 결과 0 이 '없음'인가 '긁기 고장'인가. 원천 원응답과 대조."""
    r = ex("""
$d = [sense:used]{source:"danggeun", query:"닌텐도 스위치", region:"오송읍", limit:15}
$e = [sense:used]{source:"danggeun", query:"자전거", region:"오송읍", limit:15}
return {switch_n:len($d.items), bike_n:len($e.items), note:get($d,"note",null), keys:keys($d), success:get($d,"success",null)}
""")
    v = val(r) or {}
    return bool(r.get('success') and (v.get('switch_n') or v.get('bike_n'))), ok_or_err(r, 500) + ' · 셸 대조: /kr/buy-sell/?search= → 301 /kr/search/buy-sell/?q=, 새 페이지에 application/ld+json 0개(87KB)'


def t16():
    """[조회·private] 지금 위치 근처 약국 5곳 가까운 순 — 위치 정밀도와 반경 비교(좌표·주소는 싣지 않음)."""
    r = ex("""
$h = [sense:here]
$p = [sense:place]{category:"약국", lat:$h.lat, lng:$h.lng, radius:1000, sort:"distance", limit:5}
$d = $p.items >> [table:each]{$it.distance}
return {source:$h.source, accuracy_m:$h.accuracy_m, radius_m:1000, n:len($p.items), sorted:($d == sorted($d)), precision_warning:has($p, "warning") or has($h, "warning")}
""", private=True)
    v = val(r) or {}
    safe = {k: v.get(k) for k in ('source', 'accuracy_m', 'radius_m', 'n', 'sorted', 'precision_warning')}
    return bool(r.get('success') and v.get('n')), js(safe, 300) if r.get('success') else f"FAIL {err(r)[:200]}"


def t17():
    """[왕복] 좌표 ↔ 주소 — 미술관 좌표 → 주소 → 그 주소로 다시 장소 검색 → 원래 좌표와의 거리(근사)."""
    r = ex("""
$p = [sense:place]{query:"국립현대미술관 청주", limit:1}
$g = [sense:reverse_geocode]{lat:$p.items[0].lat, lng:$p.items[0].lng}
$back = [sense:place]{query:$g.items[0].address, limit:1}
$dx = ($back.items[0].lng - $p.items[0].lng) * 89300
$dy = ($back.items[0].lat - $p.items[0].lat) * 111000
return {road_address:$p.items[0].address, reverse:$g.items[0].address, reverse_keys:keys($g.items[0]), back_name:$back.items[0].name, back_m:round(($dx*$dx+$dy*$dy) ** 0.5, 0)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('back_m') is not None and float(str(v['back_m'])) < 50 and v.get('reverse') and any(c.isdigit() for c in v.get('reverse', ''))), ok_or_err(r, 500)


def t18():
    """[정직성] 원천 0건 — 없는 말로 아홉 원천을 두드리면 성공·0건과 실패를 어떻게 가르나."""
    r = ex("""
$Q = "큐비트뇌파양자구름없는말"
[try] { $a = [sense:place]{query:$Q}; $ra = {ok:true, n:len($a.items)} } [catch] { $ra = {ok:false, code:$error.code, msg:$error.message} }
[try] { $b = [sense:restaurant]{query:$Q, enrich:false}; $rb = {ok:true, n:len($b.items)} } [catch] { $rb = {ok:false, code:$error.code, msg:$error.message} }
[try] { $c = [sense:exhibit]{query:$Q}; $rc = {ok:true, n:len(get($c,"items",[]))} } [catch] { $rc = {ok:false, code:$error.code, msg:$error.message} }
[try] { $d = [sense:performance]{query:$Q}; $rd = {ok:true, n:len(get($d,"items",[]))} } [catch] { $rd = {ok:false, code:$error.code, msg:$error.message} }
[try] { $e = [sense:stay]{region:$Q}; $re = {ok:true, n:len($e.items)} } [catch] { $re = {ok:false, code:$error.code, msg:$error.message} }
[try] { $f = [sense:search_shopping]{query:$Q}; $rf = {ok:true, n:len($f.items)} } [catch] { $rf = {ok:false, code:$error.code, msg:$error.message} }
[try] { $g = [sense:used]{query:$Q}; $rg = {ok:true, n:len($g.items)} } [catch] { $rg = {ok:false, code:$error.code, msg:$error.message} }
[try] { $h = [sense:weather]{city:$Q}; $rh = {ok:true, r:get($h,"resolved",null)} } [catch] { $rh = {ok:false, code:$error.code, msg:$error.message} }
[try] { $nav = [sense:navigate_route]{origin:"오송역", destination:$Q}; $ri = {ok:true} } [catch] { $ri = {ok:false, code:$error.code, msg:$error.message} }
[try] { $j = [sense:contest]{query:$Q}; $rj = {ok:true, n:len($j.items)} } [catch] { $rj = {ok:false, code:$error.code, msg:$error.message} }
return {place:$ra, restaurant:$rb, exhibit:$rc, performance:$rd, stay:$re, shopping:$rf, used:$rg, weather:$rh, route:$ri, contest:$rj}
""")
    v = val(r) or {}
    fails = [k for k, x in v.items() if isinstance(x, dict) and not x.get('ok')]
    zero_ok = [k for k, x in v.items() if isinstance(x, dict) and x.get('ok') and x.get('n') == 0]
    return bool(r.get('success') and not [k for k in fails if k not in ('weather', 'route')]), f"실패={fails} · 성공0건={zero_ok} · " + ok_or_err(r, 900)


def t19():
    """[조회] 아이 그림 공모전 — sense:contest 는 무엇을 주나(선언: Kaggle 하나, 국내는 sense:search). 0건 응답이 길을 말하나."""
    r = ex("""
$a = [sense:contest]{query:"어린이 그림 공모전", count:5}
$b = [sense:contest]{}
$design = $b.items >> [table:filter]{where:($x)=> contains($x.title, "디자인")}
return {kids_n:len($a.items), kids_keys:keys($a), kids_hint:get($a,"message",get($a,"note",null)), default_n:len($b.items), default_first:$b.items[0].title, corpus4755_design:len($design)}
""")
    v = val(r) or {}
    return bool(r.get('success') and (v.get('kids_n') or v.get('kids_hint'))), ok_or_err(r, 500)


def t20():
    """[시간] 열흘 날씨 추이 — days:10 을 주면 몇 날이 오고, 깎였다는 표지가 있나(+ 장소 반경 50km)."""
    r = ex("""
$w = [sense:weather]{city:"청주", days:10}
$p = [sense:place]{query:"약국", lat:36.62, lng:127.3276, radius:50000, limit:3}
return {days:len($w.items), last:$w.items[-1].date, clamp_marker:has($w, "clamped") or has($w, "truncations"), place_msg:$p.message, place_clamp_marker:has($p, "clamped")}
""")
    v = val(r) or {}
    return bool(r.get('success') and (v.get('days') == 10 or v.get('clamp_marker'))), ok_or_err(r, 400)


def t21():
    """[축적] 나들이 계획표를 스크래치 파일로 — 날씨·전시·맛집·이동시간을 한 JSON 으로 쓰고 다시 읽어 칸 보존 확인."""
    r = ex(f"""
$w = [sense:weather]{{city:"청주", days:7}}
$e = [sense:exhibit]{{query:"청주", rows:10}}
$r = [sense:restaurant]{{query:"한식", x:"{MUSEUM['x']}", y:"{MUSEUM['y']}", radius:1000, limit:3, enrich:false}}
$sat = $w.items >> [table:filter]{{where:($d)=> $d.date == "2026-10-03"}}
$plan = {{date:"2026-10-03", weather:$sat[0], exhibit:$e.items[0].title, lunch:($r.items >> [table:each]{{$it.name}}), saved_by:"IT79"}}
$f = [self:write]{{path:"outputs/IT79_나들이.json", content:json($plan)}}
$back = [self:read]{{path:"outputs/IT79_나들이.json"}}
return {{written:keys($f), back_keys:keys($back.data), lunch_n:len($back.data.lunch), same:($back.data.exhibit == $plan.exhibit)}}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('same')), ok_or_err(r, 400)


def t22():
    """[check] 코퍼스 용례 — 축 13액션의 273 용례를 판본 2 check 로(상태·오류 부류), 대표 4768·4006·4197·4770."""
    import sqlite3 as _s
    db = _s.connect(str(BASE / 'data/ibl_usage.db'))
    acts = ['place', 'restaurant', 'navigate_route', 'reverse_geocode', 'here', 'weather', 'performance', 'exhibit',
            'stay', 'search_shopping', 'used', 'contest', 'show_map']
    ids = {}
    for a in acts:
        for i, c in db.execute(f"select id, ibl_code from ibl_examples where ibl_code like '%:{a}]%'"):
            ids[i] = c
    from collections import Counter
    st, ic, wc = Counter(), Counter(), Counter()
    picks = {}
    for i, c in sorted(ids.items()):
        payload = dict(code='#!ibl edition=2\n' + c, edition=2, check=True, project_id='컨텐츠', origin='training', **AGENT)
        rr = post('ibl/execute', payload)
        st[rr.get('status')] += 1
        for x in rr.get('issues') or []:
            ic[x.get('code')] += 1
        for x in rr.get('warnings') or []:
            wc[x.get('code')] += 1
        if i in (4768, 4006, 4197, 4770, 4755, 4251):
            picks[i] = (rr.get('status'), [x.get('code') for x in rr.get('issues') or []], [x.get('code') for x in rr.get('warnings') or []])
    return (st.get('invalid', 0) == 0), f"n={len(ids)} status={dict(st)} issues={dict(ic)} warnings={dict(wc)} picks={picks}"


def t23():
    """[check] 부작용 사전 판정 — show_map(화면)·notify_user(발신)·write(쓰기) 의 check effects."""
    a = ex('return [limbs:show_map]{query:"청주시립미술관"}', check=True)
    b = ex('return [self:notify_user]{message:"IT79 주말 나들이: 토요일 흐림, 일요일 비"}', check=True)
    c = ex('return [self:write]{path:"outputs/IT79_x.json", content:"{}"}', check=True)
    d = ex('return [sense:weather]{city:"청주"}', check=True)
    return True, f"show_map={a.get('status')}/{a.get('effects')} · notify={b.get('status')}/{b.get('effects')} · write={c.get('status')}/{c.get('effects')} · weather={d.get('status')}/{d.get('effects')}"


def t24():
    """[판본 1] 저장·스케줄 호환 판본에서 정렬 내림차순 — desc vs descending(판본 2 이름)."""
    out = {}
    for key in ('desc', 'descending'):
        code = f'[table:sort]{{items: [{{a: 1}}, {{a: 3}}, {{a: 2}}], by: "a", {key}: true}}'
        payload = dict(code=code, edition=1, project_id='컨텐츠', origin='training', **AGENT)
        rr = post('ibl/execute', payload)
        LOG.append({'request': payload, 'response': rr, 'private': False})
        res = rr.get('result') or rr
        out[key] = ([x.get('a') for x in (res.get('items') or [])], (res.get('param_warning') or '')[:160])
    v2 = ex('return [table:sort]{items:[{a:1},{a:3},{a:2}], by:"a", desc:true}', check=True)
    return out['descending'][0] == [3, 2, 1], f"판본1 {out} · 판본2 desc check={v2.get('status')} {codes(v2)}"



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
    r = ex(sys.argv[2], private='--private' in sys.argv, **extra)
    if '--private' in sys.argv:
        mask_log(); print(json.dumps(LOG[-1]['response'], ensure_ascii=False, indent=1)[:6000]); return
    print(json.dumps({k: v for k, v in r.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')},
                     ensure_ascii=False, indent=1, default=str)[:12000])


def _tree_stat(root):
    root = Path(root)
    if not root.exists():
        return None
    files = [f for f in root.rglob('*') if f.is_file()]
    return {'files': len(files), 'max_mtime': max((f.stat().st_mtime for f in files), default=0)}


def _fstat(p):
    p = Path(p)
    if not p.exists():
        return None
    return {'size': p.stat().st_size, 'mtime': p.stat().st_mtime, 'h': h(p.read_bytes())}


def stores():
    """이 축이 건드릴 수 있는 사용자 상태 — 저장한 장소 원장·선언 위치·스크래치 폴더·실행기록 원장."""
    out = {
        'places_ledger': _fstat(PLACES_LEDGER),
        'body_location': _fstat(BODY_LOCATION),
        'scratch_IT79': sorted(p.name for p in SCRATCH.glob('IT79*')),
        'contents_outputs_count': len([p for p in SCRATCH.iterdir()]) if SCRATCH.exists() else None,
        'ibl_examples': q(BASE / 'data/ibl_usage.db', 'select count(*), max(id) from ibl_examples')[0],
        'episode_log_max': q(PULSE, 'select max(rowid) from episode_log')[0][0],
    }
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
