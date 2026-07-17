/**
 * 강의 워크스페이스 — 슬라이드 편집 층 (2026-07-18 모듈화 — 1500줄 규칙)
 * LectureWorkspace.tsx 에서 verbatim 이동: SlideSpecEditor(스펙 폼)·SlideCard·
 * AppendSlideButton + 필드 정의 상수. isBakedImageSlide 는 여기가 정의처(본체·SlideCard 공유).
 */
import { useEffect, useState } from 'react';
import type React from 'react';
import { api } from '../../lib/api';
import type {
  SlideMeta,
} from '../../lib/api-lecture-workspace';

export const isBakedImageSlide = (layout: string) => layout === 'native' || layout === 'image';

const STRING_FIELD_DEFS: Array<{ key: string; label: string; multiline?: boolean }> = [
  { key: 'eyebrow',       label: 'eyebrow (부·장·라벨)' },
  { key: 'title',         label: '제목 (title)' },
  { key: 'subtitle',      label: '부제 (subtitle)' },
  { key: 'body',          label: '본문 (body)',           multiline: true },
  { key: 'quote',         label: '인용 (quote)',          multiline: true },
  { key: 'attribution',   label: '출처 (attribution)' },
  { key: 'context',       label: '맥락 (context)',        multiline: true },
  { key: 'label',         label: '라벨 (label)' },
  { key: 'story',         label: '스토리 (story)',        multiline: true },
  { key: 'takeaway',      label: 'takeaway',              multiline: true },
  { key: 'left_title',    label: '좌 제목 (left_title)' },
  { key: 'left_body',     label: '좌 본문 (left_body)',   multiline: true },
  { key: 'right_title',   label: '우 제목 (right_title)' },
  { key: 'right_body',    label: '우 본문 (right_body)',  multiline: true },
  { key: 'conclusion',    label: 'conclusion',             multiline: true },
  { key: 'label_header',  label: 'label_header' },
  { key: 'source',        label: 'source' },
  { key: 'footer',        label: 'footer' },
];

const LIST_FIELDS: Array<{ key: string; label: string; hint: string }> = [
  { key: 'bullets', label: 'bullets (불릿 — 줄바꿈으로 구분)', hint: '한 줄 = 한 항목' },
  { key: 'items',   label: 'items (factbox — 줄바꿈으로 구분)', hint: '한 줄 = 한 항목' },
];

const COMPLEX_FIELDS = ['headers', 'rows', 'columns', 'text_align', 'image_path', 'left_image_path', 'right_image_path', 'image_data', 'left_image_data', 'right_image_data', 'avatar_path'];

interface StyleOverrides {
  font_scale?: number;
  text_align?: '' | 'left' | 'center' | 'right';
  accent_color?: string;
}

export function SlideSpecEditor(props: {
  lectureId: string;
  slide: SlideMeta;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { lectureId, slide, onClose, onSaved } = props;
  const [originalSpec, setOriginalSpec] = useState<Record<string, unknown> | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({}); // 문자열 필드 편집값
  const [listDraft, setListDraft] = useState<Record<string, string>>({}); // 줄바꿈 텍스트
  const [advancedJson, setAdvancedJson] = useState<string>(''); // 복잡 필드 JSON
  const [styleOverrides, setStyleOverrides] = useState<StyleOverrides>({}); // 스타일 조정
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ESC로 닫기
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // spec 로드
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const spec = await api.getSlideSpec(lectureId, slide.id);
        if (cancelled) return;
        setOriginalSpec(spec);

        // 문자열 필드 채우기
        const sd: Record<string, string> = {};
        for (const def of STRING_FIELD_DEFS) {
          const v = spec[def.key];
          if (typeof v === 'string') sd[def.key] = v;
        }
        setDraft(sd);

        // 리스트 필드 채우기 (배열 → 줄바꿈 string)
        const ld: Record<string, string> = {};
        for (const def of LIST_FIELDS) {
          const v = spec[def.key];
          if (Array.isArray(v)) {
            ld[def.key] = v.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join('\n');
          }
        }
        setListDraft(ld);

        // 복잡 필드는 JSON으로 — 알려진 필드만 노출
        const adv: Record<string, unknown> = {};
        for (const key of COMPLEX_FIELDS) {
          if (key in spec) adv[key] = spec[key];
        }
        if (Object.keys(adv).length > 0) {
          setAdvancedJson(JSON.stringify(adv, null, 2));
        }

        // style_overrides 초기값
        const so = spec.style_overrides;
        if (so && typeof so === 'object' && !Array.isArray(so)) {
          setStyleOverrides(so as StyleOverrides);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [lectureId, slide.id]);

  const save = async () => {
    if (!originalSpec) return;
    setSaving(true);
    setError(null);
    try {
      const patch: Record<string, unknown> = {};

      // 문자열 필드 — 변경된 것만 patch에 추가
      for (const def of STRING_FIELD_DEFS) {
        const newVal = draft[def.key];
        const oldVal = originalSpec[def.key];
        const oldStr = typeof oldVal === 'string' ? oldVal : (oldVal === undefined ? '' : '');
        if (typeof oldVal === 'string' || newVal !== undefined) {
          if (newVal !== oldStr) {
            patch[def.key] = newVal ?? '';
          }
        }
      }

      // 리스트 필드 — 줄바꿈 string → 배열
      for (const def of LIST_FIELDS) {
        const newStr = listDraft[def.key];
        const oldArr = Array.isArray(originalSpec[def.key]) ? originalSpec[def.key] as unknown[] : null;
        if (newStr !== undefined || oldArr !== null) {
          const newArr = (newStr || '').split('\n').map((l) => l.trim()).filter(Boolean);
          const oldStr = oldArr ? oldArr.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join('\n') : '';
          if ((newStr || '') !== oldStr) {
            patch[def.key] = newArr;
          }
        }
      }

      // 복잡 필드 (Advanced JSON)
      if (advancedJson.trim()) {
        try {
          const parsed = JSON.parse(advancedJson);
          if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
            // 변경된 키만 patch에 추가
            for (const [k, v] of Object.entries(parsed)) {
              const oldV = originalSpec[k];
              if (JSON.stringify(v) !== JSON.stringify(oldV)) {
                patch[k] = v;
              }
            }
          } else {
            throw new Error('Advanced JSON은 객체여야 합니다.');
          }
        } catch (e) {
          throw new Error(`Advanced JSON 파싱 실패: ${e instanceof Error ? e.message : String(e)}`);
        }
      }

      // style_overrides 변경 감지
      const oldSO = (originalSpec.style_overrides && typeof originalSpec.style_overrides === 'object')
        ? originalSpec.style_overrides as Record<string, unknown>
        : {};
      // 빈 값('', undefined)은 제거 → 명확한 사용자 의도만 보냄
      const cleanedSO: Record<string, unknown> = {};
      if (styleOverrides.font_scale && styleOverrides.font_scale !== 1.0) {
        cleanedSO.font_scale = styleOverrides.font_scale;
      }
      if (styleOverrides.text_align) {
        cleanedSO.text_align = styleOverrides.text_align;
      }
      if (styleOverrides.accent_color) {
        cleanedSO.accent_color = styleOverrides.accent_color;
      }
      if (JSON.stringify(cleanedSO) !== JSON.stringify(oldSO)) {
        patch.style_overrides = Object.keys(cleanedSO).length > 0 ? cleanedSO : null;
        // null 보내면 백엔드가 spec.style_overrides 제거 (기본 디자인으로 복원)
      }

      if (Object.keys(patch).length === 0) {
        setError('변경된 필드가 없습니다.');
        setSaving(false);
        return;
      }

      await api.patchSlideSpec(lectureId, slide.id, patch);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  // 현재 layout에서 의미있는 필드만 필터 (originalSpec에 있는 키만 폼에 표시)
  const visibleStringFields = STRING_FIELD_DEFS.filter(
    (d) => originalSpec && (typeof originalSpec[d.key] === 'string' || draft[d.key] !== undefined)
  );
  const visibleListFields = LIST_FIELDS.filter(
    (d) => originalSpec && (Array.isArray(originalSpec[d.key]) || listDraft[d.key] !== undefined)
  );

  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="px-5 py-3 border-b border-stone-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-stone-800">필드 직접 편집</h2>
            <div className="text-xs text-stone-500 mt-0.5">
              {slide.id} · {slide.layout} · AI 호출 없음 · 변경한 필드만 patch
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-800 text-xl"
            title="닫기 (Esc)"
          >
            ✕
          </button>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {loading && <div className="text-stone-500">spec 로드 중...</div>}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {error}
            </div>
          )}

          {!loading && originalSpec && (
            <>
              {visibleStringFields.length === 0 && visibleListFields.length === 0 && !advancedJson && (
                <div className="text-sm text-stone-500">
                  이 슬라이드의 spec에서 편집 가능한 텍스트 필드가 없습니다. Advanced JSON으로 직접 수정하세요.
                </div>
              )}

              {visibleStringFields.map((def) => (
                <div key={def.key}>
                  <label className="block text-xs text-stone-600 mb-1">{def.label}</label>
                  {def.multiline ? (
                    <textarea
                      value={draft[def.key] ?? ''}
                      onChange={(e) => setDraft({ ...draft, [def.key]: e.target.value })}
                      rows={3}
                      className="w-full px-3 py-2 text-sm border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 resize-y"
                    />
                  ) : (
                    <input
                      value={draft[def.key] ?? ''}
                      onChange={(e) => setDraft({ ...draft, [def.key]: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900"
                    />
                  )}
                </div>
              ))}

              {visibleListFields.map((def) => (
                <div key={def.key}>
                  <label className="block text-xs text-stone-600 mb-1">
                    {def.label} <span className="text-stone-400">— {def.hint}</span>
                  </label>
                  <textarea
                    value={listDraft[def.key] ?? ''}
                    onChange={(e) => setListDraft({ ...listDraft, [def.key]: e.target.value })}
                    rows={4}
                    className="w-full px-3 py-2 text-sm border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 resize-y"
                  />
                </div>
              ))}

              {/* 스타일 조정 — font_scale, text_align, accent_color */}
              <details className="border border-stone-200 rounded" open={Object.keys(styleOverrides).length > 0}>
                <summary className="px-3 py-2 text-xs text-stone-600 cursor-pointer hover:bg-stone-50">
                  🎨 스타일 조정 (글자 크기·정렬·강조색)
                </summary>
                <div className="p-3 border-t border-stone-200 space-y-3">
                  {/* font_scale 슬라이더 */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs text-stone-600">글자 크기 (텍스트만 비례)</label>
                      <span className="text-xs text-stone-500 font-mono">
                        {(styleOverrides.font_scale || 1.0).toFixed(2)}×
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0.7}
                      max={1.4}
                      step={0.05}
                      value={styleOverrides.font_scale || 1.0}
                      onChange={(e) => setStyleOverrides({
                        ...styleOverrides,
                        font_scale: parseFloat(e.target.value),
                      })}
                      className="w-full"
                    />
                    <div className="flex justify-between text-[10px] text-stone-400 mt-0.5">
                      <span>0.7× 작게</span>
                      <span>1.0× 기본</span>
                      <span>1.4× 크게</span>
                    </div>
                    {styleOverrides.font_scale && styleOverrides.font_scale !== 1.0 && (
                      <button
                        type="button"
                        onClick={() => setStyleOverrides({ ...styleOverrides, font_scale: 1.0 })}
                        className="text-[11px] text-stone-400 hover:text-stone-700 mt-1"
                      >
                        ↺ 기본으로
                      </button>
                    )}
                  </div>

                  {/* text_align */}
                  <div>
                    <label className="block text-xs text-stone-600 mb-1">텍스트 정렬 (강제)</label>
                    <div className="flex gap-1">
                      {([
                        { value: '', label: '기본' },
                        { value: 'left', label: '⇤ 왼쪽' },
                        { value: 'center', label: '↔ 중앙' },
                        { value: 'right', label: '⇥ 오른쪽' },
                      ] as const).map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => setStyleOverrides({
                            ...styleOverrides,
                            text_align: opt.value as StyleOverrides['text_align'],
                          })}
                          className={`flex-1 px-2 py-1 text-xs rounded border ${
                            (styleOverrides.text_align || '') === opt.value
                              ? 'bg-stone-800 text-white border-stone-800'
                              : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* accent_color */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs text-stone-600">강조색 (primary 색 override)</label>
                      {styleOverrides.accent_color && (
                        <button
                          type="button"
                          onClick={() => setStyleOverrides({ ...styleOverrides, accent_color: '' })}
                          className="text-[11px] text-stone-400 hover:text-stone-700"
                        >
                          ↺ 기본
                        </button>
                      )}
                    </div>
                    <div className="flex gap-2 items-center">
                      <input
                        type="color"
                        value={styleOverrides.accent_color || '#a55a3e'}
                        onChange={(e) => setStyleOverrides({
                          ...styleOverrides,
                          accent_color: e.target.value,
                        })}
                        className="w-12 h-8 rounded border border-stone-300 cursor-pointer"
                      />
                      <input
                        type="text"
                        value={styleOverrides.accent_color || ''}
                        onChange={(e) => setStyleOverrides({
                          ...styleOverrides,
                          accent_color: e.target.value,
                        })}
                        placeholder="#a55a3e"
                        className="flex-1 px-2 py-1 text-xs font-mono border border-stone-300 rounded text-stone-900"
                      />
                    </div>
                    <div className="text-[10px] text-stone-400 mt-0.5">
                      디자인 시스템의 primary 색을 이 색으로 덮어씁니다. 비우면 원래 색.
                    </div>
                  </div>
                </div>
              </details>

              {advancedJson && (
                <details className="border border-stone-200 rounded">
                  <summary className="px-3 py-2 text-xs text-stone-600 cursor-pointer hover:bg-stone-50">
                    Advanced (복잡 필드 JSON 직접 편집)
                  </summary>
                  <div className="p-3 border-t border-stone-200">
                    <textarea
                      value={advancedJson}
                      onChange={(e) => setAdvancedJson(e.target.value)}
                      rows={10}
                      className="w-full px-3 py-2 text-xs font-mono border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 resize-y"
                    />
                    <div className="text-[11px] text-stone-500 mt-1">
                      headers/rows/columns/image_path 등. 객체 JSON만. 잘못된 JSON이면 저장 실패.
                    </div>
                  </div>
                </details>
              )}
            </>
          )}
        </div>

        {/* 푸터 */}
        <div className="px-5 py-3 border-t border-stone-200 flex items-center justify-end gap-2 bg-stone-50">
          <span className="text-xs text-stone-500 mr-auto">
            변경한 필드만 patch — 나머지는 그대로 보존
          </span>
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-sm border border-stone-300 rounded hover:bg-stone-100 disabled:opacity-50"
          >
            취소
          </button>
          <button
            onClick={save}
            disabled={saving || loading}
            className="px-4 py-2 text-sm bg-stone-800 text-white rounded hover:bg-stone-700 disabled:opacity-50"
          >
            {saving ? '저장 중...' : '저장 + 재렌더'}
          </button>
        </div>
      </div>
    </div>
  );
}


export function AppendSlideButton(props: { active: boolean; onClick: () => void }) {
  const { active, onClick } = props;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        aspect-video rounded-lg border-2 border-dashed transition-colors
        flex flex-col items-center justify-center gap-1
        ${active
          ? 'border-amber-500 bg-amber-50 text-amber-700'
          : 'border-stone-300 text-stone-400 hover:border-stone-500 hover:text-stone-700 hover:bg-stone-50'}
      `}
    >
      <span className="text-2xl">＋</span>
      <span className="text-sm">{active ? '여기 추가 (끝)' : '끝에 추가'}</span>
    </button>
  );
}


export function SlideCard(props: {
  lectureId: string;
  slide: SlideMeta;
  index: number;
  isDragging: boolean;
  isHover: boolean;
  isFocus: boolean;
  onClick: () => void;
  onDoubleClick: () => void;
  onPreview: () => void;
  onSpecEdit: () => void;
  onDuplicate: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onDelete: () => void;
}) {
  const { lectureId, slide, index, isDragging, isHover, isFocus, onClick, onDoubleClick, onPreview, onSpecEdit, onDuplicate, onDragStart, onDragOver, onDrop, onDelete } = props;
  // PNG는 백엔드 HTTP 엔드포인트로 (file://은 Electron 보안 정책에 막힘).
  // updated_at을 쿼리에 붙여서 편집 후 캐시 무효화.
  const pngUrl = `${api.slidePngUrl(lectureId, slide.id)}?v=${encodeURIComponent(slide.updated_at)}`;

  return (
    <div
      draggable
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className={`
        group bg-white rounded-lg border-2 shadow-sm overflow-hidden cursor-pointer transition-all
        ${isDragging ? 'opacity-40' : ''}
        ${isFocus
          ? 'border-amber-500 ring-2 ring-amber-200 shadow-md'
          : isHover ? 'border-stone-700 shadow-md' : 'border-stone-200'}
      `}
    >
      <div className="aspect-video bg-stone-100 relative">
        <img
          src={pngUrl}
          alt={slide.title}
          className="w-full h-full object-contain"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
        <div className="absolute top-2 left-2 px-2 py-0.5 bg-black/60 text-white text-xs rounded">
          #{index + 1}
        </div>
        <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100">
          {!isBakedImageSlide(slide.layout) && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onSpecEdit();
              }}
              className="px-2 py-0.5 bg-black/40 hover:bg-black/70 text-white text-xs rounded"
              title="필드 직접 편집 (AI 없이 단어·줄 수정)"
            >
              ✏️
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onPreview();
            }}
            className="px-2 py-0.5 bg-black/40 hover:bg-black/70 text-white text-xs rounded"
            title="확대 미리보기"
          >
            🔍
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDuplicate();
            }}
            className="px-2 py-0.5 bg-black/40 hover:bg-black/70 text-white text-xs rounded"
            title="복제 (같은 슬라이드 하나 더, 바로 뒤에)"
          >
            ⧉
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="px-2 py-0.5 bg-black/40 hover:bg-red-600 text-white text-xs rounded"
          >
            삭제
          </button>
        </div>
      </div>
      <div className="px-3 py-2">
        <div className="text-sm font-medium text-stone-800 truncate">{slide.title}</div>
        <div className="text-xs text-stone-400 truncate">{slide.layout}</div>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────
// 우패널: AI 채팅 (Step 3에서 실제 연결 — 현재는 UI 셸)
// ─────────────────────────────────────────────────────────
