/**
 * API 클라이언트
 */

import type { Project, Switch, Agent, Message, Tool, SchedulerTask, SchedulerAction } from '../types';

const API_BASE = 'http://127.0.0.1:8765';

class APIClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
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

  // ============ 전역 시스템 AI 설정 ============

  async getSystemAI() {
    const data = await this.request<{ config: {
      enabled: boolean;
      provider: string;
      model: string;
      apiKey: string;
      role: string;
    }}>('/system-ai');
    return data.config;
  }

  async updateSystemAI(config: {
    enabled: boolean;
    provider: string;
    model: string;
    apiKey: string;
    role?: string;
  }) {
    return this.request<{ status: string; config: typeof config }>('/system-ai', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  }

  async chatWithSystemAI(message: string, images?: Array<{ base64: string; media_type: string }>) {
    return this.request<{ response: string }>('/system-ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message, images }),
    });
  }

  // ============ 시스템 AI 프롬프트 템플릿 ============

  async getPromptTemplates() {
    return this.request<{
      templates: Array<{
        id: string;
        name: string;
        description: string;
        tokens: number;
        selected: boolean;
      }>;
      selected_template: string;
    }>('/system-ai/prompts/templates');
  }

  async getPromptTemplateContent(templateId: string) {
    return this.request<{ template_id: string; content: string }>(
      `/system-ai/prompts/template/${templateId}`
    );
  }

  async updatePromptConfig(config: { selected_template?: string }) {
    return this.request<{ status: string; config: typeof config }>(
      '/system-ai/prompts/config',
      {
        method: 'PUT',
        body: JSON.stringify(config),
      }
    );
  }

  async getRolePrompt() {
    return this.request<{ content: string }>('/system-ai/prompts/role');
  }

  async updateRolePrompt(content: string) {
    return this.request<{ status: string }>('/system-ai/prompts/role', {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  }

  async previewFullPrompt() {
    return this.request<{
      prompt: string;
      estimated_tokens: number;
      config: { selected_template: string };
    }>('/system-ai/prompts/preview');
  }

  // ============ 시스템 AI 대화 히스토리 ============

  async getSystemAIConversationDates() {
    return this.request<{
      dates: Array<{ date: string; count: number }>;
    }>('/system-ai/conversations/dates');
  }

  async getSystemAIConversationsByDate(date: string) {
    return this.request<{
      date: string;
      conversations: Array<{
        id: number;
        timestamp: string;
        role: string;
        content: string;
      }>;
    }>(`/system-ai/conversations/by-date/${date}`);
  }

  async getSystemAIRecentConversations(limit: number = 100) {
    return this.request<{
      conversations: Array<{
        id: number;
        timestamp: string;
        role: string;
        content: string;
      }>;
    }>(`/system-ai/conversations/recent?limit=${limit}`);
  }

  // ============ Todo 상태 ============

  async getSystemAITodos() {
    return this.request<{
      todos: Array<{
        content: string;
        status: 'pending' | 'in_progress' | 'completed';
        activeForm: string;
      }>;
      updated_at: string | null;
    }>('/system-ai/todos');
  }

  async clearSystemAITodos() {
    return this.request<{ status: string }>('/system-ai/todos', {
      method: 'DELETE',
    });
  }

  // ============ 질문 상태 ============

  async getSystemAIQuestions() {
    return this.request<{
      questions: Array<{
        question: string;
        header: string;
        options: Array<{ label: string; description: string }>;
        multiSelect?: boolean;
      }>;
      status: 'none' | 'pending' | 'answered';
      answers: Record<string, string | string[]> | null;
    }>('/system-ai/questions');
  }

  async submitSystemAIQuestionAnswer(answers: Record<string, string | string[]>) {
    return this.request<{ status: string; answers: Record<string, string | string[]> }>(
      '/system-ai/questions/answer',
      {
        method: 'POST',
        body: JSON.stringify({ answers }),
      }
    );
  }

  async clearSystemAIQuestions() {
    return this.request<{ status: string }>('/system-ai/questions', {
      method: 'DELETE',
    });
  }

  // ============ 계획 모드 ============

  async getSystemAIPlanMode() {
    return this.request<{
      active: boolean;
      phase: 'exploring' | 'designing' | 'reviewing' | 'finalizing' | 'awaiting_approval' | 'approved' | 'revision_requested' | null;
      plan_content?: string;
      entered_at?: string;
    }>('/system-ai/plan-mode');
  }

  async approveSystemAIPlan() {
    return this.request<{ status: string }>('/system-ai/plan-mode/approve', {
      method: 'POST',
    });
  }

  async rejectSystemAIPlan(reason?: string) {
    return this.request<{ status: string }>('/system-ai/plan-mode/reject', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  async clearSystemAIPlanMode() {
    return this.request<{ status: string }>('/system-ai/plan-mode', {
      method: 'DELETE',
    });
  }

  // ============ IndieNet ============

  async getIndieNetStatus() {
    return this.request<{
      initialized: boolean;
      has_nostr: boolean;
      identity: { npub: string; display_name: string; created_at: string } | null;
      settings: {
        relays: string[];
        default_tags: string[];
        auto_refresh: boolean;
        refresh_interval: number;
      } | null;
    }>('/indienet/status');
  }

  async getIndieNetIdentity() {
    return this.request<{
      npub: string;
      display_name: string;
      created_at: string;
    }>('/indienet/identity');
  }

  async updateIndieNetDisplayName(displayName: string) {
    return this.request<{ status: string; display_name: string }>('/indienet/identity/display-name', {
      method: 'PUT',
      body: JSON.stringify({ display_name: displayName }),
    });
  }

  async importIndieNetNsec(nsec: string) {
    return this.request<{
      status: string;
      identity: { npub: string; display_name: string; created_at: string };
    }>('/indienet/identity/import', {
      method: 'POST',
      body: JSON.stringify({ nsec }),
    });
  }

  async resetIndieNetIdentity() {
    return this.request<{
      status: string;
      identity: { npub: string; display_name: string; created_at: string };
    }>('/indienet/identity/reset', {
      method: 'POST',
    });
  }

  async getIndieNetSettings() {
    return this.request<{
      relays: string[];
      default_tags: string[];
      auto_refresh: boolean;
      refresh_interval: number;
    }>('/indienet/settings');
  }

  async updateIndieNetSettings(settings: {
    relays?: string[];
    auto_refresh?: boolean;
    refresh_interval?: number;
  }) {
    return this.request<{ status: string; settings: any }>('/indienet/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  async getIndieNetPosts(limit = 50, since?: number) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (since) params.append('since', String(since));
    return this.request<{
      posts: Array<{
        id: string;
        author: string;
        content: string;
        created_at: number;
        tags: string[][];
      }>;
      count: number;
    }>(`/indienet/posts?${params}`);
  }

  async createIndieNetPost(content: string, extraTags?: string[]) {
    return this.request<{ status: string; event_id: string }>('/indienet/posts', {
      method: 'POST',
      body: JSON.stringify({ content, extra_tags: extraTags }),
    });
  }

  async getIndieNetUser(pubkey: string) {
    return this.request<{
      pubkey: string;
      name: string;
      display_name: string;
      about: string;
      picture: string;
    }>(`/indienet/user/${encodeURIComponent(pubkey)}`);
  }

  async getIndieNetDMs(limit = 50, since?: number) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (since) params.append('since', String(since));
    return this.request<{
      dms: Array<{
        id: string;
        from: string;
        content: string;
        created_at: number;
        tags: string[][];
      }>;
      count: number;
    }>(`/indienet/dms?${params}`);
  }

  async sendIndieNetDM(toPubkey: string, content: string) {
    return this.request<{ status: string; event_id: string; to: string; created_at: number }>('/indienet/dms', {
      method: 'POST',
      body: JSON.stringify({ to_pubkey: toPubkey, content }),
    });
  }

  // ============ IndieNet 보드 (커스텀 해시태그 게시판) ============

  async getIndieNetBoards() {
    return this.request<{
      boards: Array<{ name: string; hashtag: string; created_at: string }>;
      active_board: { name: string; hashtag: string; created_at: string } | null;
      count: number;
    }>('/indienet/boards');
  }

  async createIndieNetBoard(name: string, hashtag: string) {
    return this.request<{
      status: string;
      board: { name: string; hashtag: string; created_at: string };
    }>('/indienet/boards', {
      method: 'POST',
      body: JSON.stringify({ name, hashtag }),
    });
  }

  async deleteIndieNetBoard(hashtag: string) {
    return this.request<{ status: string; hashtag: string }>(`/indienet/boards/${encodeURIComponent(hashtag)}`, {
      method: 'DELETE',
    });
  }

  async setActiveIndieNetBoard(hashtag: string | null) {
    return this.request<{
      status: string;
      active_board: { name: string; hashtag: string; created_at: string } | null;
    }>(`/indienet/boards/active${hashtag ? `?hashtag=${encodeURIComponent(hashtag)}` : ''}`, {
      method: 'PUT',
    });
  }

  async getIndieNetBoardPosts(hashtag: string, limit = 50, since?: number) {
    const params = new URLSearchParams();
    params.set('limit', limit.toString());
    if (since) params.set('since', since.toString());
    return this.request<{
      posts: Array<{
        id: string;
        author: string;
        content: string;
        created_at: number;
        tags: string[][];
      }>;
      count: number;
      hashtag: string;
    }>(`/indienet/boards/${encodeURIComponent(hashtag)}/posts?${params}`);
  }

  async postToIndieNetBoard(content: string, hashtag?: string) {
    return this.request<{
      status: string;
      event_id: string;
      hashtag: string;
      created_at: number;
    }>('/indienet/boards/post', {
      method: 'POST',
      body: JSON.stringify({ content, hashtag }),
    });
  }

  // ============ 도구 패키지 ============

  async getPackages() {
    return this.request<{
      available: Array<{
        id: string;
        name: string;
        description: string;
        version?: string;
        installed: boolean;
        files?: string[];
        tools?: Array<{ name: string; description: string }>;
      }>;
      installed: Array<any>;
      total_available: number;
      total_installed: number;
    }>('/packages');
  }

  async getPackageInfo(packageId: string) {
    return this.request<{
      id: string;
      name: string;
      description: string;
      version?: string;
      installed: boolean;
      files?: string[];
      tools?: Array<{ name: string; description: string }>;
    }>(`/packages/${packageId}`);
  }

  async installPackage(packageId: string) {
    return this.request<{
      status: string;
      package: any;
      message: string;
    }>(`/packages/${packageId}/install`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  async uninstallPackage(packageId: string) {
    return this.request<{
      status: string;
      package_id: string;
      message: string;
    }>(`/packages/${packageId}/uninstall`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  async analyzeFolder(folderPath: string) {
    return this.request<{
      valid: boolean | null;
      error?: string;
      folder_name?: string;
      files?: string[];
      py_files?: string[];
      has_tool_json?: boolean;
      has_handler?: boolean;
      has_readme?: boolean;
      suggested_name?: string;
    }>('/packages/analyze-folder', {
      method: 'POST',
      body: JSON.stringify({ folder_path: folderPath }),
    });
  }

  async analyzeFolderWithAI(folderPath: string) {
    return this.request<{
      valid: boolean | null;
      error?: string;
      folder_name?: string;
      folder_path?: string;
      files?: string[];
      reason?: string;
      package_name?: string;
      package_description?: string;
      tools?: Array<{ name: string; description: string }>;
      readme_content?: string;
      can_auto_generate?: boolean;
    }>('/packages/analyze-folder-ai', {
      method: 'POST',
      body: JSON.stringify({ folder_path: folderPath }),
    });
  }

  async registerFolder(
    folderPath: string,
    name?: string,
    description?: string,
    readmeContent?: string
  ) {
    return this.request<{
      status: string;
      package_id: string;
      package_type: string;
      metadata: any;
      message: string;
    }>('/packages/register', {
      method: 'POST',
      body: JSON.stringify({
        folder_path: folderPath,
        name,
        description,
        readme_content: readmeContent,
      }),
    });
  }

  async removePackage(packageId: string) {
    return this.request<{
      status: string;
      package_id: string;
      message: string;
    }>(`/packages/${packageId}/remove`, {
      method: 'DELETE',
      body: JSON.stringify({}),
    });
  }

  // ============ 패키지 공개/검색 (Nostr) ============

  async publishPackageToNostr(packageId: string, installInstructions?: string, signature?: string) {
    return this.request<{
      status: string;
      package_id: string;
      message: string;
    }>(`/packages/${packageId}/publish`, {
      method: 'POST',
      body: JSON.stringify({
        package_id: packageId,
        install_instructions: installInstructions,
        signature: signature,
      }),
    });
  }

  async generateInstallInstructions(packageId: string) {
    return this.request<{
      instructions: string;
    }>(`/packages/${packageId}/generate-install`);
  }

  async searchPackagesOnNostr(query?: string, limit = 20) {
    const params = new URLSearchParams();
    if (query) params.append('query', query);
    params.append('limit', String(limit));
    return this.request<{
      packages: Array<{
        id: string;
        name: string;
        description: string;
        version: string;
        install: string;
        author: string;
        timestamp: number;
        raw_content: string;
      }>;
      count: number;
      query: string | null;
    }>(`/packages/nostr/search?${params}`);
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

  // ============ 비즈니스 관리 ============

  async getBusinesses(level?: number, search?: string) {
    const params = new URLSearchParams();
    if (level !== undefined) params.append('level', String(level));
    if (search) params.append('search', search);
    const queryString = params.toString();
    return this.request<Array<{
      id: number;
      name: string;
      level: number;
      description: string | null;
      created_at: string;
      updated_at: string;
    }>>(`/business${queryString ? `?${queryString}` : ''}`);
  }

  async createBusiness(data: { name: string; level?: number; description?: string }) {
    return this.request<{
      id: number;
      name: string;
      level: number;
      description: string | null;
      created_at: string;
      updated_at: string;
    }>('/business', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateBusiness(businessId: number, data: { name?: string; level?: number; description?: string }) {
    return this.request<{
      id: number;
      name: string;
      level: number;
      description: string | null;
      created_at: string;
      updated_at: string;
    }>(`/business/${businessId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteBusiness(businessId: number) {
    return this.request<{ status: string }>(`/business/${businessId}`, {
      method: 'DELETE',
    });
  }

  async getBusinessItems(businessId: number) {
    return this.request<Array<{
      id: number;
      business_id: number;
      title: string;
      details: string | null;
      attachment_path: string | null;
      created_at: string;
      updated_at: string;
    }>>(`/business/${businessId}/items`);
  }

  async createBusinessItem(businessId: number, data: { title: string; details?: string; attachment_path?: string }) {
    return this.request<{
      id: number;
      business_id: number;
      title: string;
      details: string | null;
      attachment_path: string | null;
      created_at: string;
      updated_at: string;
    }>(`/business/${businessId}/items`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateBusinessItem(itemId: number, data: { title?: string; details?: string; attachment_path?: string }) {
    return this.request<{
      id: number;
      business_id: number;
      title: string;
      details: string | null;
      attachment_path: string | null;
      created_at: string;
      updated_at: string;
    }>(`/business/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteBusinessItem(itemId: number) {
    return this.request<{ status: string }>(`/business/items/${itemId}`, {
      method: 'DELETE',
    });
  }

  async getAllBusinessDocuments() {
    return this.request<Array<{
      id: number;
      level: number;
      title: string;
      content: string;
      updated_at: string;
    }>>('/business/documents/all');
  }

  async updateBusinessDocument(level: number, data: { title: string; content: string }) {
    return this.request<{
      id: number;
      level: number;
      title: string;
      content: string;
      updated_at: string;
    }>(`/business/documents/${level}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getAllWorkGuidelines() {
    return this.request<Array<{
      id: number;
      level: number;
      title: string;
      content: string;
      updated_at: string;
    }>>('/business/guidelines/all');
  }

  async updateWorkGuideline(level: number, data: { title: string; content: string }) {
    return this.request<{
      id: number;
      level: number;
      title: string;
      content: string;
      updated_at: string;
    }>(`/business/guidelines/${level}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async regenerateBusinessDocuments() {
    return this.request<{ status: string; message: string }>('/business/documents/regenerate', {
      method: 'POST',
    });
  }

  // ============ 통신채널 설정 ============

  async getChannelSettings() {
    return this.request<Array<{
      id: number;
      channel_type: string;
      enabled: number;
      config: string;
      polling_interval: number;
      last_poll_at: string | null;
      updated_at: string;
    }>>('/business/channels');
  }

  async getChannelSetting(channelType: string) {
    return this.request<{
      id: number;
      channel_type: string;
      enabled: number;
      config: string;
      polling_interval: number;
      last_poll_at: string | null;
      updated_at: string;
    }>(`/business/channels/${channelType}`);
  }

  async updateChannelSetting(channelType: string, data: {
    enabled?: boolean;
    config?: string;
    polling_interval?: number;
  }) {
    return this.request<{
      id: number;
      channel_type: string;
      enabled: number;
      config: string;
      polling_interval: number;
      last_poll_at: string | null;
      updated_at: string;
    }>(`/business/channels/${channelType}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async pollChannelNow(channelType: string) {
    return this.request<{ status: string; channel: string }>(`/business/channels/${channelType}/poll`, {
      method: 'POST',
    });
  }

  async authenticateGmail() {
    return this.request<{ status: string; auth_url?: string; message?: string }>('/business/channels/gmail/authenticate', {
      method: 'POST',
    });
  }

  async getPollerStatus() {
    return this.request<{
      running: boolean;
      active_channels: string[];
    }>('/business/channels/poller/status');
  }

  // ============ 소유자 식별 정보 ============

  async getOwnerIdentities() {
    return this.request<{
      owner_emails: string;
      owner_nostr_pubkeys: string;
      system_ai_gmail: string;
    }>('/owner-identities');
  }

  async updateOwnerIdentities(data: {
    owner_emails?: string;
    owner_nostr_pubkeys?: string;
    system_ai_gmail?: string;
  }) {
    return this.request<{ status: string }>('/owner-identities', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // ============ 이웃 (비즈니스 파트너) ============

  async getNeighbors(search?: string, infoLevel?: number) {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (infoLevel !== undefined) params.append('info_level', String(infoLevel));
    const queryString = params.toString();
    return this.request<Array<{
      id: number;
      name: string;
      info_level: number;
      rating: number;
      additional_info: string | null;
      business_doc: string | null;
      info_share: number;
      created_at: string;
      updated_at: string;
    }>>(`/business/neighbors${queryString ? `?${queryString}` : ''}`);
  }

  async createNeighbor(data: {
    name: string;
    info_level?: number;
    rating?: number;
    additional_info?: string;
    business_doc?: string;
    info_share?: number;
  }) {
    return this.request<{
      id: number;
      name: string;
      info_level: number;
      rating: number;
      additional_info: string | null;
      business_doc: string | null;
      info_share: number;
      created_at: string;
      updated_at: string;
    }>('/business/neighbors', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateNeighbor(neighborId: number, data: {
    name?: string;
    info_level?: number;
    rating?: number;
    additional_info?: string;
    business_doc?: string;
    info_share?: number;
    favorite?: number;
  }) {
    return this.request<{
      id: number;
      name: string;
      info_level: number;
      rating: number;
      additional_info: string | null;
      business_doc: string | null;
      info_share: number;
      favorite: number;
      created_at: string;
      updated_at: string;
    }>(`/business/neighbors/${neighborId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async updateContact(contactId: number, data: { contact_type?: string; contact_value?: string }) {
    return this.request<{
      id: number;
      neighbor_id: number;
      contact_type: string;
      contact_value: string;
      created_at: string;
    }>(`/business/contacts/${contactId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteNeighbor(neighborId: number) {
    return this.request<{ status: string }>(`/business/neighbors/${neighborId}`, {
      method: 'DELETE',
    });
  }

  async getFavoriteNeighbors() {
    return this.request<Array<{
      id: number;
      name: string;
      info_level: number;
      rating: number;
      additional_info: string | null;
      business_doc: string | null;
      info_share: number;
      favorite: number;
      created_at: string;
      updated_at: string;
    }>>('/business/neighbors/favorites/list');
  }

  async toggleNeighborFavorite(neighborId: number) {
    return this.request<{
      id: number;
      name: string;
      info_level: number;
      rating: number;
      additional_info: string | null;
      business_doc: string | null;
      info_share: number;
      favorite: number;
      created_at: string;
      updated_at: string;
    }>(`/business/neighbors/${neighborId}/favorite/toggle`, {
      method: 'POST',
    });
  }

  async getNeighborContacts(neighborId: number) {
    return this.request<Array<{
      id: number;
      neighbor_id: number;
      contact_type: string;
      contact_value: string;
      created_at: string;
    }>>(`/business/neighbors/${neighborId}/contacts`);
  }

  async addNeighborContact(neighborId: number, data: { contact_type: string; contact_value: string }) {
    return this.request<{
      id: number;
      neighbor_id: number;
      contact_type: string;
      contact_value: string;
      created_at: string;
    }>(`/business/neighbors/${neighborId}/contacts`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteContact(contactId: number) {
    return this.request<{ status: string }>(`/business/contacts/${contactId}`, {
      method: 'DELETE',
    });
  }

  // ============ 비즈니스 메시지 ============

  async getBusinessMessages(params?: {
    neighbor_id?: number;
    status?: string;
    unprocessed_only?: boolean;
    unreplied_only?: boolean;
    limit?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.neighbor_id !== undefined) searchParams.append('neighbor_id', String(params.neighbor_id));
    if (params?.status) searchParams.append('status', params.status);
    if (params?.unprocessed_only) searchParams.append('unprocessed_only', 'true');
    if (params?.unreplied_only) searchParams.append('unreplied_only', 'true');
    if (params?.limit) searchParams.append('limit', String(params.limit));
    const queryString = searchParams.toString();
    return this.request<Array<{
      id: number;
      neighbor_id: number | null;
      subject: string | null;
      content: string;
      message_time: string;
      is_from_user: number;
      contact_type: string;
      contact_value: string;
      attachment_path: string | null;
      status: string;
      error_message: string | null;
      sent_at: string | null;
      processed: number;
      replied: number;
      created_at: string;
    }>>(`/business/messages${queryString ? `?${queryString}` : ''}`);
  }

  async createBusinessMessage(data: {
    content: string;
    contact_type: string;
    contact_value: string;
    subject?: string;
    neighbor_id?: number;
    is_from_user?: number;
    attachment_path?: string;
    status?: string;
  }) {
    return this.request<{
      id: number;
      neighbor_id: number | null;
      subject: string | null;
      content: string;
      message_time: string;
      is_from_user: number;
      contact_type: string;
      contact_value: string;
      attachment_path: string | null;
      status: string;
      error_message: string | null;
      sent_at: string | null;
      processed: number;
      replied: number;
      created_at: string;
    }>('/business/messages', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ============ 자동응답 ============

  async getAutoResponseStatus() {
    return this.request<{
      running: boolean;
      check_interval: number;
      processed_count: number;
    }>('/business/auto-response/status');
  }

  async startAutoResponse() {
    return this.request<{ status: string; running: boolean }>('/business/auto-response/start', {
      method: 'POST',
    });
  }

  async stopAutoResponse() {
    return this.request<{ status: string; running: boolean }>('/business/auto-response/stop', {
      method: 'POST',
    });
  }

  // ============ 다중채팅방 ============

  async getMultiChatRooms() {
    const data = await this.request<{ rooms: Array<{
      id: string;
      name: string;
      description: string;
      participant_count: number;
      created_at: string;
      updated_at: string;
      icon_position?: [number, number];
    }> }>('/multi-chat/rooms');
    return data.rooms;
  }

  async createMultiChatRoom(name: string, description = '') {
    const data = await this.request<{ room: {
      id: string;
      name: string;
      description: string;
      created_at: string;
    } }>('/multi-chat/rooms', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
    return data.room;
  }

  async getMultiChatRoom(roomId: string) {
    const data = await this.request<{ room: {
      id: string;
      name: string;
      description: string;
      participants: Array<{
        agent_name: string;
        agent_source: string;
        system_prompt: string;
      }>;
    } }>(`/multi-chat/rooms/${roomId}`);
    return data.room;
  }

  async deleteMultiChatRoom(roomId: string) {
    return this.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}`, {
      method: 'DELETE',
    });
  }

  async moveMultiChatRoomToTrash(roomId: string) {
    return this.request<{ status: string; item: unknown }>(`/multi-chat/rooms/${roomId}/trash`, {
      method: 'POST',
    });
  }

  async updateMultiChatRoomPosition(roomId: string, x: number, y: number) {
    return this.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}/position`, {
      method: 'PATCH',
      body: JSON.stringify({ x, y }),
    });
  }

  async getAvailableAgentsForMultiChat() {
    const data = await this.request<{ agents: Array<{
      project_id: string;
      project_name: string;
      agent_id: string;
      agent_name: string;
      role: string;
      source: string;
    }> }>('/multi-chat/available-agents');
    return data.agents;
  }

  async addAgentToMultiChatRoom(roomId: string, projectId: string, agentId: string) {
    return this.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}/participants`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, agent_id: agentId }),
    });
  }

  async removeAgentFromMultiChatRoom(roomId: string, agentName: string) {
    return this.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}/participants/${encodeURIComponent(agentName)}`, {
      method: 'DELETE',
    });
  }

  async getMultiChatMessages(roomId: string, limit = 50) {
    const data = await this.request<{ messages: Array<{
      id: number;
      room_id: string;
      speaker: string;
      content: string;
      message_time: string;
    }> }>(`/multi-chat/rooms/${roomId}/messages?limit=${limit}`);
    return data.messages;
  }

  async sendMultiChatMessage(
    roomId: string,
    message: string,
    responseCount = 2,
    images?: Array<{ base64: string; media_type: string }>
  ) {
    return this.request<{
      user_message: string;
      responses: Array<{
        speaker: string;
        content: string;
      }>;
    }>(`/multi-chat/rooms/${roomId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        message,
        response_count: responseCount,
        images: images
      }),
    });
  }

  async clearMultiChatMessages(roomId: string) {
    return this.request<{ deleted_count: number }>(`/multi-chat/rooms/${roomId}/messages`, {
      method: 'DELETE',
    });
  }

  // 다중채팅방 에이전트 전체 활성화
  async activateAllMultiChatAgents(roomId: string, tools: string[] = []) {
    return this.request<{ success: boolean; activated: string[] }>(`/multi-chat/rooms/${roomId}/activate-all`, {
      method: 'POST',
      body: JSON.stringify({ tools }),
    });
  }

  // 다중채팅방 에이전트 전체 비활성화
  async deactivateAllMultiChatAgents(roomId: string) {
    return this.request<{ success: boolean; deactivated: string[] }>(`/multi-chat/rooms/${roomId}/deactivate-all`, {
      method: 'POST',
    });
  }
}

export const api = new APIClient();

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
