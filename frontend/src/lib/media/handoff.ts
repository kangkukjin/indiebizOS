import type { MediaSession } from './types.ts';

type Player = Pick<HTMLMediaElement, 'currentSrc' | 'currentTime' | 'volume' | 'paused' | 'pause'>;
interface Transport {
  create(body: { kind: 'extension'; purpose: 'playback'; delivery: 'content'; target: string; request_id: string;
    content: { url: string; position_s: number; volume: number } }): Promise<MediaSession>;
  status(id: string): Promise<MediaSession>;
  end(id: string, reason: string): Promise<unknown>;
}
/** The source remains audible until the target confirms playback. Failure rolls back only the target. */
export async function handoff(player: Player, target: string, transport: Transport,
  options: { timeoutMs?: number; pollMs?: number; signal?: AbortSignal } = {}): Promise<MediaSession> {
  const source = player.currentSrc;
  if (!/^https?:\/\//.test(source)) throw new Error('이 소스는 직접 전달할 수 없습니다. 파일 재생 또는 소리 보내기를 사용해 주세요.');
  const initial = await transport.create({ kind: 'extension', purpose: 'playback', delivery: 'content', target,
    request_id: crypto.randomUUID(), content: { url: source, position_s: player.currentTime, volume: Math.round(player.volume * 100) } });
  const deadline = Date.now() + (options.timeoutMs ?? 20000);
  try {
    while (Date.now() < deadline) {
      if (options.signal?.aborted || player.currentSrc !== source) throw new Error('재생 이동이 취소되었습니다.');
      const current = await transport.status(initial.session_id);
      if (current.state === 'ended') throw new Error(current.error?.message || current.end_reason || '장치 재생에 실패했습니다.');
      if (current.content?.playing) { player.pause(); return current; }
      await new Promise(resolve => setTimeout(resolve, options.pollMs ?? 250));
    }
    throw new Error('장치의 재생 확인이 없어 원본 재생을 유지했습니다.');
  } catch (e) {
    await transport.end(initial.session_id, 'handoff_cancelled').catch(() => {});
    throw e;
  }
}
