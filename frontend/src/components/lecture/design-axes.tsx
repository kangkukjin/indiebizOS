/**
 * 강의 창의 선택 2축 — **톤**과 **렌더 방식** (2026-08-06 개편).
 *
 * 구조(layout/composition)는 UI 에 없다. AI가 내용을 보고 고른다 —
 * 구조까지 사람이 매번 고르는 건 도움이 안 됐고, 필요하면 자연어로 말하면 된다
 * ("좌우로 대비해서", "표로 정리해줘", "이 틀 말고 자유롭게").
 *
 * 선택지는 `GET /lectures/design-systems` 가 내려준다 — 진실 소스는 백엔드
 * 톤 레지스트리(media_producer/slide_tones.py). 여기 하드코딩하지 말 것.
 */
import { useCallback, useState } from 'react';
import { api } from '../../lib/api';
import { useRetryingLoad } from '../../lib/use-retrying-load';
import type { DesignMatrix, RenderMode, ToneOption } from '../../lib/api-lecture-workspace';

/** 선택지 매트릭스 조회. 콜드스타트(백엔드 미기동) 대비 재시도 로더 사용. */
export function useDesignMatrix() {
  const [matrix, setMatrix] = useState<DesignMatrix | null>(null);
  const load = useCallback(async () => {
    const m = await api.designMatrix();
    setMatrix(m);
    return m;
  }, []);
  const { retrying } = useRetryingLoad(load);
  return { matrix, loading: matrix === null, retrying };
}

/** 그 톤이 지원하는 렌더 방식 목록 (매트릭스 미도착이면 빈 배열). */
export function rendersOfTone(matrix: DesignMatrix | null, tone: string): RenderMode[] {
  return matrix?.tones.find((t) => t.key === tone)?.renders ?? [];
}

/**
 * 톤을 바꿨을 때 현재 렌더 방식을 쓸 수 있는지 확인하고, 못 쓰면 그 톤이 지원하는
 * 첫 방식으로 옮긴다. (예: 시네마틱 3D 는 이미지+글자로만 나온다)
 */
export function reconcileRender(
  matrix: DesignMatrix | null,
  tone: string,
  render: RenderMode,
): RenderMode {
  const allowed = rendersOfTone(matrix, tone);
  if (allowed.length === 0 || allowed.includes(render)) return render;
  return allowed[0];
}

const SELECT_CLS =
  'w-full px-3 py-2 border border-stone-300 rounded focus:outline-none focus:border-stone-500 text-stone-900 bg-white disabled:opacity-50';

export function ToneSelect(props: {
  matrix: DesignMatrix | null;
  value: string;
  onChange: (tone: string) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  const { matrix, value, onChange, disabled, compact } = props;
  const tones: ToneOption[] = matrix?.tones ?? [];
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled || tones.length === 0}
      className={compact ? `${SELECT_CLS} px-2 py-1 text-xs` : SELECT_CLS}
    >
      {tones.length === 0 && <option value={value}>불러오는 중…</option>}
      {tones.map((t) => (
        <option key={t.key} value={t.key}>
          {compact ? t.ko : `${t.ko} — ${t.desc}`}
        </option>
      ))}
    </select>
  );
}

/**
 * 렌더 방식 선택. 그 톤이 지원하지 않는 방식은 **비활성**으로 남겨 둔다 —
 * 목록에서 지우면 "왜 없지?"가 되고, 남겨 두면 "이 톤은 저 방식이 안 되는구나"가 보인다.
 */
export function RenderSelect(props: {
  matrix: DesignMatrix | null;
  tone: string;
  value: RenderMode;
  onChange: (render: RenderMode) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  const { matrix, tone, value, onChange, disabled, compact } = props;
  const allowed = rendersOfTone(matrix, tone);
  const renders = matrix?.renders ?? [];
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as RenderMode)}
      disabled={disabled || renders.length === 0}
      className={compact ? `${SELECT_CLS} px-2 py-1 text-xs` : SELECT_CLS}
    >
      {renders.length === 0 && <option value={value}>불러오는 중…</option>}
      {renders.map((r) => {
        const ok = allowed.includes(r.key);
        return (
          <option key={r.key} value={r.key} disabled={!ok}>
            {ok
              ? (compact ? r.ko : `${r.ko} — ${r.desc}`)
              : `${r.ko} — 이 톤은 지원 안 함`}
          </option>
        );
      })}
    </select>
  );
}
