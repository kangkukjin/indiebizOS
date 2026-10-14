/** Real session hook harness; REST/WebSocket and authorization stay in the actual backend. */
import { createElement, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { CallWindow } from '../components/media/CallWindow';
import { useMediaSession } from '../components/media/use-media-session';

function Session({ id }: { id: string }) {
  const view = useMediaSession(id);
  useEffect(() => {
    const video = document.getElementById('remote') as HTMLVideoElement;
    video.srcObject = view.remoteStream;
    if (view.remoteStream) void video.play();
  }, [view.remoteStream]);
  return <div data-testid="session" data-state={view.uiState} data-role={view.session?.local_role}
    data-capturing={!!view.localStream} data-error={view.error ?? ''}>
    {view.isCallee && view.uiState === 'ringing' && <button onClick={() => void view.accept()}>수락</button>}
    <button onClick={() => void view.hangUp()}>종료</button>
  </div>;
}
const id = new URLSearchParams(location.search).get('session');
if (id) {
  const root = document.createElement('div'); document.body.append(root);
  createRoot(root).render(new URLSearchParams(location.search).has('ui')
    ? createElement(CallWindow, { sessionId: id }) : createElement(Session, { id }));
}
