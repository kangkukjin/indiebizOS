/**
 * GuideDialog - 시작 가이드 다이얼로그
 * 처음 사용하는 사람들을 위한 앱 소개 및 사용법 안내
 */

import { useState, useEffect, useCallback } from 'react';
import {
  X, ChevronLeft, ChevronRight,
  Folder, Bot, Zap, Package,
  Users, Globe, Building2, Key,
  MessageSquare, FileText,
  HardDrive, Cloud
} from 'lucide-react';
import guideExampleImage from '../assets/guide-example.jpg';

interface GuideDialogProps {
  show: boolean;
  onClose: () => void;
}

interface GuidePage {
  title: string;
  icon: React.ReactNode;
  content: React.ReactNode;
}

export function GuideDialog({ show, onClose }: GuideDialogProps) {
  const [currentPage, setCurrentPage] = useState(0);

  const pages: GuidePage[] = [
    {
      title: '환영합니다!',
      icon: <span className="text-4xl">👋</span>,
      content: (
        <div className="space-y-4">
          <p className="text-lg text-center text-gray-700">
            <strong>IndieBiz OS</strong>에 오신 것을 환영합니다!
          </p>
          <p className="text-gray-600 text-center">
            하나의 "만능 AI"가 아닌,<br/>
            <strong>전문가 팀처럼 협력하는 AI 시스템</strong>입니다.
          </p>
          <div className="rounded-lg overflow-hidden border border-gray-200 shadow-sm">
            <img src={guideExampleImage} alt="IndieBiz OS 사용 예시" className="w-full" />
          </div>
          <p className="text-gray-600 text-sm text-center">
            ▲ 프로젝트와 스위치를 구성한 예시 화면
          </p>
        </div>
      )
    },
    {
      title: 'API 키 설정',
      icon: <Key className="w-10 h-10 text-red-500" />,
      content: (
        <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
          <div className="bg-red-50 p-3 rounded-lg border border-red-200">
            <p className="text-red-800 text-sm">
              가장 중요한 첫 단계는 <strong>AI의 API 키를 얻는 것</strong>입니다.
              Claude건 ChatGPT건 Gemini건 상관없지만, 추천하는 프로바이더는 있습니다.
            </p>
          </div>
          <div className="bg-green-50 p-3 rounded-lg border border-green-200">
            <p className="text-green-800 text-sm">
              <strong>추천: Google Gemini API (무료)</strong><br/>
              1. <span className="text-blue-600 underline">aistudio.google.com</span> 방문<br/>
              2. API 키 발급<br/>
              3. 안경 메뉴 → 설정 → API 키 입력
            </p>
          </div>
          <div className="bg-blue-50 p-3 rounded-lg border border-blue-200">
            <p className="text-blue-800 text-sm font-medium mb-2">모델 이름 (2026.1 현재)</p>
            <div className="space-y-1 text-blue-700 text-sm">
              <p>• <strong>gemini-3-flash-preview</strong> - 빠르고 가벼움 (추천)</p>
              <p>• <strong>gemini-3-pro-preview</strong> - 더 강력하지만 느리고 비쌈</p>
            </div>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg border border-amber-200">
            <p className="text-amber-800 text-sm">
              <strong>API 키를 설정했다면</strong> 이제 대화창에서 시스템 AI와 대화할 수 있습니다.
            </p>
            <p className="text-amber-700 text-sm mt-2">
              처음 IndieBiz OS를 사용한다면 여러 도구에 필요한 라이브러리가 없을 수 있습니다.
              시스템 AI에게 <strong>"IndieBiz OS의 파이썬을 써서 필요한 라이브러리들을 깔아줘"</strong>라고 하세요.
              필요한 목록은 <code>INSTALL_DEPENDENCIES.md</code>에 있습니다.
            </p>
            <p className="text-amber-600 text-sm mt-2">
              ⏳ 시간이 오래 걸릴 수 있으니 기다리세요.
            </p>
          </div>
          <div className="bg-gray-100 p-3 rounded-lg">
            <p className="text-gray-700 text-sm">
              💡 <strong>안경 메뉴 → 로그 보기</strong>를 켜두면 AI가 뭘 하는지 알 수 있습니다.
              문제가 생기면 로그 메시지를 복사해서 AI에게 물어볼 수도 있습니다.
            </p>
          </div>
        </div>
      )
    },
    {
      title: '프로젝트',
      icon: <Folder className="w-10 h-10 text-amber-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>프로젝트</strong>는 독립된 작업 공간입니다.<br/>
            프로젝트끼리 대화와 맥락이 섞이지 않습니다.
          </p>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div className="bg-blue-50 p-2 rounded text-center">
              <span className="text-xl">💰</span>
              <p className="text-blue-700">투자</p>
            </div>
            <div className="bg-green-50 p-2 rounded text-center">
              <span className="text-xl">🏠</span>
              <p className="text-green-700">부동산</p>
            </div>
            <div className="bg-pink-50 p-2 rounded text-center">
              <span className="text-xl">🏥</span>
              <p className="text-pink-700">의료</p>
            </div>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg text-sm text-amber-700">
            💡 바탕화면을 <strong>우클릭</strong> → "새 프로젝트"로 생성
          </div>
        </div>
      )
    },
    {
      title: '에이전트와 페르소나',
      icon: <Bot className="w-10 h-10 text-purple-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>에이전트</strong>는 특정 역할의 AI입니다.<br/>
            <strong>페르소나</strong>에 따라 답변이 달라집니다!
          </p>
          <div className="bg-purple-50 p-3 rounded-lg text-sm">
            <p className="text-purple-800 font-medium mb-2">
              "서울에서 좋은 레스토랑 추천해줘"
            </p>
            <div className="space-y-1 text-purple-700">
              <p>• <strong>30대 드라마 작가</strong> → 분위기 있는 곳</p>
              <p>• <strong>50대 과학자</strong> → 조용한 곳, 음식 퀄리티</p>
              <p>• <strong>미국 철학자</strong> → 낯선 시선의 독특한 장소</p>
            </div>
          </div>
          <p className="text-gray-500 text-sm text-center">
            범용 AI의 평균적인 답 대신,<br/>
            <strong>구체적이고 개성 있는 답</strong>을 받을 수 있습니다.
          </p>
        </div>
      )
    },
    {
      title: '도구 패키지',
      icon: <Package className="w-10 h-10 text-green-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>도구</strong>는 에이전트가 실제 행동하는 능력입니다.<br/>
            필요한 것만 설치해서 사용합니다.
          </p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-gray-50 p-2 rounded text-gray-900">
              <strong>investment</strong>
              <p className="text-gray-700 text-sm">주가, 재무제표, 공시</p>
            </div>
            <div className="bg-gray-50 p-2 rounded text-gray-900">
              <strong>real-estate</strong>
              <p className="text-gray-700 text-sm">실거래가 조회</p>
            </div>
            <div className="bg-gray-50 p-2 rounded text-gray-900">
              <strong>web</strong>
              <p className="text-gray-700 text-sm">웹 검색, 크롤링</p>
            </div>
            <div className="bg-gray-50 p-2 rounded text-gray-900">
              <strong>media_producer</strong>
              <p className="text-gray-700 text-sm">슬라이드, 영상 제작</p>
            </div>
          </div>
          <div className="bg-green-50 p-3 rounded-lg text-sm text-green-700">
            📦 안경 메뉴 → <strong>도구 상점</strong>에서 설치/제거
          </div>
        </div>
      )
    },
    {
      title: '스위치 (원클릭 자동화)',
      icon: <Zap className="w-10 h-10 text-yellow-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>스위치</strong>는 반복 작업을 저장해두고<br/>
            원클릭으로 실행하는 버튼입니다.
          </p>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 p-2 bg-yellow-50 rounded text-gray-900">
              <Zap className="w-4 h-4 text-yellow-600" />
              <div>
                <strong>오늘의 뉴스</strong>
                <p className="text-gray-700 text-sm">"AI, 블록체인 뉴스 5줄 요약해줘"</p>
              </div>
            </div>
            <div className="flex items-center gap-2 p-2 bg-yellow-50 rounded text-gray-900">
              <Zap className="w-4 h-4 text-yellow-600" />
              <div>
                <strong>관심종목 체크</strong>
                <p className="text-gray-700 text-sm">"삼성전자, 애플 현재가 알려줘"</p>
              </div>
            </div>
          </div>
          <div className="bg-yellow-50 p-3 rounded-lg text-sm text-yellow-700">
            ⚡ 바탕화면 우클릭 → <strong>새 스위치</strong>로 생성
          </div>
        </div>
      )
    },
    {
      title: '메모 (AI의 장기 기억)',
      icon: <FileText className="w-10 h-10 text-blue-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>메모</strong>는 AI가 항상 기억하는 내용입니다.<br/>
            대화가 길어져도 메모는 계속 전달됩니다.
          </p>
          <div className="space-y-2 text-sm">
            <div className="bg-blue-50 p-2 rounded text-gray-900">
              <strong>시스템 메모</strong> - 시스템 AI용
            </div>
            <div className="bg-purple-50 p-2 rounded text-gray-900">
              <strong>노트</strong> - 프로젝트 에이전트용
            </div>
            <div className="bg-indigo-50 p-2 rounded text-gray-900">
              <strong>근무지침</strong> - 자동응답 AI용
            </div>
          </div>
          <div className="bg-orange-50 p-3 rounded-lg text-sm text-orange-700">
            ⚠️ <strong>짧을수록 좋습니다!</strong><br/>
            5~10줄 이내로, 정말 중요한 것만.
          </div>
        </div>
      )
    },
    {
      title: '추가 기능',
      icon: <Building2 className="w-10 h-10 text-indigo-600" />,
      content: (
        <div className="space-y-3">
          <div className="flex items-center gap-3 p-2 bg-gray-50 rounded text-gray-900">
            <Users className="w-5 h-5 text-purple-500" />
            <div>
              <strong>다중채팅방</strong>
              <p className="text-gray-700 text-sm">여러 에이전트와 동시 대화, 토론</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-2 bg-gray-50 rounded text-gray-900">
            <MessageSquare className="w-5 h-5 text-amber-500" />
            <div>
              <strong>위임 체인</strong>
              <p className="text-gray-700 text-sm">에이전트끼리 자동 협업 (단일/순차/병렬)</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-2 bg-gray-50 rounded text-gray-900">
            <Globe className="w-5 h-5 text-green-500" />
            <div>
              <strong>IndieNet</strong>
              <p className="text-gray-700 text-sm">P2P 네트워크, 도구 패키지 공유</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-2 bg-gray-50 rounded text-gray-900">
            <Building2 className="w-5 h-5 text-blue-500" />
            <div>
              <strong>비즈니스 관리</strong>
              <p className="text-gray-700 text-sm">고객 관리, 자동응답 AI</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '원격 접근 (Finder & 런처)',
      icon: <HardDrive className="w-10 h-10 text-cyan-600" />,
      content: (
        <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
          <p className="text-gray-600">
            집에 있는 PC를 <strong>어디서든 제어 가능한 개인 서버</strong>로 만드세요.
          </p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-cyan-50 p-2 rounded text-center">
              <span className="text-xl">📁</span>
              <p className="text-cyan-700 font-medium">원격 Finder</p>
              <p className="text-cyan-600 text-xs">파일 탐색 & 스트리밍</p>
            </div>
            <div className="bg-purple-50 p-2 rounded text-center">
              <span className="text-xl">🤖</span>
              <p className="text-purple-700 font-medium">원격 런처</p>
              <p className="text-purple-600 text-xs">AI 채팅 & 스위치 실행</p>
            </div>
          </div>
          <div className="bg-gray-100 p-3 rounded-lg text-sm">
            <p className="text-gray-700">
              <strong>Cloudflare Tunnel</strong>을 사용하면 포트 포워딩이나
              DDNS 설정 없이 안전하게 외부에서 접근할 수 있습니다.
            </p>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg border border-amber-200">
            <p className="text-amber-800 text-sm font-medium mb-2">
              <Cloud className="w-4 h-4 inline mr-1" />
              사용하려면 Cloudflare 계정이 필요합니다
            </p>
            <div className="text-amber-700 text-sm space-y-1">
              <p>1. <span className="text-blue-600 underline">dash.cloudflare.com</span>에서 무료 가입</p>
              <p>2. 자신의 도메인을 Cloudflare에 연결</p>
              <p>3. <strong>API 토큰</strong>과 <strong>Account ID</strong> 발급</p>
              <p>4. IndieBiz OS 설정 → 환경변수에 입력</p>
            </div>
          </div>
          <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-700">
            📖 자세한 설정 방법: <strong>data/system_docs/remote_finder.md</strong>
          </div>
          <div className="bg-green-50 p-3 rounded-lg text-sm text-green-700">
            💡 설정 후 시스템 AI에게 <strong>"원격 접근용 터널을 설정해줘"</strong>라고 하세요.
          </div>
        </div>
      )
    },
    {
      title: '시작하기',
      icon: <span className="text-4xl">🚀</span>,
      content: (
        <div className="space-y-4">
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 p-4 rounded-lg border border-amber-200">
            <p className="text-amber-800 font-medium mb-2">Step 1: API 키 설정</p>
            <p className="text-amber-700 text-sm">
              안경 메뉴 → <strong>설정</strong> → Gemini API 키 입력
            </p>
          </div>
          <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <p className="text-blue-800 font-medium mb-2">Step 2: 시스템 AI에게 설치 요청</p>
            <p className="text-blue-700 text-sm mb-2">
              상단의 <strong>🤖 시스템 AI</strong> 버튼을 클릭하고 이렇게 말하세요:
            </p>
            <div className="bg-white p-2 rounded border border-blue-300 text-blue-900 text-sm">
              "나는 이게 처음이야. 필요한 것들을 하나씩 설치해줘."
            </div>
          </div>
          <div className="bg-orange-50 p-3 rounded-lg border border-orange-200">
            <p className="text-orange-800 text-sm">
              <strong>⏳ 처음에는 시간이 걸립니다!</strong><br/>
              시스템 AI가 필요한 라이브러리들을 설치합니다.<br/>
              설치할 것이 많으니 <strong>잠시 기다려주세요</strong>.
            </p>
          </div>
          <p className="text-gray-600 text-sm text-center">
            설치가 완료되면 프로젝트를 만들고<br/>
            에이전트와 대화할 수 있어요! 🎉
          </p>
        </div>
      )
    }
  ];

  // 키보드 네비게이션 핸들러
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!show) return;

    switch (e.key) {
      case 'ArrowLeft':
        setCurrentPage(p => Math.max(0, p - 1));
        break;
      case 'ArrowRight':
        setCurrentPage(p => Math.min(pages.length - 1, p + 1));
        break;
      case 'Escape':
        onClose();
        break;
    }
  }, [show, pages.length, onClose]);

  // 키보드 이벤트 리스너 등록
  useEffect(() => {
    if (show) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [show, handleKeyDown]);

  if (!show) return null;

  const currentGuide = pages[currentPage];
  const isFirstPage = currentPage === 0;
  const isLastPage = currentPage === pages.length - 1;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-[640px] max-h-[90vh] overflow-hidden">
        {/* 헤더 */}
        <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-amber-50 to-orange-50">
          <div className="flex items-center gap-3">
            {currentGuide.icon}
            <h2 className="text-xl font-bold text-gray-800">{currentGuide.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-amber-100 rounded-full transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* 콘텐츠 */}
        <div className="p-6 min-h-[380px] overflow-y-auto">
          {currentGuide.content}
        </div>

        {/* 페이지 인디케이터 */}
        <div className="flex justify-center gap-2 pb-4">
          {pages.map((_, index) => (
            <button
              key={index}
              onClick={() => setCurrentPage(index)}
              className={`w-2 h-2 rounded-full transition-colors ${
                index === currentPage ? 'bg-amber-500' : 'bg-gray-300 hover:bg-gray-400'
              }`}
            />
          ))}
        </div>

        {/* 푸터 (네비게이션) */}
        <div className="flex items-center justify-between p-4 border-t bg-gray-50">
          <button
            onClick={() => setCurrentPage(p => p - 1)}
            disabled={isFirstPage}
            className={`flex items-center gap-1 px-4 py-2 rounded-lg transition-colors ${
              isFirstPage
                ? 'text-gray-300 cursor-not-allowed'
                : 'text-gray-600 hover:bg-gray-200'
            }`}
          >
            <ChevronLeft className="w-4 h-4" />
            이전
          </button>

          <span className="text-sm text-gray-400">
            {currentPage + 1} / {pages.length}
          </span>

          {isLastPage ? (
            <button
              onClick={onClose}
              className="flex items-center gap-1 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
            >
              시작하기!
            </button>
          ) : (
            <button
              onClick={() => setCurrentPage(p => p + 1)}
              className="flex items-center gap-1 px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
            >
              다음
              <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
