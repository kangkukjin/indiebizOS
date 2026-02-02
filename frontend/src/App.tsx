/**
 * IndieBiz 메인 앱
 */

import { useEffect, useState } from 'react';
import { useAppStore } from './stores/appStore';
import { Launcher } from './components/Launcher';
import { Manager } from './components/Manager';
import { FolderView } from './components/FolderView';
import { IndieNet } from './components/IndieNet';
import { BusinessManager } from './components/BusinessManager';
import { MultiChat } from './components/MultiChat';
import { PCManager } from './components/PCManager';
import { PhotoManager } from './components/PhotoManager';
import { AndroidManager } from './components/AndroidManager';
import { LogViewer } from './components/LogViewer';
import { api } from './lib/api';

function App() {
  const { currentView, setCurrentProject, setIsConnected, setError } = useAppStore();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [multiChatRoomId, setMultiChatRoomId] = useState<string | null>(null);
  const [isIndieNet, setIsIndieNet] = useState(false);
  const [isBusiness, setIsBusiness] = useState(false);
  const [isPCManager, setIsPCManager] = useState(false);
  const [pcManagerPath, setPCManagerPath] = useState<string | null>(null);
  const [isPhotoManager, setIsPhotoManager] = useState(false);
  const [photoManagerPath, setPhotoManagerPath] = useState<string | null>(null);
  const [isAndroidManager, setIsAndroidManager] = useState(false);
  const [androidDeviceId, setAndroidDeviceId] = useState<string | null>(null);
  const [androidProjectId, setAndroidProjectId] = useState<string | null>(null);
  const [isLogViewer, setIsLogViewer] = useState(false);

  // URL 해시에서 프로젝트/폴더/IndieNet 확인
  useEffect(() => {
    const checkHash = () => {
      const hash = window.location.hash;

      // 로그 뷰어 체크
      if (hash === '#/log-viewer') {
        setIsLogViewer(true);
        setIsIndieNet(false);
        setIsBusiness(false);
        setIsPCManager(false);
        setIsPhotoManager(false);
        setIsAndroidManager(false);
        setProjectId(null);
        setFolderId(null);
        setMultiChatRoomId(null);
        return;
      }

      // IndieNet 체크
      if (hash === '#/indienet') {
        setIsLogViewer(false);
        setIsIndieNet(true);
        setIsBusiness(false);
        setProjectId(null);
        setFolderId(null);
        setMultiChatRoomId(null);
        return;
      }

      // Business 체크
      if (hash === '#/business') {
        setIsBusiness(true);
        setIsIndieNet(false);
        setIsPCManager(false);
        setProjectId(null);
        setFolderId(null);
        setMultiChatRoomId(null);
        return;
      }

      // PC Manager 체크
      if (hash.startsWith('#/pcmanager')) {
        setIsPCManager(true);
        setIsIndieNet(false);
        setIsBusiness(false);
        setIsPhotoManager(false);
        setProjectId(null);
        setFolderId(null);
        setMultiChatRoomId(null);
        // path 파라미터 추출
        const pathMatch = hash.match(/path=([^&]+)/);
        if (pathMatch) {
          setPCManagerPath(decodeURIComponent(pathMatch[1]));
        } else {
          setPCManagerPath(null);
        }
        return;
      }

      // Photo Manager 체크
      if (hash.startsWith('#/photo')) {
        setIsPhotoManager(true);
        setIsPCManager(false);
        setIsIndieNet(false);
        setIsBusiness(false);
        setIsAndroidManager(false);
        setProjectId(null);
        setFolderId(null);
        setMultiChatRoomId(null);
        // path 파라미터 추출
        const pathMatch = hash.match(/path=([^&]+)/);
        if (pathMatch) {
          setPhotoManagerPath(decodeURIComponent(pathMatch[1]));
        } else {
          setPhotoManagerPath(null);
        }
        return;
      }

      // Android Manager 체크
      if (hash.startsWith('#/android')) {
        setIsAndroidManager(true);
        setIsPhotoManager(false);
        setIsPCManager(false);
        setIsIndieNet(false);
        setIsBusiness(false);
        setProjectId(null);
        setFolderId(null);
        setMultiChatRoomId(null);
        // device_id 파라미터 추출
        const deviceIdMatch = hash.match(/device_id=([^&]+)/);
        if (deviceIdMatch) {
          setAndroidDeviceId(decodeURIComponent(deviceIdMatch[1]));
        } else {
          setAndroidDeviceId(null);
        }
        // project_id 파라미터 추출
        const projectIdMatch = hash.match(/project_id=([^&]+)/);
        if (projectIdMatch) {
          setAndroidProjectId(decodeURIComponent(projectIdMatch[1]));
        } else {
          setAndroidProjectId(null);
        }
        return;
      }

      // MultiChat 체크 (URL 인코딩된 ID 디코딩)
      const multiChatMatch = hash.match(/^#\/multichat\/(.+)$/);
      if (multiChatMatch) {
        setMultiChatRoomId(decodeURIComponent(multiChatMatch[1]));
        setIsIndieNet(false);
        setIsBusiness(false);
        setProjectId(null);
        setFolderId(null);
        return;
      }

      // 프로젝트 체크 (URL 인코딩된 ID 디코딩)
      const projectMatch = hash.match(/^#\/project\/(.+)$/);
      if (projectMatch) {
        setProjectId(decodeURIComponent(projectMatch[1]));
        setFolderId(null);
        setIsIndieNet(false);
        setIsBusiness(false);
        setMultiChatRoomId(null);
        return;
      }

      // 폴더 체크 (URL 인코딩된 ID 디코딩)
      const folderMatch = hash.match(/^#\/folder\/(.+)$/);
      if (folderMatch) {
        setFolderId(decodeURIComponent(folderMatch[1]));
        setProjectId(null);
        setIsIndieNet(false);
        setIsBusiness(false);
        setMultiChatRoomId(null);
        return;
      }

      // 기본
      setProjectId(null);
      setFolderId(null);
      setIsIndieNet(false);
      setIsBusiness(false);
      setIsPCManager(false);
      setIsPhotoManager(false);
      setIsAndroidManager(false);
      setIsLogViewer(false);
      setMultiChatRoomId(null);
    };

    checkHash();
    window.addEventListener('hashchange', checkHash);
    return () => window.removeEventListener('hashchange', checkHash);
  }, []);

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

  // 로그 뷰어 창인 경우
  if (isLogViewer) {
    return <LogViewer />;
  }

  // IndieNet 창인 경우
  if (isIndieNet) {
    return (
      <div className="h-screen w-screen overflow-hidden">
        <IndieNet />
      </div>
    );
  }

  // Business 창인 경우
  if (isBusiness) {
    return (
      <div className="h-screen w-screen overflow-hidden bg-[#F5F1EB] p-3">
        <div className="h-full w-full rounded-xl overflow-hidden shadow-lg">
          <BusinessManager />
        </div>
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
          <Manager />
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
