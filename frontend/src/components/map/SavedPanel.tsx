/**
 * SavedPanel — 저장한 장소(카카오맵 '즐겨찾기') 목록. 폴더(tag) 칩으로 거르고, 항목을 누르면 지도가 그곳으로.
 * 원장은 outputs/map/places.json([self:read]/[self:write]) — 부모(MapInstrument)가 소유·기록한다.
 */
import type { SavedPlace } from './types';
import { DEFAULT_TAG } from './types';

interface Props {
  saved: SavedPlace[];
  tagFilter: string | null;
  onTagFilter: (t: string | null) => void;
  onSelect: (p: SavedPlace) => void;
  onDelete: (id: string) => void;
  onBack: () => void;
  saving: boolean;
}

export function SavedPanel({ saved, tagFilter, onTagFilter, onSelect, onDelete, onBack, saving }: Props) {
  const tags = Array.from(new Set(saved.map((p) => p.tag || DEFAULT_TAG)));
  const list = (tagFilter ? saved.filter((p) => (p.tag || DEFAULT_TAG) === tagFilter) : saved)
    .slice().sort((a, b) => (b.saved_at || '').localeCompare(a.saved_at || ''));

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-4 pt-3 pb-2 border-b border-stone-100">
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="-ml-1 px-1.5 py-0.5 rounded-lg text-stone-500 hover:bg-stone-100 text-sm">‹</button>
          <h2 className="text-sm font-semibold text-stone-800">⭐ 저장한 장소 <span className="text-stone-400 font-normal">{saved.length}</span></h2>
          {saving && <span className="ml-auto text-[11px] text-stone-400">기록 중…</span>}
        </div>
        {tags.length > 0 && (
          <div className="mt-2 flex gap-1.5 flex-wrap">
            <button onClick={() => onTagFilter(null)}
              className={`px-2.5 py-1 rounded-full text-xs border ${!tagFilter ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-600'}`}>전체</button>
            {tags.map((t) => (
              <button key={t} onClick={() => onTagFilter(tagFilter === t ? null : t)}
                className={`px-2.5 py-1 rounded-full text-xs border ${tagFilter === t ? 'bg-amber-500 text-white border-amber-500' : 'bg-white border-stone-200 text-stone-600'}`}>
                {t} <span className="opacity-60">{saved.filter((p) => (p.tag || DEFAULT_TAG) === t).length}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {list.length === 0 ? (
          <div className="px-4 py-8 text-center text-xs text-stone-400">
            아직 저장한 장소가 없습니다.<br />검색 결과나 지도에서 가게를 고르고 <b>☆ 저장</b>을 누르세요.
          </div>
        ) : list.map((p) => (
          <div key={p.id} className="group px-4 py-2.5 border-b border-stone-100 hover:bg-white cursor-pointer" onClick={() => onSelect(p)}>
            <div className="flex items-start gap-2">
              <span className="mt-0.5 text-sm">⭐</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-medium text-stone-800 truncate">{p.name}</span>
                  {p.cat && <span className="text-[11px] text-stone-400 shrink-0">{p.cat}</span>}
                  {p.tag && p.tag !== DEFAULT_TAG && <span className="text-[10px] px-1.5 rounded bg-amber-100 text-amber-700 shrink-0">{p.tag}</span>}
                </div>
                {p.address && <div className="text-xs text-stone-500 truncate">{p.address}</div>}
                {p.memo && <div className="mt-0.5 text-xs text-stone-600 line-clamp-2">📝 {p.memo}</div>}
              </div>
              <button onClick={(e) => { e.stopPropagation(); onDelete(p.id); }} title="저장 해제"
                className="shrink-0 opacity-0 group-hover:opacity-100 px-1.5 py-0.5 rounded text-xs text-stone-400 hover:text-rose-600 hover:bg-rose-50">✕</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
