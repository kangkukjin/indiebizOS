/**
 * ModelGearLever - 모델 기어(계기판 변속 레버) + 설정(프리셋 편집·에이전트 핀)
 *
 * 계기판(ManualMode)의 조작 계기. 레버 하나(절약/균형/최대)로 시스템 전체 모델 등급을 바꾼다.
 * ⚙ 설정에서:
 *   - 프리셋 편집: 각 기어가 4축(분류·평가·실행·의식)을 어느 티어(경량/중급/고급)로 매핑하는지
 *   - 에이전트 핀: 특정 에이전트만 기어 무시하고 티어 고정
 * 변속·편집은 재시작 없이 다음 작업부터 반영(백엔드 리졸버 핫리로드).
 * 티어별 *모델*은 설정 → 모델 설정의 경량·중급·고급 슬롯에서.
 */

import { useEffect, useState } from 'react';
import { Gauge, Loader2, Settings2, Save, Check } from 'lucide-react';
import { api } from '../../lib/api';

interface GearState {
  current_gear: string;
  gears: string[];
  presets: Record<string, Record<string, string>>;
  axes: Record<string, { tier: string; provider: string; model: string }>;
  tiers?: string[];
  axis_names?: string[];
}

interface AgentInfo { id: string; name: string; project: string; }

const GEAR_DESC: Record<string, string> = {
  절약: '전부 경량 — 가장 빠르고 저렴',
  균형: '실행·의식 중급 — 기본',
  최대: '실행·의식 고급 — 최고 품질',
};
const AXES = ['분류', '평가', '실행', '의식'];
const TIERS = ['경량', '중급', '고급'];

export function ModelGearLever() {
  const [gear, setGear] = useState<GearState | null>(null);
  const [changing, setChanging] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // 프리셋 편집 드래프트
  const [draftPresets, setDraftPresets] = useState<Record<string, Record<string, string>>>({});
  const [savingPresets, setSavingPresets] = useState(false);
  const [presetsSaved, setPresetsSaved] = useState(false);

  // 에이전트 핀
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [savingPin, setSavingPin] = useState<string | null>(null);

  const load = async () => {
    try { setGear(await api.getModelGear()); } catch (e) { console.error('Failed to load gear:', e); }
  };
  useEffect(() => { load(); }, []);

  // 설정 패널 열 때 프리셋 드래프트 + 핀 현황 로드
  useEffect(() => {
    if (!showSettings) return;
    if (gear?.presets) setDraftPresets(JSON.parse(JSON.stringify(gear.presets)));
    api.getModelGearOverrides()
      .then((r) => { setAgents(r.agents); setOverrides(r.overrides || {}); })
      .catch((e) => console.error('Failed to load overrides:', e));
  }, [showSettings, gear?.presets]);

  const change = async (name: string) => {
    if (changing || gear?.current_gear === name) return;
    setChanging(true);
    try { setGear(await api.setModelGear(name)); } catch (e) { console.error('Failed to set gear:', e); }
    setChanging(false);
  };

  const setDraftCell = (g: string, axis: string, tier: string) => {
    setDraftPresets((prev) => ({ ...prev, [g]: { ...(prev[g] || {}), [axis]: tier } }));
    setPresetsSaved(false);
  };

  const savePresets = async () => {
    setSavingPresets(true);
    try {
      const r = await api.updateModelGearPresets(draftPresets);
      setGear(r);
      setPresetsSaved(true);
      setTimeout(() => setPresetsSaved(false), 2000);
    } catch (e) { console.error('Failed to save presets:', e); }
    setSavingPresets(false);
  };

  const setPin = async (agentId: string, tier: string) => {
    setSavingPin(agentId);
    const next = { ...overrides };
    if (tier) next[agentId] = tier; else delete next[agentId];
    try {
      const r = await api.updateModelGearOverrides(next);
      setOverrides(r.overrides || {});
    } catch (e) { console.error('Failed to set pin:', e); }
    setSavingPin(null);
  };

  const gears = gear?.gears ?? ['절약', '균형', '최대'];
  const tiers = gear?.tiers ?? TIERS;
  const axes = gear?.axis_names ?? AXES;

  return (
    <div className="rounded-xl border border-stone-200 bg-white/70 p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-stone-700 flex items-center gap-1.5">
          <Gauge size={14} /> 모델 기어
        </span>
        <div className="flex items-center gap-2">
          {changing && <Loader2 size={13} className="animate-spin text-stone-400" />}
          <button
            onClick={() => setShowSettings((v) => !v)}
            title="기어 프리셋 편집 · 에이전트 핀"
            className={`px-2 py-1 rounded-lg text-xs flex items-center gap-1 border transition-colors ${
              showSettings ? 'bg-stone-800 text-white border-stone-800' : 'bg-white border-stone-200 text-stone-500 hover:border-stone-400'
            }`}
          >
            <Settings2 size={12} /> 설정
          </button>
        </div>
      </div>

      {/* 절약 / 균형 / 최대 레버 */}
      <div className="grid grid-cols-3 gap-2">
        {gears.map((g) => {
          const active = gear?.current_gear === g;
          return (
            <button
              key={g}
              onClick={() => change(g)}
              disabled={changing}
              className={`px-3 py-2.5 rounded-lg border text-center transition-colors disabled:opacity-60 ${
                active
                  ? 'bg-stone-800 border-stone-800 text-white shadow'
                  : 'bg-white border-stone-200 text-stone-700 hover:border-stone-400'
              }`}
            >
              <div className="text-sm font-bold">{g}</div>
              <div className={`text-[10.5px] mt-0.5 leading-tight ${active ? 'text-white/80' : 'text-stone-400'}`}>
                {GEAR_DESC[g] ?? ''}
              </div>
            </button>
          );
        })}
      </div>

      {/* 현재 기어의 4축 → 티어 요약 */}
      {gear?.axes && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-stone-500 pt-1 border-t border-stone-100">
          {Object.entries(gear.axes).map(([axis, info]) => (
            <span key={axis} className="flex items-center gap-1">
              <span className="text-stone-400">{axis}</span>
              <span className="text-stone-700 font-medium">{info.tier}</span>
            </span>
          ))}
          <span className="text-stone-300">·</span>
          <span className="text-stone-400">티어별 모델은 설정 → 모델 설정</span>
        </div>
      )}

      {/* ⚙ 설정 패널 — 프리셋 편집 + 에이전트 핀 */}
      {showSettings && (
        <div className="space-y-5 pt-3 border-t border-stone-200">
          {/* 1. 프리셋 편집기 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-stone-600">기어 프리셋 — 각 기어가 4축을 어느 티어로</span>
              <button
                onClick={savePresets}
                disabled={savingPresets}
                className="px-2.5 py-1 rounded-lg text-[11px] flex items-center gap-1 border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 disabled:opacity-50"
              >
                {savingPresets ? <Loader2 size={11} className="animate-spin" /> : presetsSaved ? <Check size={11} className="text-emerald-600" /> : <Save size={11} />}
                {presetsSaved ? '저장됨' : '저장'}
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] border-collapse">
                <thead>
                  <tr className="text-stone-400">
                    <th className="text-left font-medium py-1 pr-2">기어</th>
                    {axes.map((axis) => <th key={axis} className="font-medium py-1 px-1 text-center">{axis}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(draftPresets).map((g) => (
                    <tr key={g} className="border-t border-stone-100">
                      <td className="py-1 pr-2 font-semibold text-stone-700 whitespace-nowrap">{g}</td>
                      {axes.map((axis) => (
                        <td key={axis} className="py-1 px-1">
                          <select
                            value={draftPresets[g]?.[axis] ?? ''}
                            onChange={(e) => setDraftCell(g, axis, e.target.value)}
                            className="w-full px-1 py-1 bg-white border border-stone-200 rounded text-stone-700 text-[11px] focus:border-stone-400 focus:outline-none"
                          >
                            {tiers.map((t) => <option key={t} value={t}>{t}</option>)}
                          </select>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 2. 에이전트 핀 */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-stone-600">에이전트 핀 — 특정 에이전트만 기어 무시·고정</span>
            <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
              {agents.map((a) => (
                <div key={a.id} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="min-w-0 flex-1 text-[12px] text-stone-700 truncate">
                    {a.name}
                    <span className="text-stone-400 text-[10.5px] ml-1">{a.project}</span>
                  </span>
                  <div className="flex items-center gap-1 shrink-0">
                    {savingPin === a.id && <Loader2 size={11} className="animate-spin text-stone-400" />}
                    <select
                      value={overrides[a.id] ?? ''}
                      onChange={(e) => setPin(a.id, e.target.value)}
                      disabled={savingPin === a.id}
                      className={`px-1.5 py-1 border rounded text-[11px] focus:outline-none ${
                        overrides[a.id]
                          ? 'bg-amber-50 border-amber-300 text-amber-800 font-medium'
                          : 'bg-white border-stone-200 text-stone-500'
                      }`}
                    >
                      <option value="">기어 따름</option>
                      {tiers.map((t) => <option key={t} value={t}>📌 {t} 고정</option>)}
                    </select>
                  </div>
                </div>
              ))}
              {agents.length === 0 && (
                <div className="text-[11px] text-stone-400 flex items-center gap-1.5 py-2">
                  <Loader2 size={11} className="animate-spin" /> 에이전트 목록 불러오는 중…
                </div>
              )}
            </div>
            <p className="text-[10.5px] text-stone-400">📌 고정된 에이전트는 기어를 바꿔도 그 티어를 유지합니다.</p>
          </div>
        </div>
      )}
    </div>
  );
}
