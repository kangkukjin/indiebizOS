import { useEffect, useState } from 'react';
import { documentCommand, documentRequest, type Detail } from '../lib/api-documents';

/** Recovery stays inside the open dialog, leaving the current editor mounted. */
export function DocumentOpenRecovery({ error, path, onReady, onError }: {
  error: string; path?: string; onReady: (detail: Detail) => Promise<void>; onError: (error: string) => void;
}) {
  const [source, setSource] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let dead = false;
    if (path && error.includes('working_copy_choice')) {
      documentRequest<Detail>('/open', 'POST', { path, conversion: 'source' })
        .then(d => { if (!dead) setSource(d); }, e => { if (!dead) onError(String(e)); });
    }
    return () => { dead = true; };
  }, [path, error]); // eslint-disable-line react-hooks/exhaustive-deps
  return <>
    {/engine_unreachable|engine_unconfigured|conversion_timeout/.test(error) && <button disabled={busy} onClick={async () => {
      setBusy(true);
      try { await documentRequest('/engine/start', 'POST'); onError('편집 서버를 시작했습니다. 열기를 다시 누르세요.'); }
      catch (e) { onError(String(e)); }
      finally { setBusy(false); }
    }}>편집 서버 시작</button>}
    {source?.conversion_candidates?.map(candidate => <button key={candidate.resource} disabled={busy} onClick={async () => {
      setBusy(true);
      try { await onReady(await documentCommand<Detail>(source.document.id, 'open-copy', { working_resource: candidate.resource })); }
      catch (e) { onError(String(e)); }
      finally { setBusy(false); }
    }}>이 사본 이어 열기: {candidate.path}</button>)}
  </>;
}
