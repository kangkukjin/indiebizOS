/**
 * PromptCompositionDialog — 프롬프트 구성 (안경 메뉴)
 *
 * 에이전트(시스템 AI·프로젝트 에이전트·의식·무의식·평가자 …)를 고르면 그 프롬프트가
 * 어떤 조각으로 조립되는지 A + B + C 식으로 보이고, 조각을 클릭하면 본문이 열린다.
 * 파일로 고정된 조각은 본문 그대로, 실행기억처럼 턴마다 다른 조각은 샘플 메시지 한 건으로
 * 실제 조립한 결과(분량 포함)를 보인다. 백엔드 /prompt-composition/* (LLM 호출 0).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Layers, RefreshCw, FileText, Cpu, Brain, History, Hash, Zap, MessageSquare, ChevronRight } from 'lucide-react';
import { SettingsFrame } from '../../SettingsFrame';
import { api } from '../../../lib/api';
import { useRetryingLoad } from '../../../lib/use-retrying-load';
import type { PromptCompositionCatalog, PromptCompositionResult, PromptSection } from '../../../lib/api-system-ai';

interface Props {
  show: boolean;
  onClose: () => void;
}

const LAYER_META: Record<PromptSection['layer'], { title: string; hint: string }> = {
  system: { title: '시스템 프롬프트', hint: '매 호출 동일 — 프롬프트 캐시 prefix' },
  turn: { title: '턴 컨텍스트', hint: '사용자 메시지 앞에 붙는 가변 부분 (<turn_context>)' },
  user: { title: '사용자 메시지', hint: '이력 + 이번 턴 명령' },
};

const KIND_META: Record<PromptSection['kind'], { label: string; cls: string; icon: React.ReactNode }> = {
  file: { label: '파일', cls: 'bg-stone-100 text-stone-600', icon: <FileText size={11} /> },
  constant: { label: '코드 상수', cls: 'bg-slate-100 text-slate-600', icon: <Hash size={11} /> },
  dynamic: { label: '조립', cls: 'bg-sky-50 text-sky-700', icon: <Cpu size={11} /> },
  memory: { label: '기억', cls: 'bg-violet-50 text-violet-700', icon: <Brain size={11} /> },
  history: { label: '이력', cls: 'bg-amber-50 text-amber-700', icon: <History size={11} /> },
  turn: { label: '턴마다', cls: 'bg-orange-50 text-orange-700', icon: <Zap size={11} /> },
  input: { label: '입력', cls: 'bg-emerald-50 text-emerald-700', icon: <MessageSquare size={11} /> },
};

const fmt = (n: number) => n.toLocaleString();

export function PromptCompositionDialog({ show, onClose }: Props) {
  const [catalog, setCatalog] = useState<PromptCompositionCatalog | null>(null);
  const [agentId, setAgentId] = useState<string>('system_ai');
  const [projectId, setProjectId] = useState<string>('');
  const [sample, setSample] = useState<string>('');
  const [result, setResult] = useState<PromptCompositionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [selectedKey, setSelectedKey] = useState<string>('');

  const loadCatalog = useCallback(async () => {
    const c = await api.getPromptCompositionAgents();
    setCatalog(c);
    setSample((prev) => prev || c.default_sample);
    setProjectId((prev) => prev || c.projects[0]?.id || '');
  }, []);
  useRetryingLoad(loadCatalog, { enabled: show });

  const assemble = useCallback(async (id: string, msg: string, pid: string) => {
    setLoading(true);
    setError('');
    try {
      const r = await api.assemblePromptComposition({ agent_id: id, sample_message: msg, project_id: pid || undefined });
      setResult(r);
      setSelectedKey('');
      if (r.error) setError(r.error);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // 에이전트를 고르면 즉시 조립 (샘플·프로젝트는 '다시 조립' 버튼으로)
  useEffect(() => {
    if (!show || !catalog) return;
    assemble(agentId, sample || catalog.default_sample, projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show, catalog, agentId]);

  const groups = useMemo(() => {
    const m = new Map<string, PromptCompositionCatalog['agents']>();
    for (const a of catalog?.agents || []) {
      if (!m.has(a.group)) m.set(a.group, []);
      m.get(a.group)!.push(a);
    }
    return Array.from(m.entries());
  }, [catalog]);

  const current = catalog?.agents.find((a) => a.id === agentId);
  const selected = result?.sections.find((s) => s.key === selectedKey) || null;

  if (!show) return null;

  return (
    <SettingsFrame onClose={onClose} title="프롬프트 구성" width={1040} height={760}
      icon={<Layers className="text-amber-600" size={22} />} resizable>
      <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4 bg-[#FAF8F4]">
        <p className="text-sm text-stone-600">
          에이전트마다 프롬프트가 다르게 조립됩니다. 에이전트를 고르면 조립 순서가 <b>A + B + C</b> 로 보이고,
          조각을 누르면 본문이 열립니다. 실행기억처럼 턴마다 달라지는 조각은 아래 샘플 메시지 한 건으로 실제 조립한 결과입니다(모델 호출 없음).
        </p>

        {/* 에이전트 선택 */}
        <div className="space-y-2">
          {groups.map(([group, agents]) => (
            <div key={group} className="flex flex-wrap items-center gap-2">
              <span className="w-12 shrink-0 text-[11px] font-semibold text-stone-400 tracking-wide">{group}</span>
              {agents.map((a) => (
                <button key={a.id} onClick={() => setAgentId(a.id)} title={a.summary}
                  className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                    a.id === agentId
                      ? 'bg-amber-600 border-amber-600 text-white'
                      : 'bg-white border-stone-200 text-stone-700 hover:bg-amber-50'
                  }`}>
                  {a.label}
                </button>
              ))}
            </div>
          ))}
          {catalog && catalog.no_prompt_jobs.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-12 shrink-0 text-[11px] font-semibold text-stone-400 tracking-wide">LLM 0</span>
              <span className="text-[11px] text-stone-400">프롬프트 없는 순찰: {catalog.no_prompt_jobs.join(' · ')}</span>
            </div>
          )}
        </div>

        {/* 샘플 메시지 · 프로젝트 · 다시 조립 */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2">
          <span className="text-xs text-stone-500 shrink-0">샘플 메시지</span>
          <input value={sample} onChange={(e) => setSample(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') assemble(agentId, sample, projectId); }}
            className="flex-1 min-w-[240px] px-2 py-1 text-sm border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-300" />
          {current?.needs_project && catalog && (
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)}
              className="px-2 py-1 text-sm border border-stone-200 rounded-lg bg-white">
              {catalog.projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.agents.join(', ')})</option>
              ))}
            </select>
          )}
          <button onClick={() => assemble(agentId, sample, projectId)} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-[#D97706] hover:bg-[#B45309] text-white disabled:opacity-50">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 다시 조립
          </button>
        </div>

        {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}

        {result && current && (
          <div className="space-y-4">
            {/* 머리: 요약 · 진입점 · 모델 */}
            <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 space-y-1.5">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-base font-semibold text-[#4A4035]">{current.label}</span>
                <span className="text-sm text-stone-600">{current.summary}</span>
              </div>
              {result.context?.project && (
                <div className="text-xs text-stone-500">
                  프로젝트 <b>{result.context.project}</b> · 에이전트 <b>{result.context.agent}</b>
                  {typeof result.context.agent_count === 'number' && <> · 활성 {result.context.agent_count}명</>}
                  {result.context.allowed_nodes && <> · 허용 노드 {result.context.allowed_nodes.join(', ')}</>}
                </div>
              )}
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
                {result.model.provider ? (
                  <span>모델 <b className="text-stone-700">{result.model.provider}/{result.model.model}</b>
                    {result.model.tier && <> · 티어 {result.model.tier}</>}{result.model.axis && <> · 축 {result.model.axis}</>}
                    {result.model.role && <> · 역할 {result.model.role}</>}</span>
                ) : (
                  <span>모델 {result.model.note || result.model.error || '—'}</span>
                )}
                {result.entry && <span className="font-mono text-[11px] text-stone-400 break-all">진입: {result.entry}</span>}
              </div>
              {result.output_keys && (
                <div className="text-xs text-stone-500">출력: {result.output_keys.join(' · ')}</div>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                {(['system', 'turn', 'user'] as const).map((layer) => {
                  const t = result.totals[layer];
                  if (!t || t.count === 0) return null;
                  return (
                    <span key={layer} className="text-[11px] px-2 py-0.5 rounded-full bg-stone-100 text-stone-600">
                      {LAYER_META[layer].title} {fmt(t.chars)}자 · ≈{fmt(t.tokens)}토큰
                    </span>
                  );
                })}
                {typeof result.assembled.stable_chars === 'number' && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700"
                    title="실제 빌더가 돌린 결과 — 조각 합과 대조">
                    실제 조립 안정부 {fmt(result.assembled.stable_chars)}자 · 가변부 {fmt(result.assembled.dynamic_chars || 0)}자
                  </span>
                )}
              </div>
            </div>

            {/* 층별 조립식 */}
            {(['system', 'turn', 'user'] as const).map((layer) => {
              const secs = result.sections.filter((s) => s.layer === layer);
              if (secs.length === 0) return null;
              return (
                <div key={layer} className="rounded-xl border border-stone-200 bg-white px-4 py-3">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-sm font-semibold text-[#4A4035]">{LAYER_META[layer].title}</span>
                    <span className="text-[11px] text-stone-400">{LAYER_META[layer].hint}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-y-2">
                    {secs.map((s, i) => {
                      const k = KIND_META[s.kind];
                      const active = s.key === selectedKey;
                      return (
                        <div key={s.key} className="flex items-center">
                          {i > 0 && <span className="mx-1.5 text-stone-300 text-lg leading-none select-none">+</span>}
                          <button onClick={() => setSelectedKey(active ? '' : s.key)} title={s.condition || s.source}
                            className={`flex items-center gap-1.5 pl-2 pr-2.5 py-1 rounded-lg border text-left transition-colors ${
                              active
                                ? 'border-amber-500 bg-amber-50'
                                : s.included
                                  ? 'border-stone-200 bg-white hover:bg-amber-50/60'
                                  : 'border-dashed border-stone-300 bg-stone-50 text-stone-400 hover:bg-amber-50/40'
                            }`}>
                            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${k.cls} ${s.included ? '' : 'opacity-60'}`}>
                              {k.icon}{k.label}
                            </span>
                            <span className={`text-sm ${s.included ? 'text-[#4A4035]' : 'text-stone-400'}`}>{s.label}</span>
                            <span className="text-[11px] text-stone-400 tabular-nums">
                              {s.chars > 0 ? `${fmt(s.chars)}자` : s.kind === 'turn' || s.kind === 'history' ? '턴마다' : '—'}
                            </span>
                            {!s.included && <span className="text-[10px] text-stone-400">(조건부)</span>}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            {/* 선택한 조각 */}
            {selected && (
              <div className="rounded-xl border border-amber-300 bg-white">
                <div className="px-4 py-3 border-b border-amber-100 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <ChevronRight size={14} className="text-amber-500" />
                    <span className="text-sm font-semibold text-[#4A4035]">{selected.label}</span>
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${KIND_META[selected.kind].cls}`}>
                      {KIND_META[selected.kind].icon}{KIND_META[selected.kind].label}
                    </span>
                    <span className="text-[11px] text-stone-400">{LAYER_META[selected.layer].title}</span>
                    <span className="text-[11px] text-stone-500 tabular-nums ml-auto">
                      {fmt(selected.chars)}자 · ≈{fmt(selected.tokens)}토큰
                    </span>
                  </div>
                  <div className="text-xs text-stone-500 font-mono break-all">출처: {selected.source}</div>
                  {selected.condition && (
                    <div className="text-xs text-stone-600">
                      <b>{selected.included ? '조건' : '이번 샘플엔 안 실림'}</b> — {selected.condition}
                    </div>
                  )}
                  {selected.note && <div className="text-xs text-stone-600">{selected.note}</div>}
                  {selected.ref_agent && (
                    <button onClick={() => setAgentId(selected.ref_agent!)}
                      className="text-xs text-amber-700 hover:underline">
                      → '{catalog?.agents.find((a) => a.id === selected.ref_agent)?.label || selected.ref_agent}' 항목에서 본문 보기
                    </button>
                  )}
                </div>
                {selected.content ? (
                  <pre className="px-4 py-3 text-[11px] leading-relaxed text-stone-700 whitespace-pre-wrap break-words max-h-[420px] overflow-y-auto font-mono">
                    {selected.content}
                  </pre>
                ) : (
                  <div className="px-4 py-3 text-xs text-stone-400">
                    {selected.kind === 'turn' || selected.kind === 'history'
                      ? '실제 턴에서만 생기는 조각 — 본문은 그 턴의 실행·응답에서 온다. 조종실 실행 트레이스·에피소드에서 실제 값을 볼 수 있다.'
                      : '이번 조립에서는 비어 있음.'}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {!result && !error && (
          <div className="text-sm text-stone-400 py-8 text-center">
            {loading ? '조립 중…' : '에이전트를 고르면 조립을 보여줍니다.'}
          </div>
        )}
      </div>
    </SettingsFrame>
  );
}
