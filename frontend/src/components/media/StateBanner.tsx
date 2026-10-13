/** Session state as a human sentence. `reconnecting` dims the stage so a frozen frame never reads as live. */
import type { UiState } from './use-media-session';
import type { MediaSession } from '../../lib/media/types';

const LABELS: Record<string, string> = {
  loading: '세션을 불러오는 중…',
  inviting: '초대를 보내는 중…',
  ringing: '상대를 부르는 중…',
  accepted: '수락됨 · 연결 준비 중…',
  authorized: '장치 허가됨 · 연결 준비 중…',
  connecting: '연결 중…',
  active: '',
  reconnecting: '연결이 끊겨 다시 연결하는 중… 화면은 멈춘 상태입니다',
  needs_local_action: '장치에서 할 일이 있습니다',
  ended: '통화가 끝났습니다',
  error: '오류',
};

const END_REASONS: Record<string, string> = {
  local_end: '내가 종료했습니다', remote_end: '상대가 종료했습니다', rejected: '상대가 거절했습니다',
  busy: '상대가 통화 중입니다', invite_expired: '응답이 없어 초대가 만료됐습니다', connectivity_failed: '연결을 복구하지 못했습니다',
  lease_expired: '연결 확인이 끊겨 종료됐습니다', relation_revoked: '확장관계가 해제되어 종료됐습니다', device_offline: '장치가 오프라인입니다',
  window_closed: '창을 닫아 종료했습니다', session_ended: '이미 끝난 세션입니다',
};

export function describeEnd(reason: string): string {
  if (!reason) return '';
  return END_REASONS[reason] ?? reason;
}

export function StateBanner({ state, session, error, endReason, onRetry }: {
  state: UiState; session: MediaSession | null; error: string | null; endReason: string; onRetry?: () => void;
}) {
  if (state === 'active' && !error) return null;
  const needs = session?.needs_local_action;
  const text = state === 'error' ? (error || '오류가 발생했습니다')
    : state === 'needs_local_action' ? (needs?.message || LABELS.needs_local_action)
    : state === 'ended' ? [LABELS.ended, describeEnd(endReason)].filter(Boolean).join(' · ')
    : LABELS[state] ?? state;
  const tone = state === 'error' ? 'bg-red-900/90' : state === 'reconnecting' ? 'bg-amber-900/90' : 'bg-stone-900/90';
  return (
    <div role="status" aria-live="polite" className={`pointer-events-auto rounded-lg px-5 py-3 text-center text-sm text-white shadow ${tone}`}>
      <p>{text}</p>
      {error && state !== 'error' && <p className="mt-1 text-xs text-red-200">{error}</p>}
      {state === 'needs_local_action' && needs?.code && <p className="mt-1 text-xs text-stone-300">코드 {needs.code}</p>}
      {state === 'ended' && onRetry && <button className="mt-2 rounded border border-white/30 px-3 py-1 text-xs" onClick={onRetry}>닫기</button>}
    </div>
  );
}
