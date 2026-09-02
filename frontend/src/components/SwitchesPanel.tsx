/**
 * SwitchesPanel — 스위치 전용 창 (프로젝트별)
 *
 * 프로젝트 창 안의 다이얼로그였던 것을 창으로 승격했다: 창 안 DOM 은 창 밖으로 나갈 수
 * 없어 옮길 수도, 나란히 둘 수도 없었다(2026-09-02 사용자 판정). 창이 되면서 만들기 폼만
 * 있던 판에 **이 프로젝트의 스위치 목록**을 함께 둔다 — 창은 열어두고 쓰는 물건이라
 * 고치기·지우기가 같은 자리에 있어야 한다.
 */

import { useCallback, useState } from 'react';
import { Zap, RefreshCw, Trash2, Pencil, X } from 'lucide-react';
import { api } from '../lib/api';
import { useRetryingLoad } from '../lib/use-retrying-load';
import type { Agent, Switch } from '../types';
import type { SwitchForm } from './manager-dialogs';

const EMPTY_FORM: SwitchForm = { name: '', icon: '⚡', command: '', agentName: '' };

interface SwitchesPanelProps {
  projectId: string;
}

export function SwitchesPanel({ projectId }: SwitchesPanelProps) {
  const [switches, setSwitches] = useState<Switch[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [form, setForm] = useState<SwitchForm>(EMPTY_FORM);
  const [editing, setEditing] = useState<Switch | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadSwitches = useCallback(async () => {
    const all = await api.getSwitches();
    setSwitches(all.filter((sw) => sw.config?.projectId === projectId));
  }, [projectId]);
  const { retry: refreshSwitches } = useRetryingLoad(loadSwitches);

  const loadAgents = useCallback(async () => {
    setAgents(await api.getProjectAgents(projectId));
  }, [projectId]);
  useRetryingLoad(loadAgents);

  const resetForm = () => { setEditing(null); setForm(EMPTY_FORM); };

  const handleSubmit = async () => {
    if (!form.name || !form.command || (!editing && !form.agentName)) {
      setMessage('에이전트·이름·명령어를 모두 채워주세요.');
      return;
    }
    setBusy(true);
    try {
      if (editing) {
        await api.updateSwitch(editing.id, { name: form.name, command: form.command, icon: form.icon });
        setMessage(`'${form.name}' 스위치를 수정했습니다.`);
      } else {
        await api.createSwitch(form.name, form.command, { projectId, agentName: form.agentName }, form.icon);
        setMessage(`'${form.name}' 스위치를 만들었습니다.`);
      }
      resetForm();
      await loadSwitches();
      window.electron?.refreshLauncher();  // 런처의 스위치 아이콘 갱신
    } catch (error) {
      setMessage(`실패: ${error}`);
    } finally {
      setBusy(false);
    }
  };

  const handleEdit = (sw: Switch) => {
    setEditing(sw);
    setForm({
      name: sw.name,
      icon: sw.icon || '⚡',
      command: sw.command,
      agentName: (sw.config?.agent_name as string) || '',
    });
  };

  const handleDelete = async (sw: Switch) => {
    if (!window.confirm(`'${sw.name}' 스위치를 지울까요?`)) return;
    try {
      await api.deleteSwitch(sw.id);
      if (editing?.id === sw.id) resetForm();
      setMessage(`'${sw.name}' 스위치를 지웠습니다.`);
      await loadSwitches();
      window.electron?.refreshLauncher();
    } catch (error) {
      setMessage(`삭제 실패: ${error}`);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 헤더 = 이 창의 이동 손잡이(drag). 버튼은 no-drag 로 빼둔다. */}
      <div className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-gray-200 bg-gray-50 drag">
        <div className="flex items-center gap-2 no-drag">
          <Zap size={16} className="text-[#D97706]" />
          <span className="font-semibold text-gray-800">스위치</span>
          <span className="text-xs text-gray-400">{projectId}</span>
        </div>
        <button
          onClick={() => refreshSwitches()}
          className="no-drag flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          title="새로고침"
        >
          <RefreshCw size={16} />
          <span className="text-sm">새로고침</span>
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* 이 프로젝트의 스위치 목록 */}
        <div className="px-5 pt-4">
          <p className="text-xs text-gray-500 font-medium mb-2">이 프로젝트의 스위치 ({switches.length})</p>
          {switches.length > 0 ? (
            <div className="space-y-1.5">
              {switches.map((sw) => (
                <div
                  key={sw.id}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${
                    editing?.id === sw.id ? 'border-[#D97706] bg-amber-50' : 'border-gray-200 bg-gray-50'
                  }`}
                >
                  <span className="text-lg">{sw.icon || '⚡'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-800 truncate">{sw.name}</div>
                    <div className="text-xs text-gray-400 truncate">{sw.command}</div>
                  </div>
                  <button onClick={() => handleEdit(sw)} className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-500" title="수정">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => handleDelete(sw)} className="p-1.5 rounded-lg hover:bg-red-100 text-red-500" title="삭제">
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400 py-3">아직 스위치가 없습니다.</p>
          )}
        </div>

        {/* 만들기·수정 폼 */}
        <div className="px-5 py-4 mt-4 border-t border-gray-200">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-gray-800">
              {editing ? `⚡ '${editing.name}' 수정` : '⚡ 새 스위치 만들기'}
            </h2>
            {editing && (
              <button onClick={resetForm} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
                <X size={12} /> 수정 취소
              </button>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">에이전트</label>
              <select
                value={form.agentName}
                onChange={(e) => setForm({ ...form, agentName: e.target.value })}
                disabled={!!editing}
                className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 disabled:text-gray-400"
              >
                <option value="">선택하세요</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.name}>{a.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">스위치 이름</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="예: 블로그 보고서"
                className="w-full px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">아이콘 (이모지)</label>
              <input
                type="text"
                value={form.icon}
                onChange={(e) => setForm({ ...form, icon: e.target.value })}
                className="w-24 px-4 py-2.5 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">명령어 (AI에게 보낼 내용)</label>
              <textarea
                value={form.command}
                onChange={(e) => setForm({ ...form, command: e.target.value })}
                placeholder="AI에게 보낼 명령을 입력하세요"
                className="w-full px-4 py-3 bg-gray-50 rounded-lg border border-gray-300 focus:border-orange-500 focus:outline-none text-gray-800 resize-none"
                rows={4}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="shrink-0 flex items-center justify-between gap-3 px-5 py-3 border-t border-gray-200 bg-gray-50">
        <span className="text-xs text-gray-500 truncate">{message}</span>
        <button
          onClick={handleSubmit}
          disabled={busy}
          className="px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309] transition-colors disabled:opacity-50 shrink-0"
        >
          {editing ? '✅ 스위치 수정' : '✅ 스위치 만들기'}
        </button>
      </div>
    </div>
  );
}
