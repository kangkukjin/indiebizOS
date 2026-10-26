/**
 * ControllerPresence — 재기동 제어자 부재 경고등 (조종실 '시스템 상태' 접힌 줄)
 *
 * 2026-10-26: 제어자(pid 39960)가 소리 없이 죽고 워커만 살아 있어 편집 재기동·restart 요청이
 * 5시간 접수함에 머물렀다. 워커의 `/health` 가 `restart_controller.verdict` 로 그 상태를 드러내므로
 * 여기서는 `controller_missing` 일 때만 한 줄을 켠다(정상·불명은 숨김 — 평소엔 아무것도 없다).
 */
import { BACKEND_ORIGIN } from '../../lib/backend-origin';
import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

const POLL_MS = 20000;

interface ControllerHealth {
  verdict: string;
  controller?: { pid?: number } | null;
  state_age_s?: number | null;
}

export function ControllerPresence() {
  const [info, setInfo] = useState<ControllerHealth | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch(`${BACKEND_ORIGIN}/health`);
        if (!res.ok) throw new Error('health ' + res.status);
        const data = await res.json();
        if (alive) setInfo(data.restart_controller ?? null);
      } catch {
        if (alive) setInfo(null);
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  if (!info || info.verdict !== 'controller_missing') return null;

  const pid = info.controller?.pid;
  const age = info.state_age_s != null ? `${Math.round(info.state_age_s / 60)}분` : '?';
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-normal px-2 py-0.5 rounded shrink-0 text-amber-700 bg-amber-50"
      title={`재기동 제어자(pid ${pid ?? '?'})가 죽어 있습니다. 상태 갱신이 ${age} 전에 멈췄고 편집 재기동·restart 요청은 처리되지 않습니다. 런처가 15초 안에 되살리며, 수동 복구는 backend/api.py start 입니다.`}
    >
      <AlertTriangle size={12} className="shrink-0" />
      제어자 부재 · 재기동 요청 미처리
    </span>
  );
}
