/**
 * api-packages.ts - 도구 패키지 관련 API 메서드
 * APIClient mixin: 패키지 CRUD, 분석, 등록, Nostr 공유
 */

import type { APIClientCore } from './api-types';

/** [self:install_lib] 승인 대기/승인 항목 (backend/datastore/install_approvals.py) */
export interface InstallApprovalEntry {
  package: string;
  spec?: string;
  reason?: string;
  source?: string;
  requested_at?: string;
  approved_at?: string;
}

export function applyPackagesMethods<T extends APIClientCore>(client: T) {
  return Object.assign(client, {

    // ============ 도구 패키지 ============

    async getPackages() {
      return client.request<{
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
    },

    async getPackageInfo(packageId: string) {
      return client.request<{
        id: string;
        name: string;
        description: string;
        version?: string;
        installed: boolean;
        files?: string[];
        tools?: Array<{ name: string; description: string }>;
      }>(`/packages/${packageId}`);
    },

    async installPackage(packageId: string) {
      return client.request<{
        status: string;
        package: any;
        message: string;
      }>(`/packages/${packageId}/install`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
    },

    // ============ 라이브러리 설치 승인 ([self:install_lib] 사람 전용 채널) ============

    async getInstallApprovals() {
      return client.request<{
        pending: Record<string, InstallApprovalEntry>;
        approved: Record<string, InstallApprovalEntry>;
      }>('/install-approvals');
    },

    async approveInstall(pkg: string) {
      return client.request<{ success: boolean; approved: InstallApprovalEntry; message: string }>(
        '/install-approvals/approve',
        { method: 'POST', body: JSON.stringify({ package: pkg }) },
      );
    },

    async rejectInstall(pkg: string) {
      return client.request<{ success: boolean; removed: InstallApprovalEntry }>(
        '/install-approvals/reject',
        { method: 'POST', body: JSON.stringify({ package: pkg }) },
      );
    },

    async uninstallPackage(packageId: string) {
      return client.request<{
        status: string;
        package_id: string;
        message: string;
      }>(`/packages/${packageId}/uninstall`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
    },

    async analyzeFolder(folderPath: string) {
      return client.request<{
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
    },

    async analyzeFolderWithAI(folderPath: string) {
      return client.request<{
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
    },

    async registerFolder(
      folderPath: string,
      name?: string,
      description?: string,
      readmeContent?: string
    ) {
      return client.request<{
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
    },

    async removePackage(packageId: string) {
      return client.request<{
        status: string;
        package_id: string;
        message: string;
      }>(`/packages/${packageId}/remove`, {
        method: 'DELETE',
        body: JSON.stringify({}),
      });
    },

    // ============ 패키지 공개/검색 (Nostr) ============

    async publishPackageToNostr(packageId: string, installInstructions?: string, signature?: string) {
      return client.request<{
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
    },

    async generateInstallInstructions(packageId: string) {
      return client.request<{
        instructions: string;
      }>(`/packages/${packageId}/generate-install`);
    },

    async searchPackagesOnNostr(query?: string, limit = 20) {
      const params = new URLSearchParams();
      if (query) params.append('query', query);
      params.append('limit', String(limit));
      return client.request<{
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
    },
  });
}
