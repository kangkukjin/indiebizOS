/**
 * API 클라이언트
 *
 * 코어 + 도메인별 mixin 구성:
 *   api-system-ai.ts  - 시스템 AI (설정, 프롬프트, 대화, Todo, 질문, 계획)
 *   api-indienet.ts   - IndieNet (상태, 게시, DM, 보드)
 *   api-packages.ts   - 도구 패키지 (CRUD, 분석, Nostr)
 *   api-business.ts   - 비즈니스 (관리, 이웃, 메시지, 자동응답, 통신채널)
 *   api-multi-chat.ts - 다중채팅 (방, 참가자, 메시지)
 */

import type { Project, Switch, Agent, Message, Tool, SchedulerTask, SchedulerAction } from '../types';
import { applySystemAIMethods } from './api-system-ai';
import { applyIndieNetMethods } from './api-indienet';
import { applyPackagesMethods } from './api-packages';
import { applyBusinessMethods } from './api-business';
import { applyMultiChatMethods } from './api-multi-chat';

const API_BASE = 'http://127.0.0.1:8765';

class APIClientBase {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      // error.detail이 객체일 수 있으므로 문자열로 변환
      const detail = error.detail;
      let errorMessage: string;
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (typeof detail === 'object' && detail !== null) {
        errorMessage = detail.msg || detail.message || JSON.stringify(detail);
      } else {
        errorMessage = error.message || 'API Error';
      }
      throw new Error(errorMessage);
    }

    return response.json();
  }

  // 헬스 체크
  async health() {
    return this.request<{ status: string; timestamp: string }>('/health');
  }

  // ============ 프로젝트 ============

  async getProjects() {
    const data = await this.request<{ projects: Project[] }>('/projects');
    return data.projects;
  }

  async createProject(name: string, templateName = '기본', parentFolder?: string) {
    return this.request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify({
        name,
        template_name: templateName,
        parent_folder: parentFolder,
      }),
    });
  }

  async deleteProject(projectId: string, permanent = false) {
    return this.request<{ status: string }>(`/projects/${projectId}?permanent=${permanent}`, {
      method: 'DELETE',
    });
  }

  async updateProjectPosition(projectId: string, x: number, y: number) {
    return this.request<{ status: string }>(`/projects/${projectId}/position`, {
      method: 'PUT',
      body: JSON.stringify({ x, y }),
    });
  }

  async getProjectAgents(projectId: string) {
    const data = await this.request<{ agents: Agent[] }>(`/projects/${projectId}/agents`);
    return data.agents;
  }

  // ============ 폴더 ============

  async createFolder(name: string, parentFolder?: string) {
    return this.request<Project>('/folders', {
      method: 'POST',
      body: JSON.stringify({
        name,
        parent_folder: parentFolder,
      }),
    });
  }

  async getFolderItems(folderId: string) {
    const data = await this.request<{ items: Project[] }>(`/folders/${folderId}/items`);
    return data.items;
  }

  async moveItem(itemId: string, folderId?: string) {
    return this.request<{ status: string }>(`/items/${itemId}/move?folder_id=${folderId || ''}`, {
      method: 'POST',
    });
  }

  // ============ 휴지통 ============

  async getTrash() {
    return this.request<{
      items: unknown[];
      projects: Project[];
      switches: Switch[];
      chat_rooms: Array<{ id: string; name: string; type: 'chat_room'; description?: string }>;
    }>('/trash');
  }

  async restoreFromTrash(itemId: string, itemType: 'project' | 'switch' | 'chat_room' = 'project') {
    return this.request<{ status: string; item: unknown }>(`/trash/${itemId}/restore?item_type=${itemType}`, {
      method: 'POST',
    });
  }

  async emptyTrash() {
    return this.request<{ status: string }>('/trash', {
      method: 'DELETE',
    });
  }

  async moveProjectToTrash(projectId: string) {
    return this.request<{ status: string; item: Project }>(`/projects/${projectId}/trash`, {
      method: 'POST',
    });
  }

  async moveSwitchToTrash(switchId: string) {
    return this.request<{ status: string; item: Switch }>(`/switches/${switchId}/trash`, {
      method: 'POST',
    });
  }

  // ============ 이름 변경 ============

  async renameProject(projectId: string, newName: string) {
    return this.request<{ status: string; item: Project }>(`/projects/${projectId}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ new_name: newName }),
    });
  }

  async renameSwitch(switchId: string, newName: string) {
    return this.request<{ status: string; item: Switch }>(`/switches/${switchId}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ new_name: newName }),
    });
  }

  // ============ 복사 ============

  async copyProject(projectId: string, newName?: string, parentFolder?: string) {
    const body: Record<string, string | undefined> = {};
    if (newName) body.new_name = newName;
    if (parentFolder) body.parent_folder = parentFolder;

    return this.request<{ status: string; item: Project }>(`/projects/${projectId}/copy`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async copySwitch(switchId: string) {
    return this.request<{ status: string; item: Switch }>(`/switches/${switchId}/copy`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  // ============ 스위치 ============

  async getSwitches() {
    const data = await this.request<{ switches: Switch[] }>('/switches');
    return data.switches;
  }

  async createSwitch(
    name: string,
    command: string,
    config: Record<string, unknown>,
    icon = '⚡',
    description = ''
  ) {
    return this.request<Switch>('/switches', {
      method: 'POST',
      body: JSON.stringify({ name, command, config, icon, description }),
    });
  }

  async updateSwitch(
    switchId: string,
    updates: {
      name?: string;
      command?: string;
      icon?: string;
      description?: string;
    }
  ) {
    return this.request<{ status: string; switch: Switch }>(`/switches/${switchId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteSwitch(switchId: string) {
    return this.request<{ status: string }>(`/switches/${switchId}`, {
      method: 'DELETE',
    });
  }

  async executeSwitch(switchId: string) {
    return this.request<{ status: string }>(`/switches/${switchId}/execute`, {
      method: 'POST',
    });
  }

  async updateSwitchPosition(switchId: string, x: number, y: number) {
    return this.request<{ status: string }>(`/switches/${switchId}/position`, {
      method: 'PUT',
      body: JSON.stringify({ x, y }),
    });
  }

  // ============ 템플릿 ============

  async getTemplates() {
    const data = await this.request<{ templates: string[] }>('/templates');
    return data.templates;
  }

  // ============ 대화 ============

  async getConversations(projectId: string) {
    const data = await this.request<{ conversations: Agent[] }>(`/conversations/${projectId}`);
    return data.conversations;
  }

  async getMessages(projectId: string, agentId: number, limit = 50, offset = 0) {
    const data = await this.request<{ messages: Message[] }>(
      `/conversations/${projectId}/${agentId}/messages?limit=${limit}&offset=${offset}`
    );
    return data.messages;
  }

  async getUndeliveredMessages(projectId: string, agentName: string) {
    const data = await this.request<{
      messages: Array<{
        id: number;
        from_agent_id: number;
        to_agent_id: number;
        content: string;
        timestamp: string;
      }>;
    }>(`/conversations/${projectId}/${encodeURIComponent(agentName)}/undelivered`);
    return data.messages;
  }

  // ============ 도구 ============

  async getTools() {
    const data = await this.request<{ tools: Tool[]; base_tools: string[] }>('/tools');
    return data;
  }

  // 도구 AI 설정 조회
  async getToolSettings() {
    const data = await this.request<{ settings: Record<string, { report_ai?: { provider: string; model: string; api_key: string } }> }>('/tool-settings');
    return data.settings;
  }

  // 특정 도구 AI 설정 조회
  async getToolSetting(toolKey: string) {
    const data = await this.request<{ tool_key: string; settings: { provider: string; model: string; api_key: string } }>(`/tool-settings/${toolKey}`);
    return data.settings;
  }

  // 도구 AI 설정 저장
  async updateToolSetting(toolKey: string, settings: { provider: string; model: string; api_key: string }) {
    return this.request<{ status: string; message: string }>(`/tool-settings/${toolKey}`, {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // ============ 에이전트 제어 ============

  async startAgent(projectId: string, agentId: string) {
    return this.request<{ status: string }>(`/projects/${projectId}/agents/${agentId}/start`, {
      method: 'POST',
    });
  }

  async stopAgent(projectId: string, agentId: string) {
    return this.request<{ status: string }>(`/projects/${projectId}/agents/${agentId}/stop`, {
      method: 'POST',
    });
  }

  async cancelAllAgents(projectId: string) {
    return this.request<{ status: string; cancelled_agents: Array<{ agent_id: string; name: string }> }>(
      `/projects/${projectId}/cancel_all`,
      { method: 'POST' }
    );
  }

  async stopAllAgents(projectId: string) {
    return this.request<{ status: string; stopped_agents: Array<{ agent_id: string; name: string }> }>(
      `/projects/${projectId}/stop_all`,
      { method: 'POST' }
    );
  }

  async sendCommand(projectId: string, agentId: string, command: string) {
    const data = await this.request<{ response: string }>(`/projects/${projectId}/agents/${agentId}/command`, {
      method: 'POST',
      body: JSON.stringify({ command }),
    });
    return data.response;
  }

  async getAgentNote(projectId: string, agentId: string) {
    const data = await this.request<{ note: string }>(`/projects/${projectId}/agents/${agentId}/note`);
    return data.note;
  }

  async saveAgentNote(projectId: string, agentId: string, note: string) {
    return this.request<{ status: string }>(`/projects/${projectId}/agents/${agentId}/note`, {
      method: 'PUT',
      body: JSON.stringify({ note }),
    });
  }

  // ============ Ollama 제어 ============

  async getOllamaStatus() {
    return this.request<{ running: boolean }>('/ollama/status');
  }

  async toggleOllama(action: 'start' | 'stop') {
    return this.request<{ status: string; running: boolean }>(`/ollama/${action}`, {
      method: 'POST',
    });
  }

  async getOllamaModels() {
    return this.request<{ models: string[]; running: boolean }>('/ollama/models');
  }

  // ============ 설정 ============

  async getConfig() {
    const data = await this.request<{ config: Record<string, unknown> }>('/config');
    return data.config;
  }

  async updateConfig(config: Record<string, unknown>) {
    return this.request<{ status: string }>('/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  }

  // 프로젝트별 설정 (agents.yaml + common_settings.txt)
  async getProjectConfig(projectId: string) {
    const data = await this.request<{ config: Record<string, unknown> }>(`/projects/${projectId}/config`);
    return data.config;
  }

  async updateProjectConfig(projectId: string, config: Record<string, unknown>) {
    return this.request<{ status: string }>(`/projects/${projectId}/config`, {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  }

  // 도구 자동 배분 (강제 - 모든 에이전트)
  async autoAssignTools(projectId: string) {
    return this.request<{ status: string; assignments?: Record<string, string[]> }>(
      `/projects/${projectId}/auto-assign-tools`,
      { method: 'POST' }
    );
  }

  // 도구 초기 배분 (allowed_tools가 없는 에이전트만)
  async initTools(projectId: string) {
    return this.request<{ status: string; message: string; agents?: string[] }>(
      `/projects/${projectId}/init-tools`,
      { method: 'POST' }
    );
  }

  // 에이전트 역할 조회/저장
  async getAgentRole(projectId: string, agentId: string) {
    const data = await this.request<{ role: string; agent_name: string }>(
      `/projects/${projectId}/agents/${agentId}/role`
    );
    return data;
  }

  async updateAgentRole(projectId: string, agentId: string, role: string) {
    return this.request<{ status: string }>(
      `/projects/${projectId}/agents/${agentId}/role`,
      {
        method: 'PUT',
        body: JSON.stringify({ role }),
      }
    );
  }

  // 에이전트 CRUD
  async createAgent(projectId: string, agent: {
    name: string;
    type: string;
    provider: string;
    model: string;
    api_key?: string;
    allowed_tools?: string[];
    role?: string;
    channel?: string;
    email?: string;
    gmail?: Record<string, string>;
    nostr?: Record<string, unknown>;
    channels?: Array<Record<string, unknown>>;
  }) {
    return this.request<{ status: string; agent: Agent }>(
      `/projects/${projectId}/agents`,
      {
        method: 'POST',
        body: JSON.stringify(agent),
      }
    );
  }

  async updateAgent(projectId: string, agentId: string, agent: {
    name: string;
    type: string;
    provider: string;
    model: string;
    api_key?: string;
    allowed_tools?: string[];
    role?: string;
    channel?: string;
    email?: string;
    gmail?: Record<string, string>;
    nostr?: Record<string, unknown>;
    channels?: Array<Record<string, unknown>>;
  }) {
    return this.request<{ status: string }>(
      `/projects/${projectId}/agents/${agentId}`,
      {
        method: 'PUT',
        body: JSON.stringify(agent),
      }
    );
  }

  async deleteAgent(projectId: string, agentId: string) {
    return this.request<{ status: string }>(
      `/projects/${projectId}/agents/${agentId}`,
      { method: 'DELETE' }
    );
  }

  // ============ 프로필 ============

  async getProfile() {
    const data = await this.request<{ content: string }>('/profile');
    return data.content;
  }

  async updateProfile(content: string) {
    return this.request<{ status: string }>('/profile', {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  }

  // ============ 스케줄러 ============

  async getSchedulerTasks() {
    const data = await this.request<{ tasks: SchedulerTask[] }>('/scheduler/tasks');
    return data.tasks;
  }

  async getAllEvents() {
    const data = await this.request<{ events: SchedulerTask[]; count: number }>('/scheduler/calendar/events');
    return data.events;
  }

  async getSchedulerActions() {
    const data = await this.request<{ actions: SchedulerAction[] }>('/scheduler/actions');
    return data.actions;
  }

  async createSchedulerTask(task: Omit<SchedulerTask, 'id' | 'last_run'>) {
    return this.request<SchedulerTask>('/scheduler/tasks', {
      method: 'POST',
      body: JSON.stringify(task),
    });
  }

  async updateSchedulerTask(taskId: string, updates: Partial<SchedulerTask>) {
    return this.request<SchedulerTask>(`/scheduler/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteSchedulerTask(taskId: string) {
    return this.request<{ status: string }>(`/scheduler/tasks/${taskId}`, {
      method: 'DELETE',
    });
  }

  async toggleSchedulerTask(taskId: string) {
    return this.request<{ status: string; enabled: boolean }>(`/scheduler/tasks/${taskId}/toggle`, {
      method: 'POST',
    });
  }

  async runSchedulerTask(taskId: string) {
    return this.request<{ status: string }>(`/scheduler/tasks/${taskId}/run`, {
      method: 'POST',
    });
  }

  // ============ 캘린더 ============

  async openCalendar(year?: number, month?: number) {
    const params = new URLSearchParams();
    if (year) params.append('year', year.toString());
    if (month) params.append('month', month.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.request<{ status: string; file: string }>(`/scheduler/calendar/view${query}`);
  }

  // ============ 음성 모드 ============

  async startVoiceMode(projectId: string, agentId: string) {
    return this.request<{ status: string; message: string }>('/voice/start', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, agent_id: agentId }),
    });
  }

  async stopVoiceMode(projectId: string, agentId: string) {
    return this.request<{ status: string; message: string }>('/voice/stop', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, agent_id: agentId }),
    });
  }

  async voiceListen(projectId: string, agentId: string) {
    return this.request<{ status: string; text?: string; message: string }>('/voice/listen', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, agent_id: agentId }),
    });
  }

  async voiceSpeak(text: string) {
    return this.request<{ status: string; message: string }>('/voice/speak', {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async getVoiceStatus(projectId: string, agentId: string) {
    return this.request<{ active: boolean; listening: boolean }>(
      `/voice/status?project_id=${projectId}&agent_id=${agentId}`
    );
  }
}

// mixin 적용하여 완성된 API 클라이언트 생성
function createAPIClient() {
  const base = new APIClientBase();
  const withSystemAI = applySystemAIMethods(base);
  const withIndieNet = applyIndieNetMethods(withSystemAI);
  const withPackages = applyPackagesMethods(withIndieNet);
  const withBusiness = applyBusinessMethods(withPackages);
  const withMultiChat = applyMultiChatMethods(withBusiness);
  return withMultiChat;
}

export const api = createAPIClient();

// WebSocket 연결 (자동 재연결 지원)
export function createChatWebSocket(clientId: string, onReconnect?: () => void) {
  let ws: WebSocket;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  const reconnectDelay = 2000; // 2초

  function connect(): WebSocket {
    ws = new WebSocket(`ws://127.0.0.1:8765/ws/chat/${clientId}`);

    ws.onclose = (event) => {
      console.log(`[WS] 연결 종료 (code: ${event.code})`);
      // 정상 종료가 아닌 경우 재연결 시도
      if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        console.log(`[WS] 재연결 시도 ${reconnectAttempts}/${maxReconnectAttempts}...`);
        setTimeout(() => {
          connect();
          // 원래 핸들러들 복원
          if (onReconnect) onReconnect();
        }, reconnectDelay);
      }
    };

    ws.onopen = () => {
      console.log('[WS] 연결됨');
      reconnectAttempts = 0; // 연결 성공시 카운터 리셋
    };

    ws.onerror = (error) => {
      console.error('[WS] 에러:', error);
    };

    return ws;
  }

  return connect();
}

// 작업 중단
export function cancelAllAgents(projectId: string) {
  return api.cancelAllAgents(projectId);
}
