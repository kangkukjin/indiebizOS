/**
 * PlaceDetail — 가게 한 곳의 상세 패널(카카오맵 앱의 장소 상세와 같은 자리).
 *
 *  · 머리: 이름·분류·주소·전화·거리 + 액션(저장/저장됨 · 출발 · 도착 · 외부 브라우저)
 *  · '정보' 탭: [sense:place]{op:detail} 로 붙인 네이버 설명·블로그 언급·후기 제목, 저장했으면 폴더·메모 편집
 *  · '카카오' 탭: 카카오 장소 페이지(place.map.kakao.com/<id>)를 <webview> 로 그대로 — 사진·영업시간·리뷰·평점은
 *    공개 API 가 안 주므로 원본 페이지를 안에 띄운다(반응형 페이지라 좁은 패널에도 맞는다).
 */
import { useEffect, useState } from 'react';
import type { Place, SavedPlace } from './types';
import { DEFAULT_TAG, fmtDistance } from './types';
import { WebView } from '../forage/support';

interface Props {
  place: Place;
  detail: Place | null;          // op:detail 결과(없으면 place 그대로)
  detailLoading: boolean;
  saved: SavedPlace | null;      // 저장돼 있으면 그 행
  tags: string[];                // 기존 폴더 목록(선택지)
  onBack: () => void;
  onSave: (tag: string) => void;
  onUnsave: () => void;
  onUpdateSaved: (patch: Partial<SavedPlace>) => void;
  onRouteFrom: () => void;
  onRouteTo: () => void;
}

export function PlaceDetail({ place, detail, detailLoading, saved, tags, onBack, onSave, onUnsave, onUpdateSaved, onRouteFrom, onRouteTo }: Props) {
  const p: Place = { ...place, ...(detail || {}), distance: place.distance };   // detail 의 distance 는 재조회 기준점 대비(~0m) — 검색 거리를 유지
  const [tab, setTab] = useState<'info' | 'kakao'>('info');
  const [memo, setMemo] = useState(saved?.memo || '');
  const [tag, setTag] = useState(saved?.tag || DEFAULT_TAG);
  const [newTag, setNewTag] = useState(false);
  useEffect(() => { setMemo(saved?.memo || ''); setTag(saved?.tag || DEFAULT_TAG); setNewTag(false); }, [saved?.id, saved?.memo, saved?.tag]);
  useEffect(() => { setTab('info'); }, [place.id]);

  const url = p.url ? p.url.replace(/^http:/, 'https:') : '';
  const tagChoices = Array.from(new Set([DEFAULT_TAG, ...tags]));

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 머리 */}
      <div className="px-4 pt-3 pb-2 border-b border-stone-100">
        <div className="flex items-start gap-2">
          <button onClick={onBack} className="shrink-0 -ml-1 px-1.5 py-0.5 rounded-lg text-stone-500 hover:bg-stone-100 text-sm">‹</button>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-stone-800 leading-tight">{p.name}</h2>
              {p.cat && <span className="text-xs text-stone-400">{p.cat}</span>}
            </div>
            <div className="mt-1 text-xs text-stone-500 space-y-0.5">
              {p.address && <div>📍 {p.address}{p.jibun_address && p.jibun_address !== p.address ? <span className="text-stone-400"> (지번 {p.jibun_address})</span> : null}</div>}
              {p.phone && <div>☎ <a className="hover:underline" href={`tel:${p.phone}`}>{p.phone}</a></div>}
              {p.distance != null && <div>📏 {fmtDistance(p.distance)}</div>}
            </div>
          </div>
        </div>
        <div className="mt-2.5 flex gap-1.5 flex-wrap">
          {saved ? (
            <button onClick={onUnsave} className="px-2.5 py-1.5 rounded-lg text-xs border bg-amber-50 border-amber-300 text-amber-700 hover:bg-amber-100">⭐ 저장됨 · 해제</button>
          ) : (
            <button onClick={() => onSave(tag)} className="px-2.5 py-1.5 rounded-lg text-xs border bg-white border-stone-200 text-stone-700 hover:border-amber-300 hover:text-amber-700">☆ 저장</button>
          )}
          <button onClick={onRouteFrom} className="px-2.5 py-1.5 rounded-lg text-xs border bg-white border-stone-200 text-stone-700 hover:bg-stone-50">출발</button>
          <button onClick={onRouteTo} className="px-2.5 py-1.5 rounded-lg text-xs border bg-stone-800 border-stone-800 text-white hover:bg-stone-700">도착</button>
          {url && (
            <button onClick={() => window.electron?.openExternal?.(url)} title="기본 브라우저에서 카카오맵 열기"
              className="ml-auto px-2.5 py-1.5 rounded-lg text-xs border bg-white border-stone-200 text-stone-500 hover:bg-stone-50">↗</button>
          )}
        </div>
        <div className="mt-2.5 flex gap-4 text-sm">
          {(['info', 'kakao'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`pb-1.5 border-b-2 ${tab === t ? 'border-stone-800 text-stone-800 font-medium' : 'border-transparent text-stone-400 hover:text-stone-600'}`}>
              {t === 'info' ? '정보' : '카카오 상세'}
            </button>
          ))}
        </div>
      </div>

      {/* 본문 */}
      {tab === 'info' ? (
        <div className="flex-1 min-h-0 overflow-auto px-4 py-3 space-y-3 text-sm">
          {p.category && <div className="text-xs text-stone-400">{p.category}</div>}
          {detailLoading && <div className="text-xs text-stone-400">상세 불러오는 중…</div>}
          {p.description && <p className="text-stone-700 leading-relaxed">{p.description}</p>}
          {(p.blog_count != null || p.reason) && (
            <div className="rounded-xl bg-white border border-stone-200 px-3 py-2.5">
              {p.blog_count != null && <div className="text-xs text-stone-500">💬 네이버 블로그 언급 <b className="text-stone-700">{p.blog_count.toLocaleString()}</b>건</div>}
              {p.reason && <div className="mt-1 text-xs text-stone-600">“{p.reason}”</div>}
            </div>
          )}
          {!detailLoading && !p.description && p.blog_count == null && (
            <div className="text-xs text-stone-400">공개 API 가 주는 정보는 여기까지 — 사진·영업시간·리뷰는 <button className="underline" onClick={() => setTab('kakao')}>카카오 상세</button> 탭에서.</div>
          )}
          {p.naver_url && (
            <button onClick={() => window.electron?.openExternal?.(p.naver_url!)} className="text-xs text-green-700 hover:underline">네이버 플레이스 ↗</button>
          )}

          {saved && (
            <div className="rounded-xl bg-amber-50/60 border border-amber-200 px-3 py-2.5 space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-amber-700 font-medium">폴더</span>
                {newTag ? (
                  <input autoFocus value={tag} onChange={(e) => setTag(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { onUpdateSaved({ tag: tag.trim() || DEFAULT_TAG }); setNewTag(false); } }}
                    onBlur={() => { onUpdateSaved({ tag: tag.trim() || DEFAULT_TAG }); setNewTag(false); }}
                    placeholder="새 폴더 이름" className="flex-1 px-2 py-1 rounded-lg border border-amber-300 bg-white outline-none" />
                ) : (
                  <>
                    <select value={tag} onChange={(e) => { setTag(e.target.value); onUpdateSaved({ tag: e.target.value }); }}
                      className="px-2 py-1 rounded-lg border border-amber-200 bg-white outline-none">
                      {tagChoices.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <button onClick={() => { setNewTag(true); setTag(''); }} className="px-2 py-1 rounded-lg border border-amber-200 bg-white text-amber-700 hover:bg-amber-100">+ 새 폴더</button>
                  </>
                )}
              </div>
              <textarea value={memo} onChange={(e) => setMemo(e.target.value)} onBlur={() => memo !== (saved.memo || '') && onUpdateSaved({ memo })}
                placeholder="메모 — 예: 주차 가능, 점심 웨이팅 김"
                rows={3} className="w-full px-2.5 py-1.5 rounded-lg border border-amber-200 bg-white text-sm outline-none focus:border-amber-400 resize-none" />
              <div className="text-[11px] text-stone-400">저장 {saved.saved_at?.slice(0, 10)} · 메모는 칸을 벗어나면 저장됩니다</div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 min-h-[420px] bg-white">
          {url ? <WebView src={url} style={{ width: '100%', height: '100%', border: 'none' }} />
            : <div className="p-4 text-xs text-stone-400">카카오 장소 링크가 없습니다.</div>}
        </div>
      )}
    </div>
  );
}
