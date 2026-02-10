/**
 * SettingsChannelsTab - 통신채널 설정 탭
 */

import { useEffect, useState } from 'react';
import { Radio, Mail, Globe, ChevronDown, ChevronRight, User } from 'lucide-react';
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

interface SettingsChannelsTabProps {
  show: boolean;
}

export function SettingsChannelsTab({ show }: SettingsChannelsTabProps) {
  const [channels, setChannels] = useState<ChannelSetting[]>([]);
  const [expandedChannel, setExpandedChannel] = useState<string | null>(null);
  const [channelConfigs, setChannelConfigs] = useState<Record<string, any>>({});
  const [isLoadingChannels, setIsLoadingChannels] = useState(false);

  // 소유자 식별 정보
  const [ownerEmails, setOwnerEmails] = useState('');
  const [ownerNostrPubkeys, setOwnerNostrPubkeys] = useState('');
  const [ownerDirty, setOwnerDirty] = useState(false);

  useEffect(() => {
    if (show) {
      loadChannels();
      loadOwnerIdentities();
    }
  }, [show]);

  const loadOwnerIdentities = async () => {
    try {
      const data = await api.getOwnerIdentities();
      setOwnerEmails(data.owner_emails || '');
      setOwnerNostrPubkeys(data.owner_nostr_pubkeys || '');
      setOwnerDirty(false);
    } catch (err) {
      console.error('Failed to load owner identities:', err);
    }
  };

  const saveOwnerIdentities = async () => {
    try {
      await api.updateOwnerIdentities({
        owner_emails: ownerEmails.trim(),
        owner_nostr_pubkeys: ownerNostrPubkeys.trim(),
      });
      setOwnerDirty(false);
    } catch (err) {
      console.error('Failed to save owner identities:', err);
    }
  };

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

  // 로컬 상태만 업데이트 (타이핑 중)
  const handleLocalChannelConfig = (channelType: string, config: any) => {
    setChannelConfigs(prev => ({ ...prev, [channelType]: config }));
  };

  // API에 저장 (onBlur 시)
  const handleSaveChannelConfig = async (channelType: string) => {
    try {
      const config = channelConfigs[channelType];
      if (config) {
        await api.updateChannelSetting(channelType, { config: JSON.stringify(config) });
      }
    } catch (err) {
      console.error('Failed to update channel config:', err);
    }
  };

  // 즉시 저장 (체크박스 등)
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

  return (
    <div className="space-y-4">
      {/* 소유자 식별 정보 */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <User size={16} className="text-[#D97706]" />
          <span className="font-medium text-gray-900 text-sm">소유자 식별 정보</span>
        </div>
        <p className="text-xs text-gray-600">
          외부 채널에서 아래 주소로 오는 메시지만 사용자 명령으로 처리됩니다.
        </p>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            소유자 이메일 (쉼표로 구분)
          </label>
          <input
            type="text"
            value={ownerEmails}
            onChange={(e) => { setOwnerEmails(e.target.value); setOwnerDirty(true); }}
            placeholder="user@gmail.com"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:ring-2 focus:ring-[#D97706] focus:border-transparent"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            소유자 Nostr 주소 (npub, 쉼표로 구분)
          </label>
          <input
            type="text"
            value={ownerNostrPubkeys}
            onChange={(e) => { setOwnerNostrPubkeys(e.target.value); setOwnerDirty(true); }}
            placeholder="npub1..."
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 font-mono focus:ring-2 focus:ring-[#D97706] focus:border-transparent"
          />
        </div>
        {ownerDirty && (
          <button
            onClick={saveOwnerIdentities}
            className="px-4 py-1.5 bg-[#D97706] text-white text-sm rounded-lg hover:bg-[#B45309] transition-colors"
          >
            저장
          </button>
        )}
      </div>

      <p className="text-sm text-gray-700">
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
                      <p className="text-xs text-blue-600 bg-blue-50 p-2 rounded">
                        Gmail API를 사용하여 이메일을 송수신합니다. Google Cloud Console에서 OAuth 2.0 클라이언트를 생성하세요.
                      </p>

                      {/* OAuth 클라이언트 ID */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          OAuth 클라이언트 ID
                        </label>
                        <input
                          type="text"
                          value={channelConfigs.gmail?.client_id || ''}
                          onChange={(e) => handleLocalChannelConfig('gmail', {
                            ...channelConfigs.gmail,
                            client_id: e.target.value
                          })}
                          onBlur={() => handleSaveChannelConfig('gmail')}
                          placeholder="xxxxx.apps.googleusercontent.com"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 text-sm"
                        />
                      </div>

                      {/* OAuth 클라이언트 Secret */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          OAuth 클라이언트 Secret
                        </label>
                        <input
                          type="password"
                          value={channelConfigs.gmail?.client_secret || ''}
                          onChange={(e) => handleLocalChannelConfig('gmail', {
                            ...channelConfigs.gmail,
                            client_secret: e.target.value
                          })}
                          onBlur={() => handleSaveChannelConfig('gmail')}
                          placeholder="GOCSPX-xxxxx"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 text-sm"
                        />
                      </div>

                      {/* 시스템 AI Gmail 주소 */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          시스템 AI Gmail 주소
                        </label>
                        <input
                          type="email"
                          value={channelConfigs.gmail?.email || ''}
                          onChange={(e) => handleLocalChannelConfig('gmail', {
                            ...channelConfigs.gmail,
                            email: e.target.value
                          })}
                          onBlur={() => handleSaveChannelConfig('gmail')}
                          placeholder="system-ai@gmail.com"
                          className="w-full px-3 py-2 bg-white border border-gray-300 rounded-lg focus:border-[#D97706] focus:outline-none text-gray-900 text-sm"
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          시스템 AI가 사용할 Gmail 주소 (인증 시 이 계정으로 로그인)
                        </p>
                      </div>

                      {/* 인증 상태 및 버튼 */}
                      <div className="flex items-center justify-between p-3 bg-gray-100 rounded-lg">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${channelConfigs.gmail?.authenticated ? 'bg-green-500' : 'bg-red-500'}`} />
                          <span className="text-sm text-gray-700">
                            {channelConfigs.gmail?.authenticated ? '인증됨' : '인증 필요'}
                          </span>
                        </div>
                        <button
                          onClick={async () => {
                            try {
                              const result = await api.authenticateGmail();
                              if (result.auth_url) {
                                window.open(result.auth_url, '_blank');
                              }
                              loadChannels();
                            } catch (err) {
                              console.error('Gmail 인증 시작 실패:', err);
                            }
                          }}
                          disabled={!channelConfigs.gmail?.client_id || !channelConfigs.gmail?.client_secret}
                          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                            channelConfigs.gmail?.client_id && channelConfigs.gmail?.client_secret
                              ? 'bg-blue-600 text-white hover:bg-blue-700'
                              : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                          }`}
                        >
                          {channelConfigs.gmail?.authenticated ? '재인증' : 'Google 인증'}
                        </button>
                      </div>

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
                          disabled={channel.enabled !== 1 || !channelConfigs.gmail?.authenticated}
                          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                            channel.enabled === 1 && channelConfigs.gmail?.authenticated
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
                        Nostr는 실시간 WebSocket으로 DM을 수신합니다
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
                            비밀키(nsec)는 절대 타인에게 공유하지 마세요
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
                            relays: e.target.value.split(',').map((r: string) => r.trim()).filter((r: string) => r)
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
  );
}
