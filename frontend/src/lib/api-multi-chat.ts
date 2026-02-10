/**
 * api-multi-chat.ts - 다중채팅 관련 API 메서드
 * APIClient mixin: 다중채팅방 CRUD, 참가자, 메시지
 */

import type { APIClientCore } from './api-types';

export function applyMultiChatMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    // ============ 다중채팅방 ============

    async getMultiChatRooms() {
      const data = await client.request<{ rooms: Array<{
        id: string;
        name: string;
        description: string;
        participant_count: number;
        created_at: string;
        updated_at: string;
        icon_position?: [number, number];
      }> }>('/multi-chat/rooms');
      return data.rooms;
    },

    async createMultiChatRoom(name: string, description = '') {
      const data = await client.request<{ room: {
        id: string;
        name: string;
        description: string;
        created_at: string;
      } }>('/multi-chat/rooms', {
        method: 'POST',
        body: JSON.stringify({ name, description }),
      });
      return data.room;
    },

    async getMultiChatRoom(roomId: string) {
      const data = await client.request<{ room: {
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
    },

    async deleteMultiChatRoom(roomId: string) {
      return client.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}`, {
        method: 'DELETE',
      });
    },

    async moveMultiChatRoomToTrash(roomId: string) {
      return client.request<{ status: string; item: unknown }>(`/multi-chat/rooms/${roomId}/trash`, {
        method: 'POST',
      });
    },

    async updateMultiChatRoomPosition(roomId: string, x: number, y: number) {
      return client.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}/position`, {
        method: 'PATCH',
        body: JSON.stringify({ x, y }),
      });
    },

    async getAvailableAgentsForMultiChat() {
      const data = await client.request<{ agents: Array<{
        project_id: string;
        project_name: string;
        agent_id: string;
        agent_name: string;
        role: string;
        source: string;
      }> }>('/multi-chat/available-agents');
      return data.agents;
    },

    async addAgentToMultiChatRoom(roomId: string, projectId: string, agentId: string) {
      return client.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}/participants`, {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, agent_id: agentId }),
      });
    },

    async removeAgentFromMultiChatRoom(roomId: string, agentName: string) {
      return client.request<{ success: boolean }>(`/multi-chat/rooms/${roomId}/participants/${encodeURIComponent(agentName)}`, {
        method: 'DELETE',
      });
    },

    async getMultiChatMessages(roomId: string, limit = 50) {
      const data = await client.request<{ messages: Array<{
        id: number;
        room_id: string;
        speaker: string;
        content: string;
        message_time: string;
      }> }>(`/multi-chat/rooms/${roomId}/messages?limit=${limit}`);
      return data.messages;
    },

    async sendMultiChatMessage(
      roomId: string,
      message: string,
      responseCount = 2,
      images?: Array<{ base64: string; media_type: string }>
    ) {
      return client.request<{
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
    },

    async clearMultiChatMessages(roomId: string) {
      return client.request<{ deleted_count: number }>(`/multi-chat/rooms/${roomId}/messages`, {
        method: 'DELETE',
      });
    },

    // 다중채팅방 에이전트 전체 활성화
    async activateAllMultiChatAgents(roomId: string, tools: string[] = []) {
      return client.request<{ success: boolean; activated: string[] }>(`/multi-chat/rooms/${roomId}/activate-all`, {
        method: 'POST',
        body: JSON.stringify({ tools }),
      });
    },

    // 다중채팅방 에이전트 전체 비활성화
    async deactivateAllMultiChatAgents(roomId: string) {
      return client.request<{ success: boolean; deactivated: string[] }>(`/multi-chat/rooms/${roomId}/deactivate-all`, {
        method: 'POST',
      });
    },
  });
}
