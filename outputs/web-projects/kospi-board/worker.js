/**
 * 국내 시세 보드 — TIGER 200 · 삼성전자 · 코스피
 * Cloudflare Worker 단일 파일 (프론트엔드 HTML + /api/quotes)
 * 데이터 원천: 네이버 금융 폴링 API (실시간, delayTime=0 — 2026-08-01 실측)
 *   폴백: Yahoo Finance chart API (KRX ~20분 지연) — 네이버 실패·차단 시 자동 강등
 */

const SYMBOLS = [
  { key: "tiger200", symbol: "102110.KS", naver: "stock/102110", label: "TIGER 200", sub: "미래에셋 TIGER 200 ETF", unit: "원" },
  { key: "samsung",  symbol: "005930.KS", naver: "stock/005930", label: "삼성전자",  sub: "005930 · KOSPI",          unit: "원" },
  { key: "kospi",    symbol: "^KS11",     naver: "index/KOSPI",  label: "코스피",    sub: "KOSPI Composite Index",   unit: "p"  },
];

const NAVER = "https://polling.finance.naver.com/api/realtime/domestic/";
const YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/";

const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122 Safari/537.36";

// 관용 숫자 파서 — 네이버 *Raw 필드가 맥 IP에선 숫자, Worker(해외 엣지)에선
// 문자열("109520")로 오는 것을 실측(2026-08-01). 둘 다 받고, 콤마 표기도 흡수.
function num(v) {
  if (typeof v === "number" && isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v.replace(/,/g, ""));
    if (isFinite(n)) return n;
  }
  return null;
}

// 1순위: 네이버 폴링 API — 실시간(delayTime=0), 전일대비·등락률을 서버가 직접
// 준다(전일 종가는 price-change 로 역산). Raw 필드 우선, 없으면 포맷 필드 파싱.
async function fetchQuoteNaver(item) {
  const res = await fetch(`${NAVER}${item.naver}`, {
    headers: { "User-Agent": UA, "Accept": "application/json" },
    cf: { cacheTtl: 10, cacheEverything: true },
  });
  if (!res.ok) throw new Error(`네이버 HTTP ${res.status}`);
  const data = await res.json();
  const d = data?.datas?.[0];
  if (!d) throw new Error("네이버 빈 응답");
  const price = num(d.closePriceRaw) ?? num(d.closePrice);
  const change = num(d.compareToPreviousClosePriceRaw) ?? num(d.compareToPreviousClosePrice);
  if (price == null || change == null) throw new Error("네이버 가격 필드 없음");
  return {
    ...item,
    ok: true,
    src: "naver",
    price,
    prevClose: price - change,
    change,
    changePct: num(d.fluctuationsRatioRaw) ?? num(d.fluctuationsRatio),
    high: num(d.highPriceRaw) ?? num(d.highPrice),
    low: num(d.lowPriceRaw) ?? num(d.lowPrice),
    volume: num(d.accumulatedTradingVolumeRaw),
    quoteTime: d.localTradedAt ? Date.parse(d.localTradedAt) : null,
    marketStatus: d.marketStatus || null,
    name: d.stockName || item.label,
  };
}

// 2순위(폴백): Yahoo — KRX ~20분 지연. 네이버가 Worker 해외 IP를 막거나 형식이 바뀌면 강등.
async function fetchQuoteYahoo(item) {
  const url = `${YAHOO}${encodeURIComponent(item.symbol)}?range=1d&interval=1d`;
  const res = await fetch(url, {
    headers: { "User-Agent": UA, "Accept": "application/json" },
    cf: { cacheTtl: 15, cacheEverything: true },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const result = data?.chart?.result?.[0];
  if (!result) throw new Error("빈 응답");
  const m = result.meta || {};
  const price = m.regularMarketPrice;
  const prev = m.chartPreviousClose;
  if (typeof price !== "number" || typeof prev !== "number") throw new Error("가격 필드 없음");

  const q = result.indicators?.quote?.[0] || {};
  const high = Array.isArray(q.high) ? q.high.filter(v => typeof v === "number").pop() : null;
  const low  = Array.isArray(q.low)  ? q.low.filter(v => typeof v === "number").pop()  : null;
  const vol  = Array.isArray(q.volume) ? q.volume.filter(v => typeof v === "number").pop() : null;

  return {
    ...item,
    ok: true,
    src: "yahoo",
    price,
    prevClose: prev,
    change: price - prev,
    changePct: prev ? ((price - prev) / prev) * 100 : null,
    high, low, volume: vol,
    quoteTime: m.regularMarketTime ? m.regularMarketTime * 1000 : null,
    marketStatus: null,
    name: m.longName || m.shortName || item.label,
  };
}

async function fetchQuote(item) {
  try {
    return await fetchQuoteNaver(item);
  } catch (e1) {
    try {
      return await fetchQuoteYahoo(item);
    } catch (e2) {
      return { ...item, ok: false, error: `네이버: ${e1.message} / Yahoo: ${e2.message}` };
    }
  }
}

async function handleQuotes() {
  const quotes = await Promise.all(SYMBOLS.map(fetchQuote));
  return new Response(
    JSON.stringify({ ok: true, fetchedAt: Date.now(), quotes }, null, 2),
    {
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",
      },
    }
  );
}

const HTML = `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>국내 시세 보드 — TIGER 200 · 삼성전자 · 코스피</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>📈</text></svg>">
<style>
  :root{
    --bg:#f6f7f9; --card:#fff; --line:#e6e8ec; --tx:#16181d; --tx2:#6b7280;
    --up:#e8342a; --down:#1a63d8; --flat:#6b7280; --shadow:0 1px 2px rgba(16,24,40,.05),0 6px 20px rgba(16,24,40,.06);
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#0e1014; --card:#171a20; --line:#262a33; --tx:#eceef2; --tx2:#98a0ae;
           --up:#ff5c50; --down:#5b9bff; --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.35); }
  }
  *{box-sizing:border-box}
  body{
    margin:0; background:var(--bg); color:var(--tx);
    font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR",system-ui,sans-serif;
    -webkit-font-smoothing:antialiased; padding:22px 16px 40px;
  }
  .wrap{max-width:760px;margin:0 auto}
  header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}
  h1{font-size:19px;margin:0;letter-spacing:-.02em;font-weight:700}
  .meta{font-size:12.5px;color:var(--tx2);font-variant-numeric:tabular-nums}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#22c55e;margin-right:6px;vertical-align:1px}
  .dot.stale{background:#f59e0b} .dot.err{background:#ef4444}
  .grid{display:grid;gap:12px}
  .card{
    background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 18px 15px;
    box-shadow:var(--shadow); transition:opacity .2s;
  }
  .card.loading{opacity:.55}
  .top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
  .label{font-size:15.5px;font-weight:650;letter-spacing:-.01em}
  .sub{font-size:12px;color:var(--tx2);margin-top:3px}
  .price{font-size:31px;font-weight:750;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1.1}
  .unit{font-size:15px;font-weight:600;color:var(--tx2);margin-left:3px}
  .chg{font-size:14.5px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:5px;text-align:right}
  .right{text-align:right;flex-shrink:0}
  .up{color:var(--up)} .down{color:var(--down)} .flat{color:var(--flat)}
  .rows{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:14px;padding-top:12px;border-top:1px solid var(--line);
        font-size:12.5px;color:var(--tx2);font-variant-numeric:tabular-nums}
  .rows b{color:var(--tx);font-weight:600}
  .holding{display:flex;align-items:baseline;justify-content:space-between;gap:8px 16px;flex-wrap:wrap;
    margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}
  .holding-details{display:flex;flex-wrap:wrap;gap:8px 20px;width:100%;font-size:13px;color:var(--tx2);font-variant-numeric:tabular-nums}
  .holding-details b{font-weight:650;color:var(--tx)}
  .holding-performance{display:flex;flex-wrap:wrap;gap:12px 24px;width:100%;margin-top:6px}
  .holding-performance span{display:flex;flex-direction:column;gap:4px;font-size:14px}
  .holding-performance b{font-size:24px;font-weight:750;letter-spacing:-.03em;line-height:1.2;white-space:nowrap}
  .holding-details b.up{color:var(--up)} .holding-details b.down{color:var(--down)}
  .holding-label{font-size:13px;color:var(--tx2)}
  .holding-value{font-size:26px;font-weight:750;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
  .err{color:var(--up);font-size:13px;margin-top:8px}
  footer{margin-top:22px;font-size:11.5px;color:var(--tx2);line-height:1.7}
  button{
    font:inherit;font-size:12.5px;padding:7px 14px;border-radius:999px;border:1px solid var(--line);
    background:var(--card);color:var(--tx);cursor:pointer;box-shadow:var(--shadow)
  }
  button:active{transform:translateY(1px)}
  button:disabled{opacity:.5;cursor:default}
  .bar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>📈 국내 시세 보드</h1>
    <div class="meta" id="status"><span class="dot"></span>불러오는 중…</div>
  </header>

  <div class="bar">
    <button id="refresh">새로고침</button>
    <span class="meta" id="auto">30초마다 자동 갱신</span>
  </div>

  <div class="grid" id="grid"></div>

  <footer>
    시세 출처: 네이버 금융(<b>실시간</b>) · 장애 시 Yahoo Finance(~20분 지연)로 자동 전환 · 표시 시각은 한국 표준시(KST)<br>
    투자 판단의 근거로 쓰기 전에 증권사 시세로 확인하세요.
  </footer>
</div>

<script>
const TIGER200_SHARES = 643;
const TIGER200_AVG_COST = 54397;
const KRW = new Intl.NumberFormat('ko-KR');
const PT  = new Intl.NumberFormat('ko-KR', {minimumFractionDigits:2, maximumFractionDigits:2});
const KST = ts => new Date(ts).toLocaleString('ko-KR', {timeZone:'Asia/Seoul', hour12:false,
  month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit'});

const fmt = (v, unit) => v == null ? '—' : (unit === 'p' ? PT.format(v) : KRW.format(v));
const cls = c => c > 0 ? 'up' : c < 0 ? 'down' : 'flat';
const sign = c => c > 0 ? '▲' : c < 0 ? '▼' : '—';

function holding(q){
  const valid = Number.isFinite(q.price) && q.price > 0;
  const cost = TIGER200_AVG_COST * TIGER200_SHARES;
  const value = valid ? q.price * TIGER200_SHARES : null;
  const profit = valid ? value - cost : null;
  const rate = valid ? profit / cost * 100 : null;
  const signed = (v, format) => v == null ? '—' : (v > 0 ? '+' : '') + format(v);
  return '<div class="holding">'
    + '<span class="holding-label">어머니 보유 주식 · TIGER 200 ' + KRW.format(TIGER200_SHARES) + '주</span>'
    + '<div class="holding-value">' + fmt(value, '원') + '<span class="unit">원</span></div>'
    + '<div class="sub">시세 기준 평가금액</div>'
    + '<div class="holding-details">'
    + '<span>평균 매수가 <b>' + KRW.format(TIGER200_AVG_COST) + '원</b></span>'
    + '<span>매수금액 <b>' + KRW.format(cost) + '원</b></span>'
    + '<div class="holding-performance">'
    + '<span>평가손익 <b class="' + cls(profit) + '">' + signed(profit, v => KRW.format(v)) + '원</b></span>'
    + '<span>수익률 <b class="' + cls(profit) + '">' + signed(rate, v => v.toFixed(2)) + '%</b></span>'
    + '</div></div><div class="sub">수수료·세금·분배금 제외</div></div>';
}

function card(q){
  if (!q.ok) return \`
    <div class="card">
      <div class="top"><div><div class="label">\${q.label}</div><div class="sub">\${q.sub}</div></div></div>
      <div class="err">시세를 가져오지 못했습니다 — \${q.error || '알 수 없는 오류'}</div>
    </div>\`;

  const c = cls(q.change);
  const pct = q.changePct == null ? '—' : (q.changePct > 0 ? '+' : '') + q.changePct.toFixed(2) + '%';
  const chg = (q.change > 0 ? '+' : '') + fmt(q.change, q.unit);
  return \`
    <div class="card">
      <div class="top">
        <div>
          <div class="label">\${q.label}</div>
          <div class="sub">\${q.sub}</div>
        </div>
        <div class="right">
          <div class="price \${c}">\${fmt(q.price, q.unit)}<span class="unit">\${q.unit}</span></div>
          <div class="chg \${c}">\${sign(q.change)} \${chg} (\${pct})</div>
        </div>
      </div>
      \${q.key === 'tiger200' ? holding(q) : ''}
      <div class="rows">
        <span>전일 종가 <b>\${fmt(q.prevClose, q.unit)}</b></span>
        <span>고가 <b>\${fmt(q.high, q.unit)}</b></span>
        <span>저가 <b>\${fmt(q.low, q.unit)}</b></span>
        \${q.volume ? \`<span>거래량 <b>\${KRW.format(q.volume)}</b></span>\` : ''}
        \${q.quoteTime ? \`<span>시세 시각 <b>\${KST(q.quoteTime)}</b></span>\` : ''}
        <span>\${q.src === 'naver' ? '⚡ 실시간' : '지연(~20분)'}\${q.marketStatus === 'CLOSE' ? ' · 장마감' : ''}</span>
      </div>
    </div>\`;
}

let timer = null;

async function load(){
  const grid = document.getElementById('grid');
  const status = document.getElementById('status');
  const btn = document.getElementById('refresh');
  grid.querySelectorAll('.card').forEach(el => el.classList.add('loading'));
  btn.disabled = true;
  try{
    const res = await fetch('/api/quotes', {cache:'no-store'});
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    grid.innerHTML = data.quotes.map(card).join('');
    const bad = data.quotes.filter(q => !q.ok).length;
    status.innerHTML = '<span class="dot' + (bad ? ' stale' : '') + '"></span>'
      + KST(data.fetchedAt) + ' 갱신' + (bad ? \` · \${bad}건 실패\` : '');
  }catch(e){
    document.getElementById('status').innerHTML =
      '<span class="dot err"></span>갱신 실패 — ' + e.message;
    grid.querySelectorAll('.card').forEach(el => el.classList.remove('loading'));
  }finally{
    btn.disabled = false;
  }
}

document.getElementById('refresh').addEventListener('click', load);
document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
load();
timer = setInterval(load, 30000);
</script>
</body>
</html>`;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/api/quotes") return handleQuotes();
    if (path === "/health") return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
    if (path === "/" || path === "/index.html") {
      return new Response(HTML, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=60",
        },
      });
    }
    return new Response("Not Found: " + path, { status: 404 });
  },
};
