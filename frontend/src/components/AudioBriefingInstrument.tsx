/**
 * AudioBriefingInstrument — 오디오 브리핑 "계기(instrument)" (앱 모드)
 *
 * 신문 계기(NewspaperInstrument)와 같은 급 — 디자인은 이 컴포넌트에 있고, 내용은
 * 기존 어휘 조합으로 채운다: 날씨([sense:weather]) + 코스피·TIGER200 시세([sense:stock])
 * + 오늘의 핫뉴스([sense:search_gnews], 신문과 동일한 curate 방식) → 뉴스는 경량 AI([self:ask])가
 * 하나의 자연스러운 소개 멘트로 엮고 → 전체 스크립트를 TTS([engines:tts])로 mp3화.
 * 앱 = 어휘 조합 + 약간의 코딩.
 *
 * ★발행 모델(신문과 동일): 열 때마다 재생성하지 않는다. "브리핑 만들기"를 누를 때만 새로
 *  만들어 최신 판을 저장(outputs/audio_briefing_current.json, [self:write])한다. 다음에 열면
 *  저장된 판을 그대로 보여준다(재생성 없음). mp3 자체는 프로젝트 outputs/ 에 파일로 남고,
 *  재생은 기존 /launcher/file 엔드포인트(산출물 바이트 서빙, 백엔드 기존 API)로 스트리밍한다.
 */
import { useCallback, useEffect, useState } from 'react';
import { iblExecuteApp, askAI } from '../lib/instrument';

const API = 'http://127.0.0.1:8765';
const CITY_KEY = 'audioBriefing.city';
const EDITION_PATH = 'outputs/audio_briefing_current.json';
const MD_PATH = 'outputs/audio_briefing_current.md';

const DEFAULT_CITY = '청주';

interface NewsItem { title?: string; meta?: string; summary?: string; url?: string }
interface StockData { current_price?: number; change?: number; change_percent?: number; currency?: string }
interface WeatherResp { current?: { temp?: number; feels_like?: number; humidity?: number; condition?: string } }

// 저장되는 판.
interface Edition {
  city: string; script: string; audioPath: string; articles: NewsItem[];
  dateLabel: string; issuedAt: string; durationSec?: number;
}

const audioFileUrl = (absPath: string) => `${API}/launcher/file?path=${encodeURIComponent(absPath)}`;

async function loadEdition(): Promise<Edition | null> {
  try {
    const r = await iblExecuteApp(`[self:read]{path: ${JSON.stringify(EDITION_PATH)}}`);
    if (r && typeof r === 'object' && (r as Edition).audioPath) return r as Edition;
  } catch { /* 저장된 판 없음 */ }
  return null;
}

async function saveEdition(ed: Edition): Promise<void> {
  const content = JSON.stringify(ed);
  await iblExecuteApp(`[self:write]{path: ${JSON.stringify(EDITION_PATH)}, content: ${JSON.stringify(content)}}`);
}

// 폰/원격 뷰어(정기보고식)가 읽을 스크립트 판을 남긴다 — 파생물이라 실패해도 발행 자체는 유지.
async function saveMarkdown(dateLabel: string, script: string, articles: NewsItem[]): Promise<void> {
  try {
    const lines = [`# 오디오 브리핑 · ${dateLabel}`, '', script.trim(), ''];
    if (articles.length) {
      lines.push('---', '', '**관련 기사**', '');
      for (const a of articles) lines.push(`- [${a.title || '(제목 없음)'}](${a.url || ''})${a.meta ? ` — ${a.meta}` : ''}`);
    }
    await iblExecuteApp(`[self:write]{path: ${JSON.stringify(MD_PATH)}, content: ${JSON.stringify(lines.join('\n'))}}`);
  } catch { /* 파생 파일 실패는 발행을 막지 않는다 */ }
}

// TTS 결과 텍스트("TTS 생성 완료: /abs/path.mp3\n길이: 12.3초\n음성: ...")에서 경로·길이 추출.
function parseTtsResult(raw: string): { path: string | null; durationSec?: number } {
  const pathMatch = raw.match(/TTS 생성 완료:\s*(.+?)(?:\n|$)/);
  const durMatch = raw.match(/길이:\s*([\d.]+)\s*초/);
  return {
    path: pathMatch ? pathMatch[1].trim() : null,
    durationSec: durMatch ? parseFloat(durMatch[1]) : undefined,
  };
}

const dir = (n?: number) => (typeof n === 'number' ? (n >= 0 ? '상승' : '하락') : '');
const pctAbs = (n?: number) => (typeof n === 'number' ? Math.abs(n).toFixed(2) : null);

function buildIndexLine(kospi?: StockData, tiger?: StockData): string {
  const parts: string[] = [];
  if (kospi?.current_price != null) {
    parts.push(`코스피 지수는 ${Math.round(kospi.current_price).toLocaleString()}포인트로 전일 대비 ${pctAbs(kospi.change_percent)}% ${dir(kospi.change_percent)}했습니다.`);
  }
  if (tiger?.current_price != null) {
    parts.push(`TIGER200은 ${Math.round(tiger.current_price).toLocaleString()}원으로 ${pctAbs(tiger.change_percent)}% ${dir(tiger.change_percent)}했습니다.`);
  }
  return parts.length ? parts.join(' ') : '증시 정보를 가져오지 못했습니다.';
}

const todayStr = () => {
  const d = new Date();
  const wd = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${wd})`;
};

const whenLabel = (iso: string | null): string | null => {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return null; }
};

export function AudioBriefingInstrument() {
  const [city, setCity] = useState<string>(() => localStorage.getItem(CITY_KEY) || DEFAULT_CITY);
  const [editing, setEditing] = useState(false);
  const [script, setScript] = useState<string>('');
  const [articles, setArticles] = useState<NewsItem[]>([]);
  const [audioPath, setAudioPath] = useState<string | null>(null);
  const [durationSec, setDurationSec] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState<string>(todayStr);
  const [issuedAt, setIssuedAt] = useState<string | null>(null);

  const onCity = (c: string) => { setCity(c); localStorage.setItem(CITY_KEY, c); };

  // mp3 로컬 저장(다운로드) — 저장 후 Finder/공유시트로 친구에게 공유 가능(OS 표준 경로).
  const saveMp3 = async () => {
    if (!audioPath) return;
    try {
      const res = await fetch(audioFileUrl(audioPath));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const d = new Date();
      const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = `오디오브리핑_${stamp}.mp3`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError('mp3 저장 중 오류가 발생했습니다.');
    }
  };

  // 브리핑 만들기 = 날씨+시세+핫뉴스 수집 → 경량 AI가 뉴스 소개 멘트 작성 → 스크립트 조립 → TTS.
  const issue = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [weatherRes, kospiRes, tigerRes, newsRes] = await Promise.all([
        iblExecuteApp(`[sense:weather]{city: ${JSON.stringify(city)}}`).catch(() => null),
        iblExecuteApp(`[sense:stock]{op: "quote", ticker: "^KS11"}`).catch(() => null),
        iblExecuteApp(`[sense:stock]{op: "quote", ticker: "102110"}`).catch(() => null),
        iblExecuteApp(`[sense:search_gnews]{headlines: true, curate: 6}`).catch(() => null),
      ]);

      const weather = (weatherRes as WeatherResp | null)?.current;
      const kospi = (kospiRes as { data?: StockData } | null)?.data;
      const tiger = (tigerRes as { data?: StockData } | null)?.data;
      const newsItems = ((newsRes as { items?: NewsItem[] } | null)?.items || []).slice(0, 6);

      const weatherLine = weather
        ? `오늘 ${city} 날씨는 ${weather.condition || '정보 없음'}, 현재 기온은 ${weather.temp}도, 체감 온도는 ${weather.feels_like}도입니다.`
        : `${city} 날씨 정보를 가져오지 못했습니다.`;

      const indexLine = buildIndexLine(kospi, tiger);

      let newsLine = '오늘의 주요 뉴스를 준비하지 못했습니다.';
      if (newsItems.length) {
        const digest = newsItems.map((a, i) => `${i + 1}. ${a.title || ''}${a.summary ? ' — ' + a.summary : ''}`).join('\n');
        try {
          newsLine = await askAI(
            '다음은 오늘의 주요 뉴스 목록이다. 라디오 오디오 브리핑 진행자가 되어 이 소식들을 청취자에게 자연스럽게 소개하는 멘트를 작성해줘. ' +
            '각 기사의 핵심을 한두 문장으로 짚되, 번호나 목록 기호 없이 하나로 이어지는 자연스러운 문단으로 작성해줘. 5~7문장 정도로.',
            digest
          );
        } catch { /* 기본 문구 유지 */ }
      }

      const dateLabel = todayStr();
      const fullScript = [
        `안녕하세요, ${dateLabel} 오디오 브리핑입니다.`,
        weatherLine,
        indexLine,
        '이어서 오늘의 주요 뉴스입니다.',
        newsLine,
        '지금까지 오디오 브리핑이었습니다.',
      ].join('\n\n');

      // 고정 파일명으로 굽는다 — 원격/폰 매니페스트(media_player)가 @hub 로 찾아 재생할 안정 경로.
      // "현재 판" 모델이라 매 발행이 같은 파일을 덮어쓴다(md/json 과 동일).
      const ttsRaw = await iblExecuteApp(`[engines:tts]{text: ${JSON.stringify(fullScript)}, output_filename: "audio_briefing_current.mp3"}`);
      const { path, durationSec: dur } = parseTtsResult(String(ttsRaw ?? ''));
      if (!path) throw new Error('TTS 결과에서 파일 경로를 찾지 못했습니다.');

      const iso = new Date().toISOString();
      setScript(fullScript);
      setArticles(newsItems);
      setAudioPath(path);
      setDurationSec(dur);
      setDate(dateLabel);
      setIssuedAt(iso);

      await saveEdition({ city, script: fullScript, audioPath: path, articles: newsItems, dateLabel, issuedAt: iso, durationSec: dur });
      await saveMarkdown(dateLabel, fullScript, newsItems);
    } catch {
      setError('브리핑 생성 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }, [city]);

  // 열 때: 저장된 최신 판을 보여준다(재생성 없음). 없으면 빈 상태 → "브리핑 만들기"로 첫 판 생성.
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      const ed = await loadEdition();
      if (!alive) return;
      if (ed) {
        setScript(ed.script || '');
        setArticles(ed.articles || []);
        setAudioPath(ed.audioPath || null);
        setDurationSec(ed.durationSec);
        if (ed.dateLabel) setDate(ed.dateLabel);
        setIssuedAt(ed.issuedAt || null);
        if (ed.city) setCity(ed.city);
      }
      setLoading(false);
    })();
    return () => { alive = false; };
  }, []);

  const openExternal = (url?: string) => { if (url) window.electron?.openExternal?.(url); };

  return (
    <div className="h-full w-full flex flex-col bg-[#f0f2f5] text-stone-800">
      {/* 상단 바 */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-stone-200 bg-white/70">
        <div className="text-xs text-stone-400">
          {loading ? '브리핑 준비 중…'
            : issuedAt ? `${whenLabel(issuedAt)} 생성${durationSec ? ` · ${Math.round(durationSec)}초` : ''}`
            : '아직 생성되지 않음'}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setEditing((e) => !e)}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50">
            {editing ? '완료' : '설정'}
          </button>
          <button onClick={saveMp3} disabled={loading || !audioPath}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-200 bg-white text-stone-600 hover:bg-stone-50 disabled:opacity-40">
            💾 mp3 저장
          </button>
          <button onClick={issue} disabled={loading}
            className="text-xs px-2.5 py-1 rounded-lg border border-stone-800 bg-[#1a1a2e] text-white hover:opacity-90 disabled:opacity-40">
            🎙 {loading ? '만드는 중…' : '브리핑 만들기'}
          </button>
        </div>
      </div>

      {/* 설정 패널 */}
      {editing && (
        <div className="shrink-0 px-4 py-3 border-b border-stone-200 bg-white space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-stone-400 shrink-0">날씨 지역</span>
            <input value={city} onChange={(e) => onCity(e.target.value)} placeholder={DEFAULT_CITY}
              className="flex-1 px-3 py-1.5 rounded-lg border border-stone-200 text-sm outline-none focus:border-stone-400" />
          </div>
          <div className="text-[11px] text-stone-400">코스피 지수(^KS11)·TIGER200(102110)은 고정 지표입니다.</div>
        </div>
      )}

      {/* 본문 */}
      <div className="flex-1 min-h-0 overflow-auto px-4 py-6">
        <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm px-8 py-8">
          <h1 className="text-center text-4xl font-black tracking-tight text-[#1a1a2e] border-b-4 border-[#1a1a2e] pb-4"
            style={{ fontFamily: "'Noto Serif KR', serif" }}>
            🎙 오디오 브리핑
          </h1>
          <div className="text-center text-sm text-stone-500 mt-3 mb-2">{date}</div>

          {error && <div className="text-center text-rose-500 text-sm py-4">{error}</div>}

          {!loading && !error && !audioPath && (
            <div className="text-center py-16">
              <div className="text-stone-400 text-sm mb-4">아직 만들어진 브리핑이 없습니다.</div>
              <button onClick={issue}
                className="text-sm px-4 py-2 rounded-lg bg-[#1a1a2e] text-white hover:opacity-90">
                🎙 첫 브리핑 만들기
              </button>
            </div>
          )}

          {loading && !audioPath && <div className="text-center text-stone-400 text-sm py-10">불러오는 중…</div>}

          {audioPath && (
            <div className="mt-6">
              <audio controls src={audioFileUrl(audioPath)} className="w-full" />
            </div>
          )}

          {script && (
            <section className="mt-8">
              <h2 className="text-xl font-bold text-[#1a1a2e] border-b-2 border-stone-200 pb-2 mb-4">스크립트</h2>
              <div className="text-sm text-stone-700 leading-relaxed whitespace-pre-wrap">{script}</div>
            </section>
          )}

          {articles.length > 0 && (
            <section className="mt-8">
              <h2 className="text-xl font-bold text-[#1a1a2e] border-b-2 border-stone-200 pb-2 mb-4">관련 기사</h2>
              <div className="grid gap-3 md:grid-cols-2">
                {articles.map((it, i) => (
                  <article key={i} className="border border-stone-200 rounded-lg p-3 flex flex-col bg-white">
                    <h3 className="text-sm font-semibold leading-snug text-[#22223b] mb-1">{it.title}</h3>
                    {it.meta && <div className="text-xs text-stone-400 mb-1">{it.meta}</div>}
                    {it.url && (
                      <button onClick={() => openExternal(it.url)}
                        className="mt-auto self-start text-xs font-semibold text-[#3d5a80] hover:underline">
                        기사 보기 →
                      </button>
                    )}
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
