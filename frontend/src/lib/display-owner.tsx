import { useEffect, useRef, useSyncExternalStore, Children, isValidElement } from 'react';
import type { ReactNode } from 'react';

/** State hooks stay in the host. Only these two explicit render functions are replaceable. */
export function displayOwner<B>(initial: (bindings: B) => ReactNode) {
  let render = initial;
  let revision = 0;
  const listeners = new Set<() => void>();
  const instances = new Map<object, B>();
  const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
  const snapshot = () => revision;
  const notify = () => { revision++; listeners.forEach(fn => fn()); };
  return {
    install(candidate: typeof initial) {
      if (typeof candidate !== 'function') throw Error('표시 함수 누락');
      for (const bindings of instances.values()) {
        const previousTree = render(bindings), nextTree = candidate(bindings);
        const protectedNames = ['ChatInputArea','CameraPreview','ActionDesktop','ManualMode','ForageBrowser','WarehouseView'];
        const islands = protectedNames.map(name => (bindings as Record<string, unknown>)[name]).filter(Boolean);
        function paths(tree: ReactNode, path = ''): string[] {
          return Children.toArray(tree).flatMap((child, index) => {
            if (!isValidElement<{children?: ReactNode}>(child)) return [];
            const here = path + '/' + (child.key ?? index) + ':' + (typeof child.type === 'string' ? child.type : 'component');
            const pinned = islands.includes(child.type) || ['input','textarea','iframe','audio','video'].includes(String(child.type));
            return [...(pinned ? [here + ':' + islands.indexOf(child.type)] : []), ...paths(child.props.children, here)];
          });
        }
        if (JSON.stringify(paths(previousTree).sort()) !== JSON.stringify(paths(nextTree).sort())) throw Error('상태 소유 영역의 이동에는 호스트 이행이 필요합니다');
      }
      const previous = render; render = candidate; notify();
      return () => { render = previous; notify(); };
    },
    View({ bindings }: { bindings: B }) {
      const key = useRef({});
      useSyncExternalStore(subscribe, snapshot, snapshot);
      instances.set(key.current, bindings);
      useEffect(() => { const id = key.current; return () => { instances.delete(id); }; }, []);
      return render(bindings);
    },
  };
}
