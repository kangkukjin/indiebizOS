/**
 * LectureWorkspace - 강의 만들기 워크스페이스 (3패널 UI)
 *
 * 좌: 재료 패널 (업로드 + 목록)
 * 중: 슬라이드 데크 (카드 그리드, 드래그 재배열, 클릭 focus)
 * 우: AI 채팅 (Step 3에서 실제 연결 — 현재는 UI 셸 + mock)
 *
 * 강의 선택 전: 강의 목록 + 새 강의 만들기 폼
 * 강의 선택 후: 3패널 + 상단 강의 메타 표시
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '../lib/api';
import type {
  LectureSummary,
  Deck,
  LectureLoadResponse,
  SlideMeta,
} from '../lib/api-lecture-workspace';
import { DESIGN_SYSTEM_OPTIONS } from '../lib/api-lecture-workspace';
// 서브컴포넌트 층 분리 (2026-07-18 모듈화 — 1500줄 규칙): lecture/ 참조.
import { SlideSpecEditor, isBakedImageSlide } from './lecture/editor';
import { MaterialsPanel, DeckPanel } from './lecture/panels';
import { AIChatPanel, formatDate } from './lecture/chat';

interface LectureWorkspaceProps {
  initialLectureId: string | null;
}

// 통짜 이미지(native) / 업로드 이미지(image) 슬라이드는 글자가 PNG에 구워져 있어
// 필드 직접 편집(spec patch → HTML 재렌더)이 불가능하다. 이런 슬라이드는 AI 채팅으로
// '재생성'해서 바꿔야 한다 → 필드 편집(✏️) 버튼을 숨긴다.

export function LectureWorkspace({ initialLectureId }: LectureWorkspaceProps) {
  const [lectures, setLectures] = useState<LectureSummary[]>([]);
  const [currentLectureId, setCurrentLectureId] = useState<string | null>(initialLectureId);
  const [loaded, setLoaded] = useState<LectureLoadResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // 강의 목록 새로고침
  const refreshLectures = useCallback(async () => {
    try {
      const data = await api.listLectures();
      setLectures(data.lectures);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // 강의 데이터 로드
  const loadLecture = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.loadLecture(id);
      setLoaded(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoaded(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // deck를 로컬 state에서만 갱신 (전체 리로드 없이) — 노트/메모 자동저장이 로딩 화면을
  // 띄워 textarea를 언마운트시키던(포커스 유실) 문제를 막는다.
  const patchDeckLocal = useCallback((mutate: (deck: Deck) => Deck) => {
    setLoaded((prev) => (prev ? { ...prev, deck: mutate(prev.deck) } : prev));
  }, []);

  // 초기 로드
  useEffect(() => {
    refreshLectures();
  }, [refreshLectures]);

  // 강의 선택 시 데이터 로드
  useEffect(() => {
    if (currentLectureId) {
      loadLecture(currentLectureId);
    } else {
      setLoaded(null);
    }
  }, [currentLectureId, loadLecture]);

  // Electron IPC: 다른 강의 선택 신호 받기 (메인 프로세스가 같은 창에 다른 lecture_id를 보낼 때)
  useEffect(() => {
    if (window.electron?.onLectureWorkspaceSelect) {
      window.electron.onLectureWorkspaceSelect((lectureId: string) => {
        setCurrentLectureId(lectureId);
      });
    }
    return () => {
      window.electron?.removeLectureWorkspaceSelectListener?.();
    };
  }, []);

  const handleSelectLecture = (id: string) => {
    setCurrentLectureId(id);
    // URL 해시 갱신 (창 새로고침 시 유지)
    window.location.hash = `/lecture-workspace?lecture_id=${encodeURIComponent(id)}`;
  };

  const handleBackToList = () => {
    setCurrentLectureId(null);
    window.location.hash = '/lecture-workspace';
    refreshLectures();
  };

  // ───────────────────────────────────────────────────────
  // 항상 보이는 상단 drag bar — macOS traffic lights와 같은 줄에 위치.
  // 이 영역을 잡고 창을 옮길 수 있음. sub-view 무관하게 일관 동작.
  // ───────────────────────────────────────────────────────
  const titleBar = (
    <div
      className="h-9 flex-shrink-0 bg-white/80 border-b border-stone-100 backdrop-blur-sm"
      style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
    />
  );

  // ───────────────────────────────────────────────────────
  // 강의 선택 전: 목록 화면
  // ───────────────────────────────────────────────────────
  if (!currentLectureId) {
    return (
      <div className="h-screen flex flex-col bg-[#F5F1EB]">
        {titleBar}
        <div className="flex-1 min-h-0 overflow-hidden">
          <LectureSelectScreen
            lectures={lectures}
            showCreateForm={showCreateForm}
            setShowCreateForm={setShowCreateForm}
            onSelect={handleSelectLecture}
            onCreated={(id) => {
              setShowCreateForm(false);
              refreshLectures();
              handleSelectLecture(id);
            }}
            onRefresh={refreshLectures}
            error={error}
          />
        </div>
      </div>
    );
  }

  // ───────────────────────────────────────────────────────
  // 강의 선택 후: 3패널 워크스페이스
  // ───────────────────────────────────────────────────────
  if (loading || !loaded) {
    return (
      <div className="h-screen flex flex-col bg-stone-50">
        {titleBar}
        <div className="flex-1 flex items-center justify-center text-stone-600">
          {error ? (
            <div className="text-red-600">{error}</div>
          ) : (
            <div>강의 로드 중...</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-stone-50">
      {titleBar}
      <LectureHeader
        deck={loaded.deck}
        onBack={handleBackToList}
        onChange={() => loadLecture(loaded.deck.lecture_id)}
      />
      <WorkspaceBody
        loaded={loaded}
        onChange={() => loadLecture(loaded.deck.lecture_id)}
        onPatchDeck={patchDeckLocal}
      />
    </div>
  );
}


// ─────────────────────────────────────────────────────────
// 내보내기 메뉴 (PDF/PPTX 드롭다운)
// ─────────────────────────────────────────────────────────

type ExportFormat = 'pdf' | 'pptx_image' | 'pptx_editable';

function ExportMenu(props: { lectureId: string; slideCount: number }) {
  const { lectureId, slideCount } = props;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async (format: ExportFormat) => {
    if (slideCount === 0) {
      setError('내보낼 슬라이드가 없습니다.');
      return;
    }
    setBusy(format);
    setError(null);
    setOpen(false);
    try {
      const result = await api.exportDeck(lectureId, format);
      const url = api.exportFileUrl(lectureId, result.filename);
      const a = document.createElement('a');
      a.href = url;
      a.download = result.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const busyLabel: Record<ExportFormat, string> = {
    pdf: 'PDF',
    pptx_image: 'PPTX(이미지)',
    pptx_editable: 'PPTX(편집)',
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        disabled={busy !== null}
        className="px-3 py-1.5 text-sm bg-stone-700 text-white rounded hover:bg-stone-600 disabled:opacity-60"
      >
        {busy ? `${busyLabel[busy]} 생성 중...` : '내보내기 ▾'}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 bg-white border border-stone-200 rounded shadow-lg z-10 min-w-[240px]">
          <button
            onClick={() => handleExport('pdf')}
            className="block w-full text-left px-4 py-2 text-sm hover:bg-stone-50 text-stone-800"
            title="다중 페이지 PDF"
          >
            📕 <span className="font-medium">PDF</span>
            <div className="text-[11px] text-stone-500 ml-6">다중 페이지 PDF · 디자인 보존</div>
          </button>
          <div className="border-t border-stone-100" />
          <button
            onClick={() => handleExport('pptx_image')}
            className="block w-full text-left px-4 py-2 text-sm hover:bg-stone-50 text-stone-800"
            title="슬라이드 전체를 이미지로 박아넣음. 디자인 완벽 보존, 편집 불가."
          >
            🖼️ <span className="font-medium">PPTX (이미지)</span>
            <div className="text-[11px] text-stone-500 ml-6">디자인 완벽 보존 · PPT에서 편집 불가</div>
          </button>
          <button
            onClick={() => handleExport('pptx_editable')}
            className="block w-full text-left px-4 py-2 text-sm hover:bg-stone-50 text-stone-800"
            title="텍스트박스로 분해. PPT에서 자유 위치/크기/텍스트 편집 가능. 디자인 일부 손실."
          >
            ✏️ <span className="font-medium">PPTX (편집 가능)</span>
            <div className="text-[11px] text-stone-500 ml-6">텍스트박스 분해 · PPT에서 자유 편집 · 디자인 단순화</div>
          </button>
        </div>
      )}
      {error && (
        <div className="absolute right-0 mt-1 bg-red-50 border border-red-200 rounded px-3 py-1.5 text-xs text-red-700 whitespace-nowrap z-10">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400">✕</button>
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────
// 슬라이드 미리보기 모달
// ─────────────────────────────────────────────────────────

function SlidePreviewModal(props: {
  lectureId: string;
  slide: SlideMeta;
  index: number;
  total: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  canPrev: boolean;
  canNext: boolean;
  onEdit?: () => void;
}) {
  const { lectureId, slide, index, total, onClose, onPrev, onNext, canPrev, canNext, onEdit } = props;
  const pngUrl = `${api.slidePngUrl(lectureId, slide.id)}?v=${encodeURIComponent(slide.updated_at)}`;

  // ESC / 좌우 키보드 단축키
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowLeft' && canPrev) onPrev();
      else if (e.key === 'ArrowRight' && canNext) onNext();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, onPrev, onNext, canPrev, canNext]);

  return (
    <div
      className="fixed inset-0 bg-black/80 z-50 flex flex-col items-center justify-center p-8"
      onClick={onClose}
    >
      {/* 상단 메타 */}
      <div className="text-white mb-3 text-sm flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
        <span className="font-medium">{slide.title || slide.id}</span>
        <span className="text-stone-300">·</span>
        <span className="text-stone-400">{slide.layout}</span>
        <span className="text-stone-300">·</span>
        <span className="text-stone-400">{index + 1} / {total}</span>
      </div>

      {/* 이미지 */}
      <img
        src={pngUrl}
        alt={slide.title}
        onClick={(e) => e.stopPropagation()}
        className="max-w-[90vw] max-h-[80vh] object-contain bg-white shadow-2xl"
      />

      {/* 네비게이션 */}
      <div className="mt-4 flex gap-2" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onPrev}
          disabled={!canPrev}
          className="px-4 py-2 bg-white/10 text-white rounded hover:bg-white/20 disabled:opacity-30"
        >
          ← 이전
        </button>
        {onEdit && (
          <button
            onClick={onEdit}
            className="px-4 py-2 bg-amber-500/80 text-white rounded hover:bg-amber-500"
            title="필드 직접 편집"
          >
            ✏️ 편집
          </button>
        )}
        <button
          onClick={onClose}
          className="px-4 py-2 bg-white/10 text-white rounded hover:bg-white/20"
        >
          닫기 (Esc)
        </button>
        <button
          onClick={onNext}
          disabled={!canNext}
          className="px-4 py-2 bg-white/10 text-white rounded hover:bg-white/20 disabled:opacity-30"
        >
          다음 →
        </button>
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────
// 워크스페이스 본문 — focus 상태는 여기서 공유
// ─────────────────────────────────────────────────────────

function WorkspaceBody(props: {
  loaded: LectureLoadResponse;
  onChange: () => void;
  onPatchDeck: (mutate: (deck: Deck) => Deck) => void;
}) {
  const { loaded, onChange, onPatchDeck } = props;
  const [focusSlideId, setFocusSlideId] = useState<string | null>(null);
  const [insertBeforeIndex, setInsertBeforeIndex] = useState<number | null>(null);
  const [previewSlideId, setPreviewSlideId] = useState<string | null>(null);

  // 데크가 바뀌면 사라진 slide_id를 focus/preview에서 해제
  useEffect(() => {
    if (focusSlideId && !loaded.deck.slides[focusSlideId]) {
      setFocusSlideId(null);
    }
    if (previewSlideId && !loaded.deck.slides[previewSlideId]) {
      setPreviewSlideId(null);
    }
    // 데크 길이 줄어들면 insertBeforeIndex도 정리
    if (insertBeforeIndex !== null && insertBeforeIndex > loaded.deck.slide_order.length) {
      setInsertBeforeIndex(null);
    }
  }, [focusSlideId, previewSlideId, insertBeforeIndex, loaded.deck.slides, loaded.deck.slide_order]);

  // focus와 insert는 mutually exclusive
  const handleSetFocus = (sid: string | null) => {
    setFocusSlideId(sid);
    if (sid) setInsertBeforeIndex(null);
  };
  const handleSetInsertBefore = (idx: number | null) => {
    setInsertBeforeIndex(idx);
    if (idx !== null) setFocusSlideId(null);
  };
  const clearModes = () => {
    setFocusSlideId(null);
    setInsertBeforeIndex(null);
  };

  // 직접 편집 모달 — focus/insert/preview와 별도 state
  const [specEditSlideId, setSpecEditSlideId] = useState<string | null>(null);
  useEffect(() => {
    if (specEditSlideId && !loaded.deck.slides[specEditSlideId]) {
      setSpecEditSlideId(null);
    }
  }, [specEditSlideId, loaded.deck.slides]);

  // 미리보기 모달의 이전/다음 네비게이션
  const order = loaded.deck.slide_order;
  const previewIndex = previewSlideId ? order.indexOf(previewSlideId) : -1;
  const handlePreviewNav = (direction: 1 | -1) => {
    if (previewIndex < 0) return;
    const next = previewIndex + direction;
    if (next >= 0 && next < order.length) {
      setPreviewSlideId(order[next]);
    }
  };

  return (
    <>
      <div className="flex-1 min-h-0 flex">
        <MaterialsPanel
          lectureId={loaded.deck.lecture_id}
          materials={loaded.deck.materials}
          materialsDir={loaded.materials_dir}
          lectureMemo={loaded.deck.lecture_memo ?? ''}
          focusedSlide={focusSlideId ? loaded.deck.slides[focusSlideId] ?? null : null}
          onChange={onChange}
          onPatchDeck={onPatchDeck}
        />
        <DeckPanel
          lectureId={loaded.deck.lecture_id}
          deck={loaded.deck}
          focusSlideId={focusSlideId}
          insertBeforeIndex={insertBeforeIndex}
          onFocus={handleSetFocus}
          onInsertBefore={handleSetInsertBefore}
          onPreview={setPreviewSlideId}
          onSpecEdit={setSpecEditSlideId}
          onChange={onChange}
        />
        <AIChatPanel
          deck={loaded.deck}
          focusSlideId={focusSlideId}
          insertBeforeIndex={insertBeforeIndex}
          clearModes={clearModes}
          onChange={onChange}
        />
      </div>
      {previewSlideId && loaded.deck.slides[previewSlideId] && (
        <SlidePreviewModal
          lectureId={loaded.deck.lecture_id}
          slide={loaded.deck.slides[previewSlideId]}
          index={previewIndex}
          total={order.length}
          onClose={() => setPreviewSlideId(null)}
          onPrev={() => handlePreviewNav(-1)}
          onNext={() => handlePreviewNav(1)}
          canPrev={previewIndex > 0}
          canNext={previewIndex < order.length - 1}
          onEdit={
            isBakedImageSlide(loaded.deck.slides[previewSlideId].layout)
              ? undefined
              : () => {
                  setSpecEditSlideId(previewSlideId);
                  setPreviewSlideId(null);
                }
          }
        />
      )}
      {specEditSlideId && loaded.deck.slides[specEditSlideId] && (
        <SlideSpecEditor
          lectureId={loaded.deck.lecture_id}
          slide={loaded.deck.slides[specEditSlideId]}
          onClose={() => setSpecEditSlideId(null)}
          onSaved={() => {
            setSpecEditSlideId(null);
            onChange();
          }}
        />
      )}
    </>
  );
}


// ─────────────────────────────────────────────────────────
// 강의 선택 화면 (lecture_id 없을 때)
// ─────────────────────────────────────────────────────────

function LectureSelectScreen(props: {
  lectures: LectureSummary[];
  showCreateForm: boolean;
  setShowCreateForm: (b: boolean) => void;
  onSelect: (id: string) => void;
  onCreated: (id: string) => void;
  onRefresh: () => void;
  error: string | null;
}) {
  const { lectures, showCreateForm, setShowCreateForm, onSelect, onCreated, onRefresh, error } = props;
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = async (L: LectureSummary, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`강의 "${L.title}"을(를) 삭제할까요?\n\n슬라이드 ${L.slide_count}장과 자료를 포함해 폴더 전체가 영구 삭제됩니다.`)) {
      return;
    }
    setDeletingId(L.lecture_id);
    try {
      await api.deleteLecture(L.lecture_id);
      onRefresh();
    } catch (err) {
      alert('삭제 실패: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="h-screen w-screen overflow-y-auto p-8">
      <div className="max-w-4xl mx-auto">
        <header className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold text-stone-800">강의 만들기</h1>
            <p className="text-stone-500 mt-1 text-sm">
              한 장씩 협업으로 만드는 강의 슬라이드 워크스페이스
            </p>
          </div>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="px-4 py-2 bg-stone-800 text-white rounded-lg hover:bg-stone-700"
          >
            {showCreateForm ? '취소' : '+ 새 강의'}
          </button>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
            {error}
          </div>
        )}

        {showCreateForm && (
          <CreateLectureForm onCreated={onCreated} onCancel={() => setShowCreateForm(false)} />
        )}

        <div className="bg-white rounded-lg border border-stone-200 overflow-hidden">
          {lectures.length === 0 ? (
            <div className="p-8 text-center text-stone-400">
              아직 만든 강의가 없습니다. 위의 <b>"+ 새 강의"</b>로 시작하세요.
            </div>
          ) : (
            <ul className="divide-y divide-stone-100">
              {lectures.map((L) => (
                <li
                  key={L.lecture_id}
                  onClick={() => onSelect(L.lecture_id)}
                  className="group p-4 hover:bg-stone-50 cursor-pointer flex items-center justify-between gap-3"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-stone-800 truncate">{L.title}</div>
                    <div className="text-xs text-stone-500 mt-0.5">
                      {L.audience && <span>청중: {L.audience} · </span>}
                      슬라이드 {L.slide_count}장 · {formatDate(L.updated_at)}
                    </div>
                    <div className="text-xs text-stone-400 mt-0.5 font-mono">{L.lecture_id}</div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={(e) => handleDelete(L, e)}
                      disabled={deletingId === L.lecture_id}
                      title="강의 삭제 (폴더 전체)"
                      className="px-2 py-1 text-xs text-stone-400 hover:text-white hover:bg-red-500 rounded opacity-0 group-hover:opacity-100 transition disabled:opacity-60"
                    >
                      {deletingId === L.lecture_id ? '삭제 중…' : '🗑 삭제'}
                    </button>
                    <div className="text-stone-300 text-xl">›</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}


function CreateLectureForm(props: {
  onCreated: (id: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState('');
  const [audience, setAudience] = useState('');
  const [thesis, setThesis] = useState('');
  const [duration, setDuration] = useState('60');
  const [designSystem, setDesignSystem] = useState('vintage_book');
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const submit = async () => {
    if (!title.trim()) {
      setError('제목은 필수입니다.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.createLecture({
        title: title.trim(),
        audience: audience.trim() || undefined,
        thesis: thesis.trim() || undefined,
        duration_minutes: parseInt(duration) || undefined,
        design_system: designSystem,
      });
      // 업로드한 파일을 강의 자료로 등록 (강의 생성 직후). 자료가 있으면 워크스페이스에서
      // "슬라이드 일괄생성"으로 여러 장을 한 번에 만들어 강의 끝에 덧붙일 수 있다.
      if (files.length > 0) {
        for (let i = 0; i < files.length; i++) {
          setProgress(`자료 업로드 중… (${i + 1}/${files.length}) ${files[i].name}`);
          try {
            await api.uploadMaterial(result.lecture_id, files[i]);
          } catch (e) {
            // 한 파일 실패해도 강의 생성은 유지 — 경고만
            console.warn('자료 업로드 실패:', files[i].name, e);
          }
        }
      }
      props.onCreated(result.lecture_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
      setProgress(null);
    }
  };

  return (
    <div className="mb-4 p-4 bg-white rounded-lg border border-stone-200">
      <h2 className="text-lg font-semibold mb-3 text-stone-800">새 강의 만들기</h2>
      <div className="space-y-3">
        <Field label="제목 *">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예: 하네스란 무엇인가? 1부"
            className="w-full px-3 py-2 border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 placeholder:text-stone-400"
            autoFocus
          />
        </Field>
        <Field label="청중">
          <input
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            placeholder="예: 일반인 / 학생 / 전문가"
            className="w-full px-3 py-2 border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 placeholder:text-stone-400"
          />
        </Field>
        <Field label="한 줄 요지">
          <input
            value={thesis}
            onChange={(e) => setThesis(e.target.value)}
            placeholder="청중이 절대 잊지 말아야 할 단 한 가지"
            className="w-full px-3 py-2 border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 placeholder:text-stone-400"
          />
        </Field>
        <Field label="분량 (분)">
          <input
            type="number"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            className="w-32 px-3 py-2 border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 placeholder:text-stone-400"
          />
        </Field>
        <Field label="디자인 시스템 (전체 톤)">
          <select
            value={designSystem}
            onChange={(e) => setDesignSystem(e.target.value)}
            className="w-full px-3 py-2 border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 bg-white"
          >
            <optgroup label="CSS 디자인 (빠름·무료)">
              {DESIGN_SYSTEM_OPTIONS.filter((o) => o.group === 'css').map((o) => (
                <option key={o.value} value={o.value}>{o.label} — {o.description}</option>
              ))}
            </optgroup>
            <optgroup label="프리미엄 일러스트 (이미지 생성 — 느림·비용)">
              {DESIGN_SYSTEM_OPTIONS.filter((o) => o.group === 'image').map((o) => (
                <option key={o.value} value={o.value}>{o.label} — {o.description}</option>
              ))}
            </optgroup>
            <optgroup label="자동">
              {DESIGN_SYSTEM_OPTIONS.filter((o) => o.group === 'auto').map((o) => (
                <option key={o.value} value={o.value}>{o.label} — {o.description}</option>
              ))}
            </optgroup>
          </select>
        </Field>
        <Field label="강의 자료 (선택 — 일괄생성용 원고·파일)">
          <div className="space-y-1.5">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
              className="block w-full text-sm text-stone-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:bg-stone-100 file:text-stone-700 hover:file:bg-stone-200"
            />
            {files.length > 0 && (
              <div className="text-xs text-stone-500">
                {files.length}개 파일 선택됨 — 강의 생성 후 자료로 등록됩니다.
              </div>
            )}
            <div className="text-[11px] text-stone-400">
              자료는 <b>“슬라이드 일괄생성”</b>에만 쓰입니다 — 매 슬라이드 프롬프트엔 들어가지 않아요. (docx·txt·md·pdf)
            </div>
          </div>
        </Field>
        {progress && <div className="text-xs text-stone-500">{progress}</div>}
        {error && <div className="text-sm text-red-600">{error}</div>}
        <div className="flex gap-2 pt-2">
          <button
            onClick={submit}
            disabled={submitting}
            className="px-4 py-2 bg-stone-800 text-white rounded hover:bg-stone-700 disabled:opacity-50"
          >
            {submitting ? (progress ? '자료 업로드 중...' : '생성 중...') : '만들기'}
          </button>
          <button
            onClick={props.onCancel}
            className="px-4 py-2 border border-stone-300 rounded hover:bg-stone-100"
          >
            취소
          </button>
        </div>
      </div>
    </div>
  );
}


function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-sm text-stone-600 mb-1">{props.label}</span>
      {props.children}
    </label>
  );
}


// ─────────────────────────────────────────────────────────
// 강의 상단 헤더 (메타 + 뒤로가기)
// ─────────────────────────────────────────────────────────

function LectureHeader(props: {
  deck: Deck;
  onBack: () => void;
  onChange: () => void;
}) {
  const { deck, onBack, onChange } = props;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(deck.title);
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    setDraft(deck.title);
    setEditing(true);
  };

  const save = async () => {
    const next = draft.trim();
    if (!next || next === deck.title) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await api.updateDeckMeta(deck.lecture_id, { title: next });
      onChange();
      setEditing(false);
    } catch (e) {
      alert('제목 변경 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  };

  return (
    <header className="px-6 py-3 bg-white border-b border-stone-200 flex items-center gap-4">
      <button
        onClick={onBack}
        className="text-stone-500 hover:text-stone-800 text-sm"
      >
        ← 목록
      </button>
      <div className="flex-1 min-w-0">
        {editing ? (
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); save(); }
              else if (e.key === 'Escape') { e.preventDefault(); setEditing(false); }
            }}
            disabled={saving}
            autoFocus
            className="w-full text-lg font-semibold text-stone-900 border border-stone-300 rounded px-2 py-0.5 focus:outline-none focus:border-stone-500 disabled:opacity-60"
          />
        ) : (
          <h1
            onClick={startEdit}
            title="클릭하여 제목 수정"
            className="group/title text-lg font-semibold text-stone-800 truncate cursor-text hover:text-stone-600"
          >
            {deck.title}
            <span className="ml-2 text-xs text-stone-300 group-hover/title:text-stone-500">✏️</span>
          </h1>
        )}
        <div className="text-xs text-stone-500 truncate">
          {deck.audience && `${deck.audience}`}
          {deck.duration_minutes ? ` · ${deck.duration_minutes}분` : ''}
          {deck.thesis && ` · ${deck.thesis}`}
        </div>
      </div>
      <DesignSystemPicker
        lectureId={deck.lecture_id}
        current={deck.design_system}
        onChanged={onChange}
      />
      <ExportMenu lectureId={deck.lecture_id} slideCount={deck.slide_order.length} />
      <div className="text-xs text-stone-400 font-mono">{deck.lecture_id}</div>
    </header>
  );
}


function DesignSystemPicker(props: {
  lectureId: string;
  current: string;
  onChanged: () => void;
}) {
  const { lectureId, current, onChanged } = props;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentLabel =
    DESIGN_SYSTEM_OPTIONS.find((o) => o.value === current)?.label || current;

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value;
    if (next === current) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateDeckMeta(lectureId, { design_system: next });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] text-stone-500 shrink-0">디자인</span>
      <select
        value={current}
        onChange={handleChange}
        disabled={busy}
        title={`현재: ${currentLabel}. 변경 시 새 슬라이드부터 적용 (기존 슬라이드는 옛 톤 유지).`}
        className="px-2 py-1 text-xs border border-stone-300 rounded bg-white text-stone-700 hover:border-stone-500 focus:outline-none focus:border-stone-500 disabled:opacity-50"
      >
        <optgroup label="CSS (빠름)">
          {DESIGN_SYSTEM_OPTIONS.filter((o) => o.group === 'css').map((o) => (
            <option key={o.value} value={o.value} title={o.description}>{o.label}</option>
          ))}
        </optgroup>
        <optgroup label="프리미엄 일러스트 (이미지·느림)">
          {DESIGN_SYSTEM_OPTIONS.filter((o) => o.group === 'image').map((o) => (
            <option key={o.value} value={o.value} title={o.description}>{o.label}</option>
          ))}
        </optgroup>
        <optgroup label="자동">
          {DESIGN_SYSTEM_OPTIONS.filter((o) => o.group === 'auto').map((o) => (
            <option key={o.value} value={o.value} title={o.description}>{o.label}</option>
          ))}
        </optgroup>
      </select>
      {error && (
        <span className="text-[11px] text-red-600">{error}</span>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────
// 좌패널: 재료 (업로드 + 목록)
// ─────────────────────────────────────────────────────────
