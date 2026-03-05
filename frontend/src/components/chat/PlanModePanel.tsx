/**
 * 계획 모드 패널 (승인/거부)
 */
import { FileEdit, Loader2, Check, XCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { PlanModeState } from './types';

interface PlanModePanelProps {
  planMode: PlanModeState;
  onApprove: () => void;
  onReject: () => void;
}

export function PlanModePanel({ planMode, onApprove, onReject }: PlanModePanelProps) {
  if (!planMode.active) return null;

  // 승인 대기 상태
  if (planMode.phase === 'awaiting_approval') {
    return (
      <div className="px-4 py-3 bg-purple-50 border-b border-purple-200 shrink-0 max-h-64 overflow-y-auto">
        <div className="flex items-center gap-2 text-purple-700 mb-3">
          <FileEdit size={16} />
          <span className="text-sm font-medium">구현 계획 검토</span>
        </div>
        <div className="bg-white rounded-lg p-3 border border-purple-100 mb-3">
          <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 text-gray-700">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{planMode.plan_content || ''}</ReactMarkdown>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onReject}
            className="px-4 py-2 bg-gray-200 text-gray-700 text-sm rounded-lg hover:bg-gray-300 transition-colors flex items-center gap-2"
          >
            <XCircle size={14} />
            수정 요청
          </button>
          <button
            onClick={onApprove}
            className="px-4 py-2 bg-purple-500 text-white text-sm rounded-lg hover:bg-purple-600 transition-colors flex items-center gap-2"
          >
            <Check size={14} />
            계획 승인
          </button>
        </div>
      </div>
    );
  }

  // 진행 중 표시
  return (
    <div className="px-4 py-2 bg-purple-50 border-b border-purple-200 shrink-0">
      <div className="flex items-center gap-2 text-purple-700">
        <FileEdit size={14} />
        <span className="text-xs font-medium">계획 모드 진행 중</span>
        <Loader2 size={12} className="animate-spin text-purple-500" />
        <span className="text-xs text-purple-500">
          {planMode.phase === 'exploring' ? '코드 탐색 중...' :
           planMode.phase === 'designing' ? '설계 중...' :
           planMode.phase === 'reviewing' ? '검토 중...' :
           planMode.phase === 'finalizing' ? '마무리 중...' : '진행 중...'}
        </span>
      </div>
    </div>
  );
}
