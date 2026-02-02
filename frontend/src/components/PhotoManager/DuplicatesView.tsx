/**
 * DuplicatesView - 중복 파일 뷰 컴포넌트
 */

import { useState } from 'react';
import { Copy, ChevronRight } from 'lucide-react';
import type { DuplicateGroup } from './types';

interface DuplicatesViewProps {
  groups: DuplicateGroup[];
  stats: { groups: number; total: number; wasted: number };
}

export function DuplicatesView({ groups, stats }: DuplicatesViewProps) {
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      {/* 요약 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{stats.groups}</div>
          <div className="text-sm text-[#9B8B7A]">중복 그룹</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#5C5347]">{stats.total}</div>
          <div className="text-sm text-[#9B8B7A]">중복 파일</div>
        </div>
        <div className="bg-white p-4 rounded-lg border border-[#E8E4DC]">
          <div className="text-2xl font-bold text-[#D97706]">{stats.wasted.toLocaleString()} MB</div>
          <div className="text-sm text-[#9B8B7A]">낭비된 용량</div>
        </div>
      </div>

      {/* 중복 그룹 목록 */}
      {groups.length === 0 ? (
        <div className="text-center py-12 text-[#9B8B7A]">
          중복 파일이 없습니다
        </div>
      ) : (
        <div className="space-y-2">
          {groups.map((group) => (
            <div key={group.hash} className="bg-white rounded-lg border border-[#E8E4DC] overflow-hidden">
              <button
                onClick={() => setExpandedGroup(expandedGroup === group.hash ? null : group.hash)}
                className="w-full flex items-center justify-between p-3 hover:bg-[#FAF9F7] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Copy className="text-[#8B7355]" />
                  <span className="text-sm font-medium text-[#5C5347]">
                    {group.count}개 동일 파일
                  </span>
                  <span className="text-xs text-[#9B8B7A]">
                    ({group.hash})
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-[#D97706]">
                    {group.wasted_mb.toLocaleString()} MB 낭비
                  </span>
                  <ChevronRight
                    className={`text-[#9B8B7A] transition-transform ${expandedGroup === group.hash ? 'rotate-90' : ''}`}
                  />
                </div>
              </button>

              {expandedGroup === group.hash && (
                <div className="border-t border-[#E8E4DC] p-3 bg-[#FAF9F7]">
                  <div className="space-y-2">
                    {group.files.map((file, idx) => (
                      <div
                        key={file.id}
                        className={`flex items-center gap-3 p-2 rounded-lg ${idx === 0 ? 'bg-green-50 border border-green-200' : 'bg-white border border-[#E8E4DC]'}`}
                      >
                        <span className="text-xs text-[#9B8B7A] w-6">
                          {idx === 0 ? '원본' : `#${idx + 1}`}
                        </span>
                        <span className="flex-1 text-sm text-[#5C5347] truncate">
                          {file.path}
                        </span>
                        <span className="text-xs text-[#9B8B7A]">
                          {file.size_mb} MB
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
