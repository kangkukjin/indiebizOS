/**
 * 채팅 입력 영역 (파일 첨부, 카메라, 드래그앤드롭)
 */
import { Send, StopCircle, Paperclip, Camera, FileText, File as FileIcon, X, Square } from 'lucide-react';
import type { ImageAttachment, TextAttachment, DocumentAttachment } from './types';

interface ChatInputAreaProps {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  isLoading: boolean;
  hasContent: boolean;  // input.trim() || hasAttachments
  // 파일 첨부 관련
  attachedImages: ImageAttachment[];
  attachedTextFiles: TextAttachment[];
  attachedDocuments: DocumentAttachment[];
  isDragging: boolean;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onPaste: (e: React.ClipboardEvent) => void;
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onRemoveImage: (index: number) => void;
  onRemoveTextFile: (index: number) => void;
  onRemoveDocument: (index: number) => void;
  onCameraClick: () => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  placeholder?: string;
  variant?: 'warm' | 'neutral';
  showHelpText?: boolean;
}

export function ChatInputArea({
  input,
  onInputChange,
  onSend,
  onCancel,
  onKeyDown,
  isLoading,
  hasContent,
  attachedImages,
  attachedTextFiles,
  attachedDocuments,
  isDragging,
  onDragOver,
  onDragLeave,
  onDrop,
  onPaste,
  onFileSelect,
  onRemoveImage,
  onRemoveTextFile,
  onRemoveDocument,
  onCameraClick,
  fileInputRef,
  inputRef,
  placeholder = '메시지를 입력하세요... (파일 드래그/붙여넣기 가능)',
  variant = 'warm',
  showHelpText = false,
}: ChatInputAreaProps) {
  const styles = variant === 'warm' ? {
    containerBg: 'bg-[#EAE4DA]',
    containerBorder: 'border-[#E5DFD5]',
    ring: 'ring-[#D97706]',
    imgBorder: 'border-[#E5DFD5]',
    imgSize: 'w-20 h-20',
    fileBg: 'bg-white',
    fileBorder: 'border-[#E5DFD5]',
    fileIcon: 'text-[#D97706]',
    fileNameColor: 'text-[#4A4035]',
    filePreviewColor: 'text-[#A09080]',
    dragBorder: 'border-[#D97706]',
    dragBg: 'bg-[#FEF3C7]',
    dragText: 'text-[#D97706]',
    btnBg: 'bg-white',
    btnBorder: 'border-[#E5DFD5]',
    btnHoverBorder: 'hover:border-[#D97706]',
    btnText: 'text-[#A09080]',
    btnHoverText: 'hover:text-[#D97706]',
    inputBg: 'bg-white',
    inputBorder: 'border-[#E5DFD5]',
    inputFocus: 'focus:border-[#D97706]',
    inputText: 'text-[#4A4035]',
    inputPlaceholder: 'placeholder:text-[#A09080]',
    sendBg: 'bg-[#D97706]',
    sendHover: 'hover:bg-[#B45309]',
    cancelIcon: StopCircle,
    iconSize: 20,
    gap: 'gap-3',
    btnPadding: 'p-3',
    sendPadding: 'p-3',
  } : {
    containerBg: 'bg-white',
    containerBorder: 'border-gray-200',
    ring: 'ring-amber-400',
    imgBorder: 'border-gray-200',
    imgSize: 'w-16 h-16',
    fileBg: 'bg-gray-100',
    fileBorder: 'border-gray-200',
    fileIcon: 'text-amber-500',
    fileNameColor: 'text-gray-700',
    filePreviewColor: 'text-gray-500',
    dragBorder: 'border-amber-400',
    dragBg: 'bg-amber-50',
    dragText: 'text-amber-600',
    btnBg: 'bg-gray-100',
    btnBorder: 'border-gray-200',
    btnHoverBorder: 'hover:border-amber-400',
    btnText: 'text-gray-500',
    btnHoverText: 'hover:text-amber-500',
    inputBg: 'bg-gray-100',
    inputBorder: 'border-gray-200',
    inputFocus: 'focus:border-amber-400',
    inputText: 'text-gray-800',
    inputPlaceholder: 'placeholder:text-gray-400',
    sendBg: 'bg-amber-500',
    sendHover: 'hover:bg-amber-600',
    cancelIcon: Square,
    iconSize: 18,
    gap: 'gap-2',
    btnPadding: 'p-2.5',
    sendPadding: 'px-4 py-2.5',
  };

  const CancelIcon = styles.cancelIcon;

  return (
    <div
      className={`p-4 border-t ${styles.containerBorder} ${styles.containerBg} ${variant === 'neutral' ? 'shrink-0' : ''} ${isDragging ? `ring-2 ${styles.ring} ring-inset` : ''}`}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {/* 첨부된 이미지 미리보기 */}
      {attachedImages.length > 0 && (
        <div className="flex gap-2 mb-3 flex-wrap">
          {attachedImages.map((img, index) => (
            <div key={index} className="relative group">
              <img
                src={img.preview}
                alt={`첨부 이미지 ${index + 1}`}
                className={`${styles.imgSize} object-cover rounded-lg border ${styles.imgBorder}`}
              />
              <button
                onClick={() => onRemoveImage(index)}
                className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 첨부된 텍스트 파일 미리보기 */}
      {attachedTextFiles.length > 0 && (
        <div className="flex gap-2 mb-3 flex-wrap">
          {attachedTextFiles.map((tf, index) => (
            <div key={index} className={`relative group ${styles.fileBg} border ${styles.fileBorder} rounded-lg p-2 max-w-[200px]`}>
              <div className="flex items-center gap-2 mb-1">
                <FileText size={variant === 'warm' ? 16 : 14} className={`${styles.fileIcon} flex-shrink-0`} />
                <span className={`text-xs font-medium ${styles.fileNameColor} truncate`}>{tf.file.name}</span>
              </div>
              <div className={`text-[10px] ${styles.filePreviewColor} line-clamp-2 break-all`}>
                {tf.preview}
              </div>
              <button
                onClick={() => onRemoveTextFile(index)}
                className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 첨부된 문서 파일 미리보기 */}
      {attachedDocuments.length > 0 && (
        <div className="flex gap-2 mb-3 flex-wrap">
          {attachedDocuments.map((doc, index) => (
            <div key={index} className={`relative group ${styles.fileBg} border ${styles.fileBorder} rounded-lg p-2 max-w-[200px]`}>
              <div className="flex items-center gap-2">
                <FileIcon size={variant === 'warm' ? 16 : 14} className={`${styles.fileIcon} flex-shrink-0`} />
                <span className={`text-xs font-medium ${styles.fileNameColor} truncate`}>{doc.fileName}</span>
                <span className="text-[10px] bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded uppercase flex-shrink-0">{doc.fileType}</span>
              </div>
              <button
                onClick={() => onRemoveDocument(index)}
                className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 드래그 오버레이 */}
      {isDragging && (
        <div className={`mb-3 p-${variant === 'warm' ? '4' : '3'} border-2 border-dashed ${styles.dragBorder} rounded-xl ${styles.dragBg} text-center ${styles.dragText} ${variant === 'neutral' ? 'text-sm' : ''}`}>
          파일을 여기에 놓으세요 (이미지, 텍스트, 문서 파일)
        </div>
      )}

      <div className={`flex items-end ${styles.gap}`}>
        {/* 파일 선택 버튼 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.txt,.md,.json,.yaml,.yml,.xml,.csv,.log,.py,.js,.ts,.tsx,.jsx,.html,.css,.sql,.sh,.env,.ini,.conf,.toml,.pages,.docx,.pdf"
          multiple
          onChange={onFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          className={`${styles.btnPadding} ${styles.btnBg} rounded-xl border ${styles.btnBorder} ${styles.btnHoverBorder} disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${styles.btnText} ${styles.btnHoverText}`}
          title="파일 첨부 (이미지, 텍스트)"
        >
          <Paperclip size={styles.iconSize} />
        </button>

        {/* 카메라 버튼 */}
        <button
          onClick={onCameraClick}
          disabled={isLoading}
          className={`${styles.btnPadding} ${styles.btnBg} rounded-xl border ${styles.btnBorder} ${styles.btnHoverBorder} disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${styles.btnText} ${styles.btnHoverText}`}
          title="카메라로 촬영"
        >
          <Camera size={styles.iconSize} />
        </button>

        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder={placeholder}
          className={`flex-1 px-4 py-3 ${styles.inputBg} rounded-xl border ${styles.inputBorder} ${styles.inputFocus} focus:outline-none resize-none min-h-[48px] max-h-[200px] ${styles.inputText} ${styles.inputPlaceholder}`}
          rows={2}
          disabled={isLoading}
        />
        {isLoading ? (
          <button
            onClick={onCancel}
            className={`${styles.sendPadding} bg-red-500 rounded-xl hover:bg-red-600 transition-colors text-white`}
            title="작업 중단"
          >
            <CancelIcon size={styles.iconSize} />
          </button>
        ) : (
          <button
            onClick={onSend}
            disabled={!hasContent}
            className={`${styles.sendPadding} ${styles.sendBg} rounded-xl ${styles.sendHover} disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-white`}
          >
            <Send size={styles.iconSize} />
          </button>
        )}
      </div>
      {showHelpText && (
        <p className="text-xs text-gray-400 mt-2 text-center">Enter로 전송 · Shift+Enter로 줄바꿈 · 파일 드래그 또는 붙여넣기</p>
      )}
    </div>
  );
}
