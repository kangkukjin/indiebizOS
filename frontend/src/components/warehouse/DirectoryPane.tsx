/**
 * DirectoryPane — 이웃찾기 탭의 '둘러보기' 면. 아직 아무 관계도 없는 창고를 장르로 훑는다.
 *
 * 소개글 면(#IndieNet)이 "나를 알린 사람"을 보는 수신면이라면 여기는 그 반대쪽 —
 * 나를 모르는 세상의 창고들. 방언 어댑터가 생긴 뒤로 세상엔 이미 창고가 아주 많은데
 * (색인·RSS·Neocities·페이지) 그걸 볼 방법이 없었다.
 *
 * 후보는 백엔드 warehouse_directory 가 만든다(live=Neocities 태그 브라우즈 / seed=사람이 적은 목록).
 * 등록은 소개글 면과 똑같이 /warehouse-feed/neighbors/add — 신규 배관 0.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Plus, ExternalLink, Eye, Compass } from 'lucide-react';
import { API, openExternalUrl } from './shared';

interface Genre { key: string; label: string; icon: string; hint: string; live: boolean; seed_count: number }
interface Cand {
  name: string; url: string; title: string; desc: string; thumb: string;
  views: number | null; source: string; registered?: boolean;
  /** 백엔드가 이미 아는 정체 — 등록 때 그대로 넘겨 커스텀 도메인 Neocities 를 살린다 */
  adapter?: string;
}

export function DirectoryPane() {
  const [genres, setGenres] = useState<Genre[]>([]);
  const [key, setKey] = useState<string>('');
  const [items, setItems] = useState<Cand[]>([]);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/warehouse-feed/directory`);
        const d = await r.json();
        const gs: Genre[] = d.genres || [];
        setGenres(gs);
        if (gs.length && !key) setKey(gs[0].key);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    // 최초 1회 — 카탈로그는 사용자가 파일을 고칠 때만 바뀐다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async (k: string, refresh = false) => {
    if (!k) return;
    setBusy(true); setError(null); setNote('');
    try {
      const r = await fetch(`${API}/warehouse-feed/directory/${k}?limit=60${refresh ? '&refresh=1' : ''}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setItems(d.items || []);
      setNote(d.note || '');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setItems([]);
    }
    setBusy(false);
  }, []);

  useEffect(() => { void load(key); }, [key, load]);

  // 등록 = 소개글 면과 같은 엔드포인트. adapter 힌트만 더 실어 보낸다.
  const add = async (c: Cand) => {
    if (adding[c.url]) return;
    setAdding((a) => ({ ...a, [c.url]: true }));
    try {
      const r = await fetch(`${API}/warehouse-feed/neighbors/add`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: c.url, name: c.title || c.name, adapter: c.adapter || '' }),
      });
      const d = await r.json().catch(() => null);
      if (!r.ok) throw new Error(d?.detail || `HTTP ${r.status}`);
      const n = d?.poll?.file_count;
      setItems((xs) => xs.map((x) => (x.url === c.url ? { ...x, registered: true } : x)));
      if (d?.poll?.ok === false || d?.poll?.error) {
        window.alert(`등록은 했지만 아직 못 읽었어요: ${d?.poll?.error || '연결 실패'}\n` +
          '창고 주소가 파일 목록(색인)이 아닐 수 있어요 — 하위 폴더 주소로 다시 등록해 보세요.');
      } else {
        window.alert(`창고이웃으로 등록했어요${n != null ? ` — 파일 ${n}개를 읽었습니다` : ''}.\n` +
          '이웃 탭 피드에 이 창고의 변화가 흐릅니다.');
      }
    } catch (e) {
      window.alert(`등록 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
    setAdding((a) => ({ ...a, [c.url]: false }));
  };

  const host = (u: string) => { try { return new URL(u).host; } catch { return u; } };
  const cur = genres.find((g) => g.key === key);

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <div className="max-w-5xl mx-auto space-y-3">
        <p className="text-xs text-stone-500">
          아직 나를 모르는 창고들 — 장르로 훑어보고 마음에 들면 <strong>창고이웃으로 등록</strong>하세요.
          등록하면 그 창고의 변화가 이웃 탭 피드로 흘러옵니다. (상대는 아무것도 설치할 필요가 없어요)
        </p>

        {/* 장르 칩 */}
        <div className="flex flex-wrap gap-1.5">
          {genres.map((g) => (
            <button
              key={g.key}
              title={g.hint}
              onClick={() => setKey(g.key)}
              className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                key === g.key
                  ? 'bg-[#D97706] text-white border-[#D97706]'
                  : 'bg-white text-stone-600 border-stone-200 hover:border-[#D97706]/40'
              }`}
            >
              <span className="mr-1">{g.icon}</span>{g.label}
            </button>
          ))}
        </div>

        {cur && (
          <div className="flex items-center gap-2">
            <p className="text-xs text-stone-400 flex-1">{cur.hint}</p>
            <button
              className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-100 shrink-0"
              title="목록 새로 받기 (평소엔 6시간 캐시)"
              onClick={() => void load(key, true)}
            >
              <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
            </button>
          </div>
        )}

        {note && (
          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">{note}</div>
        )}
        {error && (
          <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>
        )}
        {busy && !items.length && <div className="text-sm text-stone-400 py-10 text-center">후보 창고를 모으는 중…</div>}
        {!busy && !items.length && !error && (
          <div className="text-center text-stone-400 py-10">
            <Compass className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p className="text-sm">이 장르엔 아직 후보가 없어요</p>
          </div>
        )}

        {/* 후보 카드 — 썸네일이 있으면 눈으로 고른다(Neocities 브라우즈가 스크린샷을 준다) */}
        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((c) => (
            <li key={c.url} className="rounded-xl bg-white border border-stone-200 overflow-hidden flex flex-col hover:border-[#D97706]/40">
              {c.thumb ? (
                <button className="block w-full aspect-[4/3] bg-stone-100 overflow-hidden"
                        title="브라우저로 열어보기" onClick={() => openExternalUrl(c.url)}>
                  <img src={c.thumb} alt="" loading="lazy"
                       className="w-full h-full object-cover object-top" />
                </button>
              ) : (
                <button className="w-full aspect-[4/3] bg-gradient-to-br from-stone-100 to-stone-50 flex items-center justify-center text-3xl"
                        title="브라우저로 열어보기" onClick={() => openExternalUrl(c.url)}>
                  📦
                </button>
              )}
              <div className="p-3 flex-1 flex flex-col gap-1">
                <div className="text-sm font-medium text-stone-800 truncate" title={c.title || c.name}>
                  {c.title || c.name}
                </div>
                <div className="text-[11px] text-stone-400 truncate" title={c.url}>{host(c.url)}</div>
                {c.desc && <div className="text-[11px] text-stone-500 line-clamp-2">{c.desc}</div>}
                <div className="flex items-center gap-2 mt-auto pt-2">
                  {c.views != null && (
                    <span className="flex items-center gap-1 text-[11px] text-stone-400" title="Neocities 누적 조회수">
                      <Eye className="w-3 h-3" />{c.views.toLocaleString()}
                    </span>
                  )}
                  <div className="flex-1" />
                  <button
                    className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50"
                    title="브라우저로 열기" onClick={() => openExternalUrl(c.url)}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                  <button
                    className="flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg bg-[#D97706] text-white hover:bg-[#B45309] disabled:opacity-40"
                    title="창고이웃으로 등록 — 이 창고의 변화가 이웃 탭 피드로 흘러옵니다"
                    disabled={!!c.registered || !!adding[c.url]}
                    onClick={() => void add(c)}
                  >
                    <Plus className="w-3.5 h-3.5" />
                    {c.registered ? '등록됨' : adding[c.url] ? '읽는 중…' : '이웃 등록'}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
