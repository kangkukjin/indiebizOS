import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface CodexModel {
  slug: string;
  display_name: string;
  reasoning_efforts: string[];
}

/** 모델 이름을 복제하지 않고 설치된 Codex의 공개 카탈로그를 사용한다. */
export function CodexModelPicker({ provider, value, onChange }: {
  provider: string;
  value: string;
  onChange: (model: string) => void;
}) {
  const [models, setModels] = useState<CodexModel[]>([]);
  useEffect(() => {
    if (provider !== 'codex') return;
    let active = true;
    api.request<{ items: CodexModel[] }>('/codex/models')
      .then(({ items }) => { if (active) setModels(items); })
      .catch(() => { if (active) setModels([]); });
    return () => { active = false; };
  }, [provider]);

  if (provider !== 'codex') return null;
  if (!models.length) return (
    <p className="text-xs text-gray-500 mt-2">Codex 모델 목록이 없습니다. 위 입력란에 모델명을 직접 입력할 수 있습니다.</p>
  );
  const [slug, effort = ''] = value.split(':');
  const selected = models.find((model) => [model.slug, model.display_name]
    .some((name) => name.toLowerCase() === slug.trim().toLowerCase()));
  const fieldClass = 'min-w-0 flex-1 px-2 py-2 bg-white border border-gray-300 rounded-lg text-sm text-gray-900';
  return (
    <div className="flex gap-2 mt-2">
      <select aria-label="Codex 모델 선택" value={selected?.slug || ''}
        className={fieldClass} onChange={(event) => {
          const next = models.find((model) => model.slug === event.target.value);
          if (next) onChange(next.slug + (next.reasoning_efforts.includes(effort) ? `:${effort}` : ''));
        }}>
        <option value="" disabled>{value ? '직접 입력한 모델' : 'Codex 모델 선택'}</option>
        {models.map((model) => <option key={model.slug} value={model.slug}>{model.display_name}</option>)}
      </select>
      {selected && <select aria-label="Codex 추론 강도" value={effort}
        className={fieldClass} onChange={(event) => onChange(selected.slug + (event.target.value ? `:${event.target.value}` : ''))}>
        <option value="">추론 강도: Codex 설정 따름</option>
        {effort && !selected.reasoning_efforts.includes(effort) && <option value={effort} disabled>{effort} (지원 목록에 없음)</option>}
        {selected.reasoning_efforts.map((level) => <option key={level} value={level}>{level}</option>)}
      </select>}
    </div>
  );
}
