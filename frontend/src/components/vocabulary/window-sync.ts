/** 로컬 DOM 변경 신호를 창 사이에 중계한다. 수신한 신호는 다시 방송하지 않는다. */
export function installVocabularySync() {
  const channel = !window.electron && typeof BroadcastChannel !== 'undefined'
    ? new BroadcastChannel('indiebiz-vocabulary') : null;
  let receiving = false;
  const receive = () => {
    receiving = true;
    try { window.dispatchEvent(new Event('vocabulary-changed')); }
    finally { receiving = false; }
  };
  const send = () => {
    if (receiving) return;
    window.electron?.notifyVocabularyChanged?.();
    channel?.postMessage('changed');
  };
  const unsubscribe = window.electron?.onVocabularyChanged?.(receive);
  if (channel) channel.onmessage = receive;
  window.addEventListener('vocabulary-changed', send);
  return () => {
    window.removeEventListener('vocabulary-changed', send);
    unsubscribe?.();
    channel?.close();
  };
}
