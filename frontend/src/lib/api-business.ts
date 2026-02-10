/**
 * api-business.ts - 비즈니스/이웃/메시지 관련 API 메서드
 * APIClient mixin: 비즈니스 관리, 이웃, 연락처, 메시지, 자동응답, 통신채널, 소유자 식별
 */

import type { APIClientCore } from './api-types';

export function applyBusinessMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    // ============ 비즈니스 관리 ============

    async getBusinesses(level?: number, search?: string) {
      const params = new URLSearchParams();
      if (level !== undefined) params.append('level', String(level));
      if (search) params.append('search', search);
      const queryString = params.toString();
      return client.request<Array<{
        id: number;
        name: string;
        level: number;
        description: string | null;
        created_at: string;
        updated_at: string;
      }>>(`/business${queryString ? `?${queryString}` : ''}`);
    },

    async createBusiness(data: { name: string; level?: number; description?: string }) {
      return client.request<{
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
    },

    async updateBusiness(businessId: number, data: { name?: string; level?: number; description?: string }) {
      return client.request<{
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
    },

    async deleteBusiness(businessId: number) {
      return client.request<{ status: string }>(`/business/${businessId}`, {
        method: 'DELETE',
      });
    },

    async getBusinessItems(businessId: number) {
      return client.request<Array<{
        id: number;
        business_id: number;
        title: string;
        details: string | null;
        attachment_path: string | null;
        created_at: string;
        updated_at: string;
      }>>(`/business/${businessId}/items`);
    },

    async copyImagesForBusinessItem(sourcePaths: string[]) {
      return client.request<{ status: string; paths: string[] }>('/business/items/copy-images', {
        method: 'POST',
        body: JSON.stringify({ source_paths: sourcePaths }),
      });
    },

    async createBusinessItem(businessId: number, data: { title: string; details?: string; attachment_path?: string; attachment_paths?: string[] }) {
      return client.request<{
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
    },

    async updateBusinessItem(itemId: number, data: { title?: string; details?: string; attachment_path?: string; attachment_paths?: string[] }) {
      return client.request<{
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
    },

    async deleteBusinessItem(itemId: number) {
      return client.request<{ status: string }>(`/business/items/${itemId}`, {
        method: 'DELETE',
      });
    },

    async getAllBusinessDocuments() {
      return client.request<Array<{
        id: number;
        level: number;
        title: string;
        content: string;
        updated_at: string;
      }>>('/business/documents/all');
    },

    async updateBusinessDocument(level: number, data: { title: string; content: string }) {
      return client.request<{
        id: number;
        level: number;
        title: string;
        content: string;
        updated_at: string;
      }>(`/business/documents/${level}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    async getAllWorkGuidelines() {
      return client.request<Array<{
        id: number;
        level: number;
        title: string;
        content: string;
        updated_at: string;
      }>>('/business/guidelines/all');
    },

    async updateWorkGuideline(level: number, data: { title: string; content: string }) {
      return client.request<{
        id: number;
        level: number;
        title: string;
        content: string;
        updated_at: string;
      }>(`/business/guidelines/${level}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    async regenerateBusinessDocuments() {
      return client.request<{ status: string; message: string }>('/business/documents/regenerate', {
        method: 'POST',
      });
    },

    // ============ 통신채널 설정 ============

    async getChannelSettings() {
      return client.request<Array<{
        id: number;
        channel_type: string;
        enabled: number;
        config: string;
        polling_interval: number;
        last_poll_at: string | null;
        updated_at: string;
      }>>('/business/channels');
    },

    async getChannelSetting(channelType: string) {
      return client.request<{
        id: number;
        channel_type: string;
        enabled: number;
        config: string;
        polling_interval: number;
        last_poll_at: string | null;
        updated_at: string;
      }>(`/business/channels/${channelType}`);
    },

    async updateChannelSetting(channelType: string, data: {
      enabled?: boolean;
      config?: string;
      polling_interval?: number;
    }) {
      return client.request<{
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
    },

    async pollChannelNow(channelType: string) {
      return client.request<{ status: string; channel: string }>(`/business/channels/${channelType}/poll`, {
        method: 'POST',
      });
    },

    async authenticateGmail() {
      return client.request<{ status: string; auth_url?: string; message?: string }>('/business/channels/gmail/authenticate', {
        method: 'POST',
      });
    },

    async getPollerStatus() {
      return client.request<{
        running: boolean;
        active_channels: string[];
      }>('/business/channels/poller/status');
    },

    // ============ 소유자 식별 정보 ============

    async getOwnerIdentities() {
      return client.request<{
        owner_emails: string;
        owner_nostr_pubkeys: string;
        system_ai_gmail: string;
      }>('/owner-identities');
    },

    async updateOwnerIdentities(data: {
      owner_emails?: string;
      owner_nostr_pubkeys?: string;
      system_ai_gmail?: string;
    }) {
      return client.request<{ status: string }>('/owner-identities', {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    // ============ 이웃 (비즈니스 파트너) ============

    async getNeighbors(search?: string, infoLevel?: number) {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (infoLevel !== undefined) params.append('info_level', String(infoLevel));
      const queryString = params.toString();
      return client.request<Array<{
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
    },

    async createNeighbor(data: {
      name: string;
      info_level?: number;
      rating?: number;
      additional_info?: string;
      business_doc?: string;
      info_share?: number;
    }) {
      return client.request<{
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
    },

    async updateNeighbor(neighborId: number, data: {
      name?: string;
      info_level?: number;
      rating?: number;
      additional_info?: string;
      business_doc?: string;
      info_share?: number;
      favorite?: number;
    }) {
      return client.request<{
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
    },

    async updateContact(contactId: number, data: { contact_type?: string; contact_value?: string }) {
      return client.request<{
        id: number;
        neighbor_id: number;
        contact_type: string;
        contact_value: string;
        created_at: string;
      }>(`/business/contacts/${contactId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },

    async deleteNeighbor(neighborId: number) {
      return client.request<{ status: string }>(`/business/neighbors/${neighborId}`, {
        method: 'DELETE',
      });
    },

    async getFavoriteNeighbors() {
      return client.request<Array<{
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
    },

    async toggleNeighborFavorite(neighborId: number) {
      return client.request<{
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
    },

    async getNeighborContacts(neighborId: number) {
      return client.request<Array<{
        id: number;
        neighbor_id: number;
        contact_type: string;
        contact_value: string;
        created_at: string;
      }>>(`/business/neighbors/${neighborId}/contacts`);
    },

    async addNeighborContact(neighborId: number, data: { contact_type: string; contact_value: string }) {
      return client.request<{
        id: number;
        neighbor_id: number;
        contact_type: string;
        contact_value: string;
        created_at: string;
      }>(`/business/neighbors/${neighborId}/contacts`, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    },

    async deleteContact(contactId: number) {
      return client.request<{ status: string }>(`/business/contacts/${contactId}`, {
        method: 'DELETE',
      });
    },

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
      return client.request<Array<{
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
    },

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
      return client.request<{
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
    },

    // ============ 자동응답 ============

    async getAutoResponseStatus() {
      return client.request<{
        running: boolean;
        check_interval: number;
        processed_count: number;
      }>('/business/auto-response/status');
    },

    async startAutoResponse() {
      return client.request<{ status: string; running: boolean }>('/business/auto-response/start', {
        method: 'POST',
      });
    },

    async stopAutoResponse() {
      return client.request<{ status: string; running: boolean }>('/business/auto-response/stop', {
        method: 'POST',
      });
    },
  });
}
