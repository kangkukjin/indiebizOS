/**
 * api-system-ai.ts - 시스템 AI 관련 API 메서드
 * APIClient mixin: 시스템AI 설정, 프롬프트, 대화, Todo, 질문, 계획 모드
 */

import type { APIClientCore } from './api-types';

export function applySystemAIMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    // ============ 전역 시스템 AI 설정 ============

    async getSystemAI() {
      const data = await client.request<{ config: {
        enabled: boolean;
        provider: string;
        model: string;
        apiKey: string;
        role: string;
      }}>('/system-ai');
      return data.config;
    },

    async updateSystemAI(config: {
      enabled: boolean;
      provider: string;
      model: string;
      apiKey: string;
      role?: string;
    }) {
      return client.request<{ status: string; config: typeof config }>('/system-ai', {
        method: 'PUT',
        body: JSON.stringify(config),
      });
    },

    async chatWithSystemAI(message: string, images?: Array<{ base64: string; media_type: string }>) {
      return client.request<{ response: string }>('/system-ai/chat', {
        method: 'POST',
        body: JSON.stringify({ message, images }),
      });
    },

    // ============ 시스템 AI 프롬프트 템플릿 ============

    async getPromptTemplates() {
      return client.request<{
        templates: Array<{
          id: string;
          name: string;
          description: string;
          tokens: number;
          selected: boolean;
        }>;
        selected_template: string;
      }>('/system-ai/prompts/templates');
    },

    async getPromptTemplateContent(templateId: string) {
      return client.request<{ template_id: string; content: string }>(
        `/system-ai/prompts/template/${templateId}`
      );
    },

    async updatePromptConfig(config: { selected_template?: string }) {
      return client.request<{ status: string; config: typeof config }>(
        '/system-ai/prompts/config',
        {
          method: 'PUT',
          body: JSON.stringify(config),
        }
      );
    },

    async getRolePrompt() {
      return client.request<{ content: string }>('/system-ai/prompts/role');
    },

    async updateRolePrompt(content: string) {
      return client.request<{ status: string }>('/system-ai/prompts/role', {
        method: 'PUT',
        body: JSON.stringify({ content }),
      });
    },

    async previewFullPrompt() {
      return client.request<{
        prompt: string;
        estimated_tokens: number;
        config: { selected_template: string };
      }>('/system-ai/prompts/preview');
    },

    // ============ 시스템 AI 대화 히스토리 ============

    async getSystemAIConversationDates() {
      return client.request<{
        dates: Array<{ date: string; count: number }>;
      }>('/system-ai/conversations/dates');
    },

    async getSystemAIConversationsByDate(date: string) {
      return client.request<{
        date: string;
        conversations: Array<{
          id: number;
          timestamp: string;
          role: string;
          content: string;
        }>;
      }>(`/system-ai/conversations/by-date/${date}`);
    },

    async getSystemAIRecentConversations(limit: number = 100) {
      return client.request<{
        conversations: Array<{
          id: number;
          timestamp: string;
          role: string;
          content: string;
        }>;
      }>(`/system-ai/conversations/recent?limit=${limit}`);
    },

    // ============ Todo 상태 ============

    async getSystemAITodos() {
      return client.request<{
        todos: Array<{
          content: string;
          status: 'pending' | 'in_progress' | 'completed';
          activeForm: string;
        }>;
        updated_at: string | null;
      }>('/system-ai/todos');
    },

    async clearSystemAITodos() {
      return client.request<{ status: string }>('/system-ai/todos', {
        method: 'DELETE',
      });
    },

    // ============ 질문 상태 ============

    async getSystemAIQuestions() {
      return client.request<{
        questions: Array<{
          question: string;
          header: string;
          options: Array<{ label: string; description: string }>;
          multiSelect?: boolean;
        }>;
        status: 'none' | 'pending' | 'answered';
        answers: Record<string, string | string[]> | null;
      }>('/system-ai/questions');
    },

    async submitSystemAIQuestionAnswer(answers: Record<string, string | string[]>) {
      return client.request<{ status: string; answers: Record<string, string | string[]> }>(
        '/system-ai/questions/answer',
        {
          method: 'POST',
          body: JSON.stringify({ answers }),
        }
      );
    },

    async clearSystemAIQuestions() {
      return client.request<{ status: string }>('/system-ai/questions', {
        method: 'DELETE',
      });
    },

    // ============ 계획 모드 ============

    async getSystemAIPlanMode() {
      return client.request<{
        active: boolean;
        phase: 'exploring' | 'designing' | 'reviewing' | 'finalizing' | 'awaiting_approval' | 'approved' | 'revision_requested' | null;
        plan_content?: string;
        entered_at?: string;
      }>('/system-ai/plan-mode');
    },

    async approveSystemAIPlan() {
      return client.request<{ status: string }>('/system-ai/plan-mode/approve', {
        method: 'POST',
      });
    },

    async rejectSystemAIPlan(reason?: string) {
      return client.request<{ status: string }>('/system-ai/plan-mode/reject', {
        method: 'POST',
        body: JSON.stringify({ reason }),
      });
    },

    async clearSystemAIPlanMode() {
      return client.request<{ status: string }>('/system-ai/plan-mode', {
        method: 'DELETE',
      });
    },
  });
}
