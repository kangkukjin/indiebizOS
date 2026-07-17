/**
 * 강의 워크스페이스 — AI 채팅 층 (2026-07-18 모듈화 — 1500줄 규칙)
 * LectureWorkspace.tsx 에서 verbatim 이동: AIChatPanel(대화·재렌더 의도 감지)·
 * LayoutSelect·ChatBubble + formatDate(본체 LectureSelectScreen 도 사용 — export).
 */
import { useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import type {
  Deck,
  SlideCreateResponse,
} from '../../lib/api-lecture-workspace';

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

export function AIChatPanel(props: {
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

export function formatDate(iso: string): string {
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
