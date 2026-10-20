/**
 * ActionGrimoireWindow — IBL 사전(마법책)의 독립 창 표면 (`#/grimoire`).
 *
 * 대화창 위 모달은 좁고, 밑의 창을 끌 수도 없었다. Electron 에선 사전을 자기 창으로 띄우고
 * 고른 낱말만 이 사전을 연 대화창으로 돌려보낸다(grimoire-relay). 창은 고른 뒤에도 열려 있어
 * 대화하면서 계속 뒤적일 수 있다.
 */
import { useCallback, useState } from 'react';
import { ActionGrimoire } from './ActionGrimoire';
import { publishGrimoireSelection } from './grimoire-relay';

export function ActionGrimoireWindow() {
  const [picked, setPicked] = useState<string | null>(null);
  const onSelect = useCallback((actionId: string) => {
    publishGrimoireSelection(actionId);
    setPicked(actionId);
  }, []);
  return <ActionGrimoire open mode="page" picked={picked} onClose={() => {}} onSelect={onSelect} />;
}
