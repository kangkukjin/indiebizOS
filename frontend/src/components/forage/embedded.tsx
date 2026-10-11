import { useEffect, useRef, useState } from 'react';

type State = { id: string; url?: string; pending: boolean; state: string; controlled: boolean };
type Bridge = {
  embeddedBrowserUI?: (action: string, id?: string, contentsId?: number) => Promise<any>;
  onEmbeddedBrowserChanged?: (callback: () => void) => (() => void);
};
export const embeddedAPI = () => (window.electron || {}) as Bridge;

export function useEmbeddedTabs(open: (url: string, id: string) => void) {
  const callback = useRef(open); callback.current = open;
  const opened = useRef(new Set<string>());
  useEffect(() => {
    const api = embeddedAPI(); let live = true;
    const sync = async () => {
      try {
        const rows: State[] = await api.embeddedBrowserUI?.('list') || [];
        if (!live) return;
        for (const r of rows) if (r.pending && r.url && !opened.current.has(r.id)) {
          opened.current.add(r.id); callback.current(r.url, r.id);
        }
      } catch { /* unavailable on web or old desktop */ }
    };
    const dispose = api.onEmbeddedBrowserChanged?.(sync); void sync();
    return () => { live = false; dispose?.(); };
  }, []);
}

export function EmbeddedTabControl({ id }: { id: string }) {
  const [state, setState] = useState<State | null>(null);
  useEffect(() => {
    let live = true; const api = embeddedAPI();
    const sync = async () => {
      try { const rows: State[] = await api.embeddedBrowserUI?.('list') || [];
        if (live) setState(rows.find(r => r.id === id) || null);
      } catch { /* no bridge */ }
    };
    const dispose = api.onEmbeddedBrowserChanged?.(sync); void sync();
    return () => { live = false; dispose?.(); };
  }, [id]);
  if (!state) return null;
  return <div className="absolute right-3 bottom-3 z-20 flex gap-3 items-center rounded-lg bg-white border border-stone-300 px-3 py-2 text-xs shadow">
    <span>{state.state || '직접 탐색 중'}</span>
    <button className="text-blue-700" onClick={() => void embeddedAPI().embeddedBrowserUI?.(state.controlled ? 'pause' : 'share', id)}>
      {state.controlled ? 'AI 중지' : '이 탭을 AI에 맡기기'}
    </button>
  </div>;
}
