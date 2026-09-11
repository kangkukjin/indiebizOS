import { useEffect, useState } from 'react';
import { BACKEND_ORIGIN } from '../../lib/backend-origin';
import { checkRemoteSession } from '../../lib/remote-session';
import { openExternalLink } from '../../lib/surface-navigation';
import type { Tab } from './support';

/** 브라우저 표면의 탐색기. 교차 출처 프레임의 DOM/실제 이동 기록을 읽을 수 있다고 가장하지 않는다. */
export function RemoteBrowserTab({ tab, onUpdate, registerRef }: {
  tab: Tab;
  onUpdate: (id: string, patch: Partial<Tab>) => void;
  registerRef: (id: string, el: any) => void;
}) {
  const [url, setUrl] = useState(tab.initialUrl);
  const [revision, setRevision] = useState(0);
  const [verdict, setVerdict] = useState<{ framable: boolean; reason: string } | null>(null);
  useEffect(() => {
    registerRef(tab.id, {
      loadURL: (next: string) => { setUrl(next); setRevision(n => n + 1); },
      reload: () => setRevision(n => n + 1),
      getURL: () => url,
      getTitle: () => url,
    });
    return () => registerRef(tab.id, null);
  }, [tab.id, url, registerRef]);

  useEffect(() => {
    const controller = new AbortController();
    setVerdict(null);
    onUpdate(tab.id, { url, title: url, loading: true, canBack: false, canFwd: false });
    let parsed: URL;
    try { parsed = new URL(url); } catch { parsed = new URL('about:blank'); }
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      setVerdict({ framable: false, reason: 'http(s) 주소만 열 수 있습니다.' });
      onUpdate(tab.id, { loading: false });
    } else if (parsed.origin === BACKEND_ORIGIN) {
      setVerdict({ framable: true, reason: '' });
    } else {
      fetch(`${BACKEND_ORIGIN}/launcher/framable?url=${encodeURIComponent(url)}`, { signal: controller.signal })
        .then(async res => {
          checkRemoteSession(res.status);
          if (!res.ok) throw new Error('표시 여부를 확인하지 못했습니다.');
          return res.json();
        }).then(result => {
          if (controller.signal.aborted) return;
          setVerdict(result);
          if (!result.framable) onUpdate(tab.id, { loading: false });
        }).catch(() => {
          if (controller.signal.aborted) return;
          // 탐침 실패는 차단 판정이 아니다. 실제 브라우저 정책에 맡기며 새 탭은 항상 제공한다.
          setVerdict({ framable: true, reason: '' });
        });
    }
    return () => controller.abort();
  }, [tab.id, url, revision, onUpdate]);

  return <div className="flex flex-col h-full bg-white">
    <div className="shrink-0 px-3 py-2 text-sm border-b flex gap-3 items-center">
      <span className="text-stone-500 truncate">표시가 안 되거나 페이지 안에서 이동한 주소가 필요하면 새 탭으로 여세요.</span>
      <button onClick={() => openExternalLink(url)} className="shrink-0 underline">새 탭으로 열기</button>
    </div>
    {!verdict ? <p className="p-6 text-stone-500">표시 확인 중…</p>
      : !verdict.framable ? <p className="p-6 text-stone-600">이 페이지는 앱 안에 표시할 수 없습니다. {verdict.reason}</p>
      : <iframe key={`${url}:${revision}`} title="검색 페이지" src={url}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"
          className="flex-1 min-h-0 w-full border-0" onLoad={() => onUpdate(tab.id, { loading: false })} />}
  </div>;
}
