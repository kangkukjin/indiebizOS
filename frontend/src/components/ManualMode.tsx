/**
 * ManualMode.tsx - 조종실 (구 수동 모드/계기판 — 컴파일러 프론트엔드)
 *
 * 이름의 계보: 수동 → 계기판 → 조종실(2026-07-03). 자율주행을 포함한 시스템 전체를
 * 감독·개입하는 주권 기관이라는 승격을 반영한다(내부 탭 키는 'manual' 유지).
 *
 * 트릴레마에서 표현력+주권을 갖고 속도를 지불하는 면. 인간이 에이전트 루프를 대체한다:
 *   1) 의도 입력  → 2) 경량 모델이 해마에 기대 IBL로 번역  → 3) 효과(dry-run)로 검수·편집
 *   → 4) 되돌릴 수 있음을 믿고 실행.
 *
 * 모델은 선장이 아니라 컴파일러다. 번역만 하고, 지능은 언어(IBL)에 쌓인다.
 * 그래서 검수는 코드가 아니라 '효과 레벨'로 하고, IBL 원문은 학습을 위해 병기한다.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Wand2, Play, Check, AlertTriangle, Loader2, BookOpen, Eye, ShieldAlert, HelpCircle, Copy, X, Stethoscope, RotateCw, HardDrive, Boxes, ChevronDown, Brain } from 'lucide-react';
import { api } from '../lib/api';
import { NodePresence, ModelGearLever, ActiveProjects } from './launcher-components';
import { EpisodeJournal } from './EpisodeJournal';
import type { IblValidateResult, IblSafety, IblCatalog, DashboardStatus, RecallPreviewResult } from '../lib/api-ibl';

// 계기판 서비스 라벨
const SERVICE_LABELS: Record<string, string> = {
  scheduler: '스케줄러', channel_poller: '채널 폴러', system_ai_runner: '시스템 AI',
};

// 점검 시각을 "방금 전 / N분 전 / N시간 전 / N일 전"으로
function relTime(iso: string | null): string {
  if (!iso) return '미점검';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '미점검';
  const m = Math.floor((Date.now() - t) / 60000);
  if (m < 1) return '방금 전';
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}

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

// IBL 6개 노드의 뜻 — 둘러보기에서 "이게 무슨 종류의 일인지" 보여준다
const NODE_GLOSS: Record<string, string> = {
  sense: '감각 · 수집/검색', self: '자기 · 기억/파일/설정',
  limbs: '손발 · 조작', others: '관계 · 이웃/위임/채널', engines: '엔진 · 생성',
  table: '표 · 통화 변환',
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
  const [showAbout, setShowAbout] = useState(false);   // "IBL이란?" 설명 패널

  // 계기판: 시스템 상태 (마지막 IBL 건강 + vitals) + 수동 재점검
  const [dashboard, setDashboard] = useState<DashboardStatus | null>(null);
  const [healthChecking, setHealthChecking] = useState(false);
  // 시스템 상태 접이식 — 기본 접힘(한 줄 요약), 선택은 localStorage에 기억
  const [statusOpen, setStatusOpen] = useState<boolean>(() => {
    try { return localStorage.getItem('cockpit_status_open') === '1'; } catch { return false; }
  });

  // 기억 회상 검증 — 에이전트 0단계(연상)가 주입할 기억 묶음을 실행 없이 미리 본다 (조종실 맨 아래)
  const [recallQuery, setRecallQuery] = useState('');
  const [recalling, setRecalling] = useState(false);
  const [recallResult, setRecallResult] = useState<RecallPreviewResult | null>(null);
  const [recallError, setRecallError] = useState<string | null>(null);

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

  // 발견 레이어: 클릭한 액션을 명령줄에 씨앗으로 떨군다.
  //  - op 분기 액션은 op를 미리 채워(기본 op 또는 클릭한 op) 바로 실행 가능한 골격을 준다.
  //  - 그 외엔 target_key 골격.
  const seedFromAction = useCallback((node: string, action: string, targetKey: string, op?: string) => {
    let seed: string;
    if (op) {
      seed = `[${node}:${action}]{op: "${op}"}`;
    } else if (targetKey) {
      seed = `[${node}:${action}]{${targetKey}: }`;
    } else {
      seed = `[${node}:${action}]{}`;
    }
    setIblCode(seed);
    setBrowsing(false);
    setPendingCaret(seed.lastIndexOf('}'));
  }, []);

  // 둘러보기 필터: 액션 이름/설명/키워드/노드로 검색 (op 분기·파라미터 힌트 포함)
  const browseGroups = useMemo(() => {
    type BrowseAction = { name: string; description: string; targetKey: string; targetDesc: string; opDefault: string; ops: Array<{ op: string; desc: string }> };
    if (!catalog) return [] as Array<{ node: string; actions: BrowseAction[] }>;
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
        .map(([name, meta]) => ({
          name,
          description: meta.description || '',
          targetKey: meta.target_key || '',
          targetDesc: meta.target_description || '',
          opDefault: meta.ops?.default || '',
          ops: Object.entries(meta.ops?.values || {}).map(([op, desc]) => ({ op, desc: String(desc) })),
        })),
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

  // 계기판 상태 로드 — 마지막 기록된 IBL 건강 + vitals (검사 실행 X, 즉각)
  const loadDashboard = useCallback(async () => {
    try {
      setDashboard(await api.getDashboardStatus());
    } catch { /* 백엔드 미가동 시 무시 — 계기판은 비워둔다 */ }
  }, []);

  // 계기판 열릴 때 1회 로드
  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  // 지금 점검 — fixture 통화+정적+골든을 새로 실행(AI 0, 수십 초) 후 계기판 갱신
  const handleHealthCheck = async () => {
    if (healthChecking) return;
    setErr(null);
    setHealthChecking(true);
    try {
      await api.runIblHealthCheck();
      await loadDashboard();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'IBL 건강 점검 실패');
    } finally {
      setHealthChecking(false);
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
  // 기억 회상 검증 — 실제 주입물과 동일한 연상 묶음을 백엔드에서 받아온다 (LLM 0, 부작용 없음)
  const handleRecall = useCallback(async () => {
    const q = recallQuery.trim();
    if (!q || recalling) return;
    setRecalling(true);
    setRecallResult(null);
    setRecallError(null);
    try {
      const r = await api.recallPreview(q);
      setRecallResult(r);
    } catch (e) {
      setRecallError(e instanceof Error ? e.message : '회상 조회 실패 — 백엔드 상태를 확인하세요');
    } finally {
      setRecalling(false);
    }
  }, [recallQuery, recalling]);

  const canExecute =
    !!validation && validation.valid && !!iblCode.trim() && !executing &&
    (!needsConfirm || confirmSideEffect);

  return (
    <div className="h-full overflow-y-auto bg-[#F5F1EB]">
      <div className="max-w-2xl mx-auto px-5 py-6 space-y-4">

        {/* 액티브 프로젝트 — 지금 일하고 있는 에이전트들의 프로젝트. 클릭=대화창 맨앞으로 (조종실 맨 윗줄) */}
        <ActiveProjects />

        {/* 모델 기어 — 계기판 변속 레버(절약/균형/최대). 시스템 전체 모델 등급을 재시작 없이 변속. */}
        <ModelGearLever />

        {/* 시스템 상태 — 접이식 한 줄(dark cockpit): 요약 배지만 상시, 펼치면 상세+지금 점검 */}
        <div className="rounded-xl border border-stone-200 bg-white/70">
          <button
            onClick={() => setStatusOpen((v) => {
              const nv = !v;
              try { localStorage.setItem('cockpit_status_open', nv ? '1' : '0'); } catch { /* noop */ }
              return nv;
            })}
            className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left"
          >
            <span className="text-sm font-semibold text-stone-700 flex items-center gap-2 min-w-0">
              <Stethoscope size={14} className="shrink-0" /> 시스템 상태
              {/* 폰 접속상태 — PC(맥)에선 이게 제일 중요해 접힌 줄에 상시 표시 */}
              <NodePresence />
              {dashboard && (
                <span className={`inline-flex items-center gap-1 text-[11px] font-normal px-2 py-0.5 rounded shrink-0 ${
                  dashboard.ibl_health.healthy == null ? 'text-stone-500 bg-stone-100'
                    : !dashboard.ibl_health.healthy ? 'text-red-700 bg-red-50'
                    : dashboard.ibl_health.stale ? 'text-amber-700 bg-amber-50'
                    : 'text-emerald-700 bg-emerald-50'
                }`}>
                  {dashboard.ibl_health.healthy == null ? <HelpCircle size={11} />
                    : !dashboard.ibl_health.healthy ? <AlertTriangle size={11} />
                    : dashboard.ibl_health.stale ? <RotateCw size={11} />
                    : <Check size={11} />}
                  IBL {dashboard.ibl_health.healthy == null ? '미점검'
                    : !dashboard.ibl_health.healthy ? '주의'
                    : dashboard.ibl_health.stale ? '점검 오래됨' : '건강'}
                </span>
              )}
              {healthChecking && <Loader2 size={12} className="animate-spin text-stone-400 shrink-0" />}
              {dashboard && (
                <span className="text-[11px] font-normal text-stone-400 truncate">
                  마지막 점검 {relTime(dashboard.ibl_health.checked_at)}
                </span>
              )}
            </span>
            <ChevronDown size={14} className={`shrink-0 text-stone-400 transition-transform ${statusOpen ? 'rotate-180' : ''}`} />
          </button>

          {statusOpen && (
          <div className="px-4 pb-4 space-y-3">
          {/* 지금 점검 — 폰 연결상태는 헤더 줄로 이동(상시 표시) */}
          <div className="flex items-center justify-end pb-2 border-b border-stone-100">
            <button
              onClick={handleHealthCheck}
              disabled={healthChecking}
              title="지금 점검 — fixture 통화·정적·골든을 새로 실행 (AI 0, 수십 초)"
              className="px-2.5 py-1 rounded-lg text-xs flex items-center gap-1.5 border border-stone-200 bg-white text-stone-600 hover:bg-stone-50 disabled:opacity-50 transition shrink-0"
            >
              {healthChecking ? <Loader2 size={12} className="animate-spin" /> : <RotateCw size={12} />}
              지금 점검
            </button>
          </div>

          {/* IBL 건강 3항목 */}
          <div className="space-y-1">
            {(dashboard?.ibl_health.items ?? []).map((it) => (
              <div key={it.key} className="flex items-start gap-2 text-[13px]">
                <span className="mt-0.5 shrink-0">
                  {it.ok == null ? <HelpCircle size={14} className="text-stone-400" />
                    : it.ok ? <Check size={14} className="text-emerald-600" />
                    : <AlertTriangle size={14} className="text-red-500" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-stone-700">{it.label}</span>
                  {it.ok === false && it.detail && (
                    <span className="block text-[11px] text-red-600 break-words">{it.detail}</span>
                  )}
                </span>
              </div>
            ))}
            {!dashboard && (
              <div className="text-xs text-stone-400 flex items-center gap-1.5">
                <Loader2 size={12} className="animate-spin" /> 상태 불러오는 중…
              </div>
            )}
          </div>

          {/* vitals: 점검 시각 · 액션 수 · 디스크 · 서비스 */}
          {dashboard && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-stone-500 pt-1 border-t border-stone-100">
              <span>마지막 점검 {relTime(dashboard.ibl_health.checked_at)}</span>
              <span className="flex items-center gap-1"><Boxes size={11} /> 액션 {dashboard.ibl_health.action_count}개</span>
              {dashboard.disk_free_gb != null && (
                <span className="flex items-center gap-1"><HardDrive size={11} /> 디스크 {dashboard.disk_free_gb}GB</span>
              )}
              {Object.entries(dashboard.services).map(([k, alive]) => (
                <span key={k} className="flex items-center gap-1">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${alive ? 'bg-emerald-500' : 'bg-stone-300'}`} />
                  {SERVICE_LABELS[k] || k}
                </span>
              ))}
            </div>
          )}

          {healthChecking && (
            <div className="text-[11px] text-stone-500 flex items-center gap-1.5">
              <Loader2 size={12} className="animate-spin" />
              fixture를 실제 실행해 점검 중… 수십 초 걸릴 수 있습니다 (AI 0).
            </div>
          )}
          </div>
          )}
        </div>

        {/* 주행기록계 — 지난 주행 목록 + 분석 스위치 */}
        <EpisodeJournal />

        {/* 조종실 타이틀 + IBL 사전 / IBL이란? — 번역기 바로 위(2026-07-03 헤더에서 이동). 열리는 패널이 이 줄과 번역기 사이에 뜬다. */}
        <div className="flex items-center justify-between gap-2 text-stone-500">
          <span className="text-sm truncate min-w-0">명령을 IBL로 번역·검수해 실행합니다</span>
          <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={() => { setBrowsing((v) => !v); setShowAbout(false); }}
            className={`px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 border transition ${
              browsing ? 'bg-stone-800 text-white border-stone-800' : 'bg-white/70 border-stone-200 text-stone-600 hover:bg-white'
            }`}
          >
            <BookOpen size={13} /> IBL 사전
          </button>
          <button
            onClick={() => { setShowAbout((v) => !v); setBrowsing(false); }}
            className={`px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 border transition ${
              showAbout ? 'bg-stone-800 text-white border-stone-800' : 'bg-white/70 border-stone-200 text-stone-600 hover:bg-white'
            }`}
          >
            <HelpCircle size={13} /> IBL이란?
          </button>
          </div>
        </div>

        {/* IBL이란 무엇인가 — 언어 자체만(어휘·문법·통화). 앱·표면·인프라는 IBL이 아니라 그 위에 지은 것. */}
        {showAbout && (
          <div className="rounded-xl border border-stone-200 bg-white/70 p-4 space-y-4 text-sm text-stone-700 leading-relaxed">
            {/* 본질 */}
            <div>
              <span className="font-semibold text-stone-800">IBL (IndieBiz Logic)</span> 은 indiebizOS의{' '}
              <span className="font-semibold">신경계 역할을 하는 언어</span>입니다.
            </div>
            {/* 세 구성요소 */}
            <div>
              IBL은 세 가지로 이루어집니다 — <span className="font-semibold">어휘</span>(조합 가능한 액션),{' '}
              <span className="font-semibold">문법</span>(쓰고 잇는 규칙), 그리고 <span className="font-semibold">통화</span>(액션 사이를 흐르는 데이터).
            </div>

            {/* 어휘 */}
            <div>
              <div className="font-semibold text-stone-800 mb-1">어휘 — 무엇을 할 수 있나</div>
              <div className="text-[13px]">어휘는 <span className="font-semibold">조합 가능한 액션</span>들입니다. 액션 하나가 IBL이 할 수 있는 일 하나(예: <code className="font-mono">{'[sense:weather]'}</code> — 날씨 조회). 액션들은 다루는 대상에 따라 <span className="font-semibold">6개 노드로 분류</span>됩니다.
                <ul className="mt-1 ml-4 list-disc space-y-0.5">
                  <li><span className="font-mono">sense</span> — 감각: 바깥 정보를 수집·검색 (날씨·주가·뉴스·웹·학술)</li>
                  <li><span className="font-mono">self</span> — 자기: 내 기억·파일·설정·일정</li>
                  <li><span className="font-mono">limbs</span> — 손발: 기기·도구를 조작 (브라우저·화면·음악·폰)</li>
                  <li><span className="font-mono">others</span> — 관계: 이웃·위임·메시징·채널</li>
                  <li><span className="font-mono">engines</span> — 엔진: 콘텐츠를 생성 (슬라이드·영상·이미지·신문·웹)</li>
                  <li><span className="font-mono">table</span> — 표: 통화(데이터)를 변환 (필터·정렬·집계·차트·표·문서)</li>
                </ul>
                <div className="mt-1.5">액션은 셋 중 하나를 합니다 — <span className="font-semibold">생성</span>(통화를 낸다) · <span className="font-semibold">변환</span>(통화를 바꾼다) · <span className="font-semibold">행동</span>(통화를 쓴다 · 세상에 작용).</div>
              </div>
            </div>

            {/* 문법 */}
            <div>
              <div className="font-semibold text-stone-800 mb-1">문법 — 어떻게 쓰고 잇나</div>
              <div className="font-mono text-[12px] bg-stone-100 rounded-md px-2 py-1 inline-block">{'[node:action]{params}'}</div>
              <ul className="mt-1.5 ml-4 list-disc text-[13px] space-y-0.5">
                <li>모든 값은 <code className="font-mono">{'{key: 값}'}</code> 형태. 예: <code className="font-mono">{'[sense:weather]{city: "수원"}'}</code></li>
                <li>한 액션 안의 변형은 <code className="font-mono">op</code> 로: <code className="font-mono">{'[sense:realty]{op: "query", source: "molit"}'}</code></li>
                <li>잇기 — <code className="font-mono">{'>>'}</code> 순차(앞 결과를 뒤로) · <code className="font-mono">&</code> 병렬 · <code className="font-mono">??</code> 폴백</li>
              </ul>
              <div className="mt-2 rounded-lg bg-stone-50 border border-stone-200 p-2.5">
                <div className="font-mono text-[12px] text-stone-700 break-all">{'[sense:realty]{region:"강남구", type:"apt"} >> [table:sort]{by:"meta"} >> [table:take]{n:3}'}</div>
                <div className="mt-1.5 text-[11px] text-stone-500 leading-relaxed">
                  <span className="font-semibold text-stone-600">realty</span>(명사 · 생성)가 강남구 아파트를 <span className="font-semibold">items 통화</span>로 길어오면, <span className="font-semibold text-stone-600">sort</span>·<span className="font-semibold text-stone-600">take</span>(동사 · 변환)가 그 통화를 받아 정렬 → 상위 3개로 줄입니다. 통화가 <code className="font-mono">{'>>'}</code>로 흐릅니다.
                </div>
              </div>
            </div>

            {/* 통화 */}
            <div>
              <div className="font-semibold text-stone-800 mb-1">통화 — 무엇이 흐르나</div>
              <div className="text-[13px]">액션의 출력이 표준 모양이라 한 액션의 결과가 다음 액션으로 <code className="font-mono">{'>>'}</code> 흐릅니다 — 이게 IBL을 낱말이 아니라 <span className="font-semibold">문장</span>으로 만듭니다. 통화는 단 하나, <span className="font-semibold">items</span> 입니다.
                <div className="mt-1.5"><span className="font-semibold">items</span> — 열린 항목들의 목록 <code className="font-mono">{'[{ … }]'}</code>. 가장 흔한 모양은 카드 <code className="font-mono">{'{title, meta, summary, url}'}</code>(검색·매물·뉴스)지만, <span className="font-semibold">같은 items</span>가 통계·시세는 수치 칸을 담은 행(연도·값)으로, 문서는 문단 항목(type·text)으로 흐릅니다.</div>
                <div className="mt-1.5 text-stone-500">통화가 하나라서 어떤 액션의 결과든 어떤 변환자로든 이어집니다 — 받는 쪽이 필요한 모양(표·차트·문서)으로 <span className="font-semibold">알아서</span> 봅니다.</div>
                <div className="mt-1.5"><span className="font-semibold">변환자</span> — 통화를 받아 통화를 내는 특수 액션(거르고 잇고 모음): <span className="font-mono text-[12px]">filter · sort · take · select · dedup · groupby · join · union · merge</span></div>
                <div className="mt-1 text-stone-500">예: <code className="font-mono">{'[sense:search_naver]{query:"AI"} >> filter >> take{n:3}'}</code></div>
              </div>
            </div>
          </div>
        )}

        {/* 발견 레이어(IBL 사전): 노드별 액션 둘러보기 → 클릭하면 명령줄에 씨앗으로 */}
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
                  <div className="space-y-1.5">
                    {g.actions.map((a) => (
                      <div key={a.name} className="px-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <button
                            onClick={() => seedFromAction(g.node, a.name, a.targetKey, a.opDefault || undefined)}
                            title={a.description}
                            className="px-2 py-1 rounded-lg bg-stone-100 hover:bg-stone-200 text-[12px] text-stone-700 font-mono transition"
                          >
                            <span className="text-stone-400">{g.node}:</span>{a.name}
                          </button>
                          {a.ops.length > 0 && <span className="text-[10px] text-stone-400">op:</span>}
                          {a.ops.map((o) => (
                            <button
                              key={o.op}
                              onClick={() => seedFromAction(g.node, a.name, a.targetKey, o.op)}
                              title={o.desc}
                              className="px-1.5 py-0.5 rounded-md bg-amber-50 hover:bg-amber-100 border border-amber-200 text-[11px] text-amber-800 font-mono transition"
                            >
                              {o.op}{o.op === a.opDefault ? '★' : ''}
                            </button>
                          ))}
                        </div>
                        {a.targetDesc && (
                          <div className="text-[10px] text-stone-400 mt-0.5 leading-snug">{a.targetDesc}</div>
                        )}
                      </div>
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
                      {s.param_warning && (
                        <div className="text-xs text-amber-700 mt-0.5">⚠ {s.param_warning}</div>
                      )}
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

        {/* 기억 회상 검증 — 에이전트 0단계(연상)가 주입할 기억(실행기억·심층·포식·디스크골격)을
            실행 없이 미리 본다. 번역기와 같은 형식: 입력 → [회상] → 채널별 원문 표시(가공 없음). */}
        <div className="space-y-3 pt-3 border-t border-stone-200">
          <div className="flex items-center gap-2 text-stone-500">
            <Brain size={15} className="shrink-0" />
            <span className="text-sm truncate">기억 회상 검증 — 이 명령에 무엇이 회상되어 주입되는지 미리 봅니다</span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={recallQuery}
              onChange={(e) => setRecallQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !recalling) handleRecall(); }}
              placeholder="예) 강남구 아파트 실거래가 찾아줘"
              className="flex-1 pl-4 pr-4 py-2.5 rounded-xl border border-stone-300 bg-white text-stone-800 text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
            />
            <button
              onClick={handleRecall}
              disabled={recalling || !recallQuery.trim()}
              className="px-4 py-2 rounded-xl bg-stone-800 text-white text-sm flex items-center gap-1.5 disabled:opacity-40 hover:bg-stone-700 transition shrink-0"
            >
              {recalling ? <Loader2 size={14} className="animate-spin" /> : <Brain size={14} />}
              회상
            </button>
          </div>

          {recallError && <div className="text-xs text-red-600">{recallError}</div>}

          {recallResult && (
            <div className="space-y-2">
              {/* 요약 칩 — 해마 최고점수(0.85↑=반사 경로)와 top 용례, 총 주입량 */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-stone-500">
                <span className={`px-2 py-0.5 rounded ${
                  recallResult.top_score >= 0.85 ? 'bg-emerald-50 text-emerald-700' : 'bg-stone-100 text-stone-600'
                }`}>
                  해마 최고점수 {(recallResult.top_score * 100).toFixed(1)}%
                  {recallResult.top_score >= 0.85 ? ' — 반사(Reflex) 경로' : ''}
                </span>
                {recallResult.top_code && (
                  <code className="text-stone-400 truncate max-w-[50%]">{recallResult.top_code}</code>
                )}
                <span>주입 {recallResult.total_chars.toLocaleString()}자</span>
              </div>
              {recallResult.sections.map((sec) => (
                sec.present ? (
                  <details key={sec.key} open className="rounded-xl border border-stone-200 bg-white/70">
                    <summary className="px-4 py-2.5 text-sm text-stone-700 cursor-pointer select-none">
                      {sec.label}{' '}
                      <span className="text-[11px] text-stone-400">({sec.content.length.toLocaleString()}자)</span>
                    </summary>
                    <pre className="px-4 pb-3 text-[11px] leading-relaxed text-stone-600 whitespace-pre-wrap break-words max-h-72 overflow-y-auto">{sec.content}</pre>
                  </details>
                ) : (
                  <div key={sec.key} className="rounded-xl border border-stone-100 bg-white/40 px-4 py-2 text-[13px] text-stone-400">
                    {sec.label} — 회상 없음
                  </div>
                )
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
