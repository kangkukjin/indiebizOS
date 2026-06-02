/**
 * InvestInstrument — 투자 "계기(instrument)" (앱 모드)
 *
 * 같은 IBL 위에서 사람이 직접 도는 다이얼 (세 탭):
 *   주식  [sense:search_stock] 검색 → [sense:price]+[sense:stock_info] → [sense:kr_price]/[sense:us_price] 차트
 *   코인  [sense:crypto] 시세 + 일별 이력 차트 (days/max_points)
 *   자원  [sense:price] 금(GC=F)·은(SI=F)·유가(CL=F) 등 선물 시세 + 차트 (period/max_points)
 * 검색·조회는 LLM 없이 IBL 직접 실행(0 토큰). 마지막 선택은 localStorage에 굳혀 다음 방문에 '이미 떠 있게'.
 *
 * 스키마 출처: data/ibl_nodes_src/sense.yaml (finance 그룹), investment/handler.py
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  ResponsiveContainer, LineChart, Line, YAxis, XAxis, Tooltip, CartesianGrid,
} from 'recharts';

const IBL_ENDPOINT = 'http://127.0.0.1:8765/ibl/execute';
const PROJECT_ID = '앱모드';
const CACHE_KEY = 'invest.instrument.last';

type Tab = 'stock' | 'crypto' | 'commodity';

interface Quote { symbol: string; name: string; exchange?: string; type?: string }
interface PricePoint { date: string; close: number }
interface PriceData {
  symbol: string; current_price?: number; currency?: string;
  change?: number; change_percent?: number; previous_close?: number;
  open?: number; high?: number; low?: number; volume?: number;
  prices?: PricePoint[]; sample?: PricePoint[];
}
interface InfoData {
  symbol: string; currency?: string; current_price?: number;
  market_cap?: number; market_cap_formatted?: string;
  '52_week_high'?: number; '52_week_low'?: number;
  '50_day_avg'?: number; '200_day_avg'?: number; volume?: number;
}
interface CryptoData {
  symbol: string; name?: string; current_price_usd?: number; current_price_krw?: number;
  change_24h_percent?: number; market_cap_formatted?: string; volume_24h_usd?: number;
  high_24h_usd?: number; low_24h_usd?: number; ath_usd?: number; rank?: number;
  prices?: PricePoint[];
}
interface IblResp<T> { success?: boolean; data?: T; error?: string; message?: string }

// 주식 빠른 접근 — 6자리=한국, 알파벳=미국
const STOCK_CHIPS: { name: string; symbol: string }[] = [
  { name: '삼성전자', symbol: '005930' }, { name: 'SK하이닉스', symbol: '000660' },
  { name: 'NAVER', symbol: '035420' }, { name: '카카오', symbol: '035720' },
  { name: 'Apple', symbol: 'AAPL' }, { name: 'NVIDIA', symbol: 'NVDA' },
  { name: 'Tesla', symbol: 'TSLA' }, { name: 'S&P500', symbol: 'SPY' },
];
const CRYPTO_CHIPS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA'];
// 자원(원자재) — Yahoo Finance 선물 심볼
const COMMODITY_CHIPS: { name: string; symbol: string }[] = [
  { name: '금', symbol: 'GC=F' }, { name: '은', symbol: 'SI=F' },
  { name: 'WTI 유가', symbol: 'CL=F' }, { name: '브렌트유', symbol: 'BZ=F' },
  { name: '천연가스', symbol: 'NG=F' }, { name: '구리', symbol: 'HG=F' },
];
const PERIODS: { key: string; label: string; days: number }[] = [
  { key: '5d', label: '5일', days: 7 }, { key: '1mo', label: '1개월', days: 31 },
  { key: '3mo', label: '3개월', days: 93 }, { key: '1y', label: '1년', days: 366 },
];

// ---------- helpers ----------
async function runIBL<T>(code: string): Promise<IblResp<T>> {
  try {
    const res = await fetch(IBL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, project_id: PROJECT_ID }),
    });
    return await res.json();
  } catch {
    return { success: false, error: '서버에 연결할 수 없습니다.' };
  }
}
const esc = (s: string) => s.replace(/"/g, '');
const isKR = (sym: string) => /^\d{6}$/.test(sym) || /\.(KS|KQ)$/i.test(sym);
const krBase = (sym: string) => sym.replace(/\.(KS|KQ)$/i, '');
const looksLikeSymbol = (q: string) => /^\d{6}$/.test(q.trim()) || /^[A-Za-z]{1,5}([.\-][A-Za-z]{1,3})?$/.test(q.trim());
const ymd = (d: Date) => d.toISOString().slice(0, 10);
const daysFor = (period: string) => PERIODS.find((p) => p.key === period)?.days || 31;
function fmtNum(n?: number, currency?: string) {
  if (n == null) return '—';
  if (currency === 'USD') return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
  return Math.round(n).toLocaleString('ko-KR');
}
function fmtVol(n?: number) {
  if (n == null) return '—';
  if (n >= 1e8) return (n / 1e8).toFixed(1) + '억';
  if (n >= 1e4) return (n / 1e4).toFixed(0) + '만';
  return n.toLocaleString();
}
// 한국 관례: 상승=빨강, 하락=파랑
const upColor = (v?: number) => (v == null || v === 0 ? 'text-stone-500' : v > 0 ? 'text-rose-600' : 'text-blue-600');
const upHex = (v?: number) => (v == null || v >= 0 ? '#e11d48' : '#2563eb');
const arrow = (v?: number) => (v == null || v === 0 ? '' : v > 0 ? '▲' : '▼');

interface Cache { tab: Tab; stockSymbol?: string; stockName?: string; crypto?: string; commodity?: string }
function loadCache(): Cache {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}'); } catch { return { tab: 'stock' }; }
}

export function InvestInstrument() {
  const init = useMemo(loadCache, []);
  const [tab, setTab] = useState<Tab>(init.tab || 'stock');
  const [period, setPeriod] = useState('1mo');

  // 주식 상태
  const [query, setQuery] = useState('');
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [selected, setSelected] = useState<{ symbol: string; name: string } | null>(
    init.stockSymbol ? { symbol: init.stockSymbol, name: init.stockName || init.stockSymbol } : null,
  );
  const [quote, setQuote] = useState<PriceData | null>(null);
  const [info, setInfo] = useState<InfoData | null>(null);
  const [chart, setChart] = useState<PricePoint[] | null>(null);

  // 코인 상태
  const [coin, setCoin] = useState(init.crypto || '');
  const [cryptoData, setCryptoData] = useState<CryptoData | null>(null);
  const [coinChart, setCoinChart] = useState<PricePoint[] | null>(null);

  // 자원 상태
  const [commodity, setCommodity] = useState(init.commodity || 'GC=F');
  const [commodityData, setCommodityData] = useState<PriceData | null>(null);
  const [commodityChart, setCommodityChart] = useState<PricePoint[] | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 결정화
  useEffect(() => {
    const c: Cache = {
      tab, stockSymbol: selected?.symbol, stockName: selected?.name,
      crypto: coin || undefined, commodity,
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(c));
  }, [tab, selected, coin, commodity]);

  // ===== 주식 =====
  const loadStock = useCallback(async (symbol: string, name: string) => {
    setSelected({ symbol, name });
    setQuotes(null);
    setLoading(true); setError(null);
    setQuote(null); setInfo(null);
    const [p, i] = await Promise.all([
      runIBL<PriceData>(`[sense:price]{symbol: "${esc(symbol)}"}`),
      runIBL<InfoData>(`[sense:stock_info]{symbol: "${esc(symbol)}"}`),
    ]);
    if (p.success && p.data) setQuote(p.data);
    else setError(p.error || '시세를 불러오지 못했습니다.');
    if (i.success && i.data) setInfo(i.data);
    setLoading(false);
  }, []);

  const loadChart = useCallback(async (symbol: string, days: number) => {
    const end = new Date();
    const start = new Date(); start.setDate(start.getDate() - days);
    const kr = isKR(symbol);
    const sym = kr ? krBase(symbol) : symbol;
    const action = kr ? 'kr_price' : 'us_price';
    const r = await runIBL<PriceData>(
      `[sense:${action}]{symbol: "${esc(sym)}", start_date: "${ymd(start)}", end_date: "${ymd(end)}", max_points: 400}`,
    );
    const pts = r.success ? (r.data?.prices || r.data?.sample) : null;
    setChart(pts && pts.length ? pts : null);
  }, []);

  useEffect(() => {
    if (tab === 'stock' && quote?.symbol) loadChart(quote.symbol, daysFor(period));
  }, [tab, quote?.symbol, period, loadChart]);

  const doSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    if (looksLikeSymbol(q)) { loadStock(q.toUpperCase(), q.toUpperCase()); return; }
    setLoading(true); setError(null); setQuotes(null);
    const r = await runIBL<{ quotes?: Quote[] }>(`[sense:search_stock]{query: "${esc(q)}"}`);
    setLoading(false);
    if (r.success && r.data?.quotes?.length) setQuotes(r.data.quotes);
    else setError('검색 결과가 없습니다. 회사명·종목코드(예: 005930)·티커로 다시 시도해 보세요.');
  }, [query, loadStock]);

  // ===== 코인 =====
  const loadCrypto = useCallback(async (sym: string) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setCoin(s);
    setLoading(true); setError(null); setCryptoData(null); setCoinChart(null);
    const r = await runIBL<CryptoData>(`[sense:crypto]{coin_id: "${esc(s)}"}`);
    setLoading(false);
    if (r.success && r.data) setCryptoData(r.data);
    else setError(r.error || '코인 시세를 불러오지 못했습니다.');
  }, []);

  // 코인 차트 (현재가와 분리 — 기간만 바꿔도 전체가 깜빡이지 않게)
  useEffect(() => {
    if (tab !== 'crypto' || !coin) return;
    let alive = true;
    runIBL<CryptoData>(`[sense:crypto]{coin_id: "${esc(coin)}", days: ${daysFor(period)}, max_points: 400}`)
      .then((r) => { if (alive) setCoinChart(r.success && r.data?.prices?.length ? r.data.prices : null); });
    return () => { alive = false; };
  }, [tab, coin, period]);

  // ===== 자원 =====
  const loadCommodity = useCallback(async (sym: string) => {
    setCommodity(sym);
    setLoading(true); setError(null); setCommodityData(null); setCommodityChart(null);
    const r = await runIBL<PriceData>(`[sense:price]{symbol: "${esc(sym)}"}`);
    setLoading(false);
    if (r.success && r.data) setCommodityData(r.data);
    else setError(r.error || '시세를 불러오지 못했습니다.');
  }, []);

  // 자원 차트 (기간별)
  useEffect(() => {
    if (tab !== 'commodity' || !commodity) return;
    let alive = true;
    runIBL<PriceData>(`[sense:price]{symbol: "${esc(commodity)}", period: "${period}", max_points: 400}`)
      .then((r) => {
        const pts = r.success ? (r.data?.prices || r.data?.sample) : null;
        if (alive) setCommodityChart(pts && pts.length ? pts : null);
      });
    return () => { alive = false; };
  }, [tab, commodity, period]);

  // 첫 진입/탭 전환 시 캐시된 선택 복원
  useEffect(() => {
    if (tab === 'stock' && selected && !quote) loadStock(selected.symbol, selected.name);
    if (tab === 'crypto' && coin && !cryptoData) loadCrypto(coin);
    if (tab === 'commodity' && commodity && !commodityData) loadCommodity(commodity);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const commodityName = COMMODITY_CHIPS.find((c) => c.symbol === commodity)?.name || commodity;

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8] text-stone-800">
      {/* 탭 */}
      <div className="shrink-0 flex gap-1 px-5 pt-4">
        {([['stock', '주식'], ['crypto', '코인'], ['commodity', '자원']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} onClick={() => { setTab(t); setError(null); }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              tab === t ? 'bg-stone-800 text-white' : 'bg-white text-stone-500 border border-stone-200 hover:bg-stone-50'
            }`}>
            {label}
          </button>
        ))}
      </div>

      {/* 검색/선택 줄 */}
      <div className="shrink-0 px-5 pt-3 pb-2">
        {tab === 'stock' && (
          <>
            <div className="flex gap-2">
              <input value={query} onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && doSearch()}
                placeholder="회사명·종목코드·티커 (예: 삼성전자, 카카오, AAPL, 005930)"
                className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
              <button onClick={doSearch}
                className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
            </div>
            <ChipRow chips={STOCK_CHIPS.map((c) => ({ key: c.symbol, label: c.name, active: false }))}
              onClick={(k) => { const c = STOCK_CHIPS.find((x) => x.symbol === k)!; setQuery(''); loadStock(c.symbol, c.name); }} />
          </>
        )}
        {tab === 'crypto' && (
          <>
            <div className="flex gap-2">
              <input value={coin} onChange={(e) => setCoin(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadCrypto(coin)}
                placeholder="코인 심볼 (예: BTC, ETH, SOL)"
                className="flex-1 px-3 py-2 rounded-xl border border-stone-200 bg-white text-sm outline-none focus:border-stone-400" />
              <button onClick={() => loadCrypto(coin)}
                className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm hover:bg-stone-700">조회</button>
            </div>
            <ChipRow chips={CRYPTO_CHIPS.map((c) => ({ key: c, label: c, active: coin === c }))}
              onClick={(k) => loadCrypto(k)} />
          </>
        )}
        {tab === 'commodity' && (
          <ChipRow chips={COMMODITY_CHIPS.map((c) => ({ key: c.symbol, label: c.name, active: commodity === c.symbol }))}
            onClick={(k) => loadCommodity(k)} />
        )}
      </div>

      {/* 본문 */}
      <div className="flex-1 min-h-0 overflow-auto px-5 pb-6">
        {loading && <div className="py-10 text-center text-stone-400 text-sm">불러오는 중…</div>}
        {error && !loading && <div className="py-6 text-center text-rose-500 text-sm">{error}</div>}

        {/* 주식 검색 결과 */}
        {tab === 'stock' && quotes && !loading && (
          <div className="space-y-1.5 max-w-2xl mx-auto">
            {quotes.map((q) => (
              <button key={q.symbol} onClick={() => loadStock(q.symbol, q.name)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-xl bg-white border border-stone-200 hover:border-stone-400 text-left">
                <div>
                  <div className="font-medium text-sm">{q.name}</div>
                  <div className="text-xs text-stone-400">{q.exchange} · {q.type}</div>
                </div>
                <span className="text-sm font-mono text-stone-500">{q.symbol}</span>
              </button>
            ))}
          </div>
        )}

        {/* 주식 상세 */}
        {tab === 'stock' && quote && !quotes && !loading && (
          <div className="max-w-2xl mx-auto">
            <QuoteHeader name={selected?.name || quote.symbol} symbol={quote.symbol}
              price={quote.current_price} currency={quote.currency}
              change={quote.change} changePct={quote.change_percent} />
            <ChartCard data={chart} currency={quote.currency} change={quote.change} period={period} setPeriod={setPeriod} />
            <StatGrid quote={quote} info={info} />
          </div>
        )}

        {/* 코인 상세 */}
        {tab === 'crypto' && cryptoData && !loading && (
          <div className="max-w-2xl mx-auto">
            <QuoteHeader name={cryptoData.name || cryptoData.symbol} symbol={`${cryptoData.symbol}${cryptoData.rank ? ` · #${cryptoData.rank}` : ''}`}
              price={cryptoData.current_price_usd} currency="USD"
              changePct={cryptoData.change_24h_percent} changeSuffix="(24h)"
              subPrice={`₩${fmtNum(cryptoData.current_price_krw)}`} />
            <ChartCard data={coinChart} currency="USD" change={cryptoData.change_24h_percent} period={period} setPeriod={setPeriod} />
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Cell label="시가총액" value={cryptoData.market_cap_formatted ? '$' + cryptoData.market_cap_formatted : '—'} />
              <Cell label="24h 거래량" value={cryptoData.volume_24h_usd ? '$' + fmtNum(cryptoData.volume_24h_usd, 'USD') : '—'} />
              <Cell label="24h 고가" value={'$' + fmtNum(cryptoData.high_24h_usd, 'USD')} />
              <Cell label="24h 저가" value={'$' + fmtNum(cryptoData.low_24h_usd, 'USD')} />
              <Cell label="사상 최고가" value={'$' + fmtNum(cryptoData.ath_usd, 'USD')} />
            </div>
          </div>
        )}

        {/* 자원 상세 */}
        {tab === 'commodity' && commodityData && !loading && (
          <div className="max-w-2xl mx-auto">
            <QuoteHeader name={commodityName} symbol={commodityData.symbol}
              price={commodityData.current_price} currency={commodityData.currency}
              change={commodityData.change} changePct={commodityData.change_percent} />
            <ChartCard data={commodityChart} currency={commodityData.currency} change={commodityData.change} period={period} setPeriod={setPeriod} />
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3">
              <Cell label="시가" value={fmtNum(commodityData.open, commodityData.currency)} />
              <Cell label="고가" value={fmtNum(commodityData.high, commodityData.currency)} />
              <Cell label="저가" value={fmtNum(commodityData.low, commodityData.currency)} />
              <Cell label="전일종가" value={fmtNum(commodityData.previous_close, commodityData.currency)} />
            </div>
          </div>
        )}

        {/* 빈 상태 */}
        {!loading && !error && (
          (tab === 'stock' && !quote && !quotes) ||
          (tab === 'crypto' && !cryptoData) ||
          (tab === 'commodity' && !commodityData)
        ) && (
          <div className="py-16 text-center text-stone-400 text-sm">
            {tab === 'stock' ? '종목을 검색하거나 위 빠른 버튼을 눌러보세요.'
              : tab === 'crypto' ? '코인 심볼을 입력하거나 위 버튼을 눌러보세요.'
              : '금·은·유가 등 자원을 눌러보세요.'}
          </div>
        )}
      </div>
    </div>
  );
}

function ChipRow({ chips, onClick }: { chips: { key: string; label: string; active: boolean }[]; onClick: (k: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {chips.map((c) => (
        <button key={c.key} onClick={() => onClick(c.key)}
          className={`px-2.5 py-1 rounded-full text-xs border ${
            c.active ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-600 hover:bg-stone-50'
          }`}>
          {c.label}
        </button>
      ))}
    </div>
  );
}

function QuoteHeader({ name, symbol, price, currency, change, changePct, changeSuffix, subPrice }: {
  name: string; symbol: string; price?: number; currency?: string;
  change?: number; changePct?: number; changeSuffix?: string; subPrice?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-stone-200 p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <span className="text-lg font-semibold">{name}</span>
          <span className="ml-2 text-xs text-stone-400">{symbol}</span>
        </div>
        <div className={`text-sm font-medium ${upColor(changePct)}`}>
          {arrow(changePct)} {change != null ? `${fmtNum(change, currency)} ` : ''}({changePct?.toFixed(2)}%)
          {changeSuffix && <span className="text-stone-400 ml-1">{changeSuffix}</span>}
        </div>
      </div>
      <div className="mt-3 text-3xl font-bold">
        {currency === 'USD' ? '$' : ''}{fmtNum(price, currency)}
        {currency && currency !== 'USD' && <span className="text-base font-normal text-stone-400 ml-1">{currency}</span>}
      </div>
      {subPrice && <div className="text-sm text-stone-500">{subPrice}</div>}
    </div>
  );
}

function ChartCard({ data, currency, change, period, setPeriod }: {
  data: PricePoint[] | null; currency?: string; change?: number; period: string; setPeriod: (p: string) => void;
}) {
  return (
    <div className="mt-4 bg-white rounded-2xl border border-stone-200 p-4">
      <div className="flex justify-end gap-1 mb-2">
        {PERIODS.map((p) => (
          <button key={p.key} onClick={() => setPeriod(p.key)}
            className={`px-2 py-0.5 rounded-md text-xs ${period === p.key ? 'bg-stone-800 text-white' : 'text-stone-400 hover:bg-stone-100'}`}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="h-48">
        {data && data.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ede8" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#a8a29e' }} minTickGap={40} />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#a8a29e' }}
                width={48} tickFormatter={(v) => fmtNum(v, currency)} />
              <Tooltip formatter={(v: number) => fmtNum(v, currency)}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e7e5e4' }} />
              <Line type="monotone" dataKey="close" stroke={upHex(change)} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-stone-400 text-sm">차트 데이터 없음</div>
        )}
      </div>
    </div>
  );
}

function StatGrid({ quote, info }: { quote: PriceData; info: InfoData | null }) {
  const cur = quote.currency;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3">
      <Cell label="시가" value={fmtNum(quote.open, cur)} />
      <Cell label="고가" value={fmtNum(quote.high, cur)} />
      <Cell label="저가" value={fmtNum(quote.low, cur)} />
      <Cell label="거래량" value={fmtVol(quote.volume)} />
      <Cell label="전일종가" value={fmtNum(quote.previous_close, cur)} />
      {info?.market_cap_formatted && <Cell label="시가총액" value={info.market_cap_formatted} />}
      {info?.['52_week_high'] != null && <Cell label="52주 최고" value={fmtNum(info['52_week_high'], cur)} />}
      {info?.['52_week_low'] != null && <Cell label="52주 최저" value={fmtNum(info['52_week_low'], cur)} />}
      {info?.['50_day_avg'] != null && <Cell label="50일 평균" value={fmtNum(info['50_day_avg'], cur)} />}
      {info?.['200_day_avg'] != null && <Cell label="200일 평균" value={fmtNum(info['200_day_avg'], cur)} />}
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-3 py-2">
      <div className="text-[11px] text-stone-400">{label}</div>
      <div className="text-sm font-medium mt-0.5">{value}</div>
    </div>
  );
}
