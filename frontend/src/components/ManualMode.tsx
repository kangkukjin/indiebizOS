/**
 * ManualMode.tsx - 수동 모드 (컴파일러 프론트엔드)
 *
 * 트릴레마에서 표현력+주권을 갖고 속도를 지불하는 면. 인간이 에이전트 루프를 대체한다:
 *   1) 의도 입력  → 2) 경량 모델이 해마에 기대 IBL로 번역  → 3) 효과(dry-run)로 검수·편집
 *   → 4) 되돌릴 수 있음을 믿고 실행.
 *
 * 모델은 선장이 아니라 컴파일러다. 번역만 하고, 지능은 언어(IBL)에 쌓인다.
 * 그래서 검수는 코드가 아니라 '효과 레벨'로 하고, IBL 원문은 학습을 위해 병기한다.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Terminal, Wand2, Play, Check, AlertTriangle, Loader2, BookOpen, Eye, ShieldAlert, HelpCircle, Copy, X } from 'lucide-react';
import { api } from '../lib/api';
import type { IblValidateResult, IblSafety, IblCatalog } from '../lib/api-ibl';

// 수동 모드에서 IBL 액션이 쓰는 프로젝트 컨텍스트 (활성 프로젝트가 없어도 경로 확보)
const MANUAL_PROJECT_ID = '수동모드';

interface HistoryEntry {
  intent: string;
  code: string;
  ok: boolean;
}

/** 안전성 배지 — read는 무마찰, write는 부작용 경고. */
function SafetyBadge({ safety }: { safety: IblSafety }) {
  if (safety === 'read') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
        <Eye size={11} /> 읽기 전용
      </span>
    );
  }
  if (safety === 'write') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
        <ShieldAlert size={11} /> 부작용
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-stone-500 bg-stone-100 px-1.5 py-0.5 rounded">
      <HelpCircle size={11} /> 미분류
    </span>
  );
}

interface ParsedRef {
  intent: string;
  code: string;
  score: string;
  successRate: string;
}

/** 해마 참조 XML(<ibl_references><ref .../></ibl_references>)을 가볍게 파싱. */
function parseReferences(xml: string): ParsedRef[] {
  if (!xml) return [];
  try {
    const doc = new DOMParser().parseFromString(xml, 'text/xml');
    return Array.from(doc.querySelectorAll('ref')).map((el) => ({
      intent: el.getAttribute('intent') || '',
      code: el.getAttribute('code') || '',
      score: el.getAttribute('score') || '',
      successRate: el.getAttribute('success_rate') || '',
    }));
  } catch {
    return [];
  }
}

/** 복사 버튼 — Electron에서 <pre> 등 비입력 영역은 Cmd/Ctrl+C가 안 먹으므로 clipboard API로 직접 복사 */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch { /* clipboard 거부 시 무시 */ }
      }}
      className="inline-flex items-center gap-1 text-[11px] text-stone-500 hover:text-stone-700 px-1.5 py-0.5 rounded hover:bg-stone-100 transition"
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? '복사됨' : '복사'}
    </button>
  );
}

// IBL 5개 노드의 뜻 — 둘러보기에서 "이게 무슨 종류의 일인지" 보여준다
const NODE_GLOSS: Record<string, string> = {
  sense: '감각 · 수집/검색', self: '자기 · 기억/파일/설정',
  limbs: '손발 · 조작', others: '관계 · 이웃/위임/채널', engines: '엔진 · 생성',
};

export default function ManualMode() {
  const [intent, setIntent] = useState('');
  const [iblCode, setIblCode] = useState('');
  const [refs, setRefs] = useState<ParsedRef[]>([]);
  const [showRefs, setShowRefs] = useState(false);
  const [validation, setValidation] = useState<IblValidateResult | null>(null);
  const [execResult, setExecResult] = useState<string | null>(null);
  const [confirmSideEffect, setConfirmSideEffect] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [learned, setLearned] = useState(false);          // 사용자가 이 결과를 학습시켰음
  const [distilling, setDistilling] = useState(false);    // 학습(증류) 진행 중

  const [translating, setTranslating] = useState(false);
  const [validating, setValidating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 카탈로그 (둘러보기 + 씨앗 삽입용)
  const [catalog, setCatalog] = useState<IblCatalog | null>(null);
  const [pendingCaret, setPendingCaret] = useState<number | null>(null);

  // 발견 레이어 (둘러보기 팔레트)
  const [browsing, setBrowsing] = useState(false);
  const [browseQuery, setBrowseQuery] = useState('');

  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  // 카탈로그 1회 로드 (노드/액션 사전)
  useEffect(() => {
    api.getIblCatalog().then(setCatalog).catch(() => {});
  }, []);

  // 씨앗 삽입(둘러보기) 후 커서 위치 복원
  useEffect(() => {
    if (pendingCaret != null && taRef.current) {
      taRef.current.focus();
      taRef.current.setSelectionRange(pendingCaret, pendingCaret);
      setPendingCaret(null);
    }
  }, [pendingCaret, iblCode]);

  // 발견 레이어: 클릭한 액션을 명령줄에 씨앗으로 떨군다 (target_key가 있으면 파라미터 골격까지)
  const seedFromAction = useCallback((node: string, action: string, targetKey: string) => {
    const seed = targetKey ? `[${node}:${action}]{${targetKey}: }` : `[${node}:${action}]{}`;
    setIblCode(seed);
    setBrowsing(false);
    // 파라미터를 바로 채우도록 '{' 안쪽에 커서를 둔다
    setPendingCaret(seed.lastIndexOf('}'));
  }, []);

  // 둘러보기 필터: 액션 이름/설명/키워드/노드로 검색
  const browseGroups = useMemo(() => {
    if (!catalog) return [] as Array<{ node: string; actions: Array<{ name: string; description: string; targetKey: string }> }>;
    const q = browseQuery.trim().toLowerCase();
    return Object.entries(catalog.nodes).map(([node, nd]) => ({
      node,
      actions: Object.entries(nd.actions)
        .filter(([name, meta]) =>
          !q ||
          name.toLowerCase().includes(q) ||
          node.toLowerCase().includes(q) ||
          (meta.description || '').toLowerCase().includes(q) ||
          (meta.keywords || []).some((k) => k.toLowerCase().includes(q)))
        .map(([name, meta]) => ({ name, description: meta.description || '', targetKey: meta.target_key || '' })),
    })).filter((g) => g.actions.length > 0);
  }, [catalog, browseQuery]);

  // dry-run 검증 (편집 시 디바운스 자동 실행)
  const runValidate = useCallback(async (code: string) => {
    if (!code.trim()) {
      setValidation(null);
      return;
    }
    setValidating(true);
    try {
      const res = await api.validateIBL(code);
      setValidation(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '검증 실패');
    } finally {
      setValidating(false);
    }
  }, []);

  // IBL 코드가 바뀌면 자동으로 효과를 다시 미리보고, 부작용 확인·학습 표시는 리셋한다
  useEffect(() => {
    setConfirmSideEffect(false);
    setLearned(false);
    if (validateTimer.current) clearTimeout(validateTimer.current);
    if (!iblCode.trim()) {
      setValidation(null);
      return;
    }
    validateTimer.current = setTimeout(() => runValidate(iblCode), 500);
    return () => {
      if (validateTimer.current) clearTimeout(validateTimer.current);
    };
  }, [iblCode, runValidate]);

  // 1단계: 자연어 → IBL 번역
  const handleTranslate = async () => {
    if (!intent.trim()) return;
    setErr(null);
    setExecResult(null);
    setTranslating(true);
    try {
      const res = await api.translateToIBL(intent);
      setIblCode(res.ibl_code);
      const parsed = parseReferences(res.references);
      setRefs(parsed);
      setShowRefs(false);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '번역 실패');
    } finally {
      setTranslating(false);
    }
  };

  // 전체 비우기 — 다음 명령을 깨끗하게 시작 (입력 + 파생 패널 모두 리셋)
  const handleClear = () => {
    setIntent('');
    setIblCode('');
    setRefs([]);
    setShowRefs(false);
    setValidation(null);
    setExecResult(null);
    setErr(null);
  };

  // 4단계: 실행 (검수 통과 후)
  const handleExecute = async () => {
    if (!iblCode.trim()) return;
    setErr(null);
    setExecResult(null);
    setExecuting(true);
    try {
      const res = await api.executeIBL(iblCode, MANUAL_PROJECT_ID);
      setExecResult(typeof res === 'string' ? res : JSON.stringify(res, null, 2));
      setHistory((h) => [{ intent, code: iblCode, ok: true }, ...h].slice(0, 8));
      // 자동 학습하지 않는다 — '실행 성공'은 '결과가 좋다'가 아니다.
      // 사용자가 결과를 보고 만족하면 '학습' 버튼으로 직접 증류한다(handleLearn).
    } catch (e) {
      setErr(e instanceof Error ? e.message : '실행 실패');
      setHistory((h) => [{ intent, code: iblCode, ok: false }, ...h].slice(0, 8));
    } finally {
      setExecuting(false);
    }
  };

  // 학습(증류) — 사용자가 결과를 인정했을 때만 명시적으로 호출. intent가 있어야 함.
  const handleLearn = async () => {
    if (!intent.trim() || !iblCode.trim() || distilling || learned) return;
    setDistilling(true);
    try {
      // 사용자가 직접 인정한 예시이므로 임계값에 막히지 않게 강제 학습(top_score=0)
      const d = await api.distillIBL(intent.trim(), iblCode, 0);
      if (d.distilled) setLearned(true);
      else setErr(d.reason || '학습할 수 없습니다.');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '학습 실패');
    } finally {
      setDistilling(false);
    }
  };

  // 부작용이 있으면 명시적 확인을 받아야만 실행 가능. 전부 read-only면 무마찰.
  const needsConfirm = !!validation?.has_side_effect;
  const canExecute =
    !!validation && validation.valid && !!iblCode.trim() && !executing &&
    (!needsConfirm || confirmSideEffect);

  return (
    <div className="h-full overflow-y-auto bg-[#F5F1EB]">
      <div className="max-w-2xl mx-auto px-5 py-6 space-y-4">

        {/* 헤더 */}
        <div className="flex items-center justify-between gap-2 text-stone-500">
          <div className="flex items-center gap-2 min-w-0">
            <Terminal size={18} className="shrink-0" />
            <span className="text-sm truncate">수동 모드 — 명령을 IBL로 번역·검수한 뒤 실행합니다</span>
          </div>
          <button
            onClick={() => setBrowsing((v) => !v)}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 border transition ${
              browsing ? 'bg-stone-800 text-white border-stone-800' : 'bg-white/70 border-stone-200 text-stone-600 hover:bg-white'
            }`}
          >
            <BookOpen size={13} /> 둘러보기
          </button>
        </div>

        {/* 발견 레이어: 노드별 액션 둘러보기 → 클릭하면 명령줄에 씨앗으로 */}
        {browsing && (
          <div className="rounded-xl border border-stone-200 bg-white/70 overflow-hidden">
            <div className="p-2 border-b border-stone-100">
              <input
                type="text"
                value={browseQuery}
                onChange={(e) => setBrowseQuery(e.target.value)}
                placeholder="액션 검색  예) 검색, 파일, 차트…"
                className="w-full px-3 py-1.5 rounded-lg border border-stone-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-stone-300"
              />
            </div>
            <div className="max-h-72 overflow-y-auto p-2 space-y-3">
              {!catalog && <div className="text-xs text-stone-400 px-1">불러오는 중…</div>}
              {browseGroups.map((g) => (
                <div key={g.node}>
                  <div className="text-[11px] text-stone-400 px-1 mb-1">{NODE_GLOSS[g.node] || g.node}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {g.actions.map((a) => (
                      <button
                        key={a.name}
                        onClick={() => seedFromAction(g.node, a.name, a.targetKey)}
                        title={a.description}
                        className="px-2 py-1 rounded-lg bg-stone-100 hover:bg-stone-200 text-[12px] text-stone-700 font-mono transition"
                      >
                        {a.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {catalog && browseGroups.length === 0 && (
                <div className="text-xs text-stone-400 px-1">일치하는 액션이 없습니다.</div>
              )}
            </div>
          </div>
        )}

        {/* 1) 의도 입력 (커맨드 팔레트) */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !translating) handleTranslate(); }}
              placeholder="무엇을 할까요?  예) 강남구 아파트 실거래가 찾아줘"
              className="w-full pl-4 pr-9 py-2.5 rounded-xl border border-stone-300 bg-white text-stone-800 text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
            />
            {(intent || iblCode || execResult !== null) && (
              <button
                onClick={handleClear}
                title="비우기 (다음 명령 시작)"
                aria-label="비우기"
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition"
              >
                <X size={16} />
              </button>
            )}
          </div>
          <button
            onClick={handleTranslate}
            disabled={translating || !intent.trim()}
            className="shrink-0 px-4 py-2.5 rounded-xl bg-stone-800 text-white text-sm flex items-center gap-1.5 disabled:opacity-40 hover:bg-stone-700 transition"
          >
            {translating ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
            번역
          </button>
        </div>

        {err && (
          <div className="px-4 py-2.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            {err}
          </div>
        )}

        {/* 2) IBL 원문 병기 (편집 가능) — 리터러시를 가르치는 면 */}
        {(iblCode || translating) && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs text-stone-400">IBL 코드 (편집하면 효과가 다시 계산됩니다)</span>
              {validating && <Loader2 size={13} className="animate-spin text-stone-400" />}
            </div>
            <textarea
              ref={taRef}
              value={iblCode}
              onChange={(e) => setIblCode(e.target.value)}
              rows={Math.min(6, Math.max(2, iblCode.split('\n').length))}
              spellCheck={false}
              className="w-full px-3 py-2.5 rounded-xl border border-stone-300 bg-stone-900 text-emerald-200 font-mono text-[13px] leading-relaxed focus:outline-none focus:ring-2 focus:ring-stone-500 resize-none"
            />

            {/* 번역 근거 (해마 용례) — 펼쳐서 학습 */}
            {refs.length > 0 && (
              <div>
                <button
                  onClick={() => setShowRefs((v) => !v)}
                  className="text-xs text-stone-400 hover:text-stone-600 flex items-center gap-1"
                >
                  <BookOpen size={12} />
                  번역 근거 {refs.length}개 {showRefs ? '접기' : '보기'}
                </button>
                {showRefs && (
                  <div className="mt-1.5 space-y-1">
                    {refs.map((r, i) => (
                      <div key={i} className="px-3 py-2 rounded-lg bg-white/70 border border-stone-200 text-xs">
                        <div className="text-stone-500">{r.intent}</div>
                        <code className="text-stone-700 break-all">{r.code}</code>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 3) 효과 dry-run 검수 — 코드가 아니라 '무엇을 하는지'를 본다 */}
        {validation && (
          <div className="space-y-1.5">
            <span className="text-xs text-stone-400">실행하면 일어나는 일 (미리보기 — 아직 실행되지 않음)</span>

            {validation.syntax_error ? (
              <div className="px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm flex items-start gap-2">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                <span>문법 오류: {validation.syntax_error}</span>
              </div>
            ) : (
              <div className="space-y-1.5">
                {validation.steps.map((s, i) => (
                  <div
                    key={i}
                    className={`px-3 py-2.5 rounded-xl border flex items-start gap-2.5 ${
                      s.valid ? 'bg-white border-stone-200' : 'bg-red-50 border-red-200'
                    }`}
                  >
                    <div className="mt-0.5 shrink-0">
                      {s.valid
                        ? <Check size={16} className="text-emerald-600" />
                        : <AlertTriangle size={16} className="text-red-500" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm text-stone-800">{s.effect}</span>
                        <SafetyBadge safety={s.safety} />
                      </div>
                      <code className="text-[11px] text-stone-400">
                        [{s.node}:{s.action}]
                        {Object.keys(s.params).length > 0 && ' ' + JSON.stringify(s.params)}
                      </code>
                      {s.error && <div className="text-xs text-red-600 mt-0.5">{s.error}</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 4) 실행 — 부작용이 있으면 명시적 확인을 거친다 (되돌릴 수 없을 수 있음) */}
        {iblCode && (
          <div className="space-y-2 pt-1">
            {needsConfirm && validation?.valid && (
              <label className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-amber-50 border border-amber-200 cursor-pointer">
                <input
                  type="checkbox"
                  checked={confirmSideEffect}
                  onChange={(e) => setConfirmSideEffect(e.target.checked)}
                  className="mt-0.5 accent-amber-600"
                />
                <span className="text-xs text-amber-800 leading-relaxed">
                  이 명령에는 <b>부작용이 있는 step</b>이 포함되어 있고, 실행하면 <b>되돌릴 수 없을 수 있습니다</b>.
                  효과를 확인했고 실행합니다.
                </span>
              </label>
            )}
            <div className="flex items-center gap-3">
              <button
                onClick={handleExecute}
                disabled={!canExecute}
                className="px-5 py-2.5 rounded-xl bg-emerald-700 text-white text-sm flex items-center gap-1.5 disabled:opacity-40 hover:bg-emerald-600 transition"
              >
                {executing ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                실행
              </button>
              {validation && !validation.valid && !validation.syntax_error && (
                <span className="text-xs text-amber-700">검증을 통과하지 못한 step이 있어 실행할 수 없습니다.</span>
              )}
              {validation?.valid && !needsConfirm && (
                <span className="text-xs text-emerald-700">읽기 전용 — 안전하게 실행할 수 있습니다.</span>
              )}
            </div>
          </div>
        )}

        {/* 실행 결과 */}
        {execResult !== null && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs text-stone-400">실행 결과</span>
              {learned && (
                <span className="inline-flex items-center gap-1 text-[11px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">
                  <BookOpen size={11} /> 해마에 학습됨
                </span>
              )}
              <div className="ml-auto"><CopyButton text={execResult} /></div>
            </div>
            <pre className="px-3 py-2.5 rounded-xl bg-white border border-stone-200 text-stone-700 text-xs whitespace-pre-wrap break-words max-h-80 overflow-y-auto">
              {execResult}
            </pre>

            {/* 학습은 자동이 아니다 — 결과가 만족스러울 때만 사용자가 직접 가르친다 */}
            {!learned && intent.trim() && (
              <div className="flex items-center gap-2 pt-0.5">
                <button
                  onClick={handleLearn}
                  disabled={distilling}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs flex items-center gap-1.5 disabled:opacity-40 hover:bg-indigo-500 transition"
                >
                  {distilling ? <Loader2 size={13} className="animate-spin" /> : <BookOpen size={13} />}
                  이 결과가 좋으면 학습
                </button>
                <span className="text-[11px] text-stone-400">"{intent.trim()}" → 이 IBL을 해마에 가르칩니다</span>
              </div>
            )}
          </div>
        )}

        {/* 실행 이력 — 클릭하면 그 명령을 다시 불러온다 */}
        {history.length > 0 && (
          <div className="space-y-1.5 pt-2 border-t border-stone-200">
            <span className="text-xs text-stone-400">최근 실행</span>
            <div className="space-y-1">
              {history.map((h, i) => (
                <button
                  key={i}
                  onClick={() => { setIntent(h.intent); setIblCode(h.code); setExecResult(null); }}
                  className="w-full text-left px-3 py-1.5 rounded-lg bg-white/60 border border-stone-200 hover:bg-white transition flex items-center gap-2"
                >
                  {h.ok
                    ? <Check size={13} className="text-emerald-600 shrink-0" />
                    : <AlertTriangle size={13} className="text-red-500 shrink-0" />}
                  <span className="text-xs text-stone-600 truncate flex-1">{h.intent || h.code}</span>
                  <code className="text-[11px] text-stone-400 truncate max-w-[45%]">{h.code}</code>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
