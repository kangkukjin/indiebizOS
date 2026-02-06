/**
 * LogViewer - 실시간 로그 뷰어 컴포넌트
 */

import { useEffect, useRef, useState } from 'react';

export function LogViewer() {
  const [logs, setLogs] = useState<string[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState('');
  const logContainerRef = useRef<HTMLDivElement>(null);

  // 로그 리스너 설정
  useEffect(() => {
    if (!window.electron) return;

    // 기존 로그 히스토리 수신
    window.electron.onLogHistory?.((history) => {
      setLogs(history);
    });

    // 새 로그 메시지 수신
    window.electron.onLogMessage?.((message) => {
      setLogs((prev) => [...prev, message]);
    });

    // 로그 클리어 이벤트
    window.electron.onLogCleared?.(() => {
      setLogs([]);
    });

    // 클린업
    return () => {
      window.electron?.removeLogListeners?.();
    };
  }, []);

  // 자동 스크롤
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // 필터링된 로그
  const filteredLogs = filter
    ? logs.filter((log) => log.toLowerCase().includes(filter.toLowerCase()))
    : logs;

  // 로그 클리어
  const handleClear = () => {
    window.electron?.clearLogs?.();
  };

  // 로그 복사
  const handleCopy = () => {
    const text = filteredLogs.join('\n');
    window.electron?.copyToClipboard?.(text);
  };

  // 로그 라인 색상
  const getLogColor = (log: string) => {
    if (log.includes('[Error]') || log.includes('Error')) return 'text-red-400';
    if (log.includes('[Python Error]')) return 'text-red-400';
    if (log.includes('[Warning]') || log.includes('WARNING')) return 'text-yellow-400';
    if (log.includes('[Init]')) return 'text-blue-400';
    if (log.includes('[Electron]')) return 'text-purple-400';
    if (log.includes('[Python]')) return 'text-green-400';
    return 'text-gray-300';
  };

  const isMac = window.electron?.platform === 'darwin';

  return (
    <div className="h-screen w-screen flex flex-col bg-gray-900 text-white">
      {/* 타이틀바 (macOS 트래픽 라이트 공간) */}
      {isMac && (
        <div className="h-8 bg-gray-800 flex items-center justify-center drag">
          <span className="text-sm text-gray-400">IndieBiz 로그</span>
        </div>
      )}

      {/* 툴바 */}
      <div className="flex items-center gap-2 p-2 bg-gray-800 border-b border-gray-700">
        {/* 필터 입력 */}
        <input
          type="text"
          placeholder="필터..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="flex-1 px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-sm focus:outline-none focus:border-blue-500"
        />

        {/* 자동 스크롤 토글 */}
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`px-3 py-1.5 rounded text-sm ${
            autoScroll
              ? 'bg-blue-600 hover:bg-blue-700'
              : 'bg-gray-700 hover:bg-gray-600'
          }`}
          title="자동 스크롤"
        >
          ⬇️ 자동
        </button>

        {/* 복사 버튼 */}
        <button
          onClick={handleCopy}
          className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm"
          title="로그 복사"
        >
          📋 복사
        </button>

        {/* 클리어 버튼 */}
        <button
          onClick={handleClear}
          className="px-3 py-1.5 bg-gray-700 hover:bg-red-600 rounded text-sm"
          title="로그 클리어"
        >
          🗑️ 클리어
        </button>
      </div>

      {/* 로그 영역 */}
      <div
        ref={logContainerRef}
        className="flex-1 overflow-auto p-2 font-mono text-xs leading-5"
      >
        {filteredLogs.length === 0 ? (
          <div className="text-gray-500 text-center py-8">
            로그가 없습니다.
          </div>
        ) : (
          filteredLogs.map((log, index) => (
            <div
              key={index}
              className={`whitespace-pre-wrap break-all hover:bg-gray-800 px-1 rounded ${getLogColor(log)}`}
            >
              {log}
            </div>
          ))
        )}
      </div>

      {/* 상태바 */}
      <div className="flex items-center justify-between px-3 py-1 bg-gray-800 border-t border-gray-700 text-xs text-gray-400">
        <span>총 {logs.length}줄 {filter && `(필터: ${filteredLogs.length}줄)`}</span>
        <span>{autoScroll ? '자동 스크롤 켜짐' : '자동 스크롤 꺼짐'}</span>
      </div>
    </div>
  );
}
