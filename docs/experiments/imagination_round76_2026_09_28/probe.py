"""76회차: 외부 조회 조합 — 부동산·투자 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 외부 조회 어휘(sense:realty·stock·crypto·company·weather·http·kosis·world_bank·
commercial·legal)를 table:join·merge·union·rename·compute·groupby·judge 와 조합.
도메인: 청주·오송(청주시 흥덕구 43113) 아파트 실거래가/전세가·전세가율, 단지별 평균·전월 대비, 매물 호가 vs 실거래,
관심 종목 현재가·수익률 표, DART 재무+주가, 환율·원자재·코인, 지역 통계(KOSIS)·세계은행, 날씨 조건,
법령 조회, 외부 조회 실패 폴백·부분 실패·빈 결과.

모든 요청 edition 2·project_id 컨텐츠·origin training·agent_id IT76_probe·task_id IT76_task.
★외부 API 는 읽기 조회만. 같은 조회 반복을 피하려고 과제마다 한 프로그램 안에서 변수로 재사용한다.
★발신 0(notify_user·channel_send 는 쓰지 않는다 — 조건 알림 과제는 return 으로 판정만).
★table:judge(유료 Jev API)는 T22 한 번, 행 5개 이하.
사용: .venv/bin/python probe.py baseline | run [tNN ...] | after | raw '<code>'
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
AGENT = {'agent_id': 'IT76_probe', 'task_id': 'IT76_task'}
LOG = []
PULSE = BASE / 'data/world_pulse.db'
SINCE = BASE / 'data/table_since.db'


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


# ───────────────────────── 과제 ─────────────────────────
# 지역 상수: 오송 = 청주시 흥덕구(43113). 기간은 최근 두 달(2026-08·09).

T01_CODE = '''
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202608", end_month:"202609"}
$g = $t.items >> [table:groupby]{by:"아파트명", agg:{평균가:["avg","price"], 건수:["count"]}}
$top = $g.items >> [table:filter]{where:($r)=> $r.건수 >= 3} >> [table:sort]{by:"평균가", descending:true} >> [table:take]{n:5}
return {total:len($t.items), truncated:get($t,"truncated",null), 조회지역:get($t,"조회지역",null), groups:len($g.items), top:$top}
'''


def t01():
    """[부동산] 오송(흥덕구) 아파트 최근 두 달 매매 실거래를 단지별 평균가·건수로, 3건 이상 단지 중 비싼 순 5개."""
    r = ex(T01_CODE)
    v = val(r) or {}
    return bool(r.get('success') and v.get('top')), ok_or_err(r, 700)


T02_CODE = '''
$r = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"rent", start_month:"202608", end_month:"202609"}
$j = $r.items >> [table:filter]{where:($x)=> $x.계약유형 == "전세"}
$g = $j >> [table:groupby]{by:"아파트명", agg:{평균보증금:["avg","보증금"], 건수:["count"]}}
return {rows:len($r.items), jeonse:len($j), groups:len($g.items), sample_row:$r.items[0], top:($g.items >> [table:sort]{by:"건수", descending:true} >> [table:take]{n:3})}
'''


def t02():
    """[부동산] 오송 아파트 전세 실거래(전월세 중 전세만) 단지별 평균 보증금."""
    r = ex(T02_CODE)
    v = val(r) or {}
    return bool(r.get('success') and v.get('top')), ok_or_err(r, 900)


T03_FIRST = """(첫 시도 — 훈련자 문장 잘못) join on:"아파트명" 단일 키 → '효성' 전세가율 328.6%.
격리: 매매 '효성'=복대동 37.48㎡ 7,000만원 · 전세 '효성'=가경동 99.98㎡ 23,000만원 — 다른 단지·다른 평형.
molit 행에 법정동·전용면적이 있으므로 복합 키 + 평형 띠로 고쳐 다시 찍었다."""

T03_CODE = """
[def:국평]($rows) {
  return $rows >> [table:filter]{where:($x)=> number($x.전용면적) >= 59 and number($x.전용면적) <= 85}
}
[def:단지평균]($rows, $값열, $이름) {
  $g = $rows >> [table:groupby]{by:["아파트명","법정동"], agg:{평균:["avg", $값열], 건수:["count"]}}
  return $g.items >> [table:rename]{map:{평균:$이름}}
}
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202608", end_month:"202609"}
$r = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"rent", start_month:"202608", end_month:"202609"}
$jeonse = $r.items >> [table:filter]{where:($x)=> $x.계약유형 == "전세"}
$매매 = [fn:단지평균]{rows:[fn:국평]{rows:$t.items}, 값열:"price", 이름:"매매평균원"}
$전세 = [fn:단지평균]{rows:[fn:국평]{rows:$jeonse}, 값열:"보증금", 이름:"전세평균만원"}
$j = [table:join]{left:$매매, right:$전세, on:["아파트명","법정동"]}
$rate = $j.items >> [table:compute]{set:($x)=> {전세가율: round($x.전세평균만원 * 10000 / $x.매매평균원 * 100, 1)}}
$over = $rate >> [table:filter]{where:($x)=> $x.전세가율 >= 80}
return {matched:len($j.items), over80:len($over), rows:($rate >> [table:sort]{by:"전세가율", descending:true} >> [table:take]{n:5})}
"""


def t03():
    """[부동산] 오송 단지별 전세가율(국평 59~85㎡, 전세 평균 ÷ 매매 평균) 높은 순 — 깡통전세 위험 단지."""
    r = ex(T03_CODE)
    v = val(r) or {}
    return bool(r.get('success') and v.get('rows')), ok_or_err(r, 1000) + ' | ' + T03_FIRST.splitlines()[0]


T04_CODE = """
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202608", end_month:"202609"}
[def:월평균]($rows, $월, $이름) {
  $m = $rows >> [table:filter]{where:($x)=> $x.거래월 == $월}
  $g = $m >> [table:groupby]{by:"아파트명", agg:{평균:["avg","price"]}}
  return $g.items >> [table:rename]{map:{평균:$이름}}
}
$a = [fn:월평균]{rows:$t.items, 월:"8", 이름:"8월"}
$b = [fn:월평균]{rows:$t.items, 월:"9", 이름:"9월"}
$j = [table:join]{left:$a, right:$b, on:"아파트명"}
$d = $j.items >> [table:compute]{set:($x)=> {변화율: round((get($x,"9월",null) - get($x,"8월",null)) / get($x,"8월",null) * 100, 1)}}
$up = $d >> [table:filter]{where:($x)=> $x.변화율 > 0}
return {both:len($j.items), up:len($up), top:($d >> [table:sort]{by:"변화율", descending:true} >> [table:take]{n:3})}
"""


def t04():
    """[부동산] 오송 단지별 매매 평균가 전월(8월) 대비 9월 변화율 — 오른 단지 상위 3."""
    r = ex(T04_CODE)
    v = val(r) or {}
    return bool(r.get('success') and v.get('top') is not None), ok_or_err(r, 900)


def t05():
    """[부동산] 거래 없는 달(아직 안 온 2026-12)·없는 단지 — 빈 결과가 정직하게 0으로 흐르나(groupby·join·compute)."""
    r = ex("""
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202612", end_month:"202612"}
$g = $t.items >> [table:groupby]{by:"아파트명", agg:{평균가:["avg","price"]}}
$none = $t.items >> [table:filter]{where:($x)=> $x.아파트명 == "없는단지"}
$j = [table:join]{left:$g.items, right:[{아파트명:"x", 전세:1}], on:"아파트명"}
$c = $j.items >> [table:compute]{set:($x)=> {비율: $x.전세 / $x.평균가}}
return {n:len($t.items), total:get($t,"total",null), truncated:get($t,"truncated",null), msg:get($t,"message",null), summary:get($t,"summary",null), groups:len($g.items), joined:len($c), none:len($none)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n') == 0), ok_or_err(r, 900)


T06_CODE = """
$ask = [sense:realty]{source:"naver", region:"청주 오송읍", type:"apt", deal:"trade", limit:30}
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202608", end_month:"202609"}
$deal = $t.items >> [table:groupby]{by:"아파트명", agg:{실거래평균:["avg","price"], 건수:["count"]}}
$dealn = $deal.items >> [table:rename]{map:{아파트명:"name"}}
$askg = $ask.items >> [table:groupby]{by:"name", agg:{호가평균:["avg","price"], 매물:["count"]}}
$j = [table:join]{left:$askg.items, right:$dealn, on:"name"}
$gap = $j.items >> [table:compute]{set:($x)=> {갭: round(($x.호가평균 - $x.실거래평균) / $x.실거래평균 * 100, 1)}}
return {asks:len($ask.items), ask_names:len($askg.items), matched:len($j.items), ask_keys:keys($ask.items[0]), sample_meta:$ask.items[0].meta, rows:($gap >> [table:sort]{by:"갭", descending:true} >> [table:take]{n:5}), unmatched:[table:join]{how:"anti", left:$askg.items, right:$dealn, on:"name"}}
"""


T06_AREA = """
$ask = [sense:realty]{source:"naver", region:"청주 오송읍", type:"apt", deal:"trade", limit:30}
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202608", end_month:"202609"}
# naver 행에는 면적 칸이 없다 — meta "매매 3억 8,500 · 85/59㎡ · …" 의 둘째 칸을 쪼개 전용면적을 꺼낸다
$a2 = $ask.items >> [table:compute]{set:($x)=> {전용: number(replace(split(split($x.meta, " · ")[1], "/")[1], "㎡", ""))}}
$a59 = $a2 >> [table:filter]{where:($x)=> $x.전용 >= 59 and $x.전용 <= 85}
$t59 = $t.items >> [table:filter]{where:($x)=> number($x.전용면적) >= 59 and number($x.전용면적) <= 85}
$ag = $a59 >> [table:groupby]{by:"name", agg:{호가평균:["avg","price"], 매물:["count"]}}
$tg = $t59 >> [table:groupby]{by:"아파트명", agg:{실거래평균:["avg","price"], 건수:["count"]}}
$tn = $tg.items >> [table:rename]{map:{아파트명:"name"}}
$j = [table:join]{left:$ag.items, right:$tn, on:"name"}
$gap = $j.items >> [table:compute]{set:($x)=> {갭: round(($x.호가평균 - $x.실거래평균) / $x.실거래평균 * 100, 1)}}
return {asks_59_85:len($a59), matched:len($j.items), rows:($gap >> [table:sort]{by:"갭", descending:true})}
"""


def t06():
    """[부동산] 오송 아파트 네이버 매물 호가 vs 최근 두 달 실거래 — 단지별 호가 거품(갭%). 전 평형 혼합판과 국평(59~85㎡) 맞춤판."""
    r = ex(T06_CODE)
    v = val(r) or {}
    r2 = ex(T06_AREA, reuse={'run_id': '206af466c72041f5864857e5d6b4d979'})
    return bool(r.get('success') and v.get('matched') and r2.get('success')), ok_or_err(r, 1100) + ' || 국평맞춤(meta 쪼개기)=' + ok_or_err(r2, 800)


def t07():
    """[부동산] 오송 아파트 전세 매물 — 코퍼스 형태 deal:"lease"(4097·4116·4129)와 교재 형태 deal:"rent", lease:"전세" 비교."""
    r = ex("""
$a = [sense:realty]{source:"naver", region:"청주 오송읍", type:"apt", deal:"lease", limit:30}
$b = [sense:realty]{source:"naver", region:"청주 오송읍", type:"apt", deal:"rent", lease:"전세", limit:30}
[def:유형수]($rows) {
  $j = $rows >> [table:filter]{where:($x)=> contains($x.meta, "전세 ")}
  $w = $rows >> [table:filter]{where:($x)=> contains($x.meta, "월세 ")}
  return {전세:len($j), 월세:len($w)}
}
return {lease_form:{n:len($a.items), msg:$a.message, kinds:[fn:유형수]{rows:$a.items}, ignored:get($a,"무시된_파라미터",null)}, rent_jeonse:{n:len($b.items), msg:$b.message, kinds:[fn:유형수]{rows:$b.items}}}
""")
    v = val(r) or {}
    lf = (v.get('lease_form') or {}).get('kinds') or {}
    return bool(r.get('success') and lf.get('월세', 0) == 0), ok_or_err(r, 900)


def t08():
    """[부동산] 오송 빌라 전세 직방 매물 — ㎡당 보증금 싼 순 5개."""
    r = ex("""
$z = [sense:realty]{source:"zigbang", region:"청주 오송읍", type:"villa", deal:"rent", lease:"전세", limit:30}
$u = $z.items >> [table:filter]{where:($x)=> get($x,"area_m2",null) != null and get($x,"deposit",null) != null}
$c = $u >> [table:compute]{set:($x)=> {만원_m2: round($x.deposit / $x.area_m2, 1)}}
return {n:len($z.items), usable:len($u), msg:$z.message, rows:($c >> [table:sort]{by:"만원_m2"} >> [table:take]{n:5} >> [table:select]{columns:["title","deposit","area_m2","floor","만원_m2"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n') is not None), ok_or_err(r, 900)


HOLD = '[{ticker:"005930", name:"삼성전자", 매수가:210000, 수량:10}, {ticker:"000660", name:"SK하이닉스", 매수가:1800000, 수량:2}, {ticker:"035420", name:"NAVER", 매수가:230000, 수량:5}]'


def t09():
    """[투자] 관심 종목 셋 현재가·평가손익·수익률 표 + 한 줄 요약(보간)."""
    r = ex(f"""
$h = {HOLD}
$rows = $h >> [table:each] {{
  $q = [sense:stock]{{op:"quote", ticker:$it.ticker}}
  $p = $q.items[0].current_price
  return {{name:$it.name, 현재가:$p, 수익률:round(($p - $it.매수가) / $it.매수가 * 100, 2), 평가손익:($p - $it.매수가) * $it.수량, as_of:get($q.items[0],"as_of",null)}}
}}
$parts = $rows >> [table:each] {{ return f"${{$it.name}} ${{$it.현재가}}원(${{$it.수익률}}%)" }}
$parts2 = $rows >> [table:each] {{ return f"${{$it.name}} ${{round($it.현재가)}}원" }}
$pl = $rows >> [table:each] {{ return $it.평가손익 }}
return {{rows:$rows, 합계손익:sum($pl), line:join(", ", $parts), line_round:join(", ", $parts2)}}
""")
    v = val(r) or {}
    return bool(r.get('success') and len(v.get('rows') or []) == 3), ok_or_err(r, 1200)


def t10():
    """[투자] 관심 종목 중 하나가 없는 코드(ZZZZ99)·상장폐지형(999999) — 되는 것만 표로, 실패는 이유와 함께."""
    r = ex("""
$h = [{ticker:"005930", name:"삼성전자"}, {ticker:"ZZZZ99", name:"오타종목"}, {ticker:"999999", name:"없는코드"}]
$res = $h >> [table:each]{on_error:"collect"} {
  $q = [sense:stock]{op:"quote", ticker:$it.ticker}
  return {name:$it.name, 현재가:$q.items[0].current_price}
}
$ok = $res >> [table:each]{mode:"flat_map"} { [if: is_ok($it)] { return [unwrap($it)] } [else] { return [] } }
$bad = $res >> [table:each]{mode:"flat_map"} { [if: is_ok($it)] { return [] } [else] { $e = error_of($it); return [{code:$e.code, msg:$e.message}] } }
return {ok:$ok, bad:$bad}
""")
    v = val(r) or {}
    return bool(r.get('success') and len(v.get('ok') or []) == 1 and len(v.get('bad') or []) == 2), ok_or_err(r, 1500)


def t11():
    """[투자] 삼성전자 DART 2025 재무(당기순이익·EPS)와 현재가를 합쳐 PER — 시총 경로(info)와 EPS 경로 둘 다."""
    info = ex('return [sense:stock]{op:"info", ticker:"005930"}')
    r = ex("""
$f = [sense:company]{op:"financials", ticker:"삼성전자", year:"2025"}
$q = [sense:stock]{op:"quote", ticker:"005930"}
$doc = [self:read]{path:$f.data.file_path}
$sel = [self:ledger]{op:"select", path:$f.data.file_path, target:"income_statement"}
$eps = $sel.items >> [table:filter]{where:($x)=> $x.account_name == "기본주당이익"}
$ni = $sel.items >> [table:filter]{where:($x)=> $x.account_name == "당기순이익"}
$p = $q.items[0].current_price
$e = number($eps[0].current_amount)
return {read_data_keys:keys($doc.data), read_items0:keys($doc.data.items[0]), spill:$f.data.file_path, 당기순이익:number($ni[0].current_amount), EPS:$e, 현재가:$p, PER:round($p / $e, 1)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('PER')), f"info(시총)={('OK' if info.get('success') else 'FAIL ' + err(info)[:160])} || eps_path={ok_or_err(r, 700)}"


def t12():
    """[투자] 원달러 환율·금 선물·비트코인을 한 표로 — 금 1온스·BTC 1개 원화 환산."""
    r = ex("""
$fx = [sense:stock]{op:"quote", ticker:"USDKRW=X"}
$gold = [sense:stock]{op:"quote", ticker:"GC=F"}
$btc = [sense:crypto]{coin:"BTC"}
$u = [table:union]{inputs:[$fx, $gold, $btc]}
$rate = $fx.items[0].current_price
$rows = $u.items >> [table:each] {
  $cur = get($it, "currency", "USD")
  [if: $cur == "KRW"] { $won = $it.current_price } [else] { $won = round($it.current_price * $rate) }
  return {symbol:get($it,"symbol",null), 가격:$it.current_price, 통화:$cur, 원화:$won}
}
return {n:len($u.items), rows:$rows, btc_krw_field:$btc.items[0].current_price_krw, btc_usd_field:$btc.items[0].current_price_usd, btc_has_currency:has($btc.items[0], "currency")}
""", reuse={'run_id': '0e3659ca31f04f989b368e083aae8b5c'})
    v = val(r) or {}
    btc = [x for x in (v.get('rows') or []) if x.get('symbol') == 'BTC']
    sane = bool(btc) and v.get('btc_krw_field') and btc[0].get('원화') <= v['btc_krw_field'] * 1.01
    return bool(r.get('success') and v.get('n') == 3 and sane), ok_or_err(r, 1500)


def t13():
    """[투자] 비트코인 30일 가격 이력 — 30일 전 대비 변화율·최고/최저."""
    r = ex("""
$c = [sense:crypto]{coin:"BTC", days:30}
$p = $c.data.prices
$closes = $p >> [table:each] { return $it.close }
return {n:len($p), first:$p[0], last:$p[-1], 변화율:round(($p[-1].close - $p[0].close) / $p[0].close * 100, 2), 최고:max($closes), 최저:min($closes), now_usd:$c.items[0].current_price_usd, now_krw:$c.items[0].current_price_krw}
""")
    v = val(r) or {}
    return bool(r.get('success')), ok_or_err(r, 1200)


def t14():
    """[부동산·통계] 흥덕구 월별 주민등록인구(KOSIS)와 월별 아파트 매매 건수를 나란히 — 검색→메타→데이터→join."""
    r = ex("""
$s = [sense:kosis]{query:"시군구별 주민등록인구"}
$m = [sense:kosis]{org_id:"101", tbl_id:"DT_1B040A3", info:true}
$hd = $m.items[0].codes >> [table:filter]{where:($x)=> contains($x.name, "흥덕")}
$pop = [sense:kosis]{org_id:"101", tbl_id:"DT_1B040A3", obj_l1:$hd[0].id, prd_se:"M", start_prd_de:"202608", end_prd_de:"202609"}
$t = [sense:realty]{source:"molit", region_code:"43113", type:"apt", deal:"trade", start_month:"202608", end_month:"202609"}
$cnt = $t.items >> [table:groupby]{by:"조회년월", agg:{매매건수:["count"]}}
$cn = $cnt.items >> [table:rename]{map:{조회년월:"기간"}}
$j = [table:join]{left:$pop.items, right:$cn, on:"기간"}
return {search_n:len($s.items), code:$hd, pop_n:len($pop.items), pop_keys:keys($pop.items[0]), pop0:$pop.items[0], joined:$j.items}
""", reuse={'run_id': '76356b4f381f474487566303271af040'})  # 첫 시도(on:"period" — kosis.md 차트 예시의 열 이름)는 join 이 "실제 필드: 기간 …"으로 정직 거절 → 고쳐 reuse 로 재실행
    v = val(r) or {}
    return bool(r.get('success') and v.get('joined')), ok_or_err(r, 1500)


T15_FIXED = """
$h = [sense:stock]{op:"history", ticker:"005930", period:"5y", max_points:MAXP}
$w = [sense:world_bank]{indicator:"GDP", country:"한국"}
$y = $h.items >> [table:compute]{set:($x)=> {연도: $x.date[0:4]}}
$ya = $y >> [table:groupby]{by:"연도", agg:{평균종가:["avg","close"]}}
$j = [table:join]{left:$ya.items, right:$w.items, on:"연도"}
return {h_n:len($h.items), h_trunc:get($h,"truncations",null), w_n:len($w.items), joined:$j.items}
"""


def t15():
    """[투자·통계] 한국 GDP(세계은행)와 삼성전자 연도별 평균 주가 결합 — join 설명문 예문 그대로·max_points 전량(1500)·표본(100)."""
    lit = ex('return [sense:stock]{op:"history", ticker:"005930", period:"5y"} & [sense:world_bank]{indicator:"GDP", country:"한국"} >> [table:join]{on:"연도"}')
    full = ex(T15_FIXED.replace('MAXP', '1500'))
    r = ex(T15_FIXED.replace('MAXP', '100'))
    v = val(r) or {}
    def why(x):
        d = (x.get('diagnostic') or {}).get('partial')
        t = d.get('truncations') if isinstance(d, dict) else None
        return f"{err(x)[:80]} truncations={js(t, 200)}"
    return bool(r.get('success') and v.get('joined')), (f"literal={'OK' if lit.get('success') else why(lit)} || max_points1500={'OK' if full.get('success') else why(full)} || "
                                                       f"max_points100={ok_or_err(r, 900)}")


def t16():
    """[부동산] 이번 주말 오송 임장 — 청주 사흘 예보에 비(5mm 이상) 오는 날이 있으면 연기."""
    r = ex("""
$w = [sense:weather]{city:"청주", days:3}
$rain = $w.items >> [table:filter]{where:($x)=> get($x,"precipitation_mm",0) >= 5}
[if: len($rain) > 0] { return {판정:"임장 연기", 비오는날:$rain} } [else] { return {판정:"임장 OK", 예보:$w.items} }
""")
    return bool(r.get('success')), ok_or_err(r, 900)


def t17():
    """[부동산] 오송역 반경 1km 상권 — 업종 대분류 상위 5."""
    r = ex("""
$c = [sense:commercial]{query:"오송역", radius:1000}
$g = $c.items >> [table:groupby]{by:"category"}
return {n:len($c.items), truncated:get($c,"truncated",null), 조회지역:get($c,"조회지역",null), top:($g.items >> [table:sort]{by:"count", descending:true} >> [table:take]{n:5})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('top')), ok_or_err(r, 900)


def t18():
    """[부동산·법률] 주택임대차보호법 법령과 전세보증금 반환 판례 최근 3건씩."""
    r = ex("""
$law = [sense:legal]{query:"주택임대차보호법"}
$prec = [sense:legal]{query:"전세보증금 반환", target:"prec"}
return {law:($law.items >> [table:take]{n:3} >> [table:select]{columns:["title","date","url"]}), prec:($prec.items >> [table:sort]{by:"date", descending:true} >> [table:take]{n:3} >> [table:select]{columns:["title","date"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('law')), ok_or_err(r, 1200)


def t19():
    """[부동산] 이 집 등기부(근저당) 떼 줘 — 어휘가 있나. 없는 op 를 realty 에 주면 어떻게 되나(check·실행)."""
    c = ex('return [sense:realty]{op:"registry", region:"청주시 흥덕구", query:"오송역파라곤센트럴시티 101동"}', check=True)
    r = ex('$x = [sense:realty]{op:"registry", region:"청주시 흥덕구"}\nreturn {n:len(get($x,"items",[])), type:get($x,"type",null), period:get($x,"period",null), param_warning:get($x,"param_warning",null), keys:keys($x)}',
           reuse={'run_id': '1859ee509a7d400080512293c4858e21'})
    return (c.get('status') == 'invalid' or not r.get('success')), f"check={c.get('status')} {err(c)[:200]} | exec={ok_or_err(r, 400)}"


def t20():
    """[부동산] 네이버가 못 찾으면 직방으로, 둘 다 안 되면 이유 — 없는 동네·없는 시군구 폴백."""
    a = ex("""
$m = [sense:realty]{source:"naver", region:"없는동네가나다"} ?? [sense:realty]{source:"zigbang", region:"없는동네가나다"}
return {n:len($m.items), msg:get($m,"message",null)}
""")
    b = ex("""
[try] { $x = [sense:realty]{source:"molit", region:"없는시가나다", type:"apt", deal:"trade"}; $out = {n:len($x.items)} }
[catch] { $out = {code:$error.code, kind:get($error,"kind",null), msg:$error.message} }
return $out
""")
    return bool(a.get('success') or b.get('success')), f"naver??zigbang={ok_or_err(a, 500)} || molit_try={ok_or_err(b, 500)}"


def t21():
    """[부동산] 국토부 API·네이버부동산이 살아 있나 먼저 보고 조회 경로 고르기 (http head 두 개 → 표)."""
    r = ex("""
$a = [sense:http]{url:"https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"}
$b = [sense:http]{url:"https://m.land.naver.com/"}
$u = [table:union]{inputs:[$a, $b]}
$s = $u.items >> [table:select]{columns:["url","status","ok","elapsed_ms"]}
$up = $s >> [table:filter]{where:($x)=> contains($x.url, "data.go.kr") and $x.status < 500}
[if: len($up) > 0] { $route = "molit" } [else] { $route = "naver" }
return {rows:$s, route:$route}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('rows')), ok_or_err(r, 900)


def t22():
    """[부동산] 오송 아파트 매매 매물 설명에 급매·가격조정 언급이 있는 것만 (judge 5행)."""
    r = ex("""
$ask = [sense:realty]{source:"naver", region:"청주 오송읍", type:"apt", deal:"trade", limit:30}
$five = $ask.items >> [table:filter]{where:($x)=> len($x.summary) > 0} >> [table:take]{n:5} >> [table:select]{columns:["title","summary","price"]}
$j = $five >> [table:judge]{instruction:"매물 설명이 급매이거나 가격 조정 가능을 언급하는가", as:"급매"}
return {n:len($five), rows:($j.items >> [table:select]{columns:["title","summary","급매_result_value","급매_result_status"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('rows') is not None), ok_or_err(r, 1500)


def t23():
    """[부동산] 복대동 빌라 전세를(첫 시도 오송읍은 naver 0·zigbang 1건이라 표본이 없어 복대동으로) 네이버·직방에서 모아 한 표로 — 보증금 단위를 맞춰 싼 순."""
    r = ex("""
$n = [sense:realty]{source:"naver", region:"청주 복대동", type:"villa", deal:"rent", lease:"전세", limit:30}
$z = [sense:realty]{source:"zigbang", region:"청주 복대동", type:"villa", deal:"rent", lease:"전세", limit:30}
$nn = $n.items >> [table:compute]{set:($x)=> {보증금만원: $x.price / 10000, 출처:"naver"}}
$zz = $z.items >> [table:compute]{set:($x)=> {보증금만원: $x.deposit, 출처:"zigbang"}}
$m = [table:merge]{inputs:[$nn, $zz], by:"url"}
return {naver:len($n.items), zigbang:len($z.items), merged:len($m.items), rows:($m.items >> [table:sort]{by:"보증금만원"} >> [table:take]{n:5} >> [table:select]{columns:["title","보증금만원","출처"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('merged') is not None), ok_or_err(r, 1200)


def t24():
    """[부동산] 코퍼스 4097(전세 감시)·4112 형태를 판본 2 check 로 — count($m)·'$m.items.0.title'·deal:'lease'·[if]{파이프}."""
    a = ex("""
$m = [sense:realty]{source:"naver", region:"죽백동", deal:"lease"} >> [table:since]{key:"IT76_x"}
[if: count($m) > 0] { return "보냄" } [else] { return "없음" }
""", check=True)
    b = ex("""
$m = [sense:realty]{source:"naver", region:"죽백동", deal:"lease"}
return {body:'$m.items.0.title'}
""", check=True)
    c = ex("""
return [sense:realty]{source:"naver", region:"죽백동", deal:"rent", lease:"전세"} >> [if: count($items) > 10]{[table:take]{n:10}} [else]{[table:sort]{by:"price"}}
""", check=True)
    return (a.get('status') == 'invalid' and c.get('status') == 'invalid'), f"4097={a.get('status')} {err(a)[:250]} | str_path={b.get('status')} {err(b)[:200]} | 4112={c.get('status')} {err(c)[:250]}"


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
        store['log'].extend({'task': task.__name__, **e} for e in LOG)
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:1500], flush=True)
    store['rows'] = [rows[k] for k in sorted(rows)]
    store['passed'] = sum(r['ok'] for r in store['rows'])
    store['total'] = len(store['rows'])
    path.write_text(json.dumps(store, ensure_ascii=False, indent=1))
    print(f"{store['passed']}/{store['total']}")


def raw():
    extra = {}
    if '--check' in sys.argv:
        extra['check'] = True
    r = ex(sys.argv[2], **extra)
    print(json.dumps({k: v for k, v in r.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')},
                     ensure_ascii=False, indent=1, default=str)[:12000])


def snapshot():
    notes = post('notifications?limit=100', method='GET')
    return {
        'at': datetime.now().isoformat(timespec='seconds'),
        'notifications': [{k: n.get(k) for k in ('id', 'type', 'title', 'created_at')} for n in notes['notifications']],
        'action_health_max_id': q(PULSE, 'select max(id) from action_health')[0][0],
        'notify_log_max_id': q(PULSE, 'select max(id) from notify_log')[0][0],
        'since_streams': q(SINCE, 'select count(distinct stream), count(*) from since_seen')[0],
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
        'notify_log_new': q(PULSE, 'select id, title, emitter, source from notify_log where id > ?', (b['notify_log_max_id'],)),
        'since_streams': a['since_streams'],
    }
    base['after'] = {'snapshot': {k: a[k] for k in ('at', 'action_health_max_id', 'notify_log_max_id')}, 'diff': diff}
    (HERE / 'baseline.json').write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(json.dumps(diff, ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == '__main__':
    {'baseline': baseline, 'run': run, 'after': after, 'raw': raw}[sys.argv[1]]()
