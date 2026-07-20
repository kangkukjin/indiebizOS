/**
 * useRetryingLoad — 첫 조회가 실패해도 스스로 회복하는 로더 훅.
 *
 * 왜(2026-07-20 윈도우 실측, 그전엔 자율주행 프로젝트 목록·앱모드 매니페스트에서도 같은 부류):
 * 앱이 뜨는 순간 백엔드(8765)는 아직 바인딩 전일 수 있다(신선 설치·재기동 시 수십 초).
 * 화면들이 마운트 시 딱 한 번 조회하고 실패를 그대로 굳히면, 사용자는 "failed to fetch"만
 * 보고 창을 나갔다 와야 회복된다(재마운트가 우연히 재조회이므로). 조회를 미룰 게 아니라
 * *실패를 일시적 상태로 다루는 것*이 근본 — 준비되면 자동으로 채워진다.
 *
 * ActionDesktop 이 앱모드 매니페스트에 인라인으로 쓰던 백오프를 공용화한 것.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface Options {
  /** window focus 때 재조회 (다른 창 다녀오면 최신화) */
  onFocus?: boolean;
  /** 첫 재시도 간격(ms) — 이후 2배씩, max 까지 */
  baseDelay?: number;
  maxDelay?: number;
  /** false 면 조회 자체를 하지 않는다(탭이 안 열렸을 때 등) */
  enabled?: boolean;
}

/**
 * @param load 실패 시 반드시 throw 하는 로더(성공/실패를 훅이 구분해야 재시도가 산다)
 * @returns retry — 수동 재시도(“다시 시도” 버튼용). 백오프도 초기화한다.
 */
export function useRetryingLoad(load: () => Promise<unknown>, opts: Options = {}) {
  const { onFocus = false, baseDelay = 1000, maxDelay = 10000, enabled = true } = opts;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const delay = useRef(baseDelay);
  const [retrying, setRetrying] = useState(false);

  // ★load 신원에 의존한다 — 호출자가 useCallback deps 로 조회 조건(레벨·필터)을 표현하면
  //   조건이 바뀔 때 자동 재조회된다(옛 useEffect([level, load]) 의 역할을 그대로 흡수).
  const run = useCallback(() => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    return Promise.resolve()
      .then(() => load())
      .then((r) => { delay.current = baseDelay; setRetrying(false); return r; })
      .catch(() => {
        // 백엔드 미기동/재기동 중일 수 있다 — 조용히 백오프 재시도(화면은 기존 상태 유지)
        setRetrying(true);
        timer.current = setTimeout(run, delay.current);
        delay.current = Math.min(delay.current * 2, maxDelay);
      });
  }, [load, baseDelay, maxDelay]);

  const retry = useCallback(() => { delay.current = baseDelay; return run(); }, [run, baseDelay]);

  useEffect(() => {
    if (!enabled) return;
    run();
    if (!onFocus) return () => { if (timer.current) clearTimeout(timer.current); };
    const h = () => run();
    window.addEventListener('focus', h);
    return () => {
      window.removeEventListener('focus', h);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [run, onFocus, enabled]);

  return { retry, retrying };
}
