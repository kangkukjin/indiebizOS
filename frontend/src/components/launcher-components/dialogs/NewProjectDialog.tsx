/**
 * NewProjectDialog - 새 프로젝트 생성 다이얼로그
 */

import { useEffect, useState } from 'react';
import { api } from '../../../lib/api';

interface NewProjectDialogProps {
  show: boolean;
  name: string;
  onNameChange: (name: string) => void;
  onSubmit: (templateName: string) => void;
  onClose: () => void;
}

export function NewProjectDialog({
  show,
  name,
  onNameChange,
  onSubmit,
  onClose,
}: NewProjectDialogProps) {
  const [templates, setTemplates] = useState<string[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState('기본');
  const [isLoading, setIsLoading] = useState(false);

  // 다이얼로그 열릴 때 템플릿 목록 로드
  useEffect(() => {
    if (show) {
      setIsLoading(true);
      api.getTemplates()
        .then((list) => {
          setTemplates(list);
          // 템플릿 목록이 있으면 첫 번째 선택, 없으면 '기본'
          if (list.length > 0 && !list.includes(selectedTemplate)) {
            setSelectedTemplate(list[0]);
          }
        })
        .catch((err) => {
          console.error('템플릿 로드 실패:', err);
          setTemplates([]);
        })
        .finally(() => setIsLoading(false));
    }
  }, [show]);

  if (!show) return null;

  const handleSubmit = () => {
    onSubmit(selectedTemplate);
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-96 shadow-2xl">
        <h2 className="text-xl font-bold mb-4 text-gray-800">새 프로젝트</h2>

        {/* 프로젝트 이름 입력 */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-600 mb-1">
            프로젝트 이름
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="프로젝트 이름"
            className="w-full px-4 py-2 bg-gray-50 rounded-lg border border-gray-300 focus:border-green-500 focus:outline-none text-gray-800"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSubmit();
              if (e.key === 'Escape') onClose();
            }}
          />
        </div>

        {/* 템플릿 선택 */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-600 mb-1">
            템플릿
          </label>
          {isLoading ? (
            <div className="text-gray-500 text-sm">로딩 중...</div>
          ) : templates.length > 0 ? (
            <div className="space-y-2">
              {templates.map((template) => (
                <label
                  key={template}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedTemplate === template
                      ? 'border-green-500 bg-green-50'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="radio"
                    name="template"
                    value={template}
                    checked={selectedTemplate === template}
                    onChange={(e) => setSelectedTemplate(e.target.value)}
                    className="w-4 h-4 text-green-500"
                  />
                  <div>
                    <div className="font-medium text-gray-800">{template}</div>
                    {template === '프로젝트1' && (
                      <div className="text-xs text-gray-500">
                        집사, 직원1, 대장장이, 출판, 영상담당 에이전트 포함
                      </div>
                    )}
                    {template === '기본' && (
                      <div className="text-xs text-gray-500">
                        기본 집사 에이전트만 포함
                      </div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">
              사용 가능한 템플릿이 없습니다. 기본 설정으로 생성됩니다.
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-600"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
          >
            생성
          </button>
        </div>
      </div>
    </div>
  );
}
