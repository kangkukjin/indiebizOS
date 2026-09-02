/**
 * OnboardingDialog — 첫 성공 온보딩 (2026-09-02, docs/FIRST_SUCCESS_AND_UPGRADE_GATE_HANDOFF.md ① D)
 *
 * 종료조건은 "설정 완료"가 아니라 "시스템 AI 가 실제로 한 문장 답했다".
 * 상태기계: loading → pick(후보 선택 / 직접 입력) → probing → verified → (첫 대화로) / failed → pick
 * 후보가 1개면 선택을 건너뛰고 바로 검증한다. 후보 0 이면 직접 입력.
 * 저장은 검증이 통과한 뒤에만 한다(검증 → 저장 순서).
 */
import { useCallback, useEffect, useState } from 'react';
import { Bot, CheckCircle2, KeyRound, Loader2, RefreshCw, X, XCircle } from 'lucide-react';
import { api } from '../lib/api';

type Candidate = {
  provider: string; model: string; source: string; kind: 'api' | 'cli' | 'local';
  needs_key: boolean; login?: 'yes' | 'unknown'; label?: string;
};

type Phase = 'loading' | 'pick' | 'probing' | 'verified' | 'failed';

interface Props {
  show: boolean;
  onClose: (completed: boolean) => void;
}

const KEY_PROVIDERS = ['google', 'anthropic', 'openai', 'deepseek', 'openrouter'];
const NO_KEY_PROVIDERS = ['claude_code', 'codex', 'ollama'];

function sourceLabel(c: Candidate): string {
  if (c.source.startsWith('env:')) return `환경변수 ${c.source.slice(4)}`;
  if (c.source.startsWith('cli:')) return `설치된 CLI${c.login === 'yes' ? ' · 로그인됨' : ''}`;
  if (c.source.startsWith('local:')) return '로컬 모델 서버';
  return c.source;
}

export function OnboardingDialog({ show, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>('loading');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [manual, setManual] = useState(false);
  const [result, setResult] = useState<{ message: string; reply?: string; latency_ms?: number; error?: string } | null>(null);

  const needsKey = KEY_PROVIDERS.includes(provider);

  const load = useCallback(async () => {
    setPhase('loading');
    try {
      const { items } = await api.getSystemAICandidates();
      setCandidates(items);
      if (items.length >= 1) {
        setProvider(items[0].provider);
        setModel(items[0].model);
        setManual(false);
      } else {
        setManual(true);
      }
    } catch {
      setCandidates([]);
      setManual(true);
    }
    setPhase('pick');
  }, []);

  useEffect(() => { if (show) void load(); }, [show, load]);

  const probe = async () => {
    if (!provider || !model) return;
    setPhase('probing');
    setResult(null);
    try {
      const r = await api.probeSystemAI({ provider, model, api_key: needsKey ? apiKey : '' });
      setResult({ message: r.message, reply: r.reply, latency_ms: r.latency_ms, error: r.error });
      if (r.ok) {
        // 검증 통과 뒤에만 저장 — 키는 백엔드가 .env 로 보낸다.
        await api.updateSystemAI({ enabled: true, provider, model, apiKey: needsKey ? apiKey : '' });
        setPhase('verified');
      } else {
        setPhase('failed');
      }
    } catch (e) {
      setResult({ message: '검증 요청 자체가 실패했습니다.', error: String(e) });
      setPhase('failed');
    }
  };

  const startChat = () => {
    window.electron?.openSystemAIWindow?.();
    onClose(true);
  };

  const skip = async () => {
    try { await api.dismissOnboarding(); } catch { /* 상태 기록 실패는 온보딩을 막지 않는다 */ }
    onClose(false);
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-[600px] max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-amber-50 to-orange-50">
          <div className="flex items-center gap-3">
            <Bot className="w-8 h-8 text-amber-600" />
            <div>
              <h2 className="text-lg font-bold text-gray-800">시스템 AI 깨우기</h2>
              <p className="text-xs text-gray-500">실제로 한 문장 답을 받으면 끝납니다</p>
            </div>
          </div>
          <button onClick={skip} className="p-2 hover:bg-amber-100 rounded-full" title="나중에 (설정에서 언제든)">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <div className="p-6 space-y-4 overflow-y-auto">
          {phase === 'loading' && (
            <div className="flex items-center gap-2 text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> 이 기계가 이미 가진 AI 를 찾는 중…</div>
          )}

          {(phase === 'pick' || phase === 'failed' || phase === 'probing') && (
            <>
              {candidates.length > 0 && !manual && (
                <div className="space-y-2">
                  <p className="text-sm text-gray-600">이 기계에서 찾은 AI 입니다. 하나를 고르세요.</p>
                  {candidates.map((c, i) => {
                    const selected = c.provider === provider && c.model === model;
                    return (
                      <button key={i} onClick={() => { setProvider(c.provider); setModel(c.model); }}
                        className={`w-full text-left px-3 py-2 rounded-lg border ${selected ? 'border-amber-500 bg-amber-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                        <div className="text-sm font-medium text-gray-800">{c.label || c.provider} <span className="text-gray-400 font-normal">· {c.model || '(모델 선택 필요)'}</span></div>
                        <div className="text-xs text-gray-500">{sourceLabel(c)}</div>
                      </button>
                    );
                  })}
                  <button onClick={() => setManual(true)} className="text-xs text-amber-700 hover:underline">직접 입력하기</button>
                </div>
              )}

              {(manual || candidates.length === 0) && (
                <div className="space-y-2">
                  {candidates.length === 0 && (
                    <p className="text-sm text-gray-600">이 기계에서 바로 쓸 수 있는 AI 를 찾지 못했습니다. 프로바이더와 모델을 직접 넣어주세요. 키 발급이 처음이면 Google Gemini 가 무료로 시작할 수 있습니다 (aistudio.google.com).</p>
                  )}
                  <div className="grid grid-cols-2 gap-2">
                    <select value={provider} onChange={e => setProvider(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm">
                      <option value="">프로바이더</option>
                      {[...KEY_PROVIDERS, ...NO_KEY_PROVIDERS].map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <input value={model} onChange={e => setModel(e.target.value)} placeholder="모델명" className="border rounded-lg px-2 py-1.5 text-sm" />
                  </div>
                  {candidates.length > 0 && <button onClick={() => setManual(false)} className="text-xs text-amber-700 hover:underline">후보 목록으로</button>}
                </div>
              )}

              {needsKey && (
                <div className="flex items-center gap-2">
                  <KeyRound className="w-4 h-4 text-gray-400" />
                  <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                    placeholder={`${provider} API 키 (환경변수에 있으면 비워도 됩니다)`} className="flex-1 border rounded-lg px-2 py-1.5 text-sm" />
                </div>
              )}

              {phase === 'failed' && result && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
                  <div className="flex items-center gap-2 font-medium"><XCircle className="w-4 h-4" /> {result.message}</div>
                  {result.error && <pre className="mt-1 text-xs text-red-600 whitespace-pre-wrap break-all">{result.error}</pre>}
                </div>
              )}
            </>
          )}

          {phase === 'verified' && result && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm text-emerald-800 space-y-1">
              <div className="flex items-center gap-2 font-medium"><CheckCircle2 className="w-4 h-4" /> 응답을 받았습니다 ({provider} · {model}{result.latency_ms ? ` · ${result.latency_ms}ms` : ''})</div>
              {result.reply && <div className="text-emerald-700">“{result.reply}”</div>}
              <p className="text-xs text-emerald-700">설정은 저장됐습니다. 나머지(도구 설치·프로젝트·공개 주소·폰)는 시스템 AI 와 대화하면서 하시면 됩니다.</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between p-4 border-t bg-gray-50">
          <div className="flex items-center gap-2">
            <button onClick={skip} className="px-3 py-2 text-sm text-gray-500 hover:bg-gray-200 rounded-lg">나중에</button>
            {phase !== 'loading' && phase !== 'verified' && (
              <button onClick={() => void load()} className="p-2 text-gray-400 hover:bg-gray-200 rounded-lg" title="다시 찾기"><RefreshCw className="w-4 h-4" /></button>
            )}
          </div>
          {phase === 'verified' ? (
            <button onClick={startChat} className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm">첫 대화 시작</button>
          ) : (
            <button onClick={() => void probe()} disabled={phase === 'probing' || phase === 'loading' || !provider || !model}
              className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm disabled:opacity-50 flex items-center gap-2">
              {phase === 'probing' && <Loader2 className="w-4 h-4 animate-spin" />}
              {phase === 'probing' ? '응답 기다리는 중…' : '확인 (실제로 답하는지)'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
