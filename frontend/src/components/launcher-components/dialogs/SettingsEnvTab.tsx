/**
 * SettingsEnvTab - API 키 (.env) 설정 탭
 *
 * .env 파일을 직접 열지 않고 런처에서 키를 확인·수정·테스트한다.
 * 값은 서버에서 마스킹되어 내려오며(비밀키는 끝 4자만), 전체 값은 클라이언트에 절대 오지 않는다.
 * 입력창에 새 값을 넣고 저장하면 해당 줄만 교체된다 (write-only).
 */

import { useCallback, useState } from 'react';
import { KeyRound, ExternalLink, Eye, EyeOff, Save, CheckCircle, AlertCircle, FlaskConical, Loader2, RefreshCw, Plus } from 'lucide-react';
import { useRetryingLoad } from '../../../lib/use-retrying-load';

const API = 'http://127.0.0.1:8765';

interface EnvEntry {
  name: string;
  label: string;
  desc: string;
  signup_url: string;
  secret: boolean;
  restart_required: boolean;
  testable: boolean;
  is_set: boolean;
  masked: string;
  used_by?: {
    actions: { code: string; desc: string }[];
    core_modules: string[];
  };
}

interface EnvGroup {
  key: string;
  label: string;
  entries: EnvEntry[];
}

function openExternalUrl(url: string) {
  const el = (window as any).electron;
  if (el?.openExternal) el.openExternal(url);
  else window.open(url, '_blank', 'noopener');
}

export function SettingsEnvTab({ show }: { show: boolean }) {
  const [groups, setGroups] = useState<EnvGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [savingName, setSavingName] = useState('');
  const [testingName, setTestingName] = useState('');
  const [results, setResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [newName, setNewName] = useState('');
  const [newValue, setNewValue] = useState('');

  // 실패는 throw 되어 useRetryingLoad 가 백오프 재시도한다.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/config/env`);
      const data = await res.json();
      setGroups(data.groups || []);
    } finally {
      setLoading(false);
    }
  }, []);
  const { retry } = useRetryingLoad(load, { enabled: show });

  const saveEntry = async (name: string, value: string) => {
    if (!value.trim()) return;
    setSavingName(name);
    try {
      const res = await fetch(`${API}/config/env`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, value: value.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setResults(prev => ({
          ...prev,
          [name]: {
            ok: true,
            message: data.restart_required ? '저장됨 — 백엔드 재시작 후 반영' : '저장됨 (즉시 반영)',
          },
        }));
        setDrafts(prev => ({ ...prev, [name]: '' }));
        await load().catch(() => {});
      } else {
        setResults(prev => ({ ...prev, [name]: { ok: false, message: data.detail || '저장 실패' } }));
      }
    } catch (e) {
      setResults(prev => ({ ...prev, [name]: { ok: false, message: `저장 실패: ${e}` } }));
    }
    setSavingName('');
  };

  const testEntry = async (name: string) => {
    setTestingName(name);
    try {
      const res = await fetch(`${API}/config/env/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      setResults(prev => ({ ...prev, [name]: { ok: data.ok, message: data.message } }));
    } catch (e) {
      setResults(prev => ({ ...prev, [name]: { ok: false, message: `테스트 실패: ${e}` } }));
    }
    setTestingName('');
  };

  const addNewKey = async () => {
    if (!newName.trim() || !newValue.trim()) return;
    await saveEntry(newName.trim().toUpperCase(), newValue);
    setNewName('');
    setNewValue('');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-base font-bold text-gray-900 mb-1 flex items-center gap-2">
            <KeyRound size={18} className="text-[#D97706]" />
            외부 서비스 API 키
          </h2>
          <p className="text-sm text-gray-700">
            .env 파일을 직접 열지 않고 여기서 키를 확인·수정할 수 있습니다. 값은 마스킹되어 표시되며,
            저장하면 대부분 즉시 반영됩니다 (재시작 필요 항목은 별도 표시).
          </p>
        </div>
        <button
          onClick={retry}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors shrink-0"
          title="새로고침"
        >
          <RefreshCw size={16} className={`text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {groups.map(group => (
        <div key={group.key} className="bg-gray-50 rounded-lg p-4">
          <h3 className="text-sm font-bold text-gray-800 mb-3">{group.label}</h3>
          <div className="space-y-3">
            {group.entries.map(entry => {
              const result = results[entry.name];
              const draft = drafts[entry.name] ?? '';
              return (
                <div key={entry.name} className="bg-white rounded-lg border border-gray-200 p-3">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${entry.is_set ? 'bg-green-500' : 'bg-gray-300'}`}
                      title={entry.is_set ? '설정됨' : '비어 있음'}
                    />
                    <span className="text-sm font-semibold text-gray-900">{entry.label}</span>
                    <span className="text-[11px] font-mono text-gray-400">{entry.name}</span>
                    {entry.restart_required && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded">재시작 필요</span>
                    )}
                    {entry.signup_url && (
                      <button
                        onClick={() => openExternalUrl(entry.signup_url)}
                        className="ml-auto text-[11px] text-[#D97706] hover:underline flex items-center gap-1 shrink-0"
                      >
                        키 발급 <ExternalLink size={11} />
                      </button>
                    )}
                  </div>
                  {entry.desc && <p className="text-xs text-gray-500 mb-1.5">{entry.desc}</p>}
                  {/* 키 → 어휘: 이 키가 없으면 잠자는 IBL 어휘 (코드에서 파생) */}
                  {entry.used_by && entry.used_by.actions.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1 mb-2">
                      <span className={`text-[10px] shrink-0 ${entry.is_set ? 'text-gray-400' : 'text-red-500 font-semibold'}`}>
                        {entry.is_set ? '이 키가 있어야 작동:' : '키가 없어 잠자는 어휘:'}
                      </span>
                      {entry.used_by.actions.slice(0, 8).map(a => (
                        <span
                          key={a.code}
                          title={a.desc}
                          className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${
                            entry.is_set
                              ? 'bg-orange-50 text-orange-800 border-orange-200'
                              : 'bg-red-50 text-red-700 border-red-200'
                          }`}
                        >
                          {a.code}
                        </span>
                      ))}
                      {entry.used_by.actions.length > 8 && (
                        <span className="text-[10px] text-gray-400">+{entry.used_by.actions.length - 8}</span>
                      )}
                    </div>
                  )}
                  {entry.used_by && entry.used_by.actions.length === 0 && entry.used_by.core_modules.length > 0 && (
                    <p className="text-[10px] text-gray-400 mb-2">
                      시스템 코어에서 사용: {entry.used_by.core_modules.join(', ')}
                    </p>
                  )}
                  {entry.used_by && entry.used_by.actions.length === 0 && entry.used_by.core_modules.length === 0 && (
                    <p className="text-[10px] text-gray-400 mb-2">현재 이 키를 쓰는 어휘가 없습니다 (정리 후보)</p>
                  )}
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-gray-400 w-40 truncate shrink-0" title="현재 값 (마스킹)">
                      {entry.is_set ? entry.masked : '(비어 있음)'}
                    </span>
                    <div className="flex-1 relative">
                      <input
                        type={entry.secret && !reveal[entry.name] ? 'password' : 'text'}
                        value={draft}
                        onChange={e => setDrafts(prev => ({ ...prev, [entry.name]: e.target.value }))}
                        placeholder="새 값 입력…"
                        className="w-full px-2.5 py-1.5 pr-8 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-[#D97706] font-mono"
                      />
                      {entry.secret && (
                        <button
                          onClick={() => setReveal(prev => ({ ...prev, [entry.name]: !prev[entry.name] }))}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                        >
                          {reveal[entry.name] ? <EyeOff size={13} /> : <Eye size={13} />}
                        </button>
                      )}
                    </div>
                    <button
                      onClick={() => saveEntry(entry.name, draft)}
                      disabled={!draft.trim() || savingName === entry.name}
                      className="px-2.5 py-1.5 text-xs bg-[#D97706] text-white rounded-md hover:bg-[#B45309] disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 shrink-0"
                    >
                      {savingName === entry.name ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                      저장
                    </button>
                    {entry.testable && (
                      <button
                        onClick={() => testEntry(entry.name)}
                        disabled={!entry.is_set || testingName === entry.name}
                        className="px-2.5 py-1.5 text-xs border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 disabled:opacity-40 flex items-center gap-1 shrink-0"
                        title="저장된 키로 서비스에 실제 요청을 보내 인증을 확인합니다"
                      >
                        {testingName === entry.name ? <Loader2 size={12} className="animate-spin" /> : <FlaskConical size={12} />}
                        테스트
                      </button>
                    )}
                  </div>
                  {result && (
                    <div className={`mt-2 text-xs flex items-center gap-1.5 ${result.ok ? 'text-green-600' : 'text-red-600'}`}>
                      {result.ok ? <CheckCircle size={13} /> : <AlertCircle size={13} />}
                      {result.message}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* 새 키 추가 */}
      <div className="bg-gray-50 rounded-lg p-4">
        <h3 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-1.5">
          <Plus size={14} /> 새 키 추가
        </h3>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newName}
            onChange={e => setNewName(e.target.value.toUpperCase())}
            placeholder="KEY_NAME (대문자·숫자·_)"
            className="w-64 px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-[#D97706] font-mono"
          />
          <input
            type="text"
            value={newValue}
            onChange={e => setNewValue(e.target.value)}
            placeholder="값"
            className="flex-1 px-2.5 py-1.5 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-[#D97706] font-mono"
          />
          <button
            onClick={addNewKey}
            disabled={!newName.trim() || !newValue.trim()}
            className="px-2.5 py-1.5 text-xs bg-[#D97706] text-white rounded-md hover:bg-[#B45309] disabled:opacity-40 flex items-center gap-1"
          >
            <Save size={12} /> 추가
          </button>
        </div>
      </div>
    </div>
  );
}
