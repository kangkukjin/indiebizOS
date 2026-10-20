import { useEffect, useState } from 'react';
import { confirmAndroid, dismissAndroidTask, pendingAndroidTask, subscribeAndroidTasks } from '../lib/android-control';

export function AndroidControlRecovery({ target, disabled, onBusy }: {
  target: string; disabled: boolean; onBusy: (busy: boolean) => void;
}) {
  const [, refresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => subscribeAndroidTasks(() => refresh(v => v + 1)), []);
  const task = pendingAndroidTask(target);
  if (!task && !notice) return null;
  const confirm = async () => {
    setBusy(true); onBusy(true);
    try {
      const result = await confirmAndroid(task!);
      setNotice(result.verified ? '기존 작업의 결과를 확인했습니다. 상태를 새로 조회하세요.' : '요청 접수를 확인했습니다. 실제 효과는 미확인입니다.');
    } catch (e) { setNotice(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); onBusy(false); }
  };
  return <section className="rounded-xl bg-amber-50 p-4 text-sm space-y-2" aria-live="polite">
    {task && <><p>결과가 확인되지 않은 작업이 있습니다. 같은 변경을 다시 보내지 말고 기존 작업을 확인하세요.</p>
      <div className="flex gap-3">
        <button disabled={disabled || busy || !task.task_ref} onClick={() => void confirm()}>기존 작업 확인</button>
        <button disabled={disabled || busy} onClick={() => { dismissAndroidTask(target); setNotice('원 작업은 취소되지 않았습니다. 상태를 새로 조회한 뒤 판단하세요.'); }}>상태를 직접 확인하기</button>
      </div></>}
    {notice && <p>{notice}</p>}
  </section>;
}
