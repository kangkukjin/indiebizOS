/** 일반 프로젝트·시스템 AI·연구 대화가 공유하는 메시지 표시와 동작. */
import { memo, useState, type ReactNode } from 'react';
import { Bot, User, Zap, Brain, Gauge, Target, Copy, Check } from 'lucide-react';
import type { ChatMessage } from './types';
import { MessageContent } from './MessageContent';

// ── 작업전 공개 칩 (자율주행 신뢰 보정 계기) ──

function CognitionChip({ info }: { info: NonNullable<ChatMessage['cognition']> }) {
  // 판단별 색·라벨·아이콘 — 표시 분량 자체가 "얼마나 숙고했나" 신호가 된다.
  const meta = {
    reflex:  { label: '반사', Icon: Zap,   color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-200' },
    execute: { label: '실행', Icon: Gauge, color: 'text-amber-700',   bg: 'bg-amber-50 border-amber-200' },
    think:   { label: '숙고', Icon: Brain, color: 'text-sky-700',     bg: 'bg-sky-50 border-sky-200' },
  }[info.decision] || { label: '판단', Icon: Gauge, color: 'text-stone-700', bg: 'bg-stone-50 border-stone-200' };
  const { Icon } = meta;
  const pct = Math.round((info.score || 0) * 100);

  return (
    <div className="flex justify-start">
      <div className={`max-w-[80%] min-w-0 break-words rounded-xl border px-3 py-2 text-[12px] ${meta.bg}`}>
        <div className={`flex items-center gap-1.5 font-medium ${meta.color}`}>
          <Icon size={13} />
          <span>{meta.label}</span>
          <span className="text-stone-400">·</span>
          <span title="해마 연상 확신도">확신 {pct}%</span>
          {info.action && (
            <code className="ml-1 px-1.5 py-0.5 rounded bg-white/70 text-stone-600 font-mono text-[11px]">
              {info.action}
            </code>
          )}
        </div>
        {info.criteria && (
          <div className="mt-1.5 flex items-start gap-1.5 text-stone-600">
            <Target size={12} className="mt-0.5 flex-shrink-0 text-stone-400" />
            <span>달성 기준: {info.criteria}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 메시지 버블 ──

/**
 * 메시지 복사 버튼 — 버블 호버 시 나타나 그 메시지 하나의 텍스트를 클립보드로 복사.
 * Electron 샌드박스 렌더러에서 preload clipboard 동기 브리지는 throw 하므로
 * navigator.clipboard(기본 권한으로 동작)를 사용한다.
 */
function MessageCopyButton({ text, tone }: { text: string; tone: 'onLight' | 'onDark' | 'onWarm' }) {
  const [copied, setCopied] = useState(false);
  const color = tone === 'onDark'
    ? 'text-white/70 hover:text-white hover:bg-white/15'
    : tone === 'onWarm'
    ? 'text-[#A09080] hover:text-[#6B5B4F] hover:bg-black/5'
    : 'text-gray-400 hover:text-gray-600 hover:bg-black/5';
  return (
    <button
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch { /* clipboard 거부 시 무시 */ }
      }}
      type="button"
      aria-label={copied ? '복사됨' : '이 메시지 복사'}
      title="이 메시지 복사"
      className={`opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity inline-flex items-center justify-center p-1 rounded ${color}`}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
}

// memo: 입력창 타이핑마다 ChatView 전체가 리렌더되어도 과거 메시지의 마크다운 재파싱을 막는다
export const MessageBubble = memo(function MessageBubble({ message, variant = 'warm', children }: {
  message: ChatMessage;
  variant?: 'warm' | 'neutral';
  /** 자료실 첨부 링크·상태처럼 대화 종류에만 필요한 부가 내용. 기본 메시지 UI는 공유한다. */
  children?: ReactNode;
}) {
  const isUser = message.role === 'user';

  // 작업전 공개 — 일반 버블 대신 계기 칩으로 렌더
  if (message.cognition) {
    return <CognitionChip info={message.cognition} />;
  }

  if (variant === 'neutral') {
    return (
      <div className={`group flex ${isUser ? 'justify-end' : 'justify-start'}`}>
        <div className={`chat-bubble chat-bubble-neutral max-w-[80%] min-w-0 break-words rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-amber-500 text-white rounded-br-md'
            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm'
        }`}>
          <MessageContent
            content={message.content}
            role={message.role}
            images={message.images}
            textFiles={message.textFiles}
            toolActivities={message.toolActivities}
            variant="neutral"
          />
          {children}
          <div className={`flex ${isUser ? 'justify-start' : 'justify-end'} -mb-0.5 mt-0.5`}>
            <MessageCopyButton text={message.content} tone={isUser ? 'onDark' : 'onLight'} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`group flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-white ${
        isUser
          ? 'bg-gradient-to-br from-[#3B82F6] to-[#1D4ED8]'
          : 'bg-gradient-to-br from-[#D97706] to-[#B45309]'
      }`}>
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className={`chat-bubble max-w-[70%] min-w-0 break-words px-4 py-3 rounded-2xl ${
        isUser
          ? 'bg-[#3B82F6] text-white rounded-tr-sm'
          : 'bg-[#E5DFD5] text-[#4A4035] rounded-tl-sm'
      }`}>
        <MessageContent
          content={message.content}
          role={message.role}
          images={message.images}
          textFiles={message.textFiles}
          toolActivities={message.toolActivities}
          variant="warm"
        />
        {children}
        <div className={`flex items-center gap-1 text-xs mt-1 ${isUser ? 'flex-row-reverse text-blue-200' : 'text-[#A09080]'}`}>
          <span>{message.timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}</span>
          <MessageCopyButton text={message.content} tone={isUser ? 'onDark' : 'onWarm'} />
        </div>
      </div>
    </div>
  );
});
