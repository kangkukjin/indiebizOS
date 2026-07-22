/**
 * SystemAIView - 시스템 AI 풀페이지 채팅 뷰
 *
 * 에이전트 Chat과 동일한 풀페이지 레이아웃으로 시스템 AI와 대화합니다.
 * 계기판의 "분석 스위치"가 localStorage(indiebiz_analyze_episode)에 남긴 요청을 읽어,
 * 그 지난 주행의 분석 요청 프롬프트를 백엔드에서 받아 첫 메시지로 자동 전송한다.
 * (메인 프로세스를 안 거쳐서 Electron 재시작 없이 작동)
 */
import { useEffect, useState } from 'react';
import { ChatView } from './chat/ChatView';

const API_BASE = 'http://127.0.0.1:8765';
const PENDING_KEY = 'indiebiz_analyze_episode';
const FRESH_MS = 15000;  // 이 시간 안의 요청만 처리(옛 값으로 재발동 방지)

export function SystemAIView() {
  const [initialMessage, setInitialMessage] = useState<string | undefined>();
  const [initialLabel, setInitialLabel] = useState<string | undefined>();

  // 존재 하트비트 — 이 창이 열려 있는 동안 조종실 '액티브 프로젝트'에 System AI 가 뜨게 한다
  // (창 열림=활성). 닫힘/이탈 시 즉시 부재(open:false) + 하트비트 중단으로 TTL 만료 → 사라짐.
  useEffect(() => {
    const ping = (open: boolean) => {
      try {
        fetch(`${API_BASE}/system-ai/presence`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ open }),
          keepalive: true,
        }).catch(() => {});
      } catch { /* noop */ }
    };
    ping(true);
    const timer = setInterval(() => ping(true), 3000);
    const onHide = () => ping(false);
    window.addEventListener('pagehide', onHide);
    return () => {
      clearInterval(timer);
      window.removeEventListener('pagehide', onHide);
      ping(false);
    };
  }, []);

  useEffect(() => {
    const fetchPrompt = (id: number) => {
      fetch(`${API_BASE}/world-pulse/episodes/${id}/analysis-prompt`)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
        .then((data) => {
          if (data?.prompt) {
            setInitialMessage(data.prompt);
            setInitialLabel(`🚗 지난 주행 #${id} 분석 요청`);
          }
        })
        .catch(() => {
          setInitialMessage(`지난 주행(#${id})을 분석하려 했지만 기록을 불러오지 못했습니다. 로그가 만료됐을 수 있습니다.`);
          setInitialLabel(`🚗 지난 주행 #${id} 분석 요청`);
        });
    };

    // 대기 중인 분석 요청을 소비(읽고 즉시 제거 → 중복/재발동 방지)
    const consumePending = () => {
      let raw: string | null = null;
      try { raw = localStorage.getItem(PENDING_KEY); } catch { return; }
      if (!raw) return;
      let parsed: { id?: number; ts?: number } | null = null;
      try { parsed = JSON.parse(raw); } catch { parsed = null; }
      try { localStorage.removeItem(PENDING_KEY); } catch { /* noop */ }
      if (!parsed || parsed.id == null) return;
      if (Date.now() - (parsed.ts || 0) > FRESH_MS) return;  // 오래된 요청 무시
      fetchPrompt(parsed.id);
    };

    // 1) 새 창: 마운트 시 이미 쌓인 요청을 읽는다.
    consumePending();
    // 2) 이미 열린 창: 런처가 새로 쓰면 storage 이벤트로 받는다.
    const onStorage = (e: StorageEvent) => {
      if (e.key === PENDING_KEY && e.newValue) consumePending();
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <ChatView
        chatTarget={{ type: 'system_ai' }}
        layout="fullpage"
        initialMessage={initialMessage}
        initialMessageLabel={initialLabel}
      />
    </div>
  );
}
