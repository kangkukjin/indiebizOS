/**
 * 강의 워크스페이스 — 재료·덱 패널 층 (2026-07-18 모듈화 — 1500줄 규칙)
 * LectureWorkspace.tsx 에서 verbatim 이동: MaterialsPanel(재료 목록·자동저장 노트)·
 * DeckPanel(슬라이드 목록·삽입 거터·재료 일괄생성). SlideCard/AppendSlideButton 은 editor 에서.
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import type React from 'react';
import { api } from '../../lib/api';
import type {
  Deck,
  MaterialEntry,
  SlideMeta,
} from '../../lib/api-lecture-workspace';
import { AppendSlideButton, SlideCard } from './editor';

export function MaterialsPanel(props: {
  lectureId: string;
  materials: MaterialEntry[];
  materialsDir: string;
  lectureMemo: string;
  focusedSlide: SlideMeta | null;
  onChange: () => void;
  onPatchDeck: (mutate: (deck: Deck) => Deck) => void;
}) {
  const { lectureId, materials, lectureMemo, focusedSlide, onChange, onPatchDeck } = props;
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await api.uploadMaterial(lectureId, file);
      }
      onChange();
    } catch (err) {
      alert('업로드 실패: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (filename: string) => {
    if (!confirm(`자료 삭제: ${filename}?`)) return;
    try {
      await api.removeMaterial(lectureId, filename);
      onChange();
    } catch (err) {
      alert('삭제 실패: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  return (
    <aside className="w-72 flex-shrink-0 flex flex-col bg-white border-r border-stone-200">
      {/* 자료 (일괄생성용) — 보통 1개라 상단에 컴팩트하게 */}
      <div className="px-4 pt-3 pb-2 border-b border-stone-100 shrink-0">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-stone-700">📎 자료</h2>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-2 py-1 text-xs bg-stone-100 hover:bg-stone-200 rounded text-stone-700 disabled:opacity-50"
          >
            {uploading ? '업로드 중…' : '+ 파일'}
          </button>
        </div>
        <p className="text-[11px] text-stone-400 mt-1 leading-snug">슬라이드 일괄생성에만 사용 · 매 슬라이드엔 미포함</p>
        <input ref={fileInputRef} type="file" multiple onChange={handleFileSelect} className="hidden" />
        {materials.length === 0 ? (
          <div className="text-[11px] text-stone-400 py-2 leading-snug">
            아직 자료 없음 — 원고를 올리면 “슬라이드 일괄생성”에 쓰입니다.
          </div>
        ) : (
          <ul className="mt-2 space-y-1 max-h-28 overflow-y-auto">
            {materials.map((m, idx) => (
              <li key={idx} className="group flex items-center gap-2 px-1.5 py-1 hover:bg-stone-50 rounded">
                <span className="text-xs flex-1 truncate text-stone-700" title={m.file}>
                  <MaterialIcon type={m.type} /> {m.file.replace('materials/', '')}
                </span>
                <button
                  onClick={() => handleDelete(m.file.replace('materials/', ''))}
                  className="text-stone-300 hover:text-red-500 opacity-0 group-hover:opacity-100 text-xs"
                  title="삭제"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 메모 — 가장 큰 영역. 강의 전체 노트(항상 표시, AI 미참조). */}
      <div className="flex-1 min-h-0 flex flex-col p-3 border-b border-stone-100">
        <div className="flex items-center justify-between mb-1.5 shrink-0">
          <h3 className="text-xs font-semibold text-stone-600">📝 메모</h3>
          <span className="text-[11px] text-stone-400">나만 보기 · AI 미참조</span>
        </div>
        <AutoSaveNote
          noteKey="lecture-memo"
          value={lectureMemo}
          onSave={async (text) => {
            await api.updateDeckMeta(lectureId, { lecture_memo: text });
            onPatchDeck((d) => ({ ...d, lecture_memo: text }));  // 리로드 없이 로컬 갱신 → 포커스 유지
          }}
          placeholder="강의 전체를 위한 노트를 자유롭게 적어두세요…"
          grow
        />
      </div>

      {/* 강의 노트 — 선택한 슬라이드별 (컴팩트) */}
      <SlideNotePanel
        lectureId={lectureId}
        slide={focusedSlide}
        onPatchDeck={onPatchDeck}
      />
    </aside>
  );
}

// ─────────────────────────────────────────────────────────
// 자동 저장 메모 입력칸 (재사용) — 디바운스 + blur + 언마운트 flush + 버튼.
// blur에만 의존하면 다른 앱/창으로 전환 시 마지막 입력이 유실되던 문제를 막는다.
// ─────────────────────────────────────────────────────────

function AutoSaveNote(props: {
  noteKey: string;                          // 정체성(슬라이드 id 등) — 바뀌면 draft 재동기화
  value: string;                            // 저장된 값
  onSave: (text: string) => Promise<void>;  // 실제 저장
  placeholder: string;
  rows?: number;
  grow?: boolean;                           // true면 부모 높이를 채움(flex-1)
}) {
  const { noteKey, value, onSave, placeholder, rows = 4, grow = false } = props;
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);

  // 항상 최신 값을 ref로 — flush·동기화가 stale 클로저를 안 잡게
  const latest = useRef({ draft, value });
  latest.current = { draft, value };
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const inFlight = useRef(false);

  // draft는 '대상(noteKey)이 바뀔 때만' 저장본으로 재동기화한다.
  // value(저장본) 변화에는 재동기화하지 않음 — 자동저장 직후의 echo가 입력 중 텍스트를
  // 덮어써서 커서/포커스가 튀고 다시 클릭해야 하던 문제를 막는다.
  useEffect(() => { setDraft(latest.current.value); }, [noteKey]);

  const dirty = draft !== value;

  // 조용한 저장(디바운스·blur·언마운트용) — 실패는 상태로만 표시, alert 안 띄움
  const flush = useCallback(() => {
    const { draft, value } = latest.current;
    if (draft === value || inFlight.current) return;
    inFlight.current = true;
    onSaveRef.current(draft)
      .then(() => setError(false))
      .catch(() => setError(true))
      .finally(() => { inFlight.current = false; });
  }, []);

  // 입력 멈추면 ~1분 뒤 자동 저장 (너무 잦은 저장 방지).
  // 즉시 저장이 필요한 순간(포커스 벗어남·슬라이드 전환·창 닫기·저장 버튼)은 별도로 항상 저장하므로
  // 이 간격을 길게 둬도 유실 위험은 없다.
  useEffect(() => {
    if (!dirty) return;
    const t = setTimeout(flush, 60000);
    return () => clearTimeout(t);
  }, [draft, dirty, flush]);

  // 슬라이드 전환·창 닫기(언마운트) 시 미저장분 flush
  useEffect(() => () => flush(), [flush]);

  // 명시적 저장(버튼) — 실패 시 alert
  const saveNow = async () => {
    if (saving || !dirty) return;
    setSaving(true);
    try {
      await onSave(draft);
      setError(false);
    } catch (e) {
      setError(true);
      alert('저장 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={grow ? 'flex flex-col min-h-0 flex-1' : ''}>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={flush}
        placeholder={placeholder}
        rows={grow ? undefined : rows}
        className={`w-full px-2 py-1.5 text-xs border border-stone-300 rounded bg-white text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-stone-500 ${grow ? 'flex-1 min-h-0 resize-none' : 'resize-y'}`}
      />
      <div className="flex items-center justify-between mt-1 shrink-0">
        <span className={`text-[11px] ${error ? 'text-red-500' : 'text-stone-400'}`}>
          {saving ? '저장 중…' : error ? '⚠ 저장 실패 — 다시 시도' : dirty ? '자동 저장 대기…' : '저장됨'}
        </span>
        <button
          onClick={saveNow}
          disabled={saving || !dirty}
          className="px-2 py-0.5 text-[11px] bg-stone-700 text-white rounded hover:bg-stone-600 disabled:opacity-40"
        >
          저장
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// 좌패널 하단: 선택된 슬라이드의 강의 노트 (말할 내용)
// ─────────────────────────────────────────────────────────

function SlideNotePanel(props: {
  lectureId: string;
  slide: SlideMeta | null;
  onPatchDeck: (mutate: (deck: Deck) => Deck) => void;
}) {
  const { lectureId, slide, onPatchDeck } = props;

  return (
    <div className="border-t border-stone-200 p-3 bg-stone-50/70 flex-shrink-0">
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-xs font-semibold text-stone-600">🎤 강의 노트 (슬라이드별)</h3>
        {slide && (
          <span className="text-[11px] text-stone-400 truncate max-w-[140px]" title={slide.title || slide.id}>
            {slide.title || slide.id}
          </span>
        )}
      </div>
      {slide ? (
        <AutoSaveNote
          noteKey={slide.id}
          value={slide.speaker_note ?? ''}
          onSave={async (text) => {
            await api.setSlideNote(lectureId, slide.id, text);
            onPatchDeck((d) => ({
              ...d,
              slides: { ...d.slides, [slide.id]: { ...d.slides[slide.id], speaker_note: text } },
            }));  // 리로드 없이 로컬 갱신 → 포커스 유지, 슬라이드 전환 시에도 최신 노트 표시
          }}
          placeholder="이 슬라이드에서 말할 내용을 적어두세요…"
          rows={4}
        />
      ) : (
        <div className="text-[11px] text-stone-400 py-2 leading-relaxed">
          슬라이드를 <b>클릭</b>하면 여기에 강의할 때 말할 내용을 적어둘 수 있어요.
        </div>
      )}
    </div>
  );
}

function MaterialIcon(props: { type: string }) {
  const iconMap: Record<string, string> = {
    docx: '📄',
    pdf: '📕',
    text: '📝',
    image: '🖼️',
  };
  return <span className="mr-1">{iconMap[props.type] || '📎'}</span>;
}


// ─────────────────────────────────────────────────────────
// 슬라이드 일괄생성 (자료 기반 outline → 순차 생성, 강의 끝에 덧붙임)
// ─────────────────────────────────────────────────────────

function BatchFromMaterials(props: {
  lectureId: string;
  hasMaterials: boolean;
  isNativeDeck: boolean;
  variant?: 'button' | 'cta';
  onChange: () => void;
}) {
  const { lectureId, hasMaterials, isNativeDeck, variant = 'button', onChange } = props;
  const [open, setOpen] = useState(false);
  const [countMode, setCountMode] = useState<'auto' | 'fixed'>('auto');
  const [count, setCount] = useState('10');
  const [imageQuality, setImageQuality] = useState<'pro' | 'fast'>('pro');
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef(false);

  const run = async () => {
    setRunning(true);
    setError(null);
    cancelRef.current = false;
    try {
      setStatus('자료에서 슬라이드 구성 중… (AI 1회 호출)');
      const desired = countMode === 'fixed' ? (parseInt(count) || undefined) : undefined;
      const outline = await api.outlineLecture(lectureId, desired);
      const slides = outline.slides || [];
      if (slides.length === 0) throw new Error('생성할 슬라이드가 없습니다.');

      for (let i = 0; i < slides.length; i++) {
        if (cancelRef.current) {
          setStatus(`중단됨 — ${i}/${slides.length}장까지 생성했습니다.`);
          break;
        }
        setStatus(`슬라이드 생성 중… (${i + 1}/${slides.length})\n${slides[i].instruction.slice(0, 40)}`);
        try {
          // insert_at 없이 끝에 추가 → 순서대로 쌓이고, 각 장은 직전 장 스타일을 자동 참고.
          // 통짜 이미지 덱이면 선택한 이미지 품질(pro/fast)로 생성.
          await api.createSlide(
            lectureId, slides[i].instruction, undefined, undefined,
            isNativeDeck ? imageQuality : undefined,
          );
          onChange();
        } catch (e) {
          console.warn('슬라이드 생성 실패 (건너뜀):', slides[i].instruction, e);
        }
      }
      if (!cancelRef.current) {
        setStatus(`완료 — ${slides.length}장 생성했습니다.`);
        setTimeout(() => { setOpen(false); setStatus(null); }, 1400);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const trigger =
    variant === 'cta' ? (
      <button
        onClick={() => setOpen(true)}
        disabled={!hasMaterials}
        className="px-5 py-2.5 bg-amber-600 text-white rounded-lg hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed"
        title={hasMaterials ? '자료를 바탕으로 여러 장을 한 번에 생성' : '먼저 좌측에서 자료를 추가하세요'}
      >
        📑 슬라이드 일괄생성
      </button>
    ) : (
      <button
        onClick={() => setOpen(true)}
        disabled={!hasMaterials}
        title={hasMaterials ? '자료를 바탕으로 여러 장을 한 번에 생성' : '먼저 좌측에서 자료를 추가하세요'}
        className="px-2.5 py-1 text-xs bg-amber-100 hover:bg-amber-200 text-amber-800 rounded disabled:opacity-40 disabled:cursor-not-allowed"
      >
        📑 슬라이드 일괄생성
      </button>
    );

  return (
    <>
      {trigger}
      {open && (
        <div
          className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-6"
          onClick={() => { if (!running) setOpen(false); }}
        >
          <div
            className="bg-white rounded-lg shadow-2xl max-w-md w-full overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3 border-b border-stone-200">
              <h2 className="text-base font-semibold text-stone-800">슬라이드 일괄생성</h2>
              <div className="text-xs text-stone-500 mt-0.5">
                자료(원고)를 바탕으로 적당한 수의 슬라이드를 만들어 <b>현재 강의 맨 끝에 덧붙입니다.</b>
                자료를 바꿔 올리면 1부·2부처럼 여러 번 나눠 생성할 수 있어요.
              </div>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm text-stone-600 mb-1.5">슬라이드 장수</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setCountMode('auto')}
                    disabled={running}
                    className={`flex-1 px-3 py-2 text-sm rounded border ${
                      countMode === 'auto'
                        ? 'bg-stone-800 text-white border-stone-800'
                        : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                    }`}
                  >
                    AI 자동
                  </button>
                  <button
                    type="button"
                    onClick={() => setCountMode('fixed')}
                    disabled={running}
                    className={`flex-1 px-3 py-2 text-sm rounded border ${
                      countMode === 'fixed'
                        ? 'bg-stone-800 text-white border-stone-800'
                        : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                    }`}
                  >
                    직접 지정
                  </button>
                </div>
                {countMode === 'fixed' && (
                  <input
                    type="number"
                    min={1}
                    max={40}
                    value={count}
                    onChange={(e) => setCount(e.target.value)}
                    disabled={running}
                    className="mt-2 w-28 px-3 py-2 text-sm border border-stone-300 rounded text-stone-900"
                  />
                )}
              </div>

              {isNativeDeck && (
                <div>
                  <label className="block text-sm text-stone-600 mb-1.5">이미지 품질 (전체 장 공통)</label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setImageQuality('pro')}
                      disabled={running}
                      title="Nano Banana Pro · 2K · 약 $0.134/장 — 고품질"
                      className={`flex-1 px-3 py-2 text-sm rounded border ${
                        imageQuality === 'pro'
                          ? 'bg-stone-800 text-white border-stone-800'
                          : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                      }`}
                    >
                      고품질 (Pro)
                    </button>
                    <button
                      type="button"
                      onClick={() => setImageQuality('fast')}
                      disabled={running}
                      title="Nano Banana 2 (Flash) · 1K · 약 $0.067/장 — 저가·빠름"
                      className={`flex-1 px-3 py-2 text-sm rounded border ${
                        imageQuality === 'fast'
                          ? 'bg-amber-600 text-white border-amber-600'
                          : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                      }`}
                    >
                      저가 (Fast)
                    </button>
                  </div>
                </div>
              )}

              <div className="text-[11px] text-stone-400 leading-relaxed">
                디자인 톤은 <b>강의 헤더의 “디자인”</b>(덱 전체 공통)을 따르고, 레이아웃은 장마다 <b>AI 자동</b>입니다.
              </div>

              {status && (
                <div className="text-sm text-stone-600 bg-stone-50 border border-stone-200 rounded px-3 py-2 whitespace-pre-wrap">
                  {running && <span className="inline-block animate-pulse mr-1">⏳</span>}
                  {status}
                </div>
              )}
              {error && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
                  {error}
                </div>
              )}
              <div className="text-[11px] text-stone-400">
                여러 장(특히 일러스트·통짜 이미지 톤)은 시간이 걸립니다. 중단해도 그때까지 만든 슬라이드는 남습니다.
              </div>
            </div>
            <div className="px-5 py-3 border-t border-stone-200 flex justify-end gap-2 bg-stone-50">
              {running ? (
                <button
                  onClick={() => { cancelRef.current = true; }}
                  className="px-4 py-2 text-sm border border-stone-300 rounded hover:bg-stone-100"
                >
                  중단
                </button>
              ) : (
                <>
                  <button
                    onClick={() => setOpen(false)}
                    className="px-4 py-2 text-sm border border-stone-300 rounded hover:bg-stone-100"
                  >
                    닫기
                  </button>
                  <button
                    onClick={run}
                    className="px-4 py-2 text-sm bg-amber-600 text-white rounded hover:bg-amber-500"
                  >
                    생성 시작
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}


// ─────────────────────────────────────────────────────────
// 중앙 패널: 슬라이드 데크 (카드 그리드, 드래그 재배열)
// ─────────────────────────────────────────────────────────

export function DeckPanel(props: {
  lectureId: string;
  deck: Deck;
  focusSlideId: string | null;
  insertBeforeIndex: number | null;
  onFocus: (slideId: string | null) => void;
  onInsertBefore: (idx: number | null) => void;
  onPreview: (slideId: string) => void;
  onSpecEdit: (slideId: string) => void;
  onChange: () => void;
}) {
  const { lectureId, deck, focusSlideId, insertBeforeIndex, onFocus, onInsertBefore, onPreview, onSpecEdit, onChange } = props;
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const imgInputRef = useRef<HTMLInputElement>(null);
  const [uploadingImg, setUploadingImg] = useState(false);

  const slideIds = deck.slide_order;

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploadingImg(true);
    try {
      // 삽입 모드면 그 위치부터, 아니면 데크 끝에
      const at = insertBeforeIndex !== null ? insertBeforeIndex : undefined;
      const r = await api.uploadSlideImages(lectureId, Array.from(files), at);
      if (r.skipped && r.skipped.length) {
        alert(`이미지가 아닌 파일 ${r.skipped.length}개 건너뜀: ${r.skipped.join(', ')}`);
      }
      onChange();
    } catch (err) {
      alert('이미지 업로드 실패: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setUploadingImg(false);
      if (imgInputRef.current) imgInputRef.current.value = '';
    }
  };

  const onDragStart = (idx: number) => {
    setDragIdx(idx);
  };

  const onDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    setHoverIdx(idx);
  };

  const onDrop = async (e: React.DragEvent, targetIdx: number) => {
    e.preventDefault();
    if (dragIdx === null || dragIdx === targetIdx) {
      setDragIdx(null);
      setHoverIdx(null);
      return;
    }
    const newOrder = [...slideIds];
    const [moved] = newOrder.splice(dragIdx, 1);
    newOrder.splice(targetIdx, 0, moved);
    setDragIdx(null);
    setHoverIdx(null);
    try {
      await api.reorderDeck(lectureId, newOrder);
      onChange();
    } catch (err) {
      alert('재배열 실패: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  const handleDelete = async (slideId: string) => {
    if (!confirm(`슬라이드 ${slideId} 삭제?`)) return;
    try {
      await api.deleteSlide(lectureId, slideId);
      onChange();
    } catch (err) {
      alert('삭제 실패: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  const handleDuplicate = async (slideId: string) => {
    try {
      await api.duplicateSlide(lectureId, slideId);
      onChange();
    } catch (err) {
      alert('복제 실패: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  return (
    <main className="flex-1 min-w-0 flex flex-col bg-stone-100">
      <div className="px-6 py-3 bg-white border-b border-stone-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-stone-700">
            🎴 슬라이드 데크 ({slideIds.length}장)
          </h2>
          <BatchFromMaterials
            lectureId={lectureId}
            hasMaterials={deck.materials.length > 0}
            isNativeDeck={(deck.design_system || '').startsWith('native')}
            onChange={onChange}
          />
          <button
            onClick={() => imgInputRef.current?.click()}
            disabled={uploadingImg}
            title="이미 만든 이미지를 슬라이드로 한 번에 추가 (여러 장 선택 가능). 삽입 모드면 그 위치부터."
            className="px-2.5 py-1 text-xs bg-stone-100 hover:bg-stone-200 rounded text-stone-700 disabled:opacity-50"
          >
            {uploadingImg ? '업로드 중...' : '🖼 이미지 업로드'}
          </button>
          <input
            ref={imgInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleImageUpload}
            className="hidden"
          />
        </div>
        <div className="text-xs text-stone-400">
          {focusSlideId
            ? `편집 모드: ${focusSlideId} (다시 클릭하면 해제)`
            : insertBeforeIndex !== null
              ? `삽입 모드: 위치 ${insertBeforeIndex + 1} (해제: 같은 + 다시 클릭)`
              : '드래그=순서 · 클릭=편집 · 더블클릭=확대 · 카드 사이 +=삽입'}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {slideIds.length === 0 ? (
          <div className="text-center text-stone-400 mt-12">
            <div className="text-lg">아직 슬라이드가 없습니다</div>
            {deck.materials.length > 0 ? (
              <>
                <div className="text-sm mt-2 text-stone-500">
                  올린 자료로 슬라이드 여러 장을 한 번에 만들 수 있어요
                </div>
                <div className="mt-4 flex justify-center">
                  <BatchFromMaterials
                    lectureId={lectureId}
                    hasMaterials
                    isNativeDeck={(deck.design_system || '').startsWith('native')}
                    variant="cta"
                    onChange={onChange}
                  />
                </div>
                <div className="text-xs mt-3">
                  또는 우측 AI 채팅에서 한 장씩 만들거나, 위 <span className="font-medium text-stone-500">🖼 이미지 업로드</span> 사용
                </div>
              </>
            ) : (
              <>
                <div className="text-sm mt-2">
                  우측 AI 채팅에서 "첫 슬라이드 만들어줘"라고 시작하거나,
                </div>
                <div className="text-sm mt-1">
                  좌측에서 <span className="font-medium text-stone-500">자료를 추가</span>하면 <span className="font-medium text-stone-500">슬라이드 일괄생성</span>으로 여러 장을 한 번에 만들 수 있어요.
                </div>
                <div className="text-sm mt-1">
                  위 <span className="font-medium text-stone-500">🖼 이미지 업로드</span>로 이미 만든 이미지를 올릴 수도 있습니다.
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2">
            {slideIds.map((sid, idx) => {
              const slide = deck.slides[sid];
              if (!slide) return null;
              const toggleInsert = () =>
                onInsertBefore(insertBeforeIndex === idx ? null : idx);
              return (
                <div key={sid} className="relative pt-9">
                  <InsertGutter
                    active={insertBeforeIndex === idx}
                    label={`위치 ${idx + 1} 앞`}
                    onClick={toggleInsert}
                  />
                  <SlideCard
                    lectureId={lectureId}
                    slide={slide}
                    index={idx}
                    isDragging={dragIdx === idx}
                    isHover={hoverIdx === idx}
                    isFocus={focusSlideId === sid}
                    onClick={() => onFocus(focusSlideId === sid ? null : sid)}
                    onDoubleClick={() => onPreview(sid)}
                    onPreview={() => onPreview(sid)}
                    onSpecEdit={() => onSpecEdit(sid)}
                    onDuplicate={() => handleDuplicate(sid)}
                    onDragStart={() => onDragStart(idx)}
                    onDragOver={(e) => onDragOver(e, idx)}
                    onDrop={(e) => onDrop(e, idx)}
                    onDelete={() => handleDelete(sid)}
                  />
                </div>
              );
            })}
            {/* 끝에 추가 — 그리드 마지막 셀에 (pt-9로 위쪽 분리 일관) */}
            <div className="pt-9">
              <AppendSlideButton
                active={insertBeforeIndex === slideIds.length}
                onClick={() =>
                  onInsertBefore(insertBeforeIndex === slideIds.length ? null : slideIds.length)
                }
              />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// ─────────────────────────────────────────────────────────
// 삽입선 (카드 사이 호버 영역) + 끝에 추가 버튼
// ─────────────────────────────────────────────────────────

function InsertGutter(props: { active: boolean; label: string; onClick: () => void }) {
  const { active, label, onClick } = props;
  // 카드 wrapper의 pt-9 영역 안에 자리.
  // 평소엔 완전히 숨겨두고(opacity-0), 갭 영역에 마우스가 들어왔을 때만 표시.
  // 발견성을 위해 호버 영역(투명 button)을 padding 영역 거의 전체로 키움.
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title={active ? '삽입 위치 — 해제하려면 다시 클릭' : `${label}에 슬라이드 삽입`}
      className={`
        absolute -top-1 left-0 right-0 h-9 z-20 cursor-pointer
        flex items-center justify-center group/gutter
        ${active ? 'opacity-100' : 'opacity-0 hover:opacity-100'}
        transition-opacity
      `}
    >
      <div
        className={`flex-1 h-0.5 transition-colors ${
          active
            ? 'bg-amber-500'
            : 'bg-stone-300 border-dashed group-hover/gutter:bg-stone-500'
        }`}
      />
      <span
        className={`mx-2 px-2 py-0.5 text-[11px] rounded-full whitespace-nowrap transition-colors ${
          active
            ? 'bg-amber-500 text-white shadow'
            : 'bg-white border border-stone-300 text-stone-600 group-hover/gutter:bg-stone-700 group-hover/gutter:text-white group-hover/gutter:border-stone-700'
        }`}
      >
        {active ? `▼ ${label}에 삽입` : `+ ${label}`}
      </span>
      <div
        className={`flex-1 h-0.5 transition-colors ${
          active
            ? 'bg-amber-500'
            : 'bg-stone-300 group-hover/gutter:bg-stone-500'
        }`}
      />
    </button>
  );
}

// ─────────────────────────────────────────────────────────
// 슬라이드 필드 직접 편집 모달 — PowerPoint식 정밀 수정
// ─────────────────────────────────────────────────────────

/**
 * 단순 문자열·문장 필드. 각 layout마다 등장하는 필드들.
 * 표시 순서·라벨도 정의.
 */
