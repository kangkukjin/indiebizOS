/**
 * ProjectPanelView — 프로젝트 보조 패널 창의 문(門)
 *
 * 프로젝트 창 안에 갇혀 있던 판들을 독립 창으로 내보내는 자리. 창 만들기는 electron
 * 쪽 생성기 하나(PANELS)가 맡고, 여기서는 패널 이름을 컴포넌트로 옮기기만 한다 —
 * 새 패널은 양쪽에 한 줄씩.
 */

import { TeamChatView } from './TeamChatView';
import { SwitchesPanel } from './SwitchesPanel';

export type ProjectPanel = 'teamchat' | 'switches';

interface ProjectPanelViewProps {
  panel: ProjectPanel;
  projectId: string;
}

export function ProjectPanelView({ panel, projectId }: ProjectPanelViewProps) {
  if (panel === 'switches') return <SwitchesPanel projectId={projectId} />;
  return <TeamChatView projectId={projectId} />;
}
