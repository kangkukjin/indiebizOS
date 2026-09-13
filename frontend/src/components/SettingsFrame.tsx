import type { ReactNode } from 'react';
import { X } from 'lucide-react';

/** 시스템/프로젝트 설정의 공통 창. 항목과 저장 동작은 각 설정의 소유자가 제공한다. */
export function SettingsFrame({ children, onClose, icon, title = '설정', width = 750, height = 650,
  minWidth = 400, minHeight = 450, resizable = false }: {
  children: ReactNode;
  onClose: () => void;
  icon?: ReactNode;
  /** 창 제목 — 기본 '설정'. 프롬프트 구성 등 다른 관리창이 같은 틀을 쓴다. */
  title?: string;
  width?: number;
  height?: number;
  minWidth?: number;
  minHeight?: number;
  resizable?: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div role="dialog" aria-modal="true" aria-label={title}
        className="bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{ width: `min(${width}px, 95vw)`, height: `min(${height}px, 88dvh)`,
          minWidth: `min(${minWidth}px, 95vw)`, minHeight: `min(${minHeight}px, 88dvh)`,
          maxWidth: '95vw', maxHeight: '90dvh', resize: resizable ? 'both' : undefined }}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="flex items-center gap-3">
            {icon}
            <h2 className="text-xl font-bold text-gray-800">{title}</h2>
          </div>
          <button onClick={onClose} aria-label={`${title} 닫기`} className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors">
            <X size={20} className="text-gray-500" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
