/**
 * NarrationStudio — 실강 녹음 모드 + 동영상 렌더 버튼 (강의 창 헤더에 붙는다)
 *
 * 왜 두 버튼이 한 컴포넌트인가: 둘이 **같은 하나의 상태**를 본다 — 이 강의에
 * 녹음이 있는가. 있으면 렌더는 실녹음 경로로, 없으면 기존 스피커 노트 TTS 경로로
 * 간다. 그 분기는 백엔드(deck_video.live_recording)가 하고, 여기서는 무엇이
 * 일어날지를 누르기 전에 보여 주기만 한다.
 *
 * ★녹음 모드가 기록하는 진짜 물건은 음성이 아니라 **타이밍**이다.
 *   스피커 노트 TTS 경로는 "글이 길면 씬도 길다"인데, 실강은 반대다 —
 *   내가 그 슬라이드를 띄워 둔 시간이 이미 정답이고 씬이 거기 맞춘다.
 *   음성은 그 타이밍에 딸려오는 부산물이다.
 *
 * 능력은 어휘([self:deck]{op:"video"})가 갖고 있고 이 파일은 표현만 맡는다
 * (custom_app_instrument.md 철칙0).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../lib/api';
import type { Deck } from '../../lib/api-lecture-workspace';

type Mark = { slide_id: string; t: number };
type RecStatus = { exists: boolean; duration_sec?: number; created_at?: string; marks?: Mark[] };

function mmss(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

// ─────────────────────────────────────────────────────────────────────
// 녹음 화면 (전체 화면 오버레이 — 왼쪽 슬라이드 · 오른쪽 강의 노트)
// ─────────────────────────────────────────────────────────────────────

function RecorderOverlay(props: {
  lectureId: string;
  deck: Deck;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { lectureId, deck, onClose, onSaved } = props;
  const order = deck.slide_order;

  const [idx, setIdx] = useState(0);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const marksRef = useRef<Mark[]>([]);
  const idxRef = useRef(0);
  useEffect(() => { idxRef.current = idx; }, [idx]);

  // 경과초는 performance.now() 기준 — Date.now() 는 시스템 시계가 바뀌면 튄다.
  const since = () => (performance.now() - startedAtRef.current) / 1000;

  const finish = useCallback(async (mime: string) => {
    const total = since();
    const blob = new Blob(chunksRef.current, { type: mime || 'audio/webm' });
    setSaving(true);
    try {
      await api.saveNarrationRecording(lectureId, blob, {
        duration_sec: total,
        marks: marksRef.current,
      });
      onSaved();
      onClose();
    } catch (e) {
      setError('저장 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setSaving(false);
    }
  }, [lectureId, onSaved, onClose]);

  const start = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        void finish(mr.mimeType);
      };
      startedAtRef.current = performance.now();
      // 첫 마크 = "지금 보고 있는 이 장이 0초부터 떠 있었다"
      marksRef.current = [{ slide_id: order[idxRef.current], t: 0 }];
      setMarks(marksRef.current);
      setElapsed(0);
      recorderRef.current = mr;
      mr.start();
      setRecording(true);
    } catch (e) {
      setError('마이크를 열 수 없습니다: ' + (e instanceof Error ? e.message : String(e)));
    }
  };

  const stop = () => {
    setRecording(false);
    recorderRef.current?.stop();   // onstop → finish() 가 저장까지 한다
  };

  // 슬라이드 이동 — 녹음 중이면 그 시각이 곧 씬 경계가 된다.
  const go = useCallback((delta: number) => {
    setIdx((cur) => {
      const next = Math.min(order.length - 1, Math.max(0, cur + delta));
      if (next !== cur && recorderRef.current?.state === 'recording') {
        marksRef.current = [...marksRef.current, { slide_id: order[next], t: since() }];
        setMarks(marksRef.current);
      }
      return next;
    });
  }, [order]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
        e.preventDefault(); go(1);
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault(); go(-1);
      } else if (e.key === 'Escape' && !recording) {
        e.preventDefault(); onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, recording, onClose]);

  useEffect(() => {
    if (!recording) return;
    const id = window.setInterval(() => setElapsed(since()), 200);
    return () => window.clearInterval(id);
  }, [recording]);

  // 창이 닫힐 때 마이크가 열린 채 남지 않게.
  useEffect(() => () => {
    const mr = recorderRef.current;
    if (mr && mr.state !== 'inactive') mr.stream.getTracks().forEach((t) => t.stop());
  }, []);

  const sid = order[idx];
  const slide = deck.slides[sid];
  const note = (slide?.speaker_note ?? '').trim();

  return (
    <div className="fixed inset-0 z-50 bg-stone-900 text-stone-100 flex flex-col">
      <div className="px-5 py-2.5 flex items-center gap-4 border-b border-stone-700 bg-stone-800">
        <span className="font-semibold">🎙 나레이션 녹음</span>
        <span className="text-sm text-stone-400">
          {idx + 1} / {order.length} · {slide?.title ?? sid}
        </span>
        {recording && (
          <span className="flex items-center gap-2 text-sm">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
            <span className="font-mono">{mmss(elapsed)}</span>
            <span className="text-stone-400">· 전환 {marks.length - 1}회</span>
          </span>
        )}
        <div className="flex-1" />
        {!recording ? (
          <>
            <button
              onClick={start}
              disabled={saving || order.length === 0}
              className="px-4 py-1.5 rounded bg-red-600 hover:bg-red-500 disabled:opacity-50 text-sm font-medium"
            >
              ● 녹음 시작
            </button>
            <button
              onClick={onClose}
              disabled={saving}
              className="px-3 py-1.5 rounded border border-stone-600 hover:bg-stone-700 text-sm disabled:opacity-50"
            >
              {saving ? '저장 중…' : '닫기'}
            </button>
          </>
        ) : (
          <button
            onClick={stop}
            className="px-4 py-1.5 rounded bg-stone-100 text-stone-900 hover:bg-white text-sm font-medium"
          >
            ■ 녹음 끝
          </button>
        )}
      </div>

      {error && (
        <div className="px-5 py-2 bg-red-900/60 text-red-100 text-sm">{error}</div>
      )}

      <div className="flex-1 min-h-0 flex">
        {/* 왼쪽: 슬라이드 */}
        <div className="flex-1 min-w-0 flex items-center justify-center bg-black p-4">
          {slide ? (
            <img
              src={`${api.slidePngUrl(lectureId, sid)}?v=${encodeURIComponent(slide.updated_at ?? '')}`}
              alt={slide.title ?? sid}
              className="max-w-full max-h-full object-contain"
            />
          ) : (
            <div className="text-stone-500">슬라이드가 없습니다</div>
          )}
        </div>

        {/* 오른쪽: 강의 노트 */}
        <div className="w-[38%] min-w-[320px] border-l border-stone-700 flex flex-col">
          <div className="px-5 py-2 text-xs uppercase tracking-wide text-stone-400 border-b border-stone-700">
            강의 노트
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4 text-[15px] leading-8 whitespace-pre-wrap">
            {note || <span className="text-stone-500">이 장에는 노트가 없습니다.</span>}
          </div>
          <div className="px-5 py-2 text-xs text-stone-400 border-t border-stone-700">
            ← → 로 넘기세요. 넘긴 시각이 그대로 영상의 장면 경계가 됩니다.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// 헤더에 붙는 두 버튼
// ─────────────────────────────────────────────────────────────────────

export function NarrationStudio(props: { lectureId: string; deck: Deck }) {
  const { lectureId, deck } = props;
  const [rec, setRec] = useState<RecStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [render, setRender] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRec(await api.getNarrationRecording(lectureId));
    } catch {
      setRec({ exists: false });   // 조회 실패 = 없는 것으로 보고 TTS 경로 안내
    }
  }, [lectureId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const status = typeof render?.status === 'string' ? render.status : '';

  // 렌더는 별도 프로세스라 폴링으로 따라간다.
  // ★상태 파일을 직접 긁지 않는다 — 죽은 렌더의 'building' 을 그대로 믿게 된다
  //   (video_workflow.md 2026-08-17 실사고). check:true 가 pid 로 생사를 판정한다.
  useEffect(() => {
    if (status !== 'building' && status !== 'queued') return;
    const id = window.setInterval(async () => {
      try { setRender(await api.lectureVideoStatus(lectureId)); } catch { /* 다음 tick */ }
    }, 4000);
    return () => window.clearInterval(id);
  }, [status, lectureId]);

  const startRender = async () => {
    setBusy(true);
    setError(null);
    try {
      setRender(await api.renderLectureVideo(lectureId) as Record<string, unknown>);
    } catch (e) {
      setError('렌더 시작 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  const hasRec = !!rec?.exists;
  const busyRender = status === 'building' || status === 'queued';

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setOpen(true)}
        title={hasRec
          ? '다시 녹음하면 지금 저장된 녹음을 대체합니다'
          : '슬라이드를 보며 실제 강의를 녹음합니다'}
        className="px-3 py-1.5 rounded border border-stone-300 hover:bg-stone-100 text-sm text-stone-700"
      >
        🎙 {hasRec ? '다시 녹음' : '나레이션 녹음'}
      </button>

      <button
        onClick={startRender}
        disabled={busy || busyRender || deck.slide_order.length === 0}
        title={hasRec
          ? '저장된 녹음과 전환 타임라인으로 렌더합니다'
          : '녹음이 없어 스피커 노트 TTS 로 렌더합니다'}
        className="px-3 py-1.5 rounded border border-stone-300 hover:bg-stone-100 text-sm text-stone-700 disabled:opacity-50"
      >
        🎬 {busyRender ? '렌더 중…' : '동영상 렌더링'}
      </button>

      <span className="text-xs text-stone-500 max-w-[220px] truncate">
        {status === 'done'
          ? '✅ 렌더 완료'
          : status === 'error' || status === 'interrupted'
            ? `⚠️ ${String(render?.error ?? '렌더가 끊겼습니다')}`
            : hasRec
              ? `녹음 ${mmss(rec?.duration_sec ?? 0)} · 전환 ${Math.max(0, (rec?.marks?.length ?? 1) - 1)}회`
              : '녹음 없음 → TTS'}
      </span>

      {error && <span className="text-xs text-red-600">{error}</span>}

      {open && (
        <RecorderOverlay
          lectureId={lectureId}
          deck={deck}
          onClose={() => setOpen(false)}
          onSaved={() => { void refresh(); }}
        />
      )}
    </div>
  );
}
