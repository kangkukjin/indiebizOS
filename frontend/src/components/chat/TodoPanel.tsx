/**
 * TODO 리스트 패널
 */
import { useState } from 'react';
import { ListTodo, CheckCircle2, Circle, Loader2, X, CircleDot } from 'lucide-react';
import type { TodoItem } from './types';

interface TodoPanelProps {
  todos: TodoItem[];
  variant?: 'warm' | 'neutral' | 'inline';
  collapsible?: boolean;
}

export function TodoPanel({ todos, variant = 'warm', collapsible = false }: TodoPanelProps) {
  const [showTodos, setShowTodos] = useState(true);

  if (todos.length === 0) return null;

  const completedCount = todos.filter(t => t.status === 'completed').length;

  // 축소 상태 버튼
  if (collapsible && !showTodos) {
    return (
      <button
        onClick={() => setShowTodos(true)}
        className="px-2 py-1 bg-amber-100 text-amber-600 rounded-full text-xs flex items-center gap-1 hover:bg-amber-200 transition-colors"
      >
        <ListTodo size={12} />
        {completedCount}/{todos.length}
      </button>
    );
  }

  // inline 스타일 (스트리밍 중 표시)
  if (variant === 'inline') {
    return (
      <div className="mb-3 border border-[#E5DFD5] rounded-lg overflow-hidden bg-white">
        <div className="px-3 py-2 bg-gradient-to-r from-[#F5F1EB] to-[#EAE4DA] border-b border-[#E5DFD5]">
          <span className="text-xs font-semibold text-[#4A4035]">📋 작업 목록</span>
        </div>
        <div className="p-2 space-y-1">
          {todos.map((todo, idx) => (
            <div key={idx} className="flex items-center gap-2 px-2 py-1 text-xs">
              {todo.status === 'completed' ? (
                <CheckCircle2 size={14} className="text-green-500 shrink-0" />
              ) : todo.status === 'in_progress' ? (
                <CircleDot size={14} className="text-[#D97706] shrink-0 animate-pulse" />
              ) : (
                <Circle size={14} className="text-[#A09080] shrink-0" />
              )}
              <span className={`${
                todo.status === 'completed' ? 'text-[#A09080] line-through' :
                todo.status === 'in_progress' ? 'text-[#4A4035] font-medium' :
                'text-[#4A4035]'
              }`}>
                {todo.status === 'in_progress' ? todo.activeForm : todo.content}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // neutral 스타일 (시스템 AI 다이얼로그)
  if (variant === 'neutral') {
    return (
      <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-amber-700">
            <ListTodo size={14} />
            <span className="text-xs font-medium">작업 진행 상황</span>
            <span className="text-[10px] text-amber-500">
              ({completedCount}/{todos.length})
            </span>
          </div>
          {collapsible && (
            <button onClick={() => setShowTodos(false)} className="text-amber-400 hover:text-amber-600">
              <X size={12} />
            </button>
          )}
        </div>
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {todos.map((todo, idx) => (
            <div
              key={idx}
              className={`flex items-center gap-2 text-xs py-0.5 ${
                todo.status === 'completed' ? 'text-gray-400 line-through' :
                todo.status === 'in_progress' ? 'text-amber-700 font-medium' :
                'text-gray-600'
              }`}
            >
              {todo.status === 'completed' ? (
                <CheckCircle2 size={12} className="text-green-500 flex-shrink-0" />
              ) : todo.status === 'in_progress' ? (
                <Loader2 size={12} className="text-amber-500 animate-spin flex-shrink-0" />
              ) : (
                <Circle size={12} className="text-gray-300 flex-shrink-0" />
              )}
              <span className="truncate">
                {todo.status === 'in_progress' ? todo.activeForm : todo.content}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // warm 스타일 (기본, inline과 동일)
  return (
    <div className="mb-3 border border-[#E5DFD5] rounded-lg overflow-hidden bg-white">
      <div className="px-3 py-2 bg-gradient-to-r from-[#F5F1EB] to-[#EAE4DA] border-b border-[#E5DFD5]">
        <span className="text-xs font-semibold text-[#4A4035]">📋 작업 목록</span>
      </div>
      <div className="p-2 space-y-1">
        {todos.map((todo, idx) => (
          <div key={idx} className="flex items-center gap-2 px-2 py-1 text-xs">
            {todo.status === 'completed' ? (
              <CheckCircle2 size={14} className="text-green-500 shrink-0" />
            ) : todo.status === 'in_progress' ? (
              <CircleDot size={14} className="text-[#D97706] shrink-0 animate-pulse" />
            ) : (
              <Circle size={14} className="text-[#A09080] shrink-0" />
            )}
            <span className={`${
              todo.status === 'completed' ? 'text-[#A09080] line-through' :
              todo.status === 'in_progress' ? 'text-[#4A4035] font-medium' :
              'text-[#4A4035]'
            }`}>
              {todo.status === 'in_progress' ? todo.activeForm : todo.content}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
