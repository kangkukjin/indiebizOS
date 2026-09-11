/** Electron은 로컬 몸, 배포된 웹 표면은 그 문서를 서빙한 몸에 접속한다. */
export function resolveBackendOrigin(
  location: { protocol: string; origin: string }, native = false, development = false,
): string {
  return native || development || location.protocol === 'file:'
    ? 'http://127.0.0.1:8765'
    : location.origin;
}

const native = typeof window !== 'undefined' && !!window.electron;
const development = import.meta.env?.DEV ?? false;
const location = typeof window === 'undefined'
  ? { protocol: 'file:', origin: '' } : window.location;

// 서버가 원격 셸에 명시한 표식. Vite preview와 Electron의 기존 로컬 접속은 유지한다.
const remoteDocument = typeof document !== 'undefined'
  && document.documentElement.dataset.indiebizSurface === 'remote';
export const IS_WEB_SURFACE = remoteDocument && !native && !development;
export const BACKEND_ORIGIN = resolveBackendOrigin(location, native, development || !IS_WEB_SURFACE);
export const WEBSOCKET_ORIGIN = BACKEND_ORIGIN.replace(/^http/, 'ws');

/** 기존 런타임 포트 조회도 한 곳에서 유지한다. */
export async function getBackendOrigin(): Promise<string> {
  try {
    if (typeof window !== 'undefined' && window.electron?.getApiPort) {
      return `http://127.0.0.1:${await window.electron.getApiPort()}`;
    }
  } catch { /* 브리지 초기화 중에는 기본 포트로 재시도한다. */ }
  return BACKEND_ORIGIN;
}
