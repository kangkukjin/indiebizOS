import { IS_WEB_SURFACE } from './backend-origin';

export const SESSION_EXPIRED = 'indiebiz:session-expired';

/** remote-mobile.css와 같은 경계. 이벤트 시점의 폭을 읽어 회전에도 대응한다. */
export function isRemotePhoneLayout() {
  return IS_WEB_SURFACE && window.matchMedia('(max-width: 767px)').matches;
}

export function checkRemoteSession(status: number) {
  if (IS_WEB_SURFACE && (status === 401 || status === 1008)) {
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
}

/** IBL 실행 효과의 목적지. 표면이 생략된 기존 데스크톱 계약은 유지한다. */
export const iblSurface = IS_WEB_SURFACE ? { surface: 'web' } : {};
