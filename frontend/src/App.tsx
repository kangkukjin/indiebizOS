/**
 * IndieBiz 메인 앱
 */

import { useEffect, useState } from 'react';
import { useAppStore } from './stores/appStore';
import { Launcher } from './components/Launcher';
import { Manager } from './components/Manager';
import { FolderView } from './components/FolderView';
import { CommunityInstrumentView } from './components/CommunityInstrumentView';
import { MessengerInstrumentView } from './components/MessengerInstrumentView';
import { BusinessInstrumentView } from './components/BusinessInstrumentView';
import { MultiChat } from './components/MultiChat';
import { PCManager } from './components/PCManager';
import { PhotoManager } from './components/PhotoManager';
import { AndroidManager } from './components/AndroidManager';
import { SystemAIView } from './components/SystemAIView';
import { LectureWorkspace } from './components/LectureWorkspace';
import { api } from './lib/api';

// URL 해시 → 라우트. ★첫 렌더 전에 동기로 계산해야 한다 — useEffect에서 늦게 읽으면
// 전용 창(메신저 등)도 첫 프레임에 기본 뷰(런처 전체)가 마운트돼 무거운 초기 요청
// (창고 Nostr 피드 등)이 발사되고, 그게 백엔드를 수 초 막아 정작 그 창이 늦게 뜬다.
interface HashRoute {
  projectId: string | null;
  initialAgent: string | null;
  folderId: string | null;
  multiChatRoomId: string | null;
  isCommunity: boolean;
  isMessenger: boolean;
  isBusiness: boolean;
  isPCManager: boolean;
  pcManagerPath: string | null;
  isPhotoManager: boolean;
  photoManagerPath: string | null;
  isAndroidManager: boolean;
  androidDeviceId: string | null;
  androidProjectId: string | null;
  isSystemAI: boolean;
  isLectureWorkspace: boolean;
  lectureId: string | null;
}

const EMPTY_ROUTE: HashRoute = {
  projectId: null, initialAgent: null, folderId: null, multiChatRoomId: null,
  isCommunity: false, isMessenger: false, isBusiness: false,
  isPCManager: false, pcManagerPath: null,
  isPhotoManager: false, photoManagerPath: null,
  isAndroidManager: false, androidDeviceId: null, androidProjectId: null,
  isSystemAI: false, isLectureWorkspace: false, lectureId: null,
};

function parseHash(hash: string): HashRoute {
  const param = (name: string) => {
    const m = hash.match(new RegExp(name + '=([^&]+)'));
    return m ? decodeURIComponent(m[1]) : null;
  };

  // 커뮤니티 계기 (옛 IndieNet 전용 창 대체 — others:feed/board/nostr)
  if (hash === '#/community') return { ...EMPTY_ROUTE, isCommunity: true };
  // 메신저 계기 (옛 이웃관리 창·빠른 연락처 대체 — others:messages CRM)
  if (hash === '#/messenger') return { ...EMPTY_ROUTE, isMessenger: true };
  // 시스템 AI
  if (hash === '#/system-ai') return { ...EMPTY_ROUTE, isSystemAI: true };
  // 강의 만들기 워크스페이스
  if (hash.startsWith('#/lecture-workspace'))
    return { ...EMPTY_ROUTE, isLectureWorkspace: true, lectureId: param('lecture_id') };
  // Business
  if (hash === '#/business') return { ...EMPTY_ROUTE, isBusiness: true };
  // PC Manager
  if (hash.startsWith('#/pcmanager'))
    return { ...EMPTY_ROUTE, isPCManager: true, pcManagerPath: param('path') };
  // Photo Manager
  if (hash.startsWith('#/photo'))
    return { ...EMPTY_ROUTE, isPhotoManager: true, photoManagerPath: param('path') };
  // Android Manager
  if (hash.startsWith('#/android'))
    return { ...EMPTY_ROUTE, isAndroidManager: true, androidDeviceId: param('device_id'), androidProjectId: param('project_id') };

  // MultiChat (URL 인코딩된 ID 디코딩)
  const multiChatMatch = hash.match(/^#\/multichat\/(.+)$/);
  if (multiChatMatch) return { ...EMPTY_ROUTE, multiChatRoomId: decodeURIComponent(multiChatMatch[1]) };

  // 프로젝트 (URL 인코딩된 ID 디코딩, ?agent= 쿼리로 초기 에이전트 — 스케줄 결과 전달용)
  const projectMatch = hash.match(/^#\/project\/([^?]+)(\?.*)?$/);
  if (projectMatch) {
    const agentMatch = projectMatch[2]?.match(/agent=([^&]+)/);
    return {
      ...EMPTY_ROUTE,
      projectId: decodeURIComponent(projectMatch[1]),
      initialAgent: agentMatch ? decodeURIComponent(agentMatch[1]) : null,
    };
  }

  // 폴더 (URL 인코딩된 ID 디코딩)
  const folderMatch = hash.match(/^#\/folder\/(.+)$/);
  if (folderMatch) return { ...EMPTY_ROUTE, folderId: decodeURIComponent(folderMatch[1]) };

  return EMPTY_ROUTE;
}

function App() {
  const { currentView, setCurrentProject, setIsConnected, setError } = useAppStore();
  const [route, setRoute] = useState<HashRoute>(() => parseHash(window.location.hash));
  const {
    projectId, initialAgent, folderId, multiChatRoomId,
    isCommunity, isMessenger, isBusiness,
    isPCManager, pcManagerPath, isPhotoManager, photoManagerPath,
    isAndroidManager, androidDeviceId, androidProjectId,
    isSystemAI, isLectureWorkspace, lectureId,
  } = route;

  // 해시 변경 추적 (초기값은 위에서 이미 동기로 읽음)
  useEffect(() => {
    const onHashChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // 프로젝트 창 존재 하트비트 — 이 창이 열려 있는 동안 조종실 '액티브 프로젝트'에 이 프로젝트가
  // 뜨게 한다(창 열림=활성). System AI presence 와 동형: 닫힘/이탈 시 즉시 부재(open:false) +
  // 하트비트 중단으로 TTL 만료 → 사라짐. stop_all 같은 별도 close 신호에 의존하지 않아 재발 없음.
  useEffect(() => {
    if (!projectId) return;
    const url = `http://127.0.0.1:8765/projects/${encodeURIComponent(projectId)}/presence`;
    const ping = (open: boolean) => {
      try {
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ open }),
          keepalive: true,
        }).catch(() => {});
      } catch { /* noop */ }
    };
    ping(true);
    const timer = setInterval(() => ping(true), 3000);
    const onHide = () => ping(false);
    window.addEventListener('pagehide', onHide);
    return () => {
      clearInterval(timer);
      window.removeEventListener('pagehide', onHide);
      ping(false);
    };
  }, [projectId]);

  // 프로젝트 ID가 있으면 프로젝트 정보 로드 + 도구 자동 배분
  useEffect(() => {
    if (projectId) {
      const loadProject = async () => {
        try {
          const projects = await api.getProjects();
          const project = projects.find((p: { id: string }) => p.id === projectId);
          if (project) {
            setCurrentProject(project);

            // 프로젝트 열 때 도구 자동 배분 (allowed_tools가 없는 에이전트만)
            try {
              const result = await api.initTools(project.id);
              if (result.status === 'success') {
                console.log(`[도구 자동 배분] ${result.message}:`, result.agents);
              }
            } catch (e) {
              // 무시 (이미 배분됨 또는 에러)
            }
          }
        } catch (error) {
          console.error('Failed to load project:', error);
        }
      };
      loadProject();
    }
  }, [projectId, setCurrentProject]);

  // 서버 연결 확인
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await api.health();
        setIsConnected(true);
        setError(null);
      } catch (error) {
        setIsConnected(false);
        setError('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인해주세요.');
      }
    };

    checkConnection();

    // 주기적으로 연결 확인
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, [setIsConnected, setError]);


  // 시스템 AI 창인 경우
  if (isSystemAI) {
    return (
      <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#F5F1EB] p-3">
        <div className="flex-1 min-h-0 flex flex-col rounded-xl overflow-hidden shadow-lg">
          <SystemAIView />
        </div>
      </div>
    );
  }

  // 강의 만들기 워크스페이스 창인 경우
  if (isLectureWorkspace) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB]">
        <LectureWorkspace initialLectureId={lectureId} />
      </div>
    );
  }

  // 커뮤니티 계기 창인 경우 (옛 IndieNet 창 대체)
  if (isCommunity) {
    return (
      <div className="h-screen w-screen overflow-hidden">
        <CommunityInstrumentView />
      </div>
    );
  }

  // 메신저 계기 창인 경우 (옛 이웃관리 창·빠른 연락처 대체)
  if (isMessenger) {
    return (
      <div className="h-screen w-screen overflow-hidden">
        <MessengerInstrumentView />
      </div>
    );
  }

  // Business 창인 경우 (옛 BusinessManager → IBL 비즈니스 계기 전용 창으로 대체)
  if (isBusiness) {
    return (
      <div className="h-screen w-screen overflow-hidden">
        <BusinessInstrumentView />
      </div>
    );
  }

  // PC Manager 창인 경우
  if (isPCManager) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <PCManager initialPath={pcManagerPath} />
        </div>
      </div>
    );
  }

  // Photo Manager 창인 경우
  if (isPhotoManager) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <PhotoManager initialPath={photoManagerPath} />
        </div>
      </div>
    );
  }

  // Android Manager 창인 경우
  if (isAndroidManager) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <AndroidManager deviceId={androidDeviceId} projectId={androidProjectId} />
        </div>
      </div>
    );
  }

  // MultiChat 창인 경우
  if (multiChatRoomId) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <MultiChat roomId={multiChatRoomId} />
        </div>
      </div>
    );
  }

  // 폴더 창인 경우 FolderView 표시
  if (folderId) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <FolderView folderId={folderId} />
        </div>
      </div>
    );
  }

  // 프로젝트 창인 경우 Manager 표시
  if (projectId) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <Manager initialAgent={initialAgent} />
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
      <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
        {currentView === 'launcher' && <Launcher />}
        {currentView === 'manager' && <Manager />}
      </div>
    </div>
  );
}

export default App;
