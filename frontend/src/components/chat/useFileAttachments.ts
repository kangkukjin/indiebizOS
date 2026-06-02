/**
 * 파일 첨부 관련 공통 훅
 */
import { useState, useRef, useEffect } from 'react';
import type { ImageAttachment, TextAttachment, DocumentAttachment } from './types';
import { fileToBase64, isTextFile, readTextFile, isDocumentFile } from './chatUtils';

export function useFileAttachments() {
  const [attachedImages, setAttachedImages] = useState<ImageAttachment[]>([]);
  const [attachedTextFiles, setAttachedTextFiles] = useState<TextAttachment[]>([]);
  const [attachedDocuments, setAttachedDocuments] = useState<DocumentAttachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 컴포넌트 언마운트 시 ObjectURL 정리
  useEffect(() => {
    return () => {
      attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    };
  }, []);

  // 이미지 파일 처리
  const handleImageFile = async (file: File) => {
    if (!file.type.startsWith('image/')) return;
    const base64 = await fileToBase64(file);
    const preview = URL.createObjectURL(file);
    setAttachedImages(prev => [...prev, { file, preview, base64 }]);
  };

  // 텍스트 파일 처리
  const handleTextFile = async (file: File) => {
    if (!isTextFile(file)) return;
    const content = await readTextFile(file);
    const preview = content.length > 200 ? content.substring(0, 200) + '...' : content;
    setAttachedTextFiles(prev => [...prev, { file, content, preview }]);
  };

  // 문서 파일 처리 (.pages, .docx, .pdf)
  const handleDocumentFile = (file: File) => {
    const filePath = (file as any).path || '';
    const fileName = file.name;
    const ext = fileName.toLowerCase().split('.').pop() || '';
    setAttachedDocuments(prev => [...prev, { file, filePath, fileName, fileType: ext }]);
  };

  // 파일 타입에 따라 처리
  const handleFile = async (file: File) => {
    if (file.type.startsWith('image/')) {
      await handleImageFile(file);
    } else if (isDocumentFile(file)) {
      handleDocumentFile(file);
    } else if (isTextFile(file)) {
      await handleTextFile(file);
    }
  };

  // 이미지 제거
  const removeImage = (index: number) => {
    setAttachedImages(prev => {
      const newImages = [...prev];
      URL.revokeObjectURL(newImages[index].preview);
      newImages.splice(index, 1);
      return newImages;
    });
  };

  // 텍스트 파일 제거
  const removeTextFile = (index: number) => {
    setAttachedTextFiles(prev => {
      const newFiles = [...prev];
      newFiles.splice(index, 1);
      return newFiles;
    });
  };

  // 문서 파일 제거
  const removeDocument = (index: number) => {
    setAttachedDocuments(prev => {
      const newDocs = [...prev];
      newDocs.splice(index, 1);
      return newDocs;
    });
  };

  // 카메라 캡처 처리
  const handleCameraCapture = ({ base64, blob }: { base64: string; blob: Blob }) => {
    const file = new File([blob], `camera_${Date.now()}.jpg`, { type: 'image/jpeg' });
    const preview = URL.createObjectURL(blob);
    setAttachedImages(prev => [...prev, { file, preview, base64 }]);
    setIsCameraOpen(false);
  };

  // 드래그 앤 드롭 핸들러
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    for (const file of files) {
      await handleFile(file);
    }
  };

  // 붙여넣기 핸들러
  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) {
          await handleImageFile(file);
        }
      }
    }
  };

  // 파일 선택 핸들러
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    for (const file of files) {
      await handleFile(file);
    }
    e.target.value = '';
  };

  // 모든 첨부 파일 초기화
  const clearAttachments = () => {
    attachedImages.forEach(img => URL.revokeObjectURL(img.preview));
    setAttachedImages([]);
    setAttachedTextFiles([]);
    setAttachedDocuments([]);
  };

  // 메시지 콘텐츠 준비 (텍스트 파일 내용 추가)
  const prepareMessageContent = (inputText: string) => {
    let messageContent = inputText.trim();
    if (attachedTextFiles.length > 0) {
      const fileContents = attachedTextFiles.map(tf =>
        `\n\n--- 첨부파일: ${tf.file.name} ---\n${tf.content}`
      ).join('');
      messageContent = messageContent + fileContents;
    }
    return messageContent;
  };

  // 이미지 데이터 준비 (API 전송용)
  const prepareImageData = () => {
    return attachedImages.map(img => ({
      base64: img.base64,
      media_type: img.file.type
    }));
  };

  // 메시지에 저장할 이미지 URL
  const getMessageImages = () => {
    return attachedImages.map(img => `data:${img.file.type};base64,${img.base64}`);
  };

  // 메시지에 저장할 텍스트 파일 목록
  const getMessageTextFiles = () => {
    return attachedTextFiles.map(tf => ({ name: tf.file.name, content: tf.content }));
  };

  // 문서 데이터 준비 (WebSocket 전송용)
  const prepareDocumentData = () => {
    return attachedDocuments.map(doc => ({
      filePath: doc.filePath,
      fileName: doc.fileName,
      fileType: doc.fileType,
    }));
  };

  // 메시지에 저장할 문서 파일 목록
  const getMessageDocuments = () => {
    return attachedDocuments.map(doc => ({
      fileName: doc.fileName,
      filePath: doc.filePath,
      fileType: doc.fileType,
    }));
  };

  const hasAttachments = attachedImages.length > 0 || attachedTextFiles.length > 0 || attachedDocuments.length > 0;

  return {
    attachedImages,
    attachedTextFiles,
    attachedDocuments,
    isDragging,
    isCameraOpen,
    setIsCameraOpen,
    fileInputRef,
    hasAttachments,
    // 핸들러
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handlePaste,
    handleFileSelect,
    handleCameraCapture,
    removeImage,
    removeTextFile,
    removeDocument,
    clearAttachments,
    // 메시지 준비
    prepareMessageContent,
    prepareImageData,
    prepareDocumentData,
    getMessageImages,
    getMessageTextFiles,
    getMessageDocuments,
  };
}
