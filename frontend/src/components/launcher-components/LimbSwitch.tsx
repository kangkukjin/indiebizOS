/**
 * LimbSwitch — USB 손발(게스트 PC 헬퍼) 발급·승인·폐기 스위치 (조종실 계기)
 *
 * 이건 앱이 아니라 *시스템의 일부*다 — 앱모드 아이콘이 아니라 조종실(ManualMode)의
 * 시스템 컨트롤로 산다(모델 기어 레버·시스템 상태와 같은 자리). USB 를 낯선 PC 에 꽂아
 * 그 PC 를 내 몸의 착탈식 손발로 붙이는 자격을 여기서 발급·관리한다.
 *
 * 어휘: [self:limb]{op: issue/list/revoke/approve}. IBL 실행(api.executeIBL)으로 백엔드
 * 원장(limb_keys.py)을 조작한다 — 별도 REST 없이 어휘 하나로 전 표면이 같은 걸 부른다.
 */
import { useCallback, useEffect, useState } from 'react';
import { Usb, Loader2, Plus, Check, ShieldCheck, Trash2, ChevronDown, ChevronRight } from 'lucide-react';
import { api } from '../../lib/api';

const MANUAL_PROJECT_ID = '수동모드';

interface Limb {
  alias: string;
  device_id: string;
  key_hint?: string;
  connected?: boolean;
  approved?: boolean;
  revoked?: boolean;
  expired?: boolean;
  last_host?: string | null;
  expires_at?: number | null;
}

interface IssueResult {
  alias?: string;
  address?: string;
  payload_dir?: string;
  binary_included?: string[] | null;
  note?: string;
  warning?: string | null;
}

// /ibl/execute 응답 봉투가 중첩될 수 있어, 키를 재귀로 찾는다(엔벨로프에 안 얽매인다).
function deepFind<T = unknown>(obj: unknown, key: string): T | undefined {
  if (!obj || typeof obj !== 'object') return undefined;
  if (key in (obj as Record<string, unknown>)) return (obj as Record<string, T>)[key];
  for (const v of Object.values(obj as Record<string, unknown>)) {
    const hit = deepFind<T>(v, key);
    if (hit !== undefined) return hit;
  }
  return undefined;
}

async function runLimb(op: string, extra: Record<string, unknown> = {}): Promise<unknown> {
  const parts = Object.entries({ op, ...extra })
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? JSON.stringify(v) : v}`)
    .join(', ');
  return api.executeIBL(`[self:limb]{${parts}}`, MANUAL_PROJECT_ID);
}

export function LimbSwitch() {
  const [open, setOpen] = useState(false);
  const [limbs, setLimbs] = useState<Limb[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);   // device_id 진행 표시
  const [err, setErr] = useState<string | null>(null);

  // 발급 폼 — 기본값 = 휴대용(전 OS 동봉·무기한). 이름만 정하면 된다.
  const [alias, setAlias] = useState('');
  const [ttl, setTtl] = useState('');        // 빈값 = 무기한
  const [os, setOs] = useState('');          // 빈값 = 전 OS(휴대용)
  const [issuing, setIssuing] = useState(false);
  const [issued, setIssued] = useState<IssueResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await runLimb('list');
      const rows = deepFind<Limb[]>(res, 'limbs');
      setLimbs(Array.isArray(rows) ? rows : []);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '손발 목록을 불러오지 못했습니다');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  const handleIssue = async () => {
    if (issuing) return;
    setIssuing(true);
    setErr(null);
    setIssued(null);
    try {
      const res = await runLimb('issue', {
        alias: alias.trim() || undefined,
        ttl_days: ttl.trim() ? Number(ttl) : undefined,
        os: os || undefined,
      });
      const address = deepFind<string>(res, 'address');
      const payload_dir = deepFind<string>(res, 'payload_dir');
      const note = deepFind<string>(res, 'note');
      const warning = deepFind<string>(res, 'warning');
      const binary_included = deepFind<string[]>(res, 'binary_included');
      const outAlias = deepFind<string>(res, 'alias');
      setIssued({ alias: outAlias, address, payload_dir, note, warning, binary_included });
      setAlias('');
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : '발급 실패');
    } finally {
      setIssuing(false);
    }
  };

  const rowAction = async (op: string, l: Limb) => {
    setBusy(l.device_id);
    setErr(null);
    try {
      await runLimb(op, { target: l.device_id });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : `${op} 실패`);
    } finally {
      setBusy(null);
    }
  };

  const active = limbs.filter((l) => !l.revoked);
  const connectedCount = active.filter((l) => l.connected).length;

  const statusText = (l: Limb): string => {
    if (l.revoked) return '폐기됨';
    if (l.expired) return '만료';
    if (!l.connected) return '오프라인';
    // 자동승인 — 붙으면 바로 사용 가능. approved=false 는 수동 잠금뿐.
    return l.approved ? '연결됨 · 사용 가능' : '연결됨 · 잠금';
  };

  return (
    <div className="rounded-lg border border-stone-200 bg-white/60 text-[12px]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-stone-600 hover:text-stone-800"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Usb size={14} className="shrink-0" />
        <span className="font-medium">손발 (USB)</span>
        {connectedCount > 0 && (
          <span className="ml-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
            {connectedCount} 연결
          </span>
        )}
        {active.length > 0 && (
          <span className="ml-auto text-[11px] text-stone-400">{active.length}개 발급됨</span>
        )}
      </button>

      {open && (
        <div className="border-t border-stone-100 px-3 py-2.5">
          <p className="mb-2 text-[11px] leading-relaxed text-stone-500">
            USB 를 낯선 PC 에 꽂아 그 PC 에서 셸·파일 작업을 시킵니다. 발급하면 USB 에 담을 폴더가 만들어집니다.
            붙으면 바로 쓸 수 있고(자동 연결), 명령할 땐 <b>손발 이름</b>으로 대상을 부릅니다("사무실PC 에서 …").
            USB 엔 맥 비밀번호가 아니라 폐기 가능한 키 하나만 실립니다.
          </p>

          {/* 발급 폼 */}
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <input
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              placeholder="이름 (예: 사무실PC)"
              className="min-w-0 flex-1 rounded border border-stone-200 px-2 py-1 text-[12px] outline-none focus:border-stone-400"
            />
            <input
              value={ttl}
              onChange={(e) => setTtl(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="무기한"
              className="w-16 rounded border border-stone-200 px-2 py-1 text-center text-[12px] outline-none focus:border-stone-400"
              title="유효기간(일). 비우면 무기한"
            />
            <span className="text-[11px] text-stone-400">일</span>
            <select
              value={os}
              onChange={(e) => setOs(e.target.value)}
              className="rounded border border-stone-200 px-1.5 py-1 text-[12px] outline-none focus:border-stone-400"
              title="어느 PC에 쓸지 — 전체=모든 OS 헬퍼를 한 폴더에(휴대용)"
            >
              <option value="">전체 (휴대용)</option>
              <option value="win">Windows</option>
              <option value="mac">Mac</option>
              <option value="linux">Linux</option>
            </select>
            <button
              onClick={handleIssue}
              disabled={issuing || !alias.trim()}
              title={!alias.trim() ? '손발 이름을 먼저 지어주세요' : '발급'}
              className="flex items-center gap-1 rounded bg-stone-800 px-2.5 py-1 text-[12px] font-medium text-white hover:bg-stone-700 disabled:opacity-50"
            >
              {issuing ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              발급
            </button>
          </div>

          {issued && (
            <div className="mb-2 rounded border border-emerald-200 bg-emerald-50 px-2.5 py-2 text-[11px] leading-relaxed text-emerald-900">
              <div className="font-medium">✅ {issued.alias} 발급 완료</div>
              {issued.payload_dir && (
                <div className="mt-1 break-all">
                  USB 에 이 폴더를 복사하세요:
                  <br />
                  <code className="text-emerald-700">{issued.payload_dir}</code>
                </div>
              )}
              <div className="mt-0.5 text-emerald-700">
                주소: {issued.address || '(미설정)'} ·{' '}
                {issued.binary_included && issued.binary_included.length
                  ? `헬퍼 실행파일 ${issued.binary_included.length}종 동봉(모든 OS)`
                  : '헬퍼 실행파일은 별도 빌드 필요(helper/build.sh)'}
              </div>
              {issued.warning && <div className="mt-1 text-amber-700">⚠ {issued.warning}</div>}
              <div className="mt-1 text-emerald-600">그 PC 에서 헬퍼를 실행하면 자동으로 연결됩니다. 명령할 땐 '{issued.alias}' 이름으로 대상을 부르세요.</div>
            </div>
          )}

          {err && <div className="mb-2 rounded bg-red-50 px-2 py-1 text-[11px] text-red-600">{err}</div>}

          {/* 손발 목록 */}
          {loading ? (
            <div className="flex items-center gap-1.5 py-2 text-stone-400">
              <Loader2 size={13} className="animate-spin" /> 불러오는 중…
            </div>
          ) : active.length === 0 ? (
            <div className="py-1.5 text-[11px] text-stone-400">아직 발급한 손발이 없습니다.</div>
          ) : (
            <ul className="flex flex-col gap-1">
              {active.map((l) => (
                <li
                  key={l.device_id}
                  className="flex items-center gap-2 rounded border border-stone-100 bg-white px-2 py-1.5"
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${l.connected ? 'bg-emerald-500' : 'bg-stone-300'}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-stone-700">{l.alias}</div>
                    <div className="truncate text-[10px] text-stone-400">
                      {statusText(l)}
                      {l.last_host ? ` · ${l.last_host}` : ''}
                    </div>
                  </div>
                  {/* 자동승인이라 평소엔 버튼이 없다. approved=false 는 수동 '잠금'뿐이라 여는 버튼만 둔다. */}
                  {l.connected && !l.approved && (
                    <button
                      onClick={() => rowAction('approve', l)}
                      disabled={busy === l.device_id}
                      className="flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                      title="이 손발을 다시 사용 가능하게 (잠금 해제)"
                    >
                      {busy === l.device_id ? <Loader2 size={12} className="animate-spin" /> : <ShieldCheck size={12} />}
                      열기
                    </button>
                  )}
                  {l.connected && l.approved && (
                    <span className="flex items-center gap-0.5 text-[10px] text-emerald-600">
                      <Check size={12} /> 사용 가능
                    </span>
                  )}
                  <button
                    onClick={() => rowAction('revoke', l)}
                    disabled={busy === l.device_id}
                    className="flex items-center gap-1 rounded border border-stone-200 px-1.5 py-1 text-[11px] text-stone-500 hover:border-red-300 hover:text-red-600 disabled:opacity-50"
                    title="이 키 폐기 (USB 분실 시)"
                  >
                    <Trash2 size={12} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
