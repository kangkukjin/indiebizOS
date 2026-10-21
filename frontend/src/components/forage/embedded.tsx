import { useEffect, useRef, useState } from 'react';
import { EmbeddedTabLifecycle, type EmbeddedState as State } from './embeddedLifecycle';

type Bridge = {
  embeddedBrowserUI?: (action: string, id?: string, contentsId?: number) => Promise<any>;
  onEmbeddedBrowserChanged?: (callback: () => void) => (() => void);
};
export const embeddedAPI = () => (window.electron || {}) as Bridge;

export function useEmbeddedTabs(options: {
  panelOpen: boolean; show: () => void; hide: () => void;
  openTab: (url: string, id: string) => void; removeTabs: (ids: string[]) => void;
}) {
  const callback = useRef(options); callback.current = options;
  const lifecycle = useRef(new EmbeddedTabLifecycle());
  useEffect(() => {
    const api = embeddedAPI(); let live = true; let running = false; let dirty = false;
    const sync = async () => {
      if (running) { dirty = true; return; }
      if (!api.embeddedBrowserUI) return;
      running = true;
      try {
        do {
          dirty = false;
          const rows: State[] = await api.embeddedBrowserUI('list');
          if (!live || !Array.isArray(rows)) return;
          const actions = lifecycle.current.sync(rows, callback.current.panelOpen);
          if (actions.removed.length) callback.current.removeTabs(actions.removed);
          if (actions.added.length) callback.current.show();
          for (const r of actions.added) callback.current.openTab(r.url!, r.id);
          if (actions.close) callback.current.hide();
        } while (dirty && live);
      } catch { /* unavailable on web or old desktop */ }
      finally { running = false; }
    };
    const dispose = api.onEmbeddedBrowserChanged?.(sync); void sync();
    return () => { live = false; dispose?.(); };
  }, []);
  return () => lifecycle.current.retain();
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
