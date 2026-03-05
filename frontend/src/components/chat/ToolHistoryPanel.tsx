/**
 * 도구 실행 히스토리 패널 (Claude Desktop 스타일)
 */
import { Loader2, CheckCircle2 } from 'lucide-react';
import type { ToolActivity } from './types';
import { parseImagePaths } from './chatUtils';

interface ToolHistoryPanelProps {
  toolHistory: ToolActivity[];
  variant?: 'warm' | 'neutral';  // warm: 프로젝트 채팅, neutral: 시스템 AI
}

export function ToolHistoryPanel({ toolHistory, variant = 'warm' }: ToolHistoryPanelProps) {
  if (toolHistory.length === 0) return null;

  const styles = variant === 'warm' ? {
    border: 'border-[#E5DFD5]',
    bg: 'bg-white',
    headerBg: 'bg-gradient-to-r from-[#F5F1EB] to-[#EAE4DA]',
    headerBorder: 'border-[#E5DFD5]',
    textColor: 'text-[#4A4035]',
    spinColor: 'text-[#D97706]',
    badgeBg: 'bg-amber-100',
    badgeText: 'text-[#D97706]',
    inputBg: 'bg-blue-50/30',
    inputBorder: 'border-[#E5DFD5]/50',
    resultBg: 'bg-green-50/30',
    preBg: 'bg-white/80',
    preBorder: 'border-[#E5DFD5]/50',
    preText: 'text-[#4A4035]',
    waitText: 'text-[#A09080]',
    imgBorder: 'border-[#E5DFD5]',
  } : {
    border: 'border-gray-200',
    bg: 'bg-white',
    headerBg: 'bg-gradient-to-r from-gray-50 to-gray-100',
    headerBorder: 'border-gray-200',
    textColor: 'text-gray-800',
    spinColor: 'text-amber-500',
    badgeBg: 'bg-amber-100',
    badgeText: 'text-amber-600',
    inputBg: 'bg-blue-50/30',
    inputBorder: 'border-gray-100',
    resultBg: 'bg-green-50/30',
    preBg: 'bg-white/80',
    preBorder: 'border-gray-100',
    preText: 'text-gray-700',
    waitText: 'text-gray-500',
    imgBorder: 'border-gray-200',
  };

  return (
    <div className="mb-3 space-y-2">
      {toolHistory.map((tool, idx) => (
        <div key={idx} className={`text-xs border ${styles.border} rounded-lg overflow-hidden ${styles.bg}`}>
          {/* 도구 헤더 */}
          <div className={`flex items-center gap-2 px-3 py-2 ${styles.headerBg} border-b ${styles.headerBorder}`}>
            {tool.status === 'running' ? (
              <Loader2 size={14} className={`animate-spin ${styles.spinColor} shrink-0`} />
            ) : (
              <CheckCircle2 size={14} className="text-green-500 shrink-0" />
            )}
            <span className={`font-semibold ${styles.textColor}`}>{tool.name}</span>
            {tool.status === 'running' && (
              <span className={`ml-auto text-[10px] ${styles.badgeText} ${styles.badgeBg} px-2 py-0.5 rounded-full`}>실행 중</span>
            )}
          </div>

          {/* 입력 파라미터 */}
          {tool.input && Object.keys(tool.input).length > 0 && (
            <div className={`px-3 py-2 border-b ${styles.inputBorder} ${styles.inputBg}`}>
              <div className="text-[10px] text-blue-600 font-medium mb-1 flex items-center gap-1">
                <span>📥</span> 입력
              </div>
              <pre className={`text-[11px] ${styles.preText} ${styles.preBg} p-2 rounded border ${styles.preBorder} overflow-x-auto max-h-40 overflow-y-auto`}>
                {JSON.stringify(tool.input, null, 2)}
              </pre>
            </div>
          )}

          {/* 결과 */}
          {tool.result && (() => {
            const parsed = parseImagePaths(tool.result);
            return (
              <div className={`px-3 py-2 ${styles.resultBg}`}>
                <div className="text-[10px] text-green-600 font-medium mb-1 flex items-center gap-1">
                  <span>📤</span> 결과
                </div>
                <pre className={`text-[11px] ${styles.preText} ${styles.preBg} p-2 rounded border ${styles.preBorder} overflow-x-auto max-h-60 overflow-y-auto whitespace-pre-wrap break-words`}>
                  {tool.result}
                </pre>
                {parsed.images.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {parsed.images.map((imgPath, imgIdx) => (
                      <img
                        key={imgIdx}
                        src={`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`}
                        alt={`도구 결과 이미지 ${imgIdx + 1}`}
                        className={`max-w-full max-h-80 rounded border ${styles.imgBorder} cursor-pointer hover:opacity-90 transition-opacity`}
                        onClick={() => window.open(`http://127.0.0.1:8765/image?path=${encodeURIComponent(imgPath)}`, '_blank')}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* 실행 중일 때 로딩 표시 */}
          {tool.status === 'running' && !tool.result && (
            <div className={`px-3 py-3 flex items-center justify-center gap-2 ${styles.waitText}`}>
              <Loader2 size={12} className="animate-spin" />
              <span className="text-[11px]">결과를 기다리는 중...</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
