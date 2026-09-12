/** 내 어휘: 보유와 사용을 나누는 사람 전용 레고박스. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Boxes, Upload, Download, LockKeyhole, Moon, Search, Loader2, Settings2 } from 'lucide-react';
import { api } from '../lib/api';
import { getBackendOrigin } from '../lib/backend-origin';
import type { VocabularyPackage } from '../lib/api-packages';
import { PackageDeveloperDialog } from './launcher-components/dialogs/PackageDeveloperDialog';
import { ToolSearchDialog } from './launcher-components/dialogs/ToolSearchDialog';

export function VocabularyView() {
  const [packages, setPackages] = useState<VocabularyPackage[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'active' | 'sleeping'>('all');
  const [advanced, setAdvanced] = useState(false);
  const [search, setSearch] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const reload = useCallback(async () => {
    setLoading(true);
    try { setPackages((await api.getVocabulary()).packages); }
    catch (e) { setError(e instanceof Error ? e.message : '어휘를 불러오지 못했습니다.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  const run = async (id: string, action: () => Promise<void>) => {
    if (busy) return;
    setBusy(id); setError(''); setMessage('');
    try { await action(); }
    catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했습니다.'); }
    finally { setBusy(null); }
  };
  const receive = (file?: File) => {
    if (!file) return;
    void run('import', async () => {
      if (file.size > 20 * 1024 * 1024) throw new Error('어휘 파일은 최대 20MB입니다.');
      const result = await api.importVocabulary(file);
      if (!result.success) throw new Error(result.message || '가져오기 실패');
      setMessage(result.status === 'already_owned' ? '이미 레고박스에 있는 묶음입니다.' : `${result.package_id}를 넣었습니다. 사용할 때 깨워 주세요.`);
      await reload();
      window.dispatchEvent(new Event('vocabulary-changed'));
    });
  };
  const download = (pkg: VocabularyPackage) => void run(pkg.id, async () => {
    const response = await fetch(`${await getBackendOrigin()}/vocabulary/${encodeURIComponent(pkg.id)}/export`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || '파일을 만들지 못했습니다.');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url; link.download = `${pkg.id}.iblpack`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage(`${pkg.name} 파일을 만들었습니다.`);
  });
  const activeCount = packages.filter(p => p.installed).length;
  const shown = packages.filter(p => (filter === 'all' || (filter === 'active') === p.installed)
    && `${p.name} ${p.description} ${p.id}`.toLowerCase().includes(query.toLowerCase()));
  const button = 'inline-flex items-center justify-center gap-2 rounded-lg border border-stone-200 px-3 py-2 text-sm hover:bg-stone-100 disabled:opacity-40';
  return <section aria-labelledby="vocabulary-title" className="h-full overflow-y-auto bg-[#faf8f4] text-stone-800" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); receive(e.dataTransfer.files[0]); }}>
    <div className="w-full max-w-6xl min-h-full mx-auto flex flex-col">
      <div className="p-5 border-b border-stone-200">
        <div className="flex items-start justify-between gap-4">
          <div><h2 id="vocabulary-title" className="text-xl font-semibold flex items-center gap-2"><Boxes size={23} /> 내 어휘</h2>
            <p className="text-sm text-stone-500 mt-1">내 레고박스에서 이 몸이 쓸 어휘를 골라 주세요.</p></div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-sm mr-auto">보유 {packages.length} · 사용 중 {activeCount} · 잠듦 {packages.length - activeCount}</span>
          <input ref={fileInput} type="file" accept=".iblpack,.txt" className="hidden" onChange={e => { receive(e.target.files?.[0]); e.target.value = ''; }} />
          <button className={button} disabled={!!busy} onClick={() => fileInput.current?.click()}><Upload size={16} /> 파일 가져오기</button>
          <button className={button} disabled={!!busy} onClick={() => setSearch(true)}><Search size={16} /> 공유 어휘 찾기</button>
          <button className={button} disabled={!!busy} onClick={() => setAdvanced(true)} aria-label="제작 및 라이브러리 관리"><Settings2 size={16} /></button>
        </div>
        <p className="mt-3 text-xs text-stone-500">잠재우면 AI의 어휘 소개·실행용 회상·새 호출에서 빠집니다. 파일과 기억은 남습니다.</p>
      </div>
      <div className="px-5 pt-4 space-y-3">
        {error && <p role="alert" className="p-3 rounded-lg bg-red-50 text-red-700 text-sm break-words">{error}</p>}
        {message && <p role="status" className="p-3 rounded-lg bg-emerald-50 text-emerald-800 text-sm">{message}</p>}
        <div className="flex flex-wrap gap-2">
          <input aria-label="내 어휘 검색" placeholder="이름이나 하는 일로 찾기" value={query} onChange={e => setQuery(e.target.value)} className="min-w-0 flex-1 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm" />
          {(['all', 'active', 'sleeping'] as const).map((key, i) => <button key={key} aria-pressed={filter === key} className={`${button} ${filter === key ? 'bg-stone-200 font-medium' : ''}`} onClick={() => setFilter(key)}>{['전체', '사용 중', '잠듦'][i]}</button>)}
        </div>
      </div>
      <div className="p-5 grid sm:grid-cols-2 xl:grid-cols-3 gap-3" aria-busy={loading || !!busy}>
        {loading && packages.length === 0 && <p className="text-sm flex gap-2"><Loader2 className="animate-spin" size={16} /> 어휘를 불러오는 중</p>}
        {!loading && !shown.length && <p className="text-sm text-stone-500">해당하는 어휘가 없습니다. 파일을 끌어 놓아 레고박스에 넣을 수 있습니다.</p>}
        {shown.map(pkg => <article key={pkg.id} className={`rounded-xl border p-4 flex flex-col gap-3 ${pkg.installed ? 'bg-white border-emerald-200' : 'bg-stone-100/60 border-stone-200'}`}>
          <div className="flex items-start gap-2 justify-between"><div className="min-w-0"><h3 className="font-medium break-words">{pkg.name}</h3><span className="text-xs text-stone-500">{pkg.version || pkg.id}</span></div>
            <span className="shrink-0 text-xs flex items-center gap-1">{pkg.required ? <><LockKeyhole size={13} /> 필수</> : pkg.installed ? '● 사용 중' : <><Moon size={13} /> 잠듦</>}</span></div>
          <p className="text-sm text-stone-600 flex-1 break-words line-clamp-3" title={pkg.description}>{pkg.description.split("##")[0]}</p>
          {pkg.preparation?.length > 0 && <p className="text-xs text-amber-800">{pkg.preparation.join(' · ')}</p>}
          <div className="flex items-center justify-between gap-2">
            <button className={button} disabled={!!busy || pkg.required} onClick={() => download(pkg)} aria-label={`${pkg.name} 파일 내보내기`}><Download size={15} /> 내보내기</button>
            <button role="switch" aria-checked={pkg.installed} aria-label={`${pkg.name} 사용`} disabled={!!busy || pkg.required || (!pkg.installed && !!pkg.preparation?.length)} className={`${button} ${pkg.installed ? 'text-emerald-800 border-emerald-300' : ''}`} onClick={() => void run(pkg.id, async () => {
              const result = await api.setVocabularyActive(pkg.id, !pkg.installed);
              if (!result.success) throw new Error(result.message || '선택 변경 실패');
              setMessage(`${pkg.name}: ${result.message || '변경했습니다.'}`);
              await reload(); window.dispatchEvent(new Event('vocabulary-changed'));
            })}>{busy === pkg.id ? <Loader2 className="animate-spin" size={15} /> : pkg.required ? '항상 사용' : pkg.installed ? '잠재우기' : '깨우기'}</button>
          </div>
        </article>)}
      </div>
      <div className="mt-auto px-5 py-3 border-t border-stone-200 text-xs text-stone-500">받은 어휘는 잠든 상태로 들어옵니다. 선택은 이 몸에만 적용됩니다. 실행 중인 작업은 계속됩니다.</div>
    </div>
    <PackageDeveloperDialog show={advanced} onClose={() => { setAdvanced(false); void reload(); }} />
    <ToolSearchDialog show={search} onClose={() => { setSearch(false); void reload(); }} />
  </section>;
}
