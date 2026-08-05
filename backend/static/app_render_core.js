/**
 * app_render_core.js — 앱 표면 렌더 어휘의 "순수 로직" 단일 소스 (표면 공용)
 *
 * 왜 여기 있나: 같은 15 프리미티브를 데스크탑(React/TSX)과 원격·폰(파이썬 문자열 속 JS)이
 * 이중 구현하고 있었고, 그 둘의 *로직*은 글자 그대로 번역된 사본이었다(템플릿 엔진·액션
 * 빌더·스파크라인 좌표·달력 월 산식·compose 채널 선택·미디어 소스 결정…). 마크업은 두
 * 표면이 다를 수밖에 없지만(JSX vs HTML 문자열) 로직이 둘일 이유는 없다 — 여기가 그 하나다.
 *
 * 규칙:
 *  - **DOM·프레임워크 의존 0**. 이스케이프처럼 표면마다 다른 것은 *인자로 받는다*(esc, T).
 *  - 두 소비자:
 *      데스크탑 = Vite 가 ESM 으로 import (frontend/src/components/generic/manifest.ts)
 *      원격·폰   = backend/launcher_render_core.py 가 이 파일을 읽어 **맨 끝 export 블록만**
 *                 떼고 런처 <script> 안에 인라인 → 함수들이 전역이 된다(선언 호이스팅).
 *    그래서 파일 맨 끝의 ESM-export 마커 블록은 **파일의 마지막이어야 하고**, 그 위쪽에는
 *    `export` 키워드를 쓰지 않는다(고전 스크립트에선 SyntaxError).
 *  - 모듈 최상위 값은 `var`(고전 스크립트 인라인 시 TDZ 회피).
 *
 * 어휘 자체(어떤 프리미티브가 있는가)의 정본은 여전히 build_ibl_nodes.APP_VIEW_TYPES.
 */

/* ===== 경로·템플릿 엔진 ===== */

/** "a.b.c" 경로로 중첩 값 꺼내기 (없으면 undefined) */
function jget(o, path) {
  if (!path) return o;
  return String(path).split('.').reduce(function (a, k) { return a == null ? undefined : a[k]; }, o);
}

/** 표시 필터 — {값|round}, {값|opt:앞,뒤} 등 */
function applyFilter(v, f) {
  if (f === 'round') return v == null ? v : Math.round(Number(v));
  if (f === 'num') return v == null ? null : Number(v).toLocaleString();
  if (f === 'abs') return v == null ? v : Math.abs(Number(v));
  if (f === 'arrow') return (Number(v) || 0) >= 0 ? '▲' : '▼';
  if (f.indexOf('opt:') === 0) {
    var a = f.slice(4).split(',');
    return (v == null || v === '' || Number(v) === 0) ? '' : (a[0] || '') + String(v) + (a[1] || '');
  }
  if (f.indexOf('trunc:') === 0) {
    var n = parseInt(f.slice(6)) || 40;
    var s = String(v == null ? '' : v);
    return s.length > n ? s.slice(0, n) + '…' : s;
  }
  return v;
}

/**
 * "{path|filter|...}" → 문자열 치환.
 * esc = 치환된 *값* 에 적용할 함수. 원격(HTML 문자열)은 HTML 이스케이퍼를 넘기고,
 * 데스크탑(React 가 알아서 이스케이프)은 안 넘긴다(=String).
 */
function tplWith(t, data, esc) {
  if (t == null) return '';
  var e = esc || String;
  return String(t).replace(/\{([^{}]+)\}/g, function (_m, expr) {
    var parts = expr.split('|');
    var v = jget(data, parts[0].trim());
    for (var i = 1; i < parts.length; i++) v = applyFilter(v, parts[i].trim());
    return v == null ? '' : e(v);
  });
}

/**
 * $key 치환(사용자 입력) + 빈 입력 'param: ""' 쌍 자동 제거.
 * ★값은 스트립이 아니라 이스케이프 — IBL 값은 JSON5 문자열 리터럴로 파싱되므로
 *   윈도우 경로(C:\Users\…)의 백슬래시를 스트립하면 깨진다.
 */
function buildAction(template, values) {
  var code = String(template).replace(/\$(\w+)/g, function (_m, k) {
    var v = values ? values[k] : undefined;
    return v == null ? '' : String(v).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  });
  code = code.replace(/\w+:\s*"",?\s*/g, '');
  code = code.replace(/,\s*\}/g, '}').replace(/\{\s*,/g, '{');
  return code;
}

/** 행 데이터 {path} 치환 (드릴·행 버튼용) */
function rowAction(template, item) {
  return String(template).replace(/\{([\w.]+)\}/g, function (_m, path) {
    var v = jget(item, path);
    return v == null ? '' : String(v).replace(/"/g, '');
  });
}

/** view 통화 슬라이스 — from:'.' 은 응답 자체를 1행으로 */
function viewList(data, from) {
  if (from === '.') return [data];
  var a = jget(data, from);
  return Array.isArray(a) ? a : [];
}

/** 빈 결과 문구 (empty_from → empty → 기본) */
function emptyText(p, data) {
  return (p.empty_from ? jget(data, p.empty_from) : null) || p.empty || '결과가 없습니다';
}

/** 추세 방향 — p.trend 없으면 null(색 없음), 있으면 상승 여부. 색 어휘는 표면 몫. */
function trendUp(p, data) {
  if (!p.trend) return null;
  return (Number(jget(data, p.trend)) || 0) >= 0;
}

function statusGlyph(s) {
  return s === 'sent' ? '✓' : s === 'pending' ? '⏳' : s === 'failed' ? '⚠' : '';
}

/** 합성(>>) 응답의 final_result(마지막 단계)를 펼쳐 단일 액션처럼 노출 */
function unwrapFinalResult(data) {
  if (data && typeof data === 'object' && 'final_result' in data) {
    var fr = data.final_result;
    if (typeof fr === 'string') {
      try { return JSON.parse(fr); } catch (_e) { return { message: fr }; }
    }
    if (fr && typeof fr === 'object') return fr;
  }
  return data;
}

/* ===== 프리미티브 모델 (마크업 없는 결정층) ===== */

/**
 * group 파티션 — from 리스트를 키로 나눈다(입력 순서 보존).
 * keyOf(item) 는 표면의 템플릿 함수(이스케이프 정책 포함)를 그대로 받는다.
 */
function groupPartition(arr, keyOf, maxGroups) {
  var order = [], groups = {};
  arr.forEach(function (it) {
    var key = keyOf(it);
    if (!(key in groups)) { groups[key] = []; order.push(key); }
    groups[key].push(it);
  });
  var keys = maxGroups ? order.slice(0, maxGroups) : order;
  return keys.map(function (k) { return { key: k, members: groups[k] }; });
}

/** 스파크라인 수치 포맷 — 큰 값(가격)은 정수·천단위, 작은 값(환율·코인)은 소수 */
function fmtSpark(n) {
  var a = Math.abs(n);
  var d = a >= 1000 ? 0 : a >= 1 ? 2 : 4;
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: d });
}

/**
 * sparkline 좌표 모델 — 점이 2개 미만이면 null(그리지 않음).
 * x축 라벨 필드: p.x 우선, 없으면 흔한 시간 필드 자동 감지.
 */
function sparkModel(p, data) {
  var arr = viewList(data, p.from);
  var first = arr[0];
  var xkey = p.x || (first && typeof first === 'object'
    ? ['date', 'time', 'label', 'x'].filter(function (k) { return first[k] != null; })[0]
    : undefined);
  var rows = arr.map(function (x) {
    return { v: Number(p.y ? x[p.y] : x), x: xkey ? String(x[xkey] == null ? '' : x[xkey]) : '' };
  }).filter(function (r) { return !isNaN(r.v); });
  if (rows.length < 2) return null;
  var vals = rows.map(function (r) { return r.v; });
  var w = 280, h = 50;
  var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals), rg = (mx - mn) || 1;
  var px = function (i) { return (i / (rows.length - 1)) * w; };
  var py = function (v) { return h - ((v - mn) / rg) * h; };
  var pts = rows.map(function (r, i) { return px(i).toFixed(1) + ',' + py(r.v).toFixed(1); }).join(' ');
  return { rows: rows, xkey: xkey, w: w, h: h, mn: mn, mx: mx, rg: rg, px: px, py: py, pts: pts };
}

/**
 * calendar 월 모델 — year/month(1-12) 기준.
 *  byDay: 날짜 명확 이벤트(none/monthly/yearly)를 일자 → 이벤트[] 로
 *  recurring: 정기(daily/weekly/interval) — 그리드 밖 목록
 *  cells: 앞 공백 + 1..말일 (7의 배수로 뒤 패딩)
 * ★그 달에 없는 날(2월 31일 등)은 버린다 — monthly 반복의 31일이 30일 달에 새지 않게.
 */
var CAL_PERIODIC = ['daily', 'weekly', 'interval'];
function calendarModel(events, year, month) {
  var byDay = {};
  var daysInMonth = new Date(year, month, 0).getDate();
  (events || []).forEach(function (e) {
    var rep = e.repeat || 'none';
    if (CAL_PERIODIC.indexOf(rep) >= 0) return;
    var ps = e.date ? String(e.date).split('-').map(Number) : null;
    if (!ps || ps.length < 3) return;
    var day = null;
    if (rep === 'monthly') day = ps[2];
    else if (rep === 'yearly') { if (ps[1] === month) day = ps[2]; }
    else if (ps[0] === year && ps[1] === month) day = ps[2];
    if (day && day >= 1 && day <= daysInMonth) (byDay[day] = byDay[day] || []).push(e);
  });
  var recurring = (events || []).filter(function (e) { return CAL_PERIODIC.indexOf(e.repeat || '') >= 0; });
  var firstWeekday = new Date(year, month - 1, 1).getDay();
  var cells = [];
  for (var i = 0; i < firstWeekday; i++) cells.push(null);
  for (var d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);
  return { byDay: byDay, recurring: recurring, cells: cells, firstWeekday: firstWeekday, daysInMonth: daysInMonth };
}

/** 월 이동 (1-12 유지) */
function calShift(year, month, delta) {
  var m = month + delta, y = year;
  if (m < 1) { m = 12; y--; }
  if (m > 12) { m = 1; y++; }
  return { year: y, month: m };
}

function pad2(n) { return (n < 10 ? '0' : '') + n; }

/**
 * compose 발신 채널 후보 — 드릴 데이터의 연락처 배열에서 발신 가능한 채널만.
 * 없으면 기본(primary) 채널로 폴백. 백엔드가 정한 data.channel 을 맨 앞으로 올린다
 * (작성바 기본 선택=opts[0] — 등록 순서와 무관하게 nostr 를 가진 이웃은 nostr 가 기본).
 */
function composeChannelOptions(cmp, data) {
  var ch = cmp && cmp.channels;
  if (!ch || !data || typeof data !== 'object') return [];
  var mk = function (ct, to, label) { return { key: ct + '|' + to, channel_type: ct, to: to, label: label }; };
  var str = function (o, k) { var v = jget(o, k); return v == null ? '' : String(v); };
  var opts = viewList(data, ch.from)
    .map(function (c) { return { ct: str(c, ch.type), to: str(c, ch.value) }; })
    .filter(function (o) { return o.to && (!ch.sendable || ch.sendable.indexOf(o.ct) >= 0); })
    .map(function (o) { return mk(o.ct, o.to, o.ct + ' · ' + o.to); });
  if (!opts.length) {
    var ct = str(data, 'channel'), to = str(data, 'to');
    if (to) opts = [mk(ct, to, ct || '기본')];
  }
  var seen = {};
  var uniq = opts.filter(function (o) { return seen[o.key] ? false : (seen[o.key] = 1, true); });
  var prefCt = str(data, 'channel');
  if (prefCt) {
    var i = uniq.findIndex(function (o) { return o.channel_type === prefCt; });
    if (i > 0) { var pick = uniq.splice(i, 1)[0]; uniq.unshift(pick); }
  }
  return uniq;
}

/**
 * 느린 회선 판정 — navigator.connection(크로미움 계열). 테슬라 실측 1.4Mbps/350ms 가 걸린다.
 * 참이면 media_player 가 src_low(저대역 판)를 자동 선택한다.
 */
function isSlowNet(conn) {
  return !!conn && ((!!conn.downlink && conn.downlink < 3) || (!!conn.rtt && conn.rtt > 250));
}

/** lazy: 목록에 떠 있다고 스트림을 미리 물지 않는다(요청 자체가 서버 작업인 src) */
function preloadOf(p) { return p.lazy ? 'none' : 'metadata'; }

/**
 * media_player 한 항목의 소스 결정 — T 는 표면의 템플릿 함수(이스케이프 정책 포함).
 * URL 을 절대화하는 방식은 표면마다 달라(데스크탑=백엔드 origin 부착 / 원격=동일 origin)
 * 여기선 *어떤 문자열을 고를지*만 정한다.
 */
function mediaModel(p, it, T, slowNet) {
  var lowRaw = (typeof p.src_low === 'string') ? T(p.src_low, it) : '';
  var src = (slowNet && lowRaw) ? lowRaw : (p.src ? T(p.src, it) : '');
  var isVideo = p.video === true || (typeof p.video === 'string' && /^(true|1)$/i.test(T(p.video, it)));
  return {
    src: src,
    hls: (typeof p.src_hls === 'string') ? T(p.src_hls, it) : '',
    isVideo: isVideo,
    poster: p.poster ? T(p.poster, it) : '',
    title: p.title ? T(p.title, it) : '',
    preload: preloadOf(p),
  };
}

/* ===== 모드-레벨 결정 ===== */

/** master_detail card_list 가 있으면 2분할 레이아웃 */
function hasMasterDetail(view) {
  return (view || []).some(function (p) { return p && p.type === 'card_list' && !!p.master_detail; });
}

/** 동적 필터(filter.from_field) — 결과 필드의 distinct 값(칩 상한 12는 표면에서) */
function dynFilterCats(data, from, field) {
  if (!field || !data) return [];
  var seen = {}, cats = [];
  viewList(data, from || 'items').forEach(function (it) {
    var v = jget(it, field);
    if (v && !seen[v]) { seen[v] = 1; cats.push(String(v)); }
  });
  return cats;
}

/** 동적 필터 적용 — 고른 값의 행만 남긴 통화 사본(map 마커·card_list 동시 거름) */
function applyDynFilter(data, from, field, value) {
  if (!field || value == null || !data) return data;
  var key = from || 'items';
  var arr = viewList(data, key).filter(function (it) { return String(jget(it, field)) === String(value); });
  var nd = {};
  for (var k in data) nd[k] = data[k];
  nd[key] = arr;
  return nd;
}

/** attachment_path(JSON 배열 또는 레거시 단일 문자열) → 경로 배열 */
function parseImagePaths(v) {
  var s = String(v == null ? '' : v).trim();
  if (!s) return [];
  try { var a = JSON.parse(s); if (Array.isArray(a)) return a.map(String); } catch (_e) { /* 레거시 단일 */ }
  return [s];
}

/* ===== 폼 필드 공용 어휘 ===== */

/** 반복 주기 표준 어휘 — recurrence 필드 타입의 baked 옵션(manage_events repeat 값과 일치) */
var RECURRENCE_OPTS = [['none', '한 번'], ['daily', '매일'], ['weekly', '매주'], ['monthly', '매월'], ['yearly', '매년']];

/** date/time 은 그대로, datetime → datetime-local */
function dateInputType(t) { return t === 'datetime' ? 'datetime-local' : t; }

/* --- ESM export (데스크탑 Vite 전용 — 원격 인라인 시 이 블록만 제거된다. 파일의 마지막) --- */
export {
  jget, applyFilter, tplWith, buildAction, rowAction, viewList,
  emptyText, trendUp, statusGlyph, unwrapFinalResult,
  groupPartition, fmtSpark, sparkModel,
  CAL_PERIODIC, calendarModel, calShift, pad2,
  composeChannelOptions, isSlowNet, preloadOf, mediaModel,
  hasMasterDetail, dynFilterCats, applyDynFilter, parseImagePaths,
  RECURRENCE_OPTS, dateInputType,
};
