/**
 * NarrationStudio — 실강 녹음 창(녹음 + 재생 확인) + 동영상 렌더 버튼
 *
 * 헤더에 남는 버튼은 둘이다: 🎙 녹음 창 열기 · 🎬 동영상 렌더링.
 * ★'강의 플레이'는 헤더가 아니라 **녹음 창 안**에 있다 — 재생이 바꾸는 것이
 *   녹음 창의 슬라이드이기 때문이다. 밖에 두면 "어디서 재생되는지"가 사라진다.
 *   (2026-08-20 사용자 지적으로 헤더 → 녹음 창 이사.)
 *
 * 왜 녹음과 렌더가 한 컴포넌트인가: 둘이 **같은 하나의 상태**를 본다 — 이 강의에
 * 녹음이 있는가. 있으면 렌더는 실녹음 경로로, 없으면 기존 스피커 노트 TTS 경로로
 * 간다. 그 분기는 백엔드(deck_video.live_recording)가 하고, 여기서는 무엇이
 * 일어날지를 누르기 전에 보여 주기만 한다.
 *
 * ★녹음 모드가 기록하는 진짜 물건은 음성이 아니라 **타이밍**이다.
 *   스피커 노트 TTS 경로는 "글이 길면 씬도 길다"인데, 실강은 반대다 —
 *   내가 그 슬라이드를 띄워 둔 시간이 이미 정답이고 씬이 거기 맞춘다.
 *   음성은 그 타이밍에 딸려오는 부산물이다. 재생은 그 타이밍을 되짚는 일이다.
 *
 * 능력은 어휘([self:deck]{op:"video"})가 갖고 있고 이 파일은 표현만 맡는다
 * (custom_app_instrument.md 철칙0). 재생은 서버가 아무것도 하지 않는다 —
 * 브라우저 <audio> 가 오디오를 물고, 진행 시각으로 슬라이드를 고를 뿐이다.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../lib/api';
import type { Deck } from '../../lib/api-lecture-workspace';

type Mark = { slide_id: string; t: number };
type RecStatus = { exists: boolean; duration_sec?: number; created_at?: string; marks?: Mark[] };

function mmss(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// ─────────────────────────────────────────────────────────────────────
// 타임라인 → 구간 (★렌더러와 같은 규칙이어야 미리보기가 영상과 안 어긋난다)
// 정본: deck_video.slice_recording — marks 를 t 로 정렬해 [t_i, t_{i+1}) 로 자르고,
// 마지막 구간은 duration_sec 까지. MIN_SEGMENT_SEC 이하는 '스치듯 지나간 장'이라
// 렌더가 버리므로 미리보기도 버린다(안 버리면 영상엔 없는 장이 여기서만 깜빡인다).
// ─────────────────────────────────────────────────────────────────────

const MIN_SEGMENT_SEC = 0.05;   // = deck_video.MIN_SEGMENT_SEC

export type Segment = { slideId: string; start: number; end: number };

export function buildSegments(marks: Mark[], durationSec: number): Segment[] {
  const sorted = [...(marks || [])]
    .filter((m) => m && m.slide_id)
    .sort((a, b) => (a.t || 0) - (b.t || 0));
  const segs: Segment[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const start = Math.max(0, sorted[i].t || 0);
    const end = i + 1 < sorted.length ? (sorted[i + 1].t || 0) : durationSec;
    if (end - start <= MIN_SEGMENT_SEC) continue;
    segs.push({ slideId: String(sorted[i].slide_id), start, end });
  }
  return segs;
}

/** 재생 시각 → 구간 인덱스. 마지막으로 start <= t 인 구간(이분 탐색). */
export function segmentAt(segs: Segment[], t: number): number {
  let lo = 0, hi = segs.length - 1, ans = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segs[mid].start <= t) { ans = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return ans;
}

// ─────────────────────────────────────────────────────────────────────
// 녹음 창 — 왼쪽 슬라이드 · 오른쪽 강의 노트. 녹음도 재생도 여기서 일어난다.
// ─────────────────────────────────────────────────────────────────────

function RecorderOverlay(props: {
  lectureId: string;
  deck: Deck;
  rec: RecStatus | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const { lectureId, deck, rec, onClose, onSaved } = props;
  const order = deck.slide_order;

  const [idx, setIdx] = useState(0);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const marksRef = useRef<Mark[]>([]);
  const idxRef = useRef(0);
  useEffect(() => { idxRef.current = idx; }, [idx]);

  // ── 재생 상태 ──
  // playSid = 재생이 고른 슬라이드. null 이면 손으로 넘기는 평소 모드(order[idx]).
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [cur, setCur] = useState(0);
  const [playSid, setPlaySid] = useState<string | null>(null);
  const playSidRef = useRef<string | null>(null);
  useEffect(() => { playSidRef.current = playSid; }, [playSid]);

  const total = Math.max(0, rec?.duration_sec ?? 0);
  const segs = useMemo(() => buildSegments(rec?.marks ?? [], total), [rec?.marks, total]);
  const canPlay = !!rec?.exists && segs.length > 0;

  // 경과초는 performance.now() 기준 — Date.now() 는 시스템 시계가 바뀌면 튄다.
  const since = () => (performance.now() - startedAtRef.current) / 1000;

  const finish = useCallback(async (mime: string) => {
    const totalRec = since();
    const blob = new Blob(chunksRef.current, { type: mime || 'audio/webm' });
    setSaving(true);
    try {
      await api.saveNarrationRecording(lectureId, blob, {
        duration_sec: totalRec,
        marks: marksRef.current,
      });
      // ★창을 닫지 않는다 — 녹음 직후 바로 ▶ 로 확인하는 게 이 창의 쓸모다
      //   (2026-08-20 사용자 판정: "녹음 직후에도 플레이를 해볼 수 있게").
      //   부모의 refresh 를 **기다려야** rec 이 갱신돼 '강의 플레이' 가 켜진 채 남는다
      //   — 안 기다리면 방금 녹음했는데 버튼이 잠깐 비활성으로 보인다.
      await onSaved();
      setCur(0);
      setPlaySid(null);
      setSaved(true);
    } catch (e) {
      setError('저장 실패: ' + msg(e));
    } finally {
      setSaving(false);
    }
  }, [lectureId, onSaved]);

  const start = async () => {
    setError(null);
    setSaved(false);
    // 재생으로 넘어가 있던 장이 있으면 그 장을 손 조작 위치로 물려받는다 —
    // 안 그러면 화면은 A 를 보여주는데 첫 마크는 B 로 찍힌다(창이 안 닫히면서 생긴 경로).
    const shownSid = playSidRef.current;
    if (shownSid) {
      const i = order.indexOf(shownSid);
      if (i >= 0) { idxRef.current = i; setIdx(i); }
      setPlaySid(null);
    }
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
      setError('마이크를 열 수 없습니다: ' + msg(e));
    }
  };

  const stop = () => {
    setRecording(false);
    recorderRef.current?.stop();   // onstop → finish() 가 저장까지 한다
  };

  // 슬라이드 이동(손) — 녹음 중이면 그 시각이 곧 씬 경계가 된다.
  // 손으로 넘기면 재생이 고른 장은 놓아준다(안 그러면 화살표가 먹은 것처럼 보인다).
  const go = useCallback((delta: number) => {
    setPlaySid(null);
    setIdx((cur0) => {
      const next = Math.min(order.length - 1, Math.max(0, cur0 + delta));
      if (next !== cur0 && recorderRef.current?.state === 'recording') {
        marksRef.current = [...marksRef.current, { slide_id: order[next], t: since() }];
        setMarks(marksRef.current);
      }
      return next;
    });
  }, [order]);

  // ── 재생 ──
  const seek = useCallback((t: number) => {
    const v = Math.min(total, Math.max(0, t));
    setCur(v);
    const s = segs[segmentAt(segs, v)];
    if (s) setPlaySid(s.slideId);
    const a = audioRef.current;
    // ★MediaRecorder 가 만든 webm 은 탐색 큐가 없을 수 있어 시킹이 안 먹을 수 있다.
    //   그때는 조용히 제자리에 머문다(재생 자체에는 영향 없음).
    if (a) { try { a.currentTime = v; } catch { /* 시킹 불가 — 무시 */ } }
  }, [total, segs]);

  const togglePlay = useCallback(() => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      setError(null);
      a.play().catch((e) => setError('재생할 수 없습니다: ' + msg(e)));
    } else {
      a.pause();
    }
  }, []);

  // 재생이 멎으면(정지·끝) 타이머를 접고, 지금 보고 있던 장을 손 조작 위치로 물려준다
  // — 그래야 멈춘 순간 슬라이드가 딴 데로 튀지 않는다.
  const settle = useCallback(() => {
    setPlaying(false);
    const sid = playSidRef.current;
    if (sid) {
      const i = order.indexOf(sid);
      if (i >= 0) setIdx(i);
    }
    setPlaySid(null);
  }, [order]);

  // 진행 시각 추적 — timeupdate 는 4Hz 라 슬라이드가 늦게 넘어간다. rAF 로 읽되
  // 0.08초(≈12Hz) 넘게 움직였을 때만 state 를 건드려 매 프레임 리렌더를 막는다.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      const a = audioRef.current;
      if (a) {
        const t = a.currentTime;
        setCur((prev) => (Math.abs(prev - t) >= 0.08 ? t : prev));
        const s = segs[segmentAt(segs, t)];
        if (s) setPlaySid((prev) => (prev === s.slideId ? prev : s.slideId));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, segs]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (playing) {
        // 재생 중에는 같은 키가 '재생 조작'을 뜻한다.
        const a = audioRef.current;
        const t = a?.currentTime ?? cur;
        const i = segmentAt(segs, t);
        if (e.key === ' ') { e.preventDefault(); togglePlay(); }
        else if (e.key === 'ArrowRight') {
          e.preventDefault();
          if (i + 1 < segs.length) seek(segs[i + 1].start);
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          const here = segs[i];
          if (here && t - here.start > 1.5) seek(here.start);
          else if (i > 0) seek(segs[i - 1].start);
          else seek(0);
        } else if (e.key === 'Escape') {
          e.preventDefault(); a?.pause();   // 먼저 재생만 멈춘다(창은 안 닫음)
        }
        return;
      }
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
  }, [go, recording, onClose, playing, segs, seek, togglePlay, cur]);

  useEffect(() => {
    if (!recording) return;
    const id = window.setInterval(() => setElapsed(since()), 200);
    return () => window.clearInterval(id);
  }, [recording]);

  // 창이 닫힐 때 마이크가 열린 채, 소리가 나는 채 남지 않게.
  useEffect(() => () => {
    const mr = recorderRef.current;
    if (mr && mr.state !== 'inactive') mr.stream.getTracks().forEach((t) => t.stop());
    audioRef.current?.pause();
  }, []);

  const sid = playSid ?? order[idx];
  const slide = sid ? deck.slides[sid] : undefined;
  const note = (slide?.speaker_note ?? '').trim();
  const inPlayback = playSid !== null;
  const segIdx = segmentAt(segs, cur);

  return (
    // ★no-drag 필수: 강의 창 맨 위에는 창을 잡아 옮기는 drag bar(h-9=36px,
    //   LectureWorkspace.titleBar)가 있는데, Electron 의 드래그 영역은 z-index 가
    //   아니라 '-webkit-app-region 을 선언한 사각형의 합'으로 계산된다. 그래서 이
    //   전체화면 오버레이가 그 위를 덮어도 위 36px 은 여전히 창 드래그가 먹고,
    //   거기 놓인 버튼(py-2.5 헤더 안 → 대략 y=10~41)은 아래 몇 px 만 눌린다.
    //   (2026-08-20 사용자 신고 "버튼 하단에서만 클릭됨"의 정체.)
    //   루트에 no-drag 를 걸면 그 사각형이 드래그 영역에서 통째로 빠진다.
    <div className="fixed inset-0 z-50 bg-stone-900 text-stone-100 flex flex-col no-drag">
      {canPlay && (
        <audio
          ref={audioRef}
          src={api.narrationAudioUrl(lectureId, rec?.created_at)}
          preload="auto"
          onPlay={() => setPlaying(true)}
          onPause={settle}
          onEnded={() => { setCur(total); settle(); }}
          onTimeUpdate={(e) => setCur(e.currentTarget.currentTime)}
          onError={() => setError('녹음 오디오를 불러오지 못했습니다.')}
          className="hidden"
        />
      )}

      <div className="px-5 py-2.5 flex items-center gap-4 border-b border-stone-700 bg-stone-800">
        <span className="font-semibold">🎙 나레이션 녹음</span>
        <span className="text-sm text-stone-400">
          {inPlayback && segs.length
            ? `재생 ${segIdx + 1} / ${segs.length} 구간 · ${slide?.title ?? sid}`
            : `${idx + 1} / ${order.length} · ${slide?.title ?? sid}`}
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
              onClick={togglePlay}
              disabled={!canPlay || saving}
              title={canPlay
                ? '저장된 녹음을 틀면서 슬라이드가 기록된 시각에 자동으로 넘어갑니다 (렌더링 불필요)'
                : '먼저 녹음을 해야 재생할 수 있습니다'}
              className="px-4 py-1.5 rounded border border-stone-600 hover:bg-stone-700 text-sm disabled:opacity-40"
            >
              {playing ? '❚❚ 재생 정지' : '▶ 강의 플레이'}
            </button>
            <button
              onClick={start}
              disabled={saving || playing || order.length === 0}
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

      {/* 창이 더는 자동으로 닫히지 않으므로 저장됐다는 사실을 말해 준다 */}
      {saved && !error && !recording && (
        <div className="px-5 py-2 bg-emerald-900/50 text-emerald-100 text-sm">
          ✅ 녹음을 저장했습니다 — ▶ 강의 플레이로 바로 확인해 보세요.
        </div>
      )}

      <div className="flex-1 min-h-0 flex">
        {/* 왼쪽: 슬라이드 — 녹음 중엔 손이, 재생 중엔 타임라인이 넘긴다 */}
        <div className="flex-1 min-w-0 flex items-center justify-center bg-black p-4">
          {slide && sid ? (
            <img
              src={`${api.slidePngUrl(lectureId, sid)}?v=${encodeURIComponent(slide.updated_at ?? '')}`}
              alt={slide.title ?? sid}
              className="max-w-full max-h-full object-contain"
            />
          ) : (
            <div className="text-stone-500">
              {sid ? '이 슬라이드는 지워졌습니다' : '슬라이드가 없습니다'}
            </div>
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
            {inPlayback
              ? 'space 재생·정지 · ← → 구간 이동 · esc 재생만 멈춤'
              : '← → 로 넘기세요. 넘긴 시각이 그대로 영상의 장면 경계가 됩니다.'}
          </div>
        </div>
      </div>

      {/* 재생 바 — 재생을 한 번이라도 시작했을 때만 나온다 */}
      {inPlayback && (
        <div className="border-t border-stone-700 bg-stone-800 px-5 py-3 flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlay}
              className="w-9 h-9 rounded-full bg-stone-100 text-stone-900 hover:bg-white text-base leading-none"
              title={playing ? '정지 (space)' : '재생 (space)'}
            >
              {playing ? '❚❚' : '▶'}
            </button>
            <span className="font-mono text-sm tabular-nums">{mmss(cur)}</span>
            <input
              type="range"
              min={0}
              max={total || 1}
              step={0.01}
              value={Math.min(cur, total)}
              onChange={(e) => seek(Number(e.target.value))}
              className="flex-1 accent-stone-100"
            />
            <span className="font-mono text-sm tabular-nums text-stone-400">{mmss(total)}</span>
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {segs.map((s, i) => (
              <button
                key={`${s.slideId}-${i}`}
                onClick={() => seek(s.start)}
                title={`${mmss(s.start)} — ${deck.slides[s.slideId]?.title ?? s.slideId}`}
                className={`shrink-0 px-2.5 py-1 rounded text-xs border ${
                  i === segIdx
                    ? 'bg-stone-100 text-stone-900 border-stone-100'
                    : 'border-stone-600 text-stone-300 hover:bg-stone-700'
                }`}
              >
                {i + 1}. {mmss(s.start)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// 헤더에 붙는 두 버튼 (강의 플레이는 녹음 창 안으로 갔다)
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
      setError('렌더 시작 실패: ' + msg(e));
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
          ? '녹음 창을 엽니다 — 저장된 녹음을 재생해 확인하거나 다시 녹음할 수 있습니다'
          : '슬라이드를 보며 실제 강의를 녹음합니다'}
        className="px-3 py-1.5 rounded border border-stone-300 hover:bg-stone-100 text-sm text-stone-700"
      >
        🎙 {hasRec ? '녹음 창 열기' : '나레이션 녹음'}
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
          rec={rec}
          onClose={() => setOpen(false)}
          onSaved={refresh}
        />
      )}
    </div>
  );
}
