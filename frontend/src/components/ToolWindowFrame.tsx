import type { ReactNode } from 'react';
import { ArrowLeft } from 'lucide-react';

/**
 * 안경 메뉴 도구 창(프롬프트 구성·가이드 파일)의 공통 틀 — 화면 전체를 쓰는 독립 창.
 * Electron 은 OS 제목줄이 있는 별도 BrowserWindow 라 닫기 버튼이 없고, 웹 표면(같은 창의
 * 해시 라우트)에서만 '‹ 뒤로' 를 둔다.
 */
export function ToolWindowFrame({ title, icon, actions, children }: {
  title: string;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const isWeb = !window.electron;
  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#FAF8F4]">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[#E5DFD5] bg-gradient-to-b from-[#F7F3ED] to-[#F5F1EB] shrink-0">
        {isWeb && (
          <button onClick={() => window.history.back()} aria-label="뒤로"
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-sm text-[#6B5B4F] hover:bg-[#EAE4DA]">
            <ArrowLeft size={16} /> 뒤로
          </button>
        )}
        {icon}
        <h1 className="text-lg font-bold text-[#4A4035]">{title}</h1>
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      </div>
      {children}
    </div>
  );
}
