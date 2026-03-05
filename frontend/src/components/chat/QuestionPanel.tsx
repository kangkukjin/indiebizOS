/**
 * AI 질문 패널 (단일/다중 선택)
 */
import { useState } from 'react';
import { HelpCircle, Check } from 'lucide-react';
import type { QuestionItem } from './types';

interface QuestionPanelProps {
  questions: QuestionItem[];
  onSubmit: (answers: Record<number, string | string[]>) => void;
}

export function QuestionPanel({ questions, onSubmit }: QuestionPanelProps) {
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, string | string[]>>({});

  if (questions.length === 0) return null;

  const handleSubmit = () => {
    onSubmit(selectedAnswers);
    setSelectedAnswers({});
  };

  return (
    <div className="px-4 py-3 bg-blue-50 border-b border-blue-200 shrink-0">
      <div className="flex items-center gap-2 text-blue-700 mb-3">
        <HelpCircle size={16} />
        <span className="text-sm font-medium">AI가 질문합니다</span>
      </div>
      <div className="space-y-4">
        {questions.map((q, qIdx) => (
          <div key={qIdx} className="bg-white rounded-lg p-3 border border-blue-100">
            <div className="flex items-center gap-2 mb-2">
              <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-[10px] font-medium rounded">
                {q.header}
              </span>
            </div>
            <p className="text-sm text-gray-700 mb-3">{q.question}</p>
            <div className="space-y-2">
              {q.options.map((opt, optIdx) => (
                <label
                  key={optIdx}
                  className={`flex items-start gap-3 p-2 rounded-lg cursor-pointer transition-colors ${
                    (q.multiSelect
                      ? (selectedAnswers[qIdx] as string[] || []).includes(opt.label)
                      : selectedAnswers[qIdx] === opt.label)
                      ? 'bg-blue-100 border border-blue-300'
                      : 'bg-gray-50 border border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  <input
                    type={q.multiSelect ? 'checkbox' : 'radio'}
                    name={`question-${qIdx}`}
                    checked={
                      q.multiSelect
                        ? (selectedAnswers[qIdx] as string[] || []).includes(opt.label)
                        : selectedAnswers[qIdx] === opt.label
                    }
                    onChange={() => {
                      if (q.multiSelect) {
                        const current = (selectedAnswers[qIdx] as string[]) || [];
                        const updated = current.includes(opt.label)
                          ? current.filter(l => l !== opt.label)
                          : [...current, opt.label];
                        setSelectedAnswers(prev => ({ ...prev, [qIdx]: updated }));
                      } else {
                        setSelectedAnswers(prev => ({ ...prev, [qIdx]: opt.label }));
                      }
                    }}
                    className="mt-1"
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-gray-800">{opt.label}</div>
                    {opt.description && (
                      <div className="text-xs text-gray-500 mt-0.5">{opt.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex justify-end gap-2 mt-3">
        <button
          onClick={handleSubmit}
          disabled={Object.keys(selectedAnswers).length === 0}
          className="px-4 py-2 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          <Check size={14} />
          응답 제출
        </button>
      </div>
    </div>
  );
}
