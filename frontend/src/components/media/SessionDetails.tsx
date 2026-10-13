/** Session detail drawer: path (direct/relay), receive state, quality numbers. No ICE/SDP/token internals. */
import type { MediaPath, MediaSession, Quality } from '../../lib/media/types';
import type { EngineState } from '../../lib/media/engine';

const PATH_LABEL: Record<string, string> = { direct: '직접 연결', relay: '중계(TURN)' };
const ENGINE_LABEL: Record<string, string> = {
  none: '엔진 없음', new: '준비', connecting: '연결 중', active: '수신 중', reconnecting: '재연결 중', failed: '실패', closed: '닫힘',
};

export function SessionDetails({ session, path, quality, engineState, socketOpen, remoteFrames, onClose }: {
  session: MediaSession | null; path: MediaPath; quality: Quality; engineState: EngineState | 'none'; socketOpen: boolean;
  remoteFrames: boolean; onClose: () => void;
}) {
  const row = (label: string, value: string | number) => (
    <div className="flex justify-between gap-3 border-b border-white/10 py-1.5" key={label}>
      <dt className="text-stone-400">{label}</dt><dd className="text-right text-white">{value}</dd>
    </div>
  );
  const receive = engineState === 'active' ? (remoteFrames ? '수신 중 · 출력 확인됨' : '연결됨 · 아직 출력 없음')
    : engineState === 'reconnecting' ? '재연결 중 · 멈춤' : ENGINE_LABEL[engineState] ?? engineState;
  return (
    <aside aria-label="세션 상세" className="flex w-72 shrink-0 flex-col border-l border-white/10 bg-stone-950/95 p-4 text-xs">
      <div className="mb-2 flex items-center">
        <strong className="flex-1 text-sm text-white">세션 상세</strong>
        <button className="rounded border border-white/20 px-2 py-0.5 text-stone-300" onClick={onClose}>닫기</button>
      </div>
      <dl className="flex flex-col">
        {row('경로', path ? PATH_LABEL[path] : '아직 모름')}
        {row('수신 상태', receive)}
        {row('제어 통로', socketOpen ? '연결됨' : '끊김')}
        {row('세션 상태', session?.state ?? '-')}
        {row('왕복 시간', `${quality.rtt_ms} ms`)}
        {row('손실', `${(quality.loss * 100).toFixed(1)} %`)}
        {row('지터', `${quality.jitter_ms} ms`)}
        {row('비트레이트', `${quality.bitrate_kbps} kbps`)}
        {row('프레임', quality.width ? `${quality.width}×${quality.height} · ${quality.fps} fps` : '-')}
        {row('버린 프레임', quality.dropped)}
        {row('임대', session?.lease ? `${session.lease.lease_s}s · 확인 ${session.lease.keepalive_s}s · 복구 ${session.lease.reconnect_s}s` : '-')}
        {row('판본 · 세대', session ? `${session.revision} · ${session.generation}` : '-')}
      </dl>
      <p className="mt-3 text-[11px] leading-relaxed text-stone-500">왕복 시간은 체감 지연이 아닙니다. 실제 지연은 종단 측정으로 확인합니다.</p>
    </aside>
  );
}
