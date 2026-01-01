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
      throw new Error(error.detail || 'API Error');
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
    return this.request<{ items: (Project | Switch)[]; projects: Project[]; switches: Switch[] }>('/trash');
  }

  async restoreFromTrash(itemId: string, itemType: 'project' | 'switch' = 'project') {
    return this.request<{ status: string; item: Project | Switch }>(`/trash/${itemId}/restore?item_type=${itemType}`, {
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

  async updateRoleDescriptions(projectId: string, descriptions: Record<string, string>) {
    return this.request<{ status: string; updated_agents: string[] }>(
      `/projects/${projectId}/agents/role-descriptions`,
      {
        method: 'PUT',
        body: JSON.stringify({ descriptions }),
      }
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
    role: string;
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

  // ============ 프롬프트 생성 ============

  async generatePrompts(projectId: string, params: {
    project_purpose: string;
    agents: Array<{ name: string; role_description: string; type?: string }>;
    use_ai?: boolean;
    ai_config?: Record<string, unknown>;
  }) {
    return this.request<{
      status: string;
      common_settings: string;
      agent_roles: Record<string, string>;
      validation_errors?: string[];
    }>(`/projects/${projectId}/generate-prompts`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  async savePrompts(projectId: string, params: {
    common_settings: string;
    agent_roles: Record<string, string>;
  }) {
    return this.request<{
      status: string;
      saved_files: Record<string, string>;  // {파일종류: 경로}
      common_settings?: string;
      agent_roles?: Record<string, string>;
    }>(`/projects/${projectId}/save-prompts`, {
      method: 'POST',
      body: JSON.stringify(params),
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

export const api = new APIClient();

// WebSocket 연결
export function createChatWebSocket(clientId: string) {
  const ws = new WebSocket(`ws://127.0.0.1:8765/ws/chat/${clientId}`);
  return ws;
}

// 작업 중단
export function cancelAllAgents(projectId: string) {
  return api.cancelAllAgents(projectId);
}
