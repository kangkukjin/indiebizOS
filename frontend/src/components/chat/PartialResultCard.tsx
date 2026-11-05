import { useLayoutEffect } from 'react';
import type { ToolActivity } from './types';

export function PartialResultCard({ result }: { result: NonNullable<ToolActivity['partialResult']> }) {
  useLayoutEffect(() => {
    const key = `indiebiz:partial:${result.run_id}:${result.id}:${result.version}:${result.state}`;
    if (!performance.getEntriesByName(key).length) {
      performance.mark(key);
      const start = `indiebiz:request:${result.run_id}`;
      if (performance.getEntriesByName(start).length)
        performance.measure(`${key}:elapsed`, start, key);
    }
  }, [result.id, result.run_id, result.version, result.state]);
  const withdrawn = result.state === 'withdrawn';
  return <section className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 text-sm" data-testid="partial-result">
    <div className="font-medium text-amber-900">{withdrawn ? '부분 결과 재확인 필요' : '확인된 부분 결과 · 읽은 원문'}</div>
    <div className="mt-1 text-xs text-gray-600">
      <a href={result.source} target="_blank" rel="noreferrer" className="underline">{result.title}</a>
      {' · '}{result.locator} · 판본 {result.version.slice(0, 12)} / 추출 {result.extraction_revision}
    </div>
    {withdrawn ? <p className="mt-2">자료의 판본이나 사용 상태가 바뀌어 이전 표시를 철회했습니다.</p>
      : <blockquote className="mt-2 whitespace-pre-wrap break-words">{result.content}{result.truncated ? '…' : ''}</blockquote>}
    <p className="mt-2 text-xs text-gray-500">출처의 주장을 읽은 구간입니다. 전체 답변의 최종 승인과는 별개입니다.</p>
  </section>;
}
