import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { PointerEvent, KeyboardEvent } from 'react';

type Point = { x: number; y: number };

/** 폴더마다 마지막 창 위치를 기억하고, 창 크기가 바뀌어도 제목 표시줄을 화면 안에 둔다. */
export function useFolderWindowMotion(folderId: string | null) {
  const windowRef = useRef<HTMLDivElement>(null);
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [dragging, setDragging] = useState(false);
  const origin = useRef<(Point & { pointerX: number; pointerY: number }) | null>(null);
  const place = useCallback((x: number, y: number) => {
    const element = windowRef.current;
    const parent = element?.parentElement;
    if (!folderId || !element || !parent) return;
    const point = {
      x: Math.max(0, Math.min(x, Math.max(0, parent.clientWidth - element.offsetWidth))),
      y: Math.max(0, Math.min(y, Math.max(0, parent.clientHeight - element.offsetHeight))),
    };
    setPositions(previous => previous[folderId]?.x === point.x && previous[folderId]?.y === point.y
      ? previous : { ...previous, [folderId]: point });
  }, [folderId]);
  useLayoutEffect(() => {
    const element = windowRef.current;
    const parent = element?.parentElement;
    if (!element || !parent || !folderId) return;
    const fit = () => place(element.offsetLeft, element.offsetTop);
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(parent); observer.observe(element);
    return () => { observer.disconnect(); origin.current = null; };
  }, [folderId, place]);
  const stop = () => { origin.current = null; setDragging(false); };
  const headerEvents = {
    onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0 || (event.target as HTMLElement).closest('button')) return;
      const element = windowRef.current;
      if (!element) return;
      event.preventDefault(); event.currentTarget.focus();
      origin.current = { x: element.offsetLeft, y: element.offsetTop, pointerX: event.clientX, pointerY: event.clientY };
      event.currentTarget.setPointerCapture(event.pointerId); setDragging(true);
    },
    onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
      if (origin.current) place(origin.current.x + event.clientX - origin.current.pointerX, origin.current.y + event.clientY - origin.current.pointerY);
    },
    onPointerUp: (event: PointerEvent<HTMLDivElement>) => {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      stop();
    },
    onPointerCancel: stop,
    onLostPointerCapture: stop,
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.target !== event.currentTarget || !event.key.startsWith('Arrow')) return;
      const element = windowRef.current;
      if (!element) return;
      event.preventDefault();
      place(element.offsetLeft + (event.key === 'ArrowRight' ? 10 : event.key === 'ArrowLeft' ? -10 : 0),
        element.offsetTop + (event.key === 'ArrowDown' ? 10 : event.key === 'ArrowUp' ? -10 : 0));
    },
  };
  const point = folderId ? positions[folderId] : undefined;
  return { windowRef, style: point ? { left: point.x, top: point.y } : undefined, headerEvents, dragging };
}
