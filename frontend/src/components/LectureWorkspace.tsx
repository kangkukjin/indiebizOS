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
  MaterialEntry,
  SlideMeta,
  SlideCreateResponse,
} from '../lib/api-lecture-workspace';
import { DESIGN_SYSTEM_OPTIONS } from '../lib/api-lecture-workspace';

interface LectureWorkspaceProps {
  initialLectureId: string | null;
}

// 통짜 이미지(native) / 업로드 이미지(image) 슬라이드는 글자가 PNG에 구워져 있어
// 필드 직접 편집(spec patch → HTML 재렌더)이 불가능하다. 이런 슬라이드는 AI 채팅으로
// '재생성'해서 바꿔야 한다 → 필드 편집(✏️) 버튼을 숨긴다.
const isBakedImageSlide = (layout: string) => layout === 'native' || layout === 'image';

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

function MaterialsPanel(props: {
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

function DeckPanel(props: {
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

function SlideSpecEditor(props: {
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


function AppendSlideButton(props: { active: boolean; onClick: () => void }) {
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


function SlideCard(props: {
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

interface ChatMessage {
  role: 'user' | 'ai' | 'system';
  text: string;
  slideId?: string;     // AI 응답이 슬라이드 생성/편집을 동반한 경우
  reasoning?: string;
  speakerNote?: string;
  mode?: 'create' | 'edit';
}

/**
 * "재생성/재렌더/다시 그려/redraw" 같이 spec 변경 의도가 없는 instruction을 감지.
 * 매칭되면 slide_edit(AI 호출) 대신 slide_rerender(PNG만 재렌더)로 분기.
 *
 * 보수적으로: 짧은 문장 + 명백한 키워드. 추가 변경 의도(목적어·수정 사항)가 있으면 매칭 안 됨.
 */
const RERENDER_INTENT_RE =
  /^\s*(재\s*생성|재\s*렌더|리\s*렌더|다시\s*그려|다시\s*만들어|다시\s*렌더|새로\s*그려|rerender|re-?render|redraw|regenerate|refresh)[\s.!?]*(해|해줘|해주세요|줘|주세요|please)?[\s.!?]*$/i;

function AIChatPanel(props: {
  deck: Deck;
  focusSlideId: string | null;
  insertBeforeIndex: number | null;
  clearModes: () => void;
  onChange: () => void;
}) {
  const { deck, focusSlideId, insertBeforeIndex, clearModes, onChange } = props;
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'ai',
      text:
        `안녕하세요. "${deck.title}" 강의를 같이 만들어 갑니다.\n\n` +
        `현재 슬라이드 ${deck.slide_order.length}장.\n\n` +
        `• 새 슬라이드 (끝에 추가): 그냥 자연어로 요청\n` +
        `• 사이에 삽입: 가운데 패널의 카드 사이 호버 → "+ 삽입" 클릭 → 입력\n` +
        `• 편집: 슬라이드 클릭 → 노란 테두리 보이면 편집 모드 → 코멘트 입력\n` +
        `• Layout 강제: 입력란 위 드롭다운에서 선택 (미선택 시 AI 자동)`,
    },
  ]);
  const [input, setInput] = useState('');
  const [layoutChoice, setLayoutChoice] = useState<string>(''); // '' = AI 자동
  const [imageQuality, setImageQuality] = useState<'pro' | 'fast'>('pro'); // 통짜 이미지 품질
  const [editMode, setEditMode] = useState<'image' | 'regen'>('image'); // 통짜 편집: 부분수정 vs 전체재생성
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 통짜 이미지(native) 덱일 때만 이미지 품질 선택이 의미 있음
  const isNativeDeck = (deck.design_system || '').startsWith('native');

  // 편집 대상 슬라이드의 종류 — 통짜 이미지(native)/업로드 이미지(image)면 '이미지 편집' 경로 가능
  const focusedSlide = focusSlideId ? deck.slides[focusSlideId] : null;
  const focusNative = focusedSlide?.layout === 'native';
  const focusImage = focusedSlide?.layout === 'image';
  const focusBaked = focusNative || focusImage;

  // 모드 결정
  const mode: 'edit' | 'insert' | 'append' = focusSlideId
    ? 'edit'
    : insertBeforeIndex !== null
      ? 'insert'
      : 'append';

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, busy]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');

    const userMsg: ChatMessage = { role: 'user', text };
    setMessages((m) => [...m, userMsg]);
    setBusy(true);

    const chosenLayout = layoutChoice || undefined;
    // 휴리스틱: focus 모드 + 짧은 instruction이 "재생성/재렌더/다시 그려"류로만 끝나면
    // editSlide(AI 재생성)가 아니라 rerenderSlide(spec 보존, PNG만 재렌더)로 분기.
    // 디자인 변경 후 같은 내용을 새 톤으로 다시 그리고 싶을 때 자연스러운 명령.
    const isRerenderIntent =
      mode === 'edit' &&
      focusSlideId !== null &&
      !focusBaked &&    // 통짜/이미지 슬라이드는 spec 재렌더가 불가 — 아래 경로로 보냄
      !chosenLayout &&  // layout 강제하면 spec을 바꾸려는 명백한 의도
      RERENDER_INTENT_RE.test(text);

    try {
      if (isRerenderIntent) {
        const rr = await api.rerenderSlide(deck.lecture_id, focusSlideId!);
        const summary = `🔄 재렌더됨 (spec 보존) — ${rr.slide_id}: 「${rr.title}」 · ${rr.design_system}`;
        setMessages((m) => [...m, { role: 'ai', text: summary, slideId: rr.slide_id, mode: 'edit' }]);
        clearModes();
        onChange();
        return;
      }

      const q = isNativeDeck ? imageQuality : undefined;

      // 통짜/이미지 슬라이드 편집: '부분수정'(이미지 편집) 또는 image 슬라이드는 무조건 이미지 편집.
      // → 다시 그리지 않고 현재 이미지에서 시키는 부분만 수정 (구도 보존).
      if (mode === 'edit' && focusSlideId && (focusImage || (focusNative && editMode === 'image'))) {
        const r = await api.imageEditSlide(deck.lecture_id, focusSlideId, text, q);
        setMessages((m) => [...m, {
          role: 'ai',
          text: `🖌 이미지 부분 수정됨 (기존 그림 유지) — ${r.slide_id}: 「${r.title || r.slide_id}」`,
          slideId: r.slide_id, mode: 'edit',
        }]);
        clearModes();
        onChange();
        return;
      }

      let result: SlideCreateResponse;
      if (mode === 'edit' && focusSlideId) {
        result = await api.editSlide(deck.lecture_id, focusSlideId, text, chosenLayout, q);
      } else if (mode === 'insert' && insertBeforeIndex !== null) {
        result = await api.createSlide(deck.lecture_id, text, insertBeforeIndex, chosenLayout, q);
      } else {
        result = await api.createSlide(deck.lecture_id, text, undefined, chosenLayout, q);
      }

      const slideTitle = (result.slide?.title as string) || result.slide_id;
      const summary =
        result.mode === 'edit'
          ? `✏️ 편집됨 — ${result.slide_id}: 「${slideTitle}」`
          : mode === 'insert'
            ? `➕ 삽입됨 (위치 ${(insertBeforeIndex ?? 0) + 1}) — ${result.slide_id}: 「${slideTitle}」`
            : `✨ 새 슬라이드 — ${result.slide_id}: 「${slideTitle}」`;

      const aiMsg: ChatMessage = {
        role: 'ai',
        text: summary,
        slideId: result.slide_id,
        reasoning: result.reasoning,
        speakerNote: result.speaker_note,
        mode: result.mode,
      };
      setMessages((m) => [...m, aiMsg]);

      // edit·insert 모드는 자동 해제 (다음 작업이 자연스럽게 끝에 추가로)
      if (mode !== 'append') {
        clearModes();
      }
      onChange();
    } catch (err) {
      const errText = err instanceof Error ? err.message : String(err);
      setMessages((m) => [
        ...m,
        { role: 'system', text: `❌ 실패: ${errText}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  // 모드별 헤더·placeholder
  const headerLabel =
    mode === 'edit'
      ? `편집 모드: ${focusSlideId} (해제: 슬라이드 다시 클릭)`
      : mode === 'insert'
        ? `삽입 모드: 위치 ${(insertBeforeIndex ?? 0) + 1} (해제: 같은 + 다시 클릭)`
        : '슬라이드 생성 AI (끝에 추가)';
  const placeholder =
    mode === 'edit'
      ? (focusBaked && (focusImage || editMode === 'image')
          ? `이 부분만 바꿔줘 (예: 제목을 '...'로). 나머지는 유지됩니다`
          : `${focusSlideId}을 어떻게 바꿀까요?`)
      : mode === 'insert'
        ? `위치 ${(insertBeforeIndex ?? 0) + 1}에 어떤 슬라이드?`
        : '다음 슬라이드는 어떤 명제로?';

  return (
    <aside className="w-96 flex-shrink-0 flex flex-col bg-white border-l border-stone-200">
      <div className="px-4 py-3 border-b border-stone-100">
        <h2 className="text-sm font-semibold text-stone-700">💬 AI 채팅</h2>
        <div className="text-xs mt-0.5">
          {mode === 'append' ? (
            <span className="text-stone-400">{headerLabel}</span>
          ) : (
            <span className="text-amber-600 font-medium">{headerLabel}</span>
          )}
        </div>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 bg-stone-50">
        {messages.map((m, i) => (
          <ChatBubble key={i} msg={m} />
        ))}
        {busy && (
          <div className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-500 max-w-[85%]">
            <span className="inline-block animate-pulse">슬라이드 생성 중...</span>
            <div className="text-xs text-stone-400 mt-1">AI 호출 + 렌더링 (5~30초)</div>
          </div>
        )}
      </div>
      <div className="p-3 border-t border-stone-100 space-y-2">
        {mode === 'edit' && focusSlideId && (
          <button
            type="button"
            onClick={async () => {
              if (busy) return;
              setBusy(true);
              try {
                const rr = await api.rerenderSlide(deck.lecture_id, focusSlideId);
                setMessages((m) => [...m, {
                  role: 'ai',
                  text: `🔄 재렌더됨 (spec 보존) — ${rr.slide_id}: 「${rr.title}」 · ${rr.design_system}`,
                  slideId: rr.slide_id,
                  mode: 'edit',
                }]);
                clearModes();
                onChange();
              } catch (err) {
                setMessages((m) => [...m, {
                  role: 'system',
                  text: `❌ 재렌더 실패: ${err instanceof Error ? err.message : String(err)}`,
                }]);
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
            className="w-full px-3 py-1.5 text-xs bg-stone-100 hover:bg-stone-200 rounded text-stone-700 disabled:opacity-50"
            title="spec(제목·본문·layout) 변경 없이 PNG만 다시 그림. 디자인 시스템 바꾼 뒤 사용."
          >
            🔄 spec 그대로 재렌더 (현재 디자인 적용)
          </button>
        )}
        {mode === 'edit' && focusNative && (
          <div className="flex items-center gap-2">
            <label className="text-[11px] text-stone-500 shrink-0">수정</label>
            <div className="flex gap-1 flex-1">
              <button
                type="button"
                onClick={() => setEditMode('image')}
                disabled={busy}
                title="기존 그림은 그대로 두고 시키는 부분만 편집 (구도·그림 보존, 제목 한 줄 고치기 등)"
                className={`flex-1 px-2 py-1 text-xs rounded border ${
                  editMode === 'image'
                    ? 'bg-stone-800 text-white border-stone-800'
                    : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                } disabled:opacity-50`}
              >
                🖌 부분수정
              </button>
              <button
                type="button"
                onClick={() => setEditMode('regen')}
                disabled={busy}
                title="처음부터 다시 그림 (구도·그림이 달라질 수 있음)"
                className={`flex-1 px-2 py-1 text-xs rounded border ${
                  editMode === 'regen'
                    ? 'bg-stone-800 text-white border-stone-800'
                    : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                } disabled:opacity-50`}
              >
                🔁 전체 재생성
              </button>
            </div>
          </div>
        )}
        {isNativeDeck && (
          <div className="flex items-center gap-2">
            <label className="text-[11px] text-stone-500 shrink-0">이미지</label>
            <div className="flex gap-1 flex-1">
              <button
                type="button"
                onClick={() => setImageQuality('pro')}
                disabled={busy}
                title="Nano Banana Pro (Gemini 3 Pro Image) · 2K · 약 $0.134/장 — 고품질"
                className={`flex-1 px-2 py-1 text-xs rounded border ${
                  imageQuality === 'pro'
                    ? 'bg-stone-800 text-white border-stone-800'
                    : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                } disabled:opacity-50`}
              >
                고품질 (Pro)
              </button>
              <button
                type="button"
                onClick={() => setImageQuality('fast')}
                disabled={busy}
                title="Nano Banana 2 (Gemini 3.1 Flash Image) · 1K · 약 $0.067/장 — 저가·빠름"
                className={`flex-1 px-2 py-1 text-xs rounded border ${
                  imageQuality === 'fast'
                    ? 'bg-amber-600 text-white border-amber-600'
                    : 'bg-white text-stone-700 border-stone-300 hover:border-stone-500'
                } disabled:opacity-50`}
              >
                저가 (Fast)
              </button>
            </div>
          </div>
        )}
        <LayoutSelect
          value={layoutChoice}
          onChange={setLayoutChoice}
          disabled={busy}
        />
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={placeholder}
            disabled={busy}
            className="flex-1 px-3 py-2 text-sm border border-stone-300 rounded focus:outline-none focus:border-stone-500 disabled:bg-stone-100 text-stone-900 placeholder:text-stone-400"
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="px-3 py-2 text-sm bg-stone-800 text-white rounded hover:bg-stone-700 disabled:opacity-50"
          >
            보내기
          </button>
        </div>
      </div>
    </aside>
  );
}

// ─────────────────────────────────────────────────────────
// Layout 선택 드롭다운 — 슬라이드 생성/편집 시 강제 layout
// ─────────────────────────────────────────────────────────

const LAYOUT_OPTIONS: Array<{ value: string; label: string; group: '텍스트' | '일러스트' | '자유형' }> = [
  // 텍스트형 — 이미지 생성 없음, 빠름
  { value: 'hero',              label: '표지 (hero)',                  group: '텍스트' },
  { value: 'lecture_body',      label: '본문 (lecture_body)',          group: '텍스트' },
  { value: 'metaphor_story',    label: '메타포 (metaphor_story)',      group: '텍스트' },
  { value: 'comparison_table',  label: '비교표 (comparison_table)',    group: '텍스트' },
  { value: 'factbox',           label: '팩트박스 (factbox)',           group: '텍스트' },
  { value: 'quote',             label: '인용 (quote)',                 group: '텍스트' },
  // 일러스트형 — image_gemini 호출, 느림/비용
  { value: 'hero_illustration',     label: '표지+일러스트 (hero_illustration)',         group: '일러스트' },
  { value: 'illustration_anchor',   label: '상단 일러스트+본문 (illustration_anchor)',   group: '일러스트' },
  { value: 'split_concept',         label: '좌우 대비 (split_concept) — 좌+우 2장',      group: '일러스트' },
  { value: 'illustration_background', label: '배경 일러스트+텍스트 (illustration_background)', group: '일러스트' },
  { value: 'illustration_overlay',  label: '전면 다이어그램 (illustration_overlay)',    group: '일러스트' },
  { value: 'comparison_iconic',     label: '아이콘 비교표 (comparison_iconic)',         group: '일러스트' },
  // 자유형 — AI가 슬라이드 HTML을 직접 작성 (고정 틀 없음, 이미지 생성 안 함)
  { value: 'custom',                label: '자유형 (틀 없이 AI가 직접 디자인)',         group: '자유형' },
];

function LayoutSelect(props: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  const { value, onChange, disabled } = props;
  const isForced = value !== '';
  return (
    <div className="flex items-center gap-2">
      <label className="text-[11px] text-stone-500 shrink-0">Layout</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={`
          flex-1 px-2 py-1 text-xs rounded border focus:outline-none
          ${isForced
            ? 'border-amber-400 bg-amber-50 text-amber-900'
            : 'border-stone-300 bg-white text-stone-700'}
          disabled:opacity-50
        `}
      >
        <option value="">AI 자동 선택</option>
        <optgroup label="텍스트형 (빠름)">
          {LAYOUT_OPTIONS.filter((o) => o.group === '텍스트').map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </optgroup>
        <optgroup label="일러스트형 (이미지 생성 — 느림)">
          {LAYOUT_OPTIONS.filter((o) => o.group === '일러스트').map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </optgroup>
        <optgroup label="자유형 (틀 없음 — AI 직접 디자인)">
          {LAYOUT_OPTIONS.filter((o) => o.group === '자유형').map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </optgroup>
      </select>
      {isForced && (
        <button
          type="button"
          onClick={() => onChange('')}
          disabled={disabled}
          className="text-[11px] text-stone-400 hover:text-stone-700"
          title="layout 강제 해제"
        >
          ✕
        </button>
      )}
    </div>
  );
}


function ChatBubble(props: { msg: ChatMessage }) {
  const { msg } = props;
  if (msg.role === 'system') {
    return (
      <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
        {msg.text}
      </div>
    );
  }
  return (
    <div
      className={`max-w-[85%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap ${
        msg.role === 'user'
          ? 'bg-stone-800 text-white ml-auto'
          : 'bg-white border border-stone-200 text-stone-800'
      }`}
    >
      <div>{msg.text}</div>
      {msg.role === 'ai' && (msg.reasoning || msg.speakerNote) && (
        <details className="mt-2 text-xs text-stone-500">
          <summary className="cursor-pointer hover:text-stone-700">자세히</summary>
          {msg.reasoning && (
            <div className="mt-1">
              <span className="font-medium text-stone-600">왜 이 구도:</span> {msg.reasoning}
            </div>
          )}
          {msg.speakerNote && (
            <div className="mt-1">
              <span className="font-medium text-stone-600">스피커 노트:</span>{' '}
              <span className="whitespace-pre-wrap">{msg.speakerNote}</span>
            </div>
          )}
        </details>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────
// 유틸
// ─────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}
