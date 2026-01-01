/**
 * SchedulerDialog - 예약작업 다이얼로그
 */

import { X, Clock, Plus, Play, Edit2, Trash, ToggleLeft, ToggleRight } from 'lucide-react';
import type { SchedulerTask } from '../types';

interface SchedulerDialogProps {
  show: boolean;
  tasks: SchedulerTask[];
  onAddTask: () => void;
  onEditTask: (task: SchedulerTask) => void;
  onDeleteTask: (taskId: string) => void;
  onToggleTask: (taskId: string) => void;
  onRunTask: (taskId: string) => void;
  formatLastRun: (lastRun: string | null) => string;
  onClose: () => void;
}

export function SchedulerDialog({
  show,
  tasks,
  onAddTask,
  onEditTask,
  onDeleteTask,
  onToggleTask,
  onRunTask,
  formatLastRun,
  onClose,
}: SchedulerDialogProps) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          width: 'min(800px, 90vw)',
          height: 'min(600px, 80vh)',
          minWidth: '500px',
          minHeight: '400px',
          resize: 'both',
        }}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-gray-800">프로그램 스케줄러</h2>
            <span className="text-sm text-gray-500">(에이전트 없이 백그라운드에서 실행)</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors"
          >
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* 작업 목록 */}
        <div className="flex-1 overflow-y-auto p-4">
          {tasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <Clock size={48} className="mb-4 text-gray-400" />
              <p>예약된 작업이 없습니다.</p>
            </div>
          ) : (
            <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
              {tasks.map((task) => (
                <div key={task.id} className="flex items-center gap-4 px-5 py-4 hover:bg-gray-50">
                  {/* 활성화 토글 */}
                  <button
                    onClick={() => onToggleTask(task.id)}
                    className={`transition-colors shrink-0 ${task.enabled ? 'text-green-500' : 'text-gray-300'}`}
                    title={task.enabled ? '활성화됨' : '비활성화됨'}
                  >
                    {task.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                  </button>

                  {/* 시간 */}
                  <span className="font-bold text-lg text-gray-800 w-16 shrink-0">{task.time}</span>

                  {/* 이름 */}
                  <span className="font-medium text-gray-700 w-36 truncate shrink-0">{task.name}</span>

                  {/* 설명 */}
                  <span className="flex-1 text-gray-500 text-sm truncate">{task.description}</span>

                  {/* 마지막 실행 */}
                  <span className="text-xs text-gray-400 w-28 text-right shrink-0">
                    최근: {formatLastRun(task.last_run)}
                  </span>

                  {/* 버튼들 */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => onRunTask(task.id)}
                      className="p-2 rounded hover:bg-blue-100 text-blue-500"
                      title="즉시 실행"
                    >
                      <Play size={18} />
                    </button>
                    <button
                      onClick={() => onEditTask(task)}
                      className="p-2 rounded hover:bg-gray-200 text-gray-500"
                      title="편집"
                    >
                      <Edit2 size={18} />
                    </button>
                    <button
                      onClick={() => onDeleteTask(task.id)}
                      className="p-2 rounded hover:bg-red-100 text-red-500"
                      title="삭제"
                    >
                      <Trash size={18} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 푸터 */}
        <div className="flex justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 shrink-0">
          <button
            onClick={onAddTask}
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors flex items-center gap-2"
          >
            <Plus size={18} />
            작업 추가
          </button>
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
