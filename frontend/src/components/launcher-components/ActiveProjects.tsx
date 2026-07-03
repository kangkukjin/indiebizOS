/**
 * ActiveProjects — 조종실 맨 윗줄 "액티브 프로젝트" 계기.
 *
 * 판단 기준 2층 (GET /nodes/active-work):
 *   · 칩(로스터) = started AgentRunner 가 있는 프로젝트 — 사용자가 직접 명령하려면 창을
 *     열어야 하고, 창을 닫으면 stop_all 로 비활성화되므로 "칩 = 창이 열려 당직 중".
 *   · 펄스 = 지금 실제로 요청을 처리 중인 곳(시스템 AI 는 처리 중일 때만 등장).
 * 이름을 클릭하면 연결된 대화창이 화면 맨앞으로 온다(이미 열려 있으면 focus, 없으면 생성):
 *   시스템 AI → openSystemAIWindow() / 프로젝트 → openProjectWindow(id, name).
 * dark cockpit: 당직도 작업도 없으면 흐린 '없음' 한 단어만.
 */
import { useEffect, useState } from 'react';

const API_BASE = 'http://127.0.0.1:8765';
const POLL_MS = 3000;

interface ActiveWorkItem {
  kind: 'system_ai' | 'project';
  project_id: string;
  project_name: string;
  agents: string[];
  busy: boolean;
  elapsed_sec: number;
}

function elapsedLabel(sec: number): string {
  if (sec < 60) return `${sec}초째`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분째`;
  return `${Math.floor(sec / 3600)}시간째`;
}

export function ActiveProjects() {
  const [items, setItems] = useState<ActiveWorkItem[]>([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/nodes/active-work`);
        if (!res.ok) throw new Error('active-work ' + res.status);
        const data = await res.json();
        if (alive) setItems(data.items || []);
      } catch {
        if (alive) setItems([]);
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  const open = (it: ActiveWorkItem) => {
    if (it.kind === 'system_ai') window.electron?.openSystemAIWindow?.();
    else window.electron?.openProjectWindow?.(it.project_id, it.project_name);
  };

  return (
    <div className="flex items-center gap-2 text-[12px] flex-wrap select-none">
      <span className="text-stone-400 shrink-0">액티브 프로젝트 :</span>
      {items.length === 0 ? (
        <span className="text-stone-300">없음</span>
      ) : (
        items.map((it) => (
          <button
            key={it.kind === 'system_ai' ? 'system_ai' : it.project_id}
            onClick={() => open(it)}
            title={
              (it.agents.length ? `${it.agents.join(', ')} · ` : '') +
              (it.busy ? `${elapsedLabel(it.elapsed_sec)} 작업 중` : '대기 중') +
              ' — 클릭하면 대화창을 맨앞으로'
            }
            className={`px-2 py-0.5 rounded-full border transition flex items-center gap-1.5 ${
              it.busy
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                : 'border-stone-200 bg-white/70 text-stone-600 hover:bg-white'
            }`}
          >
            <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
              {it.busy && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              )}
              <span
                className={`relative inline-flex h-1.5 w-1.5 rounded-full ${
                  it.busy ? 'bg-emerald-500' : 'bg-emerald-400/70'
                }`}
              />
            </span>
            {it.project_name}
          </button>
        ))
      )}
    </div>
  );
}
