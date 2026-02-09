/**
 * SchedulerDialog - 이벤트 & 스케줄 다이얼로그 (읽기 전용)
 * 캘린더 이벤트와 스케줄 작업을 통합 표시합니다.
 */

import { X, Clock, ToggleLeft, ToggleRight, Bell, Zap, MessageSquare, CalendarDays } from 'lucide-react';
import type { SchedulerTask } from '../types';

const TYPE_LABELS: Record<string, string> = {
  anniversary: '기념일',
  birthday: '생일',
  appointment: '약속',
  reminder: '리마인더',
  schedule: '스케줄',
  other: '기타',
};

const TYPE_COLORS: Record<string, string> = {
  anniversary: 'bg-pink-100 text-pink-700',
  birthday: 'bg-purple-100 text-purple-700',
  appointment: 'bg-blue-100 text-blue-700',
  reminder: 'bg-amber-100 text-amber-700',
  schedule: 'bg-green-100 text-green-700',
  other: 'bg-gray-100 text-gray-600',
};

const TYPE_EMOJI: Record<string, string> = {
  anniversary: '\uD83D\uDC8D',
  birthday: '\uD83C\uDF82',
  appointment: '\uD83D\uDCCB',
  reminder: '\uD83D\uDD14',
  schedule: '\u26A1',
  other: '\uD83D\uDCCC',
};

const REPEAT_LABELS: Record<string, string> = {
  none: '1회',
  daily: '매일',
  weekly: '매주',
  monthly: '매월',
  yearly: '매년',
  interval: '간격',
};

const REPEAT_COLORS: Record<string, string> = {
  none: 'bg-gray-100 text-gray-500',
  daily: 'bg-blue-50 text-blue-600',
  weekly: 'bg-indigo-50 text-indigo-600',
  monthly: 'bg-teal-50 text-teal-600',
  yearly: 'bg-rose-50 text-rose-600',
  interval: 'bg-emerald-50 text-emerald-600',
};

const WEEKDAY_NAMES = ['월', '화', '수', '목', '금', '토', '일'];

const ACTION_LABELS: Record<string, string> = {
  test: '테스트',
  run_switch: '스위치 실행',
  send_notification: '알림',
};

function getRepeatDetail(task: SchedulerTask): string {
  const repeat = task.repeat || 'none';
  switch (repeat) {
    case 'weekly':
      if (task.weekdays && task.weekdays.length > 0) {
        return task.weekdays.map(d => WEEKDAY_NAMES[d]).join(', ');
      }
      return '';
    case 'none':
      return task.date || '';
    case 'yearly':
      if (task.month && task.day) {
        return `${task.month}월 ${task.day}일`;
      }
      if (task.date) {
        const parts = task.date.split('-');
        if (parts.length === 3) return `${parseInt(parts[1])}월 ${parseInt(parts[2])}일`;
      }
      return '';
    case 'monthly':
      if (task.date) {
        const parts = task.date.split('-');
        if (parts.length === 3) return `${parseInt(parts[2])}일`;
      }
      return '';
    case 'interval':
      if (task.interval_hours) {
        return `${task.interval_hours}시간마다`;
      }
      return '';
    default:
      return '';
  }
}

function getActionIcon(action: string | undefined) {
  if (!action) return null;
  switch (action) {
    case 'run_switch': return <Zap size={14} />;
    case 'send_notification': return <Bell size={14} />;
    default: return null;
  }
}

function getDisplayTitle(task: SchedulerTask): string {
  return task.title || task.name || '';
}

interface SchedulerDialogProps {
  show: boolean;
  tasks: SchedulerTask[];
  formatLastRun: (lastRun: string | null | undefined) => string;
  onClose: () => void;
  onOpenCalendar?: () => void;
}

export function SchedulerDialog({
  show,
  tasks,
  formatLastRun,
  onClose,
  onOpenCalendar,
}: SchedulerDialogProps) {
  if (!show) return null;

  // 이벤트를 두 그룹으로 분리: 실행 가능(action 있음) / 순수 캘린더
  const scheduleTasks = tasks.filter(t => t.action);
  const calendarEvents = tasks.filter(t => !t.action);

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(800px, 90vw)',
          height: 'min(650px, 85vh)',
          minWidth: '500px',
          minHeight: '400px',
          resize: 'both',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-gray-800">이벤트 & 스케줄</h2>
            <span className="text-sm text-gray-400">{tasks.length}개</span>
            {onOpenCalendar && (
              <button
                onClick={onOpenCalendar}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-gray-200 hover:bg-blue-50 hover:border-blue-300 transition-colors text-gray-600 hover:text-blue-600"
                title="월간 캘린더 보기"
              >
                <CalendarDays size={15} />
                <span className="text-xs font-medium">캘린더</span>
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 이벤트 목록 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {tasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <Clock size={48} className="mb-4 text-gray-400" />
              <p className="mb-2">등록된 이벤트가 없습니다.</p>
              <div className="flex items-center gap-2 text-sm text-gray-400 mt-2">
                <MessageSquare size={16} />
                <span>시스템 AI에게 기념일이나 스케줄 등록을 요청하세요</span>
              </div>
            </div>
          ) : (
            <>
              {/* 실행 가능한 스케줄 */}
              {scheduleTasks.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2 px-1">
                    실행 스케줄 ({scheduleTasks.length})
                  </div>
                  <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
                    {scheduleTasks.map((task) => {
                      const repeat = task.repeat || 'none';
                      const repeatDetail = getRepeatDetail(task);
                      const eventType = task.type || 'schedule';
                      const actionLabel = task.action ? (ACTION_LABELS[task.action] || task.action) : '';

                      return (
                        <div key={task.id} className={`flex items-center gap-3 px-5 py-4 ${task.enabled === false ? 'opacity-50' : ''}`}>
                          {/* 활성화 상태 표시 */}
                          <span className={`shrink-0 ${task.enabled !== false ? 'text-green-500' : 'text-gray-300'}`}>
                            {task.enabled !== false ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                          </span>

                          {/* 시간 */}
                          <span className="font-bold text-lg text-gray-800 w-14 shrink-0">{task.time || '--:--'}</span>

                          {/* 타입 배지 */}
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${TYPE_COLORS[eventType] || 'bg-gray-100 text-gray-600'}`}>
                            {TYPE_EMOJI[eventType] || ''} {TYPE_LABELS[eventType] || eventType}
                          </span>

                          {/* 반복 배지 */}
                          <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${REPEAT_COLORS[repeat] || 'bg-gray-100 text-gray-500'}`}>
                            {REPEAT_LABELS[repeat] || repeat}
                          </span>

                          {/* 이름 + 상세 정보 */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-700 truncate">{getDisplayTitle(task)}</span>
                              {/* 액션 배지 */}
                              {task.action && (
                                <span className="inline-flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded shrink-0">
                                  {getActionIcon(task.action)}
                                  {actionLabel}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              {repeatDetail && (
                                <span className="text-xs text-gray-400">{repeatDetail}</span>
                              )}
                              {task.description && (
                                <span className="text-xs text-gray-400 truncate">{task.description}</span>
                              )}
                            </div>
                          </div>

                          {/* 마지막 실행 */}
                          <span className="text-xs text-gray-400 w-24 text-right shrink-0">
                            {formatLastRun(task.last_run)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 캘린더 이벤트 */}
              {calendarEvents.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2 px-1">
                    캘린더 이벤트 ({calendarEvents.length})
                  </div>
                  <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
                    {calendarEvents.map((evt) => {
                      const repeat = evt.repeat || 'none';
                      const repeatDetail = getRepeatDetail(evt);
                      const eventType = evt.type || 'other';

                      return (
                        <div key={evt.id} className="flex items-center gap-3 px-5 py-3.5">
                          {/* 이모지 */}
                          <span className="text-lg shrink-0">{TYPE_EMOJI[eventType] || ''}</span>

                          {/* 날짜/시간 */}
                          <div className="w-24 shrink-0">
                            {evt.date && (
                              <span className="text-sm font-medium text-gray-700">{evt.date}</span>
                            )}
                            {evt.time && (
                              <span className="text-xs text-gray-400 ml-1">{evt.time}</span>
                            )}
                          </div>

                          {/* 타입 배지 */}
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${TYPE_COLORS[eventType] || 'bg-gray-100 text-gray-600'}`}>
                            {TYPE_LABELS[eventType] || eventType}
                          </span>

                          {/* 반복 */}
                          {repeat !== 'none' && (
                            <span className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${REPEAT_COLORS[repeat] || 'bg-gray-100 text-gray-500'}`}>
                              {REPEAT_LABELS[repeat] || repeat}
                            </span>
                          )}

                          {/* 이름 + 설명 */}
                          <div className="flex-1 min-w-0">
                            <span className="font-medium text-gray-700 truncate block">{getDisplayTitle(evt)}</span>
                            <div className="flex items-center gap-2 mt-0.5">
                              {repeatDetail && repeat !== 'none' && (
                                <span className="text-xs text-gray-400">{repeatDetail}</span>
                              )}
                              {evt.description && (
                                <span className="text-xs text-gray-400 truncate">{evt.description}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* 푸터 */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <MessageSquare size={16} />
            <span>이벤트의 추가/편집/삭제는 시스템 AI와 대화하세요</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-200 transition-colors text-gray-600"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
