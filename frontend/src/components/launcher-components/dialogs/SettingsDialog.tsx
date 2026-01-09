/**
 * SettingsDialog - 시스템 설정 다이얼로그
 */

import { useEffect, useState } from 'react';
import { X, Settings, Brain, Eye, EyeOff, Save, Radio, Mail, Globe, ChevronDown, ChevronRight } from 'lucide-react';
import type { SystemAISettings } from '../types';
import { api } from '../../../lib/api';

interface ChannelSetting {
  id: number;
  channel_type: string;
  enabled: number;
  config: string;
  polling_interval: number;
  last_poll_at: string | null;
  updated_at: string;
}

interface SettingsDialogProps {
  show: boolean;
  settings: SystemAISettings;
  showApiKey: boolean;
  onSettingsChange: (settings: SystemAISettings) => void;
  onToggleApiKey: () => void;
  onSave: () => void;
  onClose: () => void;
}

export function SettingsDialog({
  show,
  settings,
  showApiKey,
  onSettingsChange,
  onToggleApiKey,
  onSave,
  onClose,
}: SettingsDialogProps) {
  const [activeTab, setActiveTab] = useState<'ai' | 'channels'>('ai');
  const [channels, setChannels] = useState<ChannelSetting[]>([]);
  const [expandedChannel, setExpandedChannel] = useState<string | null>(null);
  const [channelConfigs, setChannelConfigs] = useState<Record<string, any>>({});
  const [isLoadingChannels, setIsLoadingChannels] = useState(false);

  // 통신채널 설정 로드
  useEffect(() => {
    if (show && activeTab === 'channels') {
      loadChannels();
    }
  }, [show, activeTab]);

  const loadChannels = async () => {
    try {
      setIsLoadingChannels(true);
      const data = await api.getChannelSettings();
      setChannels(data);
      // config JSON 파싱
      const configs: Record<string, any> = {};
      data.forEach(ch => {
        try {
          configs[ch.channel_type] = JSON.parse(ch.config || '{}');
        } catch {
          configs[ch.channel_type] = {};
        }
      });
      setChannelConfigs(configs);
    } catch (err) {
      console.error('Failed to load channels:', err);
    } finally {
      setIsLoadingChannels(false);
    }
  };

  const handleToggleChannel = async (channelType: string, enabled: boolean) => {
    try {
      await api.updateChannelSetting(channelType, { enabled });
      setChannels(prev => prev.map(ch =>
        ch.channel_type === channelType ? { ...ch, enabled: enabled ? 1 : 0 } : ch
      ));
    } catch (err) {
      console.error('Failed to toggle channel:', err);
    }
  };

  const handleUpdateChannelConfig = async (channelType: string, config: any) => {
    try {
      await api.updateChannelSetting(channelType, { config: JSON.stringify(config) });
      setChannelConfigs(prev => ({ ...prev, [channelType]: config }));
    } catch (err) {
      console.error('Failed to update channel config:', err);
    }
  };

  const handleUpdatePollingInterval = async (channelType: string, interval: number) => {
    try {
      await api.updateChannelSetting(channelType, { polling_interval: interval });
      setChannels(prev => prev.map(ch =>
        ch.channel_type === channelType ? { ...ch, polling_interval: interval } : ch
      ));
    } catch (err) {
      console.error('Failed to update polling interval:', err);
    }
  };

  const getChannelIcon = (type: string) => {
    switch (type) {
      case 'gmail': return <Mail size={18} className="text-red-500" />;
      case 'nostr': return <Globe size={18} className="text-purple-500" />;
      default: return <Radio size={18} className="text-gray-500" />;
    }
  };

  const getChannelLabel = (type: string) => {
    switch (type) {
      case 'gmail': return 'Gmail';
      case 'nostr': return 'Nostr';
      default: return type;
    }
  };

  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(600px, 90vw)',
          height: 'min(550px, 85vh)',
          minWidth: '350px',
          minHeight: '400px',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <Settings size={24} className="text-gray-600" />
            <h2 className="text-xl font-bold text-gray-800">설정</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 탭 */}
        <div className="flex border-b border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={() => setActiveTab('ai')}
            className={`flex-1 py-3 text-sm font-medium transition-colors ${
              activeTab === 'ai'
                ? 'text-[#D97706] border-b-2 border-[#D97706] bg-white'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Brain size={16} />
              시스템 AI
            </div>
          </button>
          <button
            onClick={() => setActiveTab('channels')}
            className={`flex-1 py-3 text-sm font-medium transition-colors ${
              activeTab === 'channels'
                ? 'text-[#D97706] border-b-2 border-[#D97706] bg-white'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center justify-center gap-2">
              <Radio size={16} />
              통신채널
            </div>
          </button>
        </div>

        {/* 내용 */}
        <div className="flex-1 overflow-auto p-6">
          {activeTab === 'ai' && (
            <div className="space-y-6">
              <div>
                <p className="text-sm text-gray-700 mb-4">
                  프로그램 전체에서 사용하는 AI 설정입니다. 프로젝트 시작 시 에이전트들의 도구를 배분하거나 자동 프롬프트 생성에 활용됩니다.
                </p>
              </div>

              <div className="bg-gray-50 rounded-lg p-5 space-y-4">
                {/* 제공자 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">AI 제공자</label>
                  <select
                    value={settings.provider}
                    onChange={(e) => onSettingsChange({ ...settings, provider: e.target.value })}
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                  >
                    <option value="google">Google (Gemini)</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                  </select>
                </div>

                {/* 모델 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">모델</label>
                  <input
                    type="text"
                    value={settings.model}
                    onChange={(e) => onSettingsChange({ ...settings, model: e.target.value })}
                    placeholder="gemini-2.0-flash-exp"
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                  />
                </div>

                {/* API 키 */}
                <div>
                  <label className="block text-sm font-semibold text-gray-900 mb-1">API 키</label>
                  <div className="flex gap-2">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={settings.apiKey}
                      onChange={(e) => onSettingsChange({ ...settings, apiKey: e.target.value })}
                      placeholder="API 키를 입력하세요"
                      className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 placeholder:text-gray-500"
                    />
                    <button
                      onClick={onToggleApiKey}
                      className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700"
                    >
                      {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'channels' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-700 mb-4">
                비즈니스 메시지 수신을 위한 통신채널 설정입니다. 활성화된 채널은 주기적으로 메시지를 확인합니다.
              </p>

              {isLoadingChannels ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#D97706]" />
                </div>
              ) : channels.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  설정된 통신채널이 없습니다
                </div>
              ) : (
                <div className="space-y-3">
                  {channels.map(channel => (
                    <div key={channel.channel_type} className="bg-gray-50 rounded-lg overflow-hidden">
                      {/* 채널 헤더 */}
                      <div
                        className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-100"
                        onClick={() => setExpandedChannel(
                          expandedChannel === channel.channel_type ? null : channel.channel_type
                        )}
                      >
                        <div className="flex items-center gap-3">
                          {expandedChannel === channel.channel_type
                            ? <ChevronDown size={16} className="text-gray-400" />
                            : <ChevronRight size={16} className="text-gray-400" />
                          }
                          {getChannelIcon(channel.channel_type)}
                          <span className="font-medium text-gray-900">
                            {getChannelLabel(channel.channel_type)}
                          </span>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer" onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={channel.enabled === 1}
                            onChange={(e) => handleToggleChannel(channel.channel_type, e.target.checked)}
                            className="sr-only peer"
                          />
                          <div className="w-11 h-6 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#D97706]"></div>
                        </label>
                      </div>

                      {/* 채널 상세 설정 */}
                      {expandedChannel === channel.channel_type && (
                        <div className="px-4 pb-4 space-y-4 border-t border-gray-200 pt-4">
                          {/* Gmail 설정 */}
                          {channel.channel_type === 'gmail' && (
                            <>
                              {/* 폴링 주기 */}
                              <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                  폴링 주기 (초)
                                </label>
                                <input
                                  type="number"
                                  value={channel.polling_interval}
                                  onChange={(e) => handleUpdatePollingInterval(channel.channel_type, parseInt(e.target.value) || 60)}
                                  min={10}
                                  max={3600}
                                  className="w-32 px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900"
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                  최소 10초, 최대 3600초 (1시간)
                                </p>
                              </div>
                              <p className="text-xs text-blue-600 bg-blue-50 p-2 rounded">
                                📧 읽지 않은 모든 이메일을 비즈니스 메시지로 수신합니다
                              </p>
                              {/* 즉시 확인 버튼 */}
                              <div className="flex items-center justify-between">
                                <button
                                  onClick={async () => {
                                    try {
                                      await api.pollChannelNow(channel.channel_type);
                                      loadChannels();
                                    } catch (err) {
                                      console.error('즉시 폴링 실패:', err);
                                    }
                                  }}
                                  disabled={channel.enabled !== 1}
                                  className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                                    channel.enabled === 1
                                      ? 'bg-[#D97706] text-white hover:bg-[#B45309]'
                                      : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                                  }`}
                                >
                                  지금 확인
                                </button>
                                {channel.last_poll_at && (
                                  <p className="text-xs text-gray-500">
                                    마지막 확인: {new Date(channel.last_poll_at).toLocaleString('ko-KR')}
                                  </p>
                                )}
                              </div>
                            </>
                          )}

                          {/* Nostr 설정 */}
                          {channel.channel_type === 'nostr' && (
                            <>
                              <p className="text-xs text-purple-600 bg-purple-50 p-2 rounded">
                                ⚡ Nostr는 실시간 WebSocket으로 DM을 수신합니다
                              </p>

                              {/* 내 주소 (npub) 표시 */}
                              <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                  내 Nostr 주소 (npub)
                                </label>
                                {channelConfigs.nostr?.npub ? (
                                  <div className="flex gap-2">
                                    <input
                                      type="text"
                                      value={channelConfigs.nostr?.npub || ''}
                                      readOnly
                                      className="flex-1 px-3 py-2 bg-gray-100 border border-gray-300 rounded-lg text-gray-700 font-mono text-xs"
                                    />
                                    <button
                                      onClick={() => {
                                        navigator.clipboard.writeText(channelConfigs.nostr?.npub || '');
                                      }}
                                      className="px-3 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-gray-700 text-sm"
                                    >
                                      복사
                                    </button>
                                  </div>
                                ) : (
                                  <p className="text-sm text-gray-500">채널을 활성화하면 자동 생성됩니다</p>
                                )}
                              </div>

                              {/* 키 가져오기 (접힘) */}
                              <details className="text-sm">
                                <summary className="cursor-pointer text-gray-600 hover:text-gray-900">
                                  다른 키로 변경하기
                                </summary>
                                <div className="mt-2 p-3 bg-gray-50 rounded-lg space-y-2">
                                  <input
                                    type="password"
                                    placeholder="nsec1... 또는 hex 형식의 비밀키 입력"
                                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 font-mono text-xs"
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter') {
                                        const input = e.target as HTMLInputElement;
                                        if (input.value.trim()) {
                                          handleUpdateChannelConfig('nostr', {
                                            ...channelConfigs.nostr,
                                            nsec: input.value.trim(),
                                            npub: '', // 리셋하여 새로 생성되도록
                                            private_key_hex: ''
                                          });
                                          input.value = '';
                                        }
                                      }
                                    }}
                                  />
                                  <p className="text-xs text-red-500">
                                    ⚠️ 비밀키(nsec)는 절대 타인에게 공유하지 마세요
                                  </p>
                                </div>
                              </details>

                              {/* 릴레이 서버 */}
                              <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                  릴레이 서버
                                </label>
                                <input
                                  type="text"
                                  value={(channelConfigs.nostr?.relays || []).join(', ')}
                                  onChange={(e) => handleUpdateChannelConfig('nostr', {
                                    ...channelConfigs.nostr,
                                    relays: e.target.value.split(',').map(r => r.trim()).filter(r => r)
                                  })}
                                  placeholder="wss://relay.damus.io, wss://nos.lol"
                                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 font-mono text-xs"
                                />
                              </div>

                              {/* 연결 상태 */}
                              <div className="flex items-center gap-2">
                                <div className={`w-2 h-2 rounded-full ${channel.enabled === 1 ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
                                <span className="text-sm text-gray-600">
                                  {channel.enabled === 1 ? '실시간 연결 중' : '비활성화됨'}
                                </span>
                              </div>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 푸터 */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 transition-colors text-gray-700"
          >
            취소
          </button>
          {activeTab === 'ai' && (
            <button
              onClick={onSave}
              className="flex items-center gap-2 px-4 py-2 bg-[#D97706] text-white rounded-lg hover:bg-[#B45309]"
            >
              <Save size={16} />
              저장
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
