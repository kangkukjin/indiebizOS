import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

/* Electron 전용: 내장 alert()/confirm() 은 윈도우에서 닫힌 뒤 렌더러가 키보드 포커스를
   잃어 모든 입력창이 죽는다(electron#19977). 메인프로세스 dialog 판으로 갈아끼운다.
   브라우저(웹 셸)에는 electron 브리지가 없어 내장 그대로 쓴다. */
const bridge = (window as unknown as {
  electron?: {
    dialogPing?: () => Promise<unknown>;
    dialogAlert?: (m: string) => void;
    dialogConfirm?: (m: string) => boolean;
  };
}).electron;
if (bridge?.dialogPing && bridge?.dialogAlert && bridge?.dialogConfirm) {
  // ★핸드셰이크 후에만 교체: sendSync 는 메인에 리스너가 없으면 렌더러가 영원히 굳는다.
  //   개발 모드에서 메인이 옛 코드인 채 렌더러만 리로드되면 그 상태가 된다(2026-08-31 실측
  //   — 런처 전체 먹통). ping(invoke)은 리스너가 없으면 reject 라 안전: 실패 시 내장 유지.
  bridge.dialogPing().then(() => {
    window.alert = (message?: unknown) => { bridge.dialogAlert!(String(message ?? '')); };
    window.confirm = (message?: string) => bridge.dialogConfirm!(String(message ?? ''));
  }).catch(() => { /* 메인이 다이얼로그 채널을 모름 — 내장 alert/confirm 그대로 */ });
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
