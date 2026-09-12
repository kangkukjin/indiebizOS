/** Nostr는 .iblpack의 운송 경로. 같은 등록 관문을 지난다. */
import { useState } from 'react';
import { X, Search, Download, Loader2 } from 'lucide-react';
import { api } from '../../../lib/api';
type SharedPackage = Awaited<ReturnType<typeof api.searchPackagesOnNostr>>['packages'][number];
export function ToolSearchDialog({ show, onClose }: { show: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [packages, setPackages] = useState<SharedPackage[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  if (!show) return null;
  const search = async () => {
    setBusy(true); setError(''); setMessage('');
    try { const result = await api.searchPackagesOnNostr(query || undefined, 30); setPackages(result.packages); if (!result.packages.length) setMessage('검색 결과가 없습니다.'); }
    catch (e) { setError(e instanceof Error ? e.message : '검색 실패'); }
    finally { setBusy(false); }
  };
  const receive = async (pkg: SharedPackage) => {
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await api.importVocabulary(new Blob([pkg.install], { type: 'text/plain' }));
      if (!result.success) throw new Error(result.message || '가져오기 실패');
      setMessage(result.status === 'already_owned' ? '이미 보유한 묶음입니다.' : `${pkg.name}을 레고박스에 넣었습니다. 내 어휘에서 깨울 수 있습니다.`);
      window.dispatchEvent(new Event('vocabulary-changed'));
    } catch (e) { setError(e instanceof Error ? e.message : '가져오기 실패'); }
    finally { setBusy(false); }
  };
  return <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape' && !busy) onClose(); }}>
    <div role="dialog" aria-modal="true" aria-labelledby="shared-vocabulary-title" className="bg-white rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col p-5 gap-4">
      <div className="flex items-center justify-between"><h2 id="shared-vocabulary-title" className="font-semibold">공유 어휘 찾기</h2><button onClick={onClose} disabled={busy} aria-label="공유 어휘 닫기"><X size={20} /></button></div>
      <p className="text-sm text-stone-500">Nostr에서 찾은 묶음을 내 레고박스에 보관합니다. 받은 코드의 실행은 깨운 뒤에 시작됩니다.</p>
      <form className="flex gap-2" onSubmit={e => { e.preventDefault(); void search(); }}><input autoFocus aria-label="공유 어휘 검색어" className="border rounded-lg p-2 flex-1 min-w-0" value={query} onChange={e => setQuery(e.target.value)} placeholder="필요한 어휘 찾기" /><button disabled={busy} className="px-3 border rounded-lg flex items-center gap-2">{busy ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />} 검색</button></form>
      {error && <p role="alert" className="text-red-700 text-sm break-words">{error}</p>}
      {message && <p role="status" className="text-emerald-800 text-sm">{message}</p>}
      <div className="overflow-y-auto space-y-3">{packages.map((pkg, i) => <article key={`${pkg.id}-${i}`} className="border rounded-lg p-4 space-y-2">
        <h3 className="font-medium">{pkg.name} <span className="text-xs text-stone-500">{pkg.version}</span></h3><p className="text-sm text-stone-600">{pkg.description}</p>
        <p className="text-xs text-stone-400 break-all">게시자 {pkg.author}</p>
        <button disabled={busy} onClick={() => void receive(pkg)} className="border rounded-lg px-3 py-2 text-sm flex items-center gap-2 disabled:opacity-40"><Download size={15} /> 레고박스에 넣기</button>
      </article>)}</div>
    </div>
  </div>;
}
