/**
 * PCManager - AI 파일 탐색기
 */

import { useEffect, useState } from 'react';
import {
  Folder,
  File,
  HardDrive,
  ChevronRight,
  Home,
  RefreshCw,
  ArrowUp,
  Monitor,
  Usb,
  BarChart3,
  FolderOpen
} from 'lucide-react';
import { PCManagerAnalyze } from './PCManagerAnalyze';

interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: string;
}

interface DriveInfo {
  name: string;
  path: string;
  total?: number;
  free?: number;
  type: 'internal' | 'external';
}

interface PCManagerProps {
  initialPath?: string | null;
}

export function PCManager({ initialPath }: PCManagerProps) {
  const [currentPath, setCurrentPath] = useState<string>(initialPath || '');
  const [items, setItems] = useState<FileItem[]>([]);
  const [drives, setDrives] = useState<DriveInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [isAnalyzeMode, setIsAnalyzeMode] = useState(false);

  // API 포트 가져오기
  const getApiUrl = async () => {
    if (window.electron?.getApiPort) {
      const port = await window.electron.getApiPort();
      return `http://127.0.0.1:${port}`;
    }
    return 'http://127.0.0.1:8765';
  };

  // 드라이브 목록 로드
  const loadDrives = async () => {
    try {
      const apiUrl = await getApiUrl();
      const response = await fetch(`${apiUrl}/pcmanager/drives`);
      if (response.ok) {
        const data = await response.json();
        setDrives(data.drives || []);
      }
    } catch (err) {
      console.error('드라이브 로드 실패:', err);
    }
  };

  // 디렉토리 내용 로드
  const loadDirectory = async (path: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const apiUrl = await getApiUrl();
      const response = await fetch(`${apiUrl}/pcmanager/list?path=${encodeURIComponent(path)}`);
      if (response.ok) {
        const data = await response.json();
        setItems(data.items || []);
        setCurrentPath(data.path || path);
      } else {
        const errData = await response.json();
        setError(errData.detail || '디렉토리를 열 수 없습니다.');
      }
    } catch (err) {
      setError('서버에 연결할 수 없습니다.');
      console.error('디렉토리 로드 실패:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // 초기 로드
  useEffect(() => {
    loadDrives();
    loadDirectory(initialPath || '');
  }, [initialPath]);

  // 상위 디렉토리로 이동
  const goUp = () => {
    if (!currentPath) return;
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    const parentPath = parts.length > 0 ? '/' + parts.join('/') : '/';
    loadDirectory(parentPath);
  };

  // 홈으로 이동
  const goHome = () => {
    loadDirectory('');
  };

  // 아이템 더블클릭
  const handleItemDoubleClick = (item: FileItem) => {
    if (item.type === 'directory') {
      loadDirectory(item.path);
    }
  };

  // 드라이브 클릭
  const handleDriveClick = (drive: DriveInfo) => {
    loadDirectory(drive.path);
  };

  // 파일 크기 포맷
  const formatSize = (bytes?: number) => {
    if (bytes === undefined) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  // 경로 표시 (브레드크럼)
  const pathParts = currentPath.split('/').filter(Boolean);

  return (
    <div className="h-full flex flex-col bg-[#FAFAF8]">
      {/* 타이틀바 영역 (드래그 가능) */}
      <div className="h-12 bg-[#F5F1EB] flex items-center px-4 drag border-b border-[#E5E0D8]">
        <div className="w-20" /> {/* 트래픽 라이트 공간 */}
        <div className="flex-1 flex items-center justify-center">
          <Monitor className="w-4 h-4 text-[#6B5B4F] mr-2" />
          <span className="text-sm font-medium text-[#4A4A4A]">PC Manager</span>
        </div>
        {/* 모드 전환 버튼 */}
        <div className="w-32 flex justify-end no-drag">
          <button
            onClick={() => setIsAnalyzeMode(!isAnalyzeMode)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
              isAnalyzeMode
                ? 'bg-[#6B5B4F] text-white'
                : 'bg-[#E8E4DC] text-[#6B5B4F] hover:bg-[#DDD8D0]'
            }`}
            title={isAnalyzeMode ? '탐색 모드로 전환' : '분석 모드로 전환'}
          >
            {isAnalyzeMode ? (
              <>
                <FolderOpen className="w-4 h-4" />
                탐색
              </>
            ) : (
              <>
                <BarChart3 className="w-4 h-4" />
                분석
              </>
            )}
          </button>
        </div>
      </div>

      {isAnalyzeMode ? (
        /* 분석 모드 */
        <PCManagerAnalyze />
      ) : (
        /* 탐색 모드 */
        <div className="flex-1 flex overflow-hidden">
          {/* 사이드바 - 드라이브 목록 */}
          <div className="w-56 bg-[#F5F1EB] border-r border-[#E5E0D8] overflow-y-auto p-3">
            <div className="text-xs font-semibold text-[#8B7B6B] mb-2 px-2">저장소</div>

            {/* 홈 */}
            <button
              onClick={goHome}
              className="w-full flex items-center px-2 py-1.5 rounded-md hover:bg-[#E8E4DC] text-sm text-[#4A4A4A] mb-1"
            >
              <Home className="w-4 h-4 mr-2 text-[#6B5B4F]" />
              홈
            </button>

            {/* 드라이브 목록 */}
            {drives.map((drive) => (
              <button
                key={drive.path}
                onClick={() => handleDriveClick(drive)}
                className="w-full flex items-center px-2 py-1.5 rounded-md hover:bg-[#E8E4DC] text-sm text-[#4A4A4A] mb-1"
              >
                {drive.type === 'external' ? (
                  <Usb className="w-4 h-4 mr-2 text-[#6B5B4F]" />
                ) : (
                  <HardDrive className="w-4 h-4 mr-2 text-[#6B5B4F]" />
                )}
                <span className="truncate">{drive.name}</span>
              </button>
            ))}
          </div>

          {/* 메인 콘텐츠 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* 툴바 */}
            <div className="h-10 bg-[#F5F1EB] border-b border-[#E5E0D8] flex items-center px-3 gap-2">
              <button
                onClick={goUp}
                disabled={!currentPath || currentPath === '/'}
                className="p-1.5 rounded hover:bg-[#E8E4DC] disabled:opacity-40"
                title="상위 폴더"
              >
                <ArrowUp className="w-4 h-4 text-[#6B5B4F]" />
              </button>
              <button
                onClick={() => loadDirectory(currentPath)}
                className="p-1.5 rounded hover:bg-[#E8E4DC]"
                title="새로고침"
              >
                <RefreshCw className="w-4 h-4 text-[#6B5B4F]" />
              </button>

              {/* 경로 표시 */}
              <div className="flex-1 flex items-center bg-white rounded px-2 py-1 text-sm text-[#4A4A4A] overflow-hidden">
                <button onClick={goHome} className="hover:text-[#6B5B4F]">
                  <Home className="w-3.5 h-3.5" />
                </button>
                {pathParts.map((part, idx) => (
                  <span key={idx} className="flex items-center">
                    <ChevronRight className="w-3 h-3 mx-1 text-[#A0A0A0]" />
                    <button
                      onClick={() => {
                        const targetPath = '/' + pathParts.slice(0, idx + 1).join('/');
                        loadDirectory(targetPath);
                      }}
                      className="hover:text-[#6B5B4F] truncate max-w-32"
                    >
                      {part}
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* 파일 목록 */}
            <div className="flex-1 overflow-y-auto p-3">
              {isLoading ? (
                <div className="flex items-center justify-center h-32 text-[#8B7B6B]">
                  불러오는 중...
                </div>
              ) : error ? (
                <div className="flex items-center justify-center h-32 text-red-500">
                  {error}
                </div>
              ) : items.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-[#8B7B6B]">
                  빈 폴더입니다
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-1">
                  {items.map((item) => (
                    <div
                      key={item.path}
                      onClick={() => setSelectedItem(item.path)}
                      onDoubleClick={() => handleItemDoubleClick(item)}
                      className={`flex items-center px-3 py-2 rounded-lg cursor-pointer ${
                        selectedItem === item.path
                          ? 'bg-[#E8E4DC]'
                          : 'hover:bg-[#F0EDE7]'
                      }`}
                    >
                      {item.type === 'directory' ? (
                        <Folder className="w-5 h-5 mr-3 text-[#D4A574]" />
                      ) : (
                        <File className="w-5 h-5 mr-3 text-[#8B7B6B]" />
                      )}
                      <span className="flex-1 text-sm text-[#4A4A4A] truncate">
                        {item.name}
                      </span>
                      <span className="text-xs text-[#A0A0A0] ml-4">
                        {item.type === 'file' ? formatSize(item.size) : ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 상태바 */}
            <div className="h-7 bg-[#F5F1EB] border-t border-[#E5E0D8] flex items-center px-3 text-xs text-[#8B7B6B]">
              {items.length}개 항목
              {selectedItem && ` • 선택됨: ${items.find(i => i.path === selectedItem)?.name || ''}`}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
