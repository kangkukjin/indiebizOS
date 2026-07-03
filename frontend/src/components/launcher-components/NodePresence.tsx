/**
 * NodePresence — 다른 몸(피어)의 연결상태 계기등 (계기판 안에 표기)
 *
 * 몸-인식 단일 엔드포인트 `GET /nodes/peer-status` 를 폴링한다(각 백엔드가 자기 피어를 안다):
 *   · 맥 계기판 → 연결된 폰을 표시(허브 라이브 테이블).
 *   · 폰 계기판 → 맥(집 PC)을 표시(맥 /ping 핑). ※폰은 웹런처라 이 컴포넌트가 아닌
 *     api_launcher_web.py HTML 이 같은 엔드포인트를 그려준다.
 *
 * "지금 믿고 맡길까"를 판단하려면 연락할 몸이 살아있는지부터 보여야 한다.
 */
import { useEffect, useState } from 'react';
import { Smartphone } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8765';
const POLL_MS = 20000;

interface PeerStatus {
  has_peer: boolean;
  peer_name: string;
  online: boolean;
  detail?: string | null;
}

export function NodePresence() {
  const [peer, setPeer] = useState<PeerStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/nodes/peer-status`);
        if (!res.ok) throw new Error('peer-status ' + res.status);
        const data = await res.json();
        if (alive) setPeer(data);
      } catch {
        if (alive) setPeer(null);
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  if (!peer) return null;  // 첫 로드 전/조회 실패 시 숨김

  const online = peer.has_peer && peer.online;
  const name = peer.peer_name || '다른 몸';
  const statusText = !peer.has_peer ? '미연동' : (peer.online ? '연결됨' : '오프라인');
  const title = peer.detail || (online ? `${name} 연결됨` : `${name} ${statusText}`);

  // 루트가 span(inline-flex)인 이유: 조종실 '시스템 상태' 접힌 줄(button 요소) 안에
  // IBL 배지와 나란히 들어가므로 phrasing content 여야 한다.
  return (
    <span className="inline-flex items-center gap-2 text-[12px] font-normal select-none" title={title}>
      <span className="relative flex h-2 w-2" aria-hidden="true">
        {online && (
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
        )}
        <span
          className={`relative inline-flex h-2 w-2 rounded-full ${online ? 'bg-emerald-500' : 'bg-stone-300'}`}
        />
      </span>
      <Smartphone size={13} className={online ? 'text-stone-600' : 'text-stone-400'} />
      <span className={online ? 'text-stone-700' : 'text-stone-400'}>{name}</span>
      <span className={online ? 'text-emerald-600' : 'text-stone-400'}>· {statusText}</span>
    </span>
  );
}
