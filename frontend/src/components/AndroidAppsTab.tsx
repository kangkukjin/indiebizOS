/**
 * AndroidAppsTab.tsx
 * 안드로이드 앱 정리 탭 - 앱 목록, 선택/삭제, 검색, 페이지네이션
 */

import { useState } from 'react';
import {
  Trash2, Search, Loader2, Package, HardDrive, Clock3
} from 'lucide-react';

// ─── 타입 ─────────────────────────────
export interface AppItem {
  package: string;
  name: string;
  size?: string;
  last_used?: string;
  total_time_formatted?: string;
}

interface AndroidAppsTabProps {
  getApiUrl: () => string;
  apps: AppItem[];
  setApps: React.Dispatch<React.SetStateAction<AppItem[]>>;
  addAssistantMessage: (content: string) => void;
  loadApps: (page?: number) => Promise<void>;
  // 페이지네이션
  appPage: number;
  appTotalCount: number;
  appHasMore: boolean;
  PAGE_SIZE: number;
}

// ─── 컴포넌트 ─────────────────────────
export function AndroidAppsTab({
  getApiUrl,
  apps,
  setApps,
  addAssistantMessage,
  loadApps,
  appPage,
  appTotalCount,
  appHasMore,
  PAGE_SIZE,
}: AndroidAppsTabProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedApps, setSelectedApps] = useState<Set<string>>(new Set());
  const [deletingApp, setDeletingApp] = useState<string | null>(null);

  // 검색 필터링
  const filteredApps = apps.filter(a =>
    a.package?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // 앱 선택 토글
  const toggleAppSelection = (packageName: string) => {
    setSelectedApps(prev => {
      const next = new Set(prev);
      if (next.has(packageName)) next.delete(packageName);
      else next.add(packageName);
      return next;
    });
  };

  // 앱 삭제
  const uninstallApp = async (packageName: string) => {
    if (!confirm(`${packageName} 앱을 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    setDeletingApp(packageName);
    try {
      const res = await fetch(`${getApiUrl()}/android/apps/${packageName}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (data.success) {
        setApps(prev => prev.filter(a => a.package !== packageName));
        setSelectedApps(prev => {
          const next = new Set(prev);
          next.delete(packageName);
          return next;
        });
        addAssistantMessage(`${packageName} 앱이 삭제되었습니다.`);
      } else {
        addAssistantMessage(`삭제 실패: ${data.message}`);
      }
    } catch (e) {
      console.error('앱 삭제 실패:', e);
      addAssistantMessage('앱 삭제 중 오류가 발생했습니다.');
    }
    setDeletingApp(null);
  };

  // 선택된 앱 삭제
  const uninstallSelectedApps = async () => {
    if (selectedApps.size === 0) return;
    if (!confirm(`선택된 ${selectedApps.size}개의 앱을 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;

    for (const pkg of selectedApps) {
      setDeletingApp(pkg);
      try {
        const res = await fetch(`${getApiUrl()}/android/apps/${pkg}`, {
          method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
          setApps(prev => prev.filter(a => a.package !== pkg));
        }
      } catch (e) {
        console.error(`앱 삭제 실패 (${pkg}):`, e);
      }
    }
    addAssistantMessage(`${selectedApps.size}개의 앱이 삭제되었습니다.`);
    setSelectedApps(new Set());
    setDeletingApp(null);
  };

  // ─── 렌더링 ─────────────────────────
  return (
    <>
      {/* 검색 */}
      <div className="px-4 py-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="앱 검색..."
            className="w-full pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      <div className="flex flex-col h-full">
        {/* 선택 삭제 버튼 */}
        {selectedApps.size > 0 && (
          <div className="sticky top-0 bg-gray-800 px-4 py-2 border-b border-gray-700 flex items-center justify-between z-10">
            <span className="text-sm text-gray-300">{selectedApps.size}개 선택됨</span>
            <button
              onClick={uninstallSelectedApps}
              disabled={!!deletingApp}
              className="flex items-center gap-2 px-3 py-1 bg-red-600 rounded-lg text-sm hover:bg-red-700 disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" />
              선택 삭제
            </button>
          </div>
        )}

        <div className="flex-1 divide-y divide-gray-800 overflow-y-auto">
          {filteredApps.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-gray-500 mb-2">앱 목록을 불러오는 중...</p>
              <p className="text-xs text-gray-600">잠시만 기다려주세요.</p>
            </div>
          ) : (
            filteredApps.map(app => (
              <div
                key={app.package}
                className={`flex items-center px-4 py-3 hover:bg-gray-800 ${
                  selectedApps.has(app.package) ? 'bg-gray-800/50' : ''
                }`}
              >
                {/* 체크박스 */}
                <button
                  onClick={() => toggleAppSelection(app.package)}
                  className={`w-5 h-5 rounded border mr-3 flex items-center justify-center ${
                    selectedApps.has(app.package)
                      ? 'bg-blue-500 border-blue-500'
                      : 'border-gray-600'
                  }`}
                >
                  {selectedApps.has(app.package) && (
                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>

                {/* 앱 아이콘 */}
                <div className="w-10 h-10 bg-gray-700 rounded-lg flex items-center justify-center mr-3">
                  <Package className="w-5 h-5 text-gray-400" />
                </div>

                {/* 앱 정보 */}
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate text-sm">{app.name || app.package.split('.').pop()}</div>
                  <div className="text-xs text-gray-500 truncate">{app.package}</div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                    {app.size && (
                      <span className="flex items-center gap-1">
                        <HardDrive className="w-3 h-3" />
                        {app.size}
                      </span>
                    )}
                    {app.total_time_formatted && (
                      <span className="flex items-center gap-1">
                        <Clock3 className="w-3 h-3" />
                        {app.total_time_formatted}
                      </span>
                    )}
                  </div>
                </div>

                {/* 삭제 버튼 */}
                <button
                  onClick={() => uninstallApp(app.package)}
                  disabled={deletingApp === app.package}
                  className="p-2 hover:bg-gray-700 rounded-full text-red-500 disabled:opacity-50"
                >
                  {deletingApp === app.package ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                </button>
              </div>
            ))
          )}
        </div>

        {/* 페이지네이션 */}
        {appTotalCount > PAGE_SIZE && (
          <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 px-4 py-3 flex items-center justify-between">
            <div className="text-xs text-gray-400">
              전체 {appTotalCount}개 중 {appPage * PAGE_SIZE + 1}~{Math.min((appPage + 1) * PAGE_SIZE, appTotalCount)}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => loadApps(appPage - 1)}
                disabled={appPage === 0}
                className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                이전
              </button>
              <span className="text-sm text-gray-300">
                {appPage + 1} / {Math.ceil(appTotalCount / PAGE_SIZE)}
              </span>
              <button
                onClick={() => loadApps(appPage + 1)}
                disabled={!appHasMore}
                className="px-3 py-1 bg-gray-700 rounded text-sm hover:bg-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                다음
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
