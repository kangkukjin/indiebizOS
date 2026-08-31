import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

/* Electron 전용: 내장 alert()/confirm() 은 윈도우에서 닫힌 뒤 렌더러가 키보드 포커스를
   잃어 모든 입력창이 죽는다(electron#19977). 메인프로세스 dialog 판으로 갈아끼운다.
   브라우저(웹 셸)에는 electron 브리지가 없어 내장 그대로 쓴다. */
const bridge = (window as unknown as {
  electron?: { dialogAlert?: (m: string) => void; dialogConfirm?: (m: string) => boolean };
}).electron;
if (bridge?.dialogAlert && bridge?.dialogConfirm) {
  window.alert = (message?: unknown) => { bridge.dialogAlert!(String(message ?? '')); };
  window.confirm = (message?: string) => bridge.dialogConfirm!(String(message ?? ''));
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
