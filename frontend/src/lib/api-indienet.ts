/**
 * api-indienet.ts - IndieNet 관련 API 메서드
 * APIClient mixin: IndieNet 상태, 게시, DM, 보드
 */

import type { APIClientCore } from './api-types';

export function applyIndieNetMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    // ============ IndieNet ============

    async getIndieNetStatus() {
      return client.request<{
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
    },

    async getIndieNetIdentity() {
      return client.request<{
        npub: string;
        display_name: string;
        created_at: string;
      }>('/indienet/identity');
    },

    async updateIndieNetDisplayName(displayName: string) {
      return client.request<{ status: string; display_name: string }>('/indienet/identity/display-name', {
        method: 'PUT',
        body: JSON.stringify({ display_name: displayName }),
      });
    },

    async importIndieNetNsec(nsec: string) {
      return client.request<{
        status: string;
        identity: { npub: string; display_name: string; created_at: string };
      }>('/indienet/identity/import', {
        method: 'POST',
        body: JSON.stringify({ nsec }),
      });
    },

    async resetIndieNetIdentity() {
      return client.request<{
        status: string;
        identity: { npub: string; display_name: string; created_at: string };
      }>('/indienet/identity/reset', {
        method: 'POST',
      });
    },

    async getIndieNetSettings() {
      return client.request<{
        relays: string[];
        default_tags: string[];
        auto_refresh: boolean;
        refresh_interval: number;
      }>('/indienet/settings');
    },

    async updateIndieNetSettings(settings: {
      relays?: string[];
      auto_refresh?: boolean;
      refresh_interval?: number;
    }) {
      return client.request<{ status: string; settings: any }>('/indienet/settings', {
        method: 'PUT',
        body: JSON.stringify(settings),
      });
    },

    async getIndieNetPosts(limit = 50, since?: number) {
      const params = new URLSearchParams({ limit: String(limit) });
      if (since) params.append('since', String(since));
      return client.request<{
        posts: Array<{
          id: string;
          author: string;
          content: string;
          created_at: number;
          tags: string[][];
        }>;
        count: number;
      }>(`/indienet/posts?${params}`);
    },

    async createIndieNetPost(content: string, extraTags?: string[]) {
      return client.request<{ status: string; event_id: string }>('/indienet/posts', {
        method: 'POST',
        body: JSON.stringify({ content, extra_tags: extraTags }),
      });
    },

    async getIndieNetUser(pubkey: string) {
      return client.request<{
        pubkey: string;
        name: string;
        display_name: string;
        about: string;
        picture: string;
      }>(`/indienet/user/${encodeURIComponent(pubkey)}`);
    },

    async getIndieNetDMs(limit = 50, since?: number) {
      const params = new URLSearchParams({ limit: String(limit) });
      if (since) params.append('since', String(since));
      return client.request<{
        dms: Array<{
          id: string;
          from: string;
          content: string;
          created_at: number;
          tags: string[][];
        }>;
        count: number;
      }>(`/indienet/dms?${params}`);
    },

    async sendIndieNetDM(toPubkey: string, content: string) {
      return client.request<{ status: string; event_id: string; to: string; created_at: number }>('/indienet/dms', {
        method: 'POST',
        body: JSON.stringify({ to_pubkey: toPubkey, content }),
      });
    },

    // ============ IndieNet 보드 (커스텀 해시태그 게시판) ============

    async getIndieNetBoards() {
      return client.request<{
        boards: Array<{ name: string; hashtag: string; created_at: string }>;
        active_board: { name: string; hashtag: string; created_at: string } | null;
        count: number;
      }>('/indienet/boards');
    },

    async createIndieNetBoard(name: string, hashtag: string) {
      return client.request<{
        status: string;
        board: { name: string; hashtag: string; created_at: string };
      }>('/indienet/boards', {
        method: 'POST',
        body: JSON.stringify({ name, hashtag }),
      });
    },

    async deleteIndieNetBoard(hashtag: string) {
      return client.request<{ status: string; hashtag: string }>(`/indienet/boards/${encodeURIComponent(hashtag)}`, {
        method: 'DELETE',
      });
    },

    async setActiveIndieNetBoard(hashtag: string | null) {
      return client.request<{
        status: string;
        active_board: { name: string; hashtag: string; created_at: string } | null;
      }>(`/indienet/boards/active${hashtag ? `?hashtag=${encodeURIComponent(hashtag)}` : ''}`, {
        method: 'PUT',
      });
    },

    async getIndieNetBoardPosts(hashtag: string, limit = 50, since?: number) {
      const params = new URLSearchParams();
      params.set('limit', limit.toString());
      if (since) params.set('since', since.toString());
      return client.request<{
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
    },

    async postToIndieNetBoard(content: string, hashtag?: string) {
      return client.request<{
        status: string;
        event_id: string;
        hashtag: string;
        created_at: number;
      }>('/indienet/boards/post', {
        method: 'POST',
        body: JSON.stringify({ content, hashtag }),
      });
    },
  });
}
