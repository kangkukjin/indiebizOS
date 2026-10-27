/**
 * 도구 실행 히스토리 패널 (Claude Desktop 스타일)
 */
import { useEffect, useState } from 'react';
import { BACKEND_ORIGIN } from '../../lib/backend-origin';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import type { ToolActivity, ToolProgress } from './types';
import { parseImagePaths } from '../../lib/message-images';

/** 마지막 움직임 경과를 사람 말로 — 멈춤과 느림을 가르는 유일한 증거라 초 단위로 흐른다 */
function formatAge(seconds: number): string {
  if (seconds < 2) return '지금';
  if (seconds < 60) return `${seconds}초 전`;
  const m = Math.floor(seconds / 60), s = seconds % 60;
  return s ? `${m}분 ${s}초 전` : `${m}분 전`;
}

/** 진행 신고(ibl_progress)를 한 줄로 — 현재 액션 · 호출 번호 · each 회차 · 하위 step */
function describeProgress(p: ToolProgress): string {
  const parts: string[] = [];
  const d = p.detail || {};
  const computing = d.phase === 'compute';
  if (p.action) {
    let action = p.action;
    if (p.reused) action += '(재사용)';
    if (p.of) action += ` (${p.step}/${p.of})`;
    else if (p.step) action += ` · ${p.step}번째 호출`;
    parts.push(action + (computing ? ' 뒤' : ''));
  }
  if (d.row && d.rows) parts.push(`each ${d.row}/${d.rows}행${d.row_label ? `(${d.row_label})` : ''}${computing ? ' 계산 중' : ''}`);
  if (d.substep && d.substeps) parts.push(`하위 ${d.substep}/${d.substeps} ${d.subaction ?? ''}`.trim());
  const known = new Set(['row', 'rows', 'row_label', 'substep', 'substeps', 'subaction', 'phase']);
  const rest = Object.entries(d).filter(([k]) => !known.has(k)).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`);
  if (rest.length) parts.push(rest.join(' '));
  return parts.join(' · ');
}

/** 실행 중인 도구 카드 아래의 진행 줄 — 1초마다 "마지막 움직임" 경과가 흐른다 */
function ProgressLine({ progress, waitText }: { progress: ToolProgress; waitText: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const age = Math.max(0, Math.round((now - progress.at) / 1000));
  const text = describeProgress(progress) || '진행 중';
  // 30초 넘게 움직임이 없으면 색으로 알린다 — "죽었나, 오래 걸리나"를 사람이 바로 가른다.
  const ageClass = age >= 120 ? 'text-red-500' : age >= 30 ? 'text-amber-600' : waitText;
  return (
    <div className={`px-3 py-2 flex items-center gap-2 text-[11px] ${waitText}`} data-testid="tool-progress">
      <Loader2 size={12} className="animate-spin shrink-0" />
      <span className="font-mono break-all">{text}</span>
      <span className={`ml-auto shrink-0 whitespace-nowrap ${ageClass}`}>마지막 움직임 {formatAge(age)}</span>
    </div>
  );
}

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
            ) : tool.isError ? (
              <XCircle size={14} className="text-red-500 shrink-0" />
            ) : (
              <CheckCircle2 size={14} className="text-green-500 shrink-0" />
            )}
            <span className={`font-semibold ${styles.textColor}`}>{tool.name}</span>
            {tool.status === 'running' && (
              <span className={`ml-auto text-[10px] ${styles.badgeText} ${styles.badgeBg} px-2 py-0.5 rounded-full`}>실행 중</span>
            )}
            {tool.status !== 'running' && tool.isError && (
              <span className="ml-auto text-[10px] text-red-600 bg-red-100 px-2 py-0.5 rounded-full">실패</span>
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
              <div className={`px-3 py-2 ${tool.isError ? 'bg-red-50/40' : styles.resultBg}`}>
                <div className={`text-[10px] font-medium mb-1 flex items-center gap-1 ${tool.isError ? 'text-red-600' : 'text-green-600'}`}>
                  <span>{tool.isError ? '⚠️' : '📤'}</span> {tool.isError ? '실패' : '결과'}
                </div>
                <pre className={`text-[11px] ${styles.preText} ${styles.preBg} p-2 rounded border ${styles.preBorder} overflow-x-auto max-h-60 overflow-y-auto whitespace-pre-wrap break-words`}>
                  {tool.result}
                </pre>
                {parsed.images.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {parsed.images.map((imgPath, imgIdx) => (
                      <img
                        key={imgIdx}
                        src={`${BACKEND_ORIGIN}/image?path=${encodeURIComponent(imgPath)}`}
                        alt={`도구 결과 이미지 ${imgIdx + 1}`}
                        className={`max-w-full max-h-80 rounded border ${styles.imgBorder} cursor-pointer hover:opacity-90 transition-opacity`}
                        onClick={() => window.open(`${BACKEND_ORIGIN}/image?path=${encodeURIComponent(imgPath)}`, '_blank')}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })()}

          {/* 실행 중일 때: 진행 신고가 있으면 현재 액션·마지막 움직임, 없으면 로딩 표시 */}
          {tool.status === 'running' && !tool.result && (
            tool.progress ? (
              <ProgressLine progress={tool.progress} waitText={styles.waitText} />
            ) : (
              <div className={`px-3 py-3 flex items-center justify-center gap-2 ${styles.waitText}`}>
                <Loader2 size={12} className="animate-spin" />
                <span className="text-[11px]">결과를 기다리는 중...</span>
              </div>
            )
          )}
        </div>
      ))}
    </div>
  );
}
