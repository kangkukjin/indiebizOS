/**
 * GuidesView — 가이드 파일 (안경 메뉴 → 독립 창, 웹은 #/guides)
 *
 * data/guides/*.md 전체 목록을 등록(guide_db.json)·신선도(guide_registry: 작성·최종수정·
 * 무수정 사용·마지막 검토)·예산(lifecycle_policy guide_budget_bytes)·표식(lifecycle candidate)과
 * 함께 보이고, 고르면 본문을 렌더/원문으로 읽고 고쳐 저장한다. 백엔드 /guides/*.
 * 폴더가 정본 — 등록만 있고 파일이 없는 것, 파일만 있고 등록이 없는 것을 숨기지 않는다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Search, RefreshCw, Pencil, Save, X, AlertTriangle, Eye, Code } from 'lucide-react';
import { ToolWindowFrame } from './ToolWindowFrame';
import { api } from '../lib/api';
import { useRetryingLoad } from '../lib/use-retrying-load';
import type { GuideCatalog, GuideEntry } from '../lib/api-system-ai';

type SortKey = 'name' | 'bytes' | 'updated' | 'uses' | 'topic';

const kb = (n: number) => `${(n / 1024).toFixed(1)}KB`;
const ago = (d: number | null) => (d === null ? '—' : d === 0 ? '오늘' : `${d}일 전`);

export function GuidesView() {
  const [catalog, setCatalog] = useState<GuideCatalog | null>(null);
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('');
  const [sort, setSort] = useState<SortKey>('name');
  const [selected, setSelected] = useState<string>('');
  const [content, setContent] = useState<string>('');
  const [draft, setDraft] = useState<string>('');
  const [editing, setEditing] = useState(false);
  const [raw, setRaw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string>('');

  const loadCatalog = useCallback(async () => {
    setCatalog(await api.getGuides());
  }, []);
  const { retry } = useRetryingLoad(loadCatalog, { onFocus: true });

  const openGuide = useCallback(async (file: string) => {
    setSelected(file);
    setEditing(false);
    setNotice('');
    try {
      const r = await api.getGuide(file);
      setContent(r.content);
      setDraft(r.content);
    } catch (e) {
      setContent('');
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // 첫 목록이 오면 첫 항목을 연다
  useEffect(() => {
    if (catalog && !selected && catalog.guides[0]) openGuide(catalog.guides[0].file);
  }, [catalog, selected, openGuide]);

  const topics = useMemo(() => {
    const set = new Set<string>();
    for (const g of catalog?.guides || []) if (g.topic) set.add(g.topic);
    return Array.from(set).sort();
  }, [catalog]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = (catalog?.guides || []).filter((g) => !topic || g.topic === topic);
    if (q) {
      list = list.filter((g) =>
        [g.name, g.file, g.description, g.topic, ...(g.keywords || [])].join(' ').toLowerCase().includes(q));
    }
    const cmp: Record<SortKey, (a: GuideEntry, b: GuideEntry) => number> = {
      name: (a, b) => a.name.localeCompare(b.name, 'ko'),
      bytes: (a, b) => b.bytes - a.bytes,
      updated: (a, b) => (a.age_days ?? 1e9) - (b.age_days ?? 1e9),
      uses: (a, b) => b.clean_uses - a.clean_uses,
      topic: (a, b) => (a.topic || '').localeCompare(b.topic || '', 'ko') || a.name.localeCompare(b.name, 'ko'),
    };
    return [...list].sort(cmp[sort]);
  }, [catalog, query, topic, sort]);

  const current = catalog?.guides.find((g) => g.file === selected) || null;
  const budget = catalog?.budget_bytes || 36000;
  const unregistered = (catalog?.guides || []).filter((g) => !g.registered).length;
  const overBudget = (catalog?.guides || []).filter((g) => g.over_budget).length;

  const save = async () => {
    if (!current) return;
    setBusy(true);
    setNotice('');
    try {
      const r = await api.saveGuide(current.file, draft);
      setContent(draft);
      setEditing(false);
      setNotice(r.over_budget
        ? `저장됨 (${kb(r.bytes)}) — 예산 ${kb(r.budget_bytes)} 초과: 커밋 전 압축·분할이 필요합니다(삭제 금지).`
        : `저장됨 (${kb(r.bytes)})`);
      await loadCatalog();
    } catch (e) {
      setNotice('저장 실패: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ToolWindowFrame title="가이드 파일" icon={<FileText className="text-amber-600" size={20} />}
      actions={
        <button onClick={() => retry()} title="다시 읽기"
          className="p-1.5 rounded-lg text-stone-500 hover:bg-[#EAE4DA]"><RefreshCw size={15} /></button>
      }>
      <div className="flex-1 min-h-0 flex">
        {/* 목록 */}
        <div className="shrink-0 border-r border-[#E5DFD5] flex flex-col min-h-0 bg-white/60" style={{ width: 460 }}>
          <div className="px-3 py-2 border-b border-[#E5DFD5] space-y-2">
            <div className="text-[11px] text-stone-500">
              {catalog ? (
                <>
                  {catalog.guides.length}개 · 총 {kb(catalog.total_bytes)} · 파일당 예산 {kb(budget)}
                  {overBudget > 0 && <span className="text-red-600"> · 예산 초과 {overBudget}</span>}
                  {unregistered > 0 && <span className="text-amber-700"> · 미등록 {unregistered}</span>}
                  {catalog.missing_files.length > 0 && <span className="text-red-600"> · 등록만 있고 파일 없음 {catalog.missing_files.length}</span>}
                </>
              ) : '불러오는 중…'}
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-1.5 px-2 py-1 rounded-lg border border-stone-200 bg-white">
                <Search size={13} className="text-stone-400" />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="이름·설명·키워드 검색"
                  className="flex-1 text-sm focus:outline-none bg-transparent" />
              </div>
              <select value={topic} onChange={(e) => setTopic(e.target.value)}
                className="text-xs px-1.5 py-1 border border-stone-200 rounded-lg bg-white" style={{ maxWidth: 130 }}>
                <option value="">모든 주제</option>
                {topics.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}
                className="text-xs px-1.5 py-1 border border-stone-200 rounded-lg bg-white">
                <option value="name">이름순</option>
                <option value="topic">주제순</option>
                <option value="bytes">큰 것부터</option>
                <option value="updated">최근 수정</option>
                <option value="uses">무수정 사용</option>
              </select>
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {rows.map((g) => {
              const active = g.file === selected;
              const pct = Math.min(100, Math.round((g.bytes / budget) * 100));
              return (
                <button key={g.file} onClick={() => openGuide(g.file)}
                  className={`block w-full text-left px-3 py-2 border-b border-stone-100 transition-colors ${
                    active ? 'bg-amber-50' : 'hover:bg-amber-50/50'
                  }`}>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-[#4A4035] font-medium truncate">{g.name}</span>
                    <span className="text-[11px] text-stone-400 font-mono truncate">{g.file}</span>
                    {!g.registered && <span className="text-[10px] px-1 rounded bg-amber-100 text-amber-800 shrink-0">미등록</span>}
                    {g.lifecycle_candidate_since && <span className="text-[10px] px-1 rounded bg-stone-200 text-stone-600 shrink-0" title={`정리 후보 표식 ${g.lifecycle_candidate_since}`}>후보</span>}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-stone-500">
                    {g.topic && <span className="px-1.5 rounded-full bg-stone-100 text-stone-600">{g.topic}</span>}
                    <span className={g.over_budget ? 'text-red-600 font-semibold' : ''}>{kb(g.bytes)}</span>
                    <span title="최종수정">수정 {ago(g.age_days)}</span>
                    <span title="최종수정 이후 무수정 사용">사용 {g.clean_uses}</span>
                    {g.last_review && <span title="마지막 검토">검토 {g.last_review}</span>}
                  </div>
                  <div className="mt-1 h-1 rounded bg-stone-100 overflow-hidden">
                    <div className={`h-full ${g.over_budget ? 'bg-red-400' : pct > 80 ? 'bg-amber-400' : 'bg-emerald-400'}`}
                      style={{ width: `${pct}%` }} />
                  </div>
                </button>
              );
            })}
            {catalog && catalog.missing_files.length > 0 && (
              <div className="px-3 py-2 text-[11px] text-red-700 bg-red-50 border-t border-red-100">
                <div className="font-semibold mb-1">guide_db.json 에 등록됐지만 파일이 없음</div>
                {catalog.missing_files.map((m) => <div key={m.file} className="font-mono">{m.file} — {m.name || m.id}</div>)}
              </div>
            )}
            {catalog && rows.length === 0 && <div className="px-3 py-6 text-sm text-stone-400 text-center">해당하는 가이드가 없습니다.</div>}
          </div>
        </div>

        {/* 본문 */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          {current ? (
            <>
              <div className="px-5 py-3 border-b border-[#E5DFD5] bg-white/70 space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-base font-semibold text-[#4A4035]">{current.name}</span>
                  <span className="text-xs font-mono text-stone-400">data/guides/{current.file}</span>
                  <span className={`text-xs ${current.over_budget ? 'text-red-600 font-semibold' : 'text-stone-500'}`}>
                    {kb(current.bytes)} / {kb(budget)}
                  </span>
                  <div className="ml-auto flex items-center gap-1.5">
                    {!editing ? (
                      <>
                        <button onClick={() => setRaw(!raw)} title={raw ? '렌더로 보기' : '원문으로 보기'}
                          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg border border-stone-200 bg-white hover:bg-amber-50 text-stone-600">
                          {raw ? <Eye size={13} /> : <Code size={13} />}{raw ? '렌더' : '원문'}
                        </button>
                        <button onClick={() => { setDraft(content); setEditing(true); }}
                          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-[#D97706] hover:bg-[#B45309] text-white">
                          <Pencil size={13} /> 편집
                        </button>
                      </>
                    ) : (
                      <>
                        <span className={`text-xs ${new Blob([draft]).size > budget ? 'text-red-600' : 'text-stone-500'}`}>
                          {kb(new Blob([draft]).size)}
                        </span>
                        <button onClick={() => { setEditing(false); setDraft(content); }} disabled={busy}
                          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-600">
                          <X size={13} /> 취소
                        </button>
                        <button onClick={save} disabled={busy || draft === content}
                          className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-[#D97706] hover:bg-[#B45309] text-white disabled:opacity-50">
                          <Save size={13} /> 저장
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {current.description && <div className="text-sm text-stone-600">{current.description}</div>}
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-stone-500">
                  {current.topic && <span>주제 {current.topic}</span>}
                  <span>작성 {current.born || '—'}</span>
                  <span>최종수정 {current.updated || '—'} ({ago(current.age_days)})</span>
                  <span>이후 무수정 사용 {current.clean_uses}회{current.last_use ? ` (최근 ${current.last_use})` : ''}</span>
                  <span>마지막 검토 {current.last_review || '없음'}</span>
                  {!current.registered && <span className="text-amber-700">guide_db.json 미등록 — read_guide 검색에 잡히지 않는다</span>}
                  {current.lifecycle_candidate_since && <span>정리 후보 표식 {current.lifecycle_candidate_since}</span>}
                </div>
                {current.keywords.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {current.keywords.map((k) => <span key={k} className="text-[10px] px-1.5 py-0.5 rounded-full bg-stone-100 text-stone-600">{k}</span>)}
                  </div>
                )}
                {notice && (
                  <div className={`flex items-center gap-1.5 text-xs ${notice.includes('초과') || notice.includes('실패') ? 'text-red-700' : 'text-emerald-700'}`}>
                    {(notice.includes('초과') || notice.includes('실패')) && <AlertTriangle size={13} />}{notice}
                  </div>
                )}
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto bg-white">
                {editing ? (
                  <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false}
                    className="w-full h-full px-5 py-4 text-[12px] leading-relaxed font-mono text-stone-800 resize-none focus:outline-none" />
                ) : raw ? (
                  <pre className="px-5 py-4 text-[12px] leading-relaxed font-mono text-stone-700 whitespace-pre-wrap break-words">{content}</pre>
                ) : (
                  <div className="px-6 py-4 prose prose-sm prose-stone max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-stone-400">
              {catalog ? '왼쪽에서 가이드를 고르세요.' : '불러오는 중…'}
            </div>
          )}
        </div>
      </div>
    </ToolWindowFrame>
  );
}
