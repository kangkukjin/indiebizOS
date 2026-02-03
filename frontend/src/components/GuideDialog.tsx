/**
 * GuideDialog - 시작 가이드 다이얼로그
 * 처음 사용하는 사람들을 위한 앱 소개 및 사용법 안내
 */

import { useState } from 'react';
import {
  X, ChevronLeft, ChevronRight,
  Folder, Bot, Zap, Package,
  Users, Globe, Building2, ScrollText,
  Monitor, Image, Smartphone
} from 'lucide-react';

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
            IndieBiz는 개인과 소규모 비즈니스를 위한<br/>
            <strong>AI 기반 운영 시스템</strong>입니다.
          </p>
          <div className="bg-amber-50 p-4 rounded-lg border border-amber-200">
            <p className="text-amber-800 text-sm text-center">
              여러 AI 에이전트가 협력하여<br/>
              다양한 업무를 자동화하고 도와줍니다.
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
            <strong>프로젝트</strong>는 작업 공간입니다.
          </p>
          <ul className="space-y-2 text-gray-600">
            <li className="flex items-start gap-2">
              <span className="text-amber-500">•</span>
              <span>바탕화면을 <strong>우클릭</strong>하여 새 프로젝트 생성</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber-500">•</span>
              <span>프로젝트 안에 여러 <strong>AI 에이전트</strong>를 배치</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-amber-500">•</span>
              <span>에이전트들이 <strong>협력</strong>하여 작업 수행</span>
            </li>
          </ul>
          <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-700">
            💡 예: "홈페이지 제작" 프로젝트에 디자이너, 개발자, 기획자 에이전트 배치
          </div>
        </div>
      )
    },
    {
      title: 'AI 에이전트',
      icon: <Bot className="w-10 h-10 text-purple-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>에이전트</strong>는 특정 역할을 수행하는 AI입니다.
          </p>
          <ul className="space-y-2 text-gray-600">
            <li className="flex items-start gap-2">
              <span className="text-purple-500">•</span>
              <span>각 에이전트에 <strong>역할</strong>을 부여 (예: "웹 개발자")</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-purple-500">•</span>
              <span><strong>도구</strong>를 할당하여 실제 작업 수행</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-purple-500">•</span>
              <span>에이전트끼리 <strong>대화하며 협력</strong></span>
            </li>
          </ul>
          <div className="bg-purple-50 p-3 rounded-lg text-sm text-purple-700">
            💡 시스템 AI가 적절한 에이전트에게 작업을 위임합니다
          </div>
        </div>
      )
    },
    {
      title: '스위치',
      icon: <Zap className="w-10 h-10 text-yellow-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>스위치</strong>는 원클릭 자동화 버튼입니다.
          </p>
          <ul className="space-y-2 text-gray-600">
            <li className="flex items-start gap-2">
              <span className="text-yellow-500">•</span>
              <span>자주 하는 작업을 <strong>한 번의 클릭</strong>으로 실행</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-yellow-500">•</span>
              <span>바탕화면 우클릭 → <strong>새 스위치</strong>로 생성</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-yellow-500">•</span>
              <span>자연어로 명령 작성 (예: "오늘의 뉴스 요약해줘")</span>
            </li>
          </ul>
          <div className="bg-yellow-50 p-3 rounded-lg text-sm text-yellow-700">
            ⚡ 예: "매일 아침 뉴스 요약", "주간 보고서 작성" 등
          </div>
        </div>
      )
    },
    {
      title: '도구 패키지',
      icon: <Package className="w-10 h-10 text-green-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>도구</strong>는 에이전트가 실제 작업을 수행하는 능력입니다.
          </p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-gray-50 p-2 rounded flex items-center gap-2">
              <Globe className="w-4 h-4 text-blue-500" />
              <span>웹 검색/크롤링</span>
            </div>
            <div className="bg-gray-50 p-2 rounded flex items-center gap-2">
              <Monitor className="w-4 h-4 text-purple-500" />
              <span>브라우저 자동화</span>
            </div>
            <div className="bg-gray-50 p-2 rounded flex items-center gap-2">
              <Image className="w-4 h-4 text-pink-500" />
              <span>이미지/영상 제작</span>
            </div>
            <div className="bg-gray-50 p-2 rounded flex items-center gap-2">
              <Smartphone className="w-4 h-4 text-green-500" />
              <span>안드로이드 연결</span>
            </div>
          </div>
          <div className="bg-green-50 p-3 rounded-lg text-sm text-green-700">
            📦 상단 "도구" 버튼에서 설치된 도구 확인 및 관리
          </div>
        </div>
      )
    },
    {
      title: '시스템 AI',
      icon: <span className="text-4xl">🤖</span>,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600">
            <strong>시스템 AI</strong>는 당신의 개인 비서입니다.
          </p>
          <ul className="space-y-2 text-gray-600">
            <li className="flex items-start gap-2">
              <span className="text-blue-500">•</span>
              <span>바탕화면의 <strong>🤖 아이콘</strong>을 클릭</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-500">•</span>
              <span>무엇이든 <strong>대화</strong>로 요청하세요</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-500">•</span>
              <span>적절한 에이전트와 도구를 <strong>자동 선택</strong></span>
            </li>
          </ul>
          <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-700">
            💬 "오늘 할 일 정리해줘", "경쟁사 분석해줘" 등 자유롭게 대화
          </div>
        </div>
      )
    },
    {
      title: '추가 기능',
      icon: <Building2 className="w-10 h-10 text-indigo-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600 mb-3">
            더 많은 기능들이 있습니다:
          </p>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-3 p-2 bg-gray-50 rounded">
              <Users className="w-5 h-5 text-indigo-500" />
              <div>
                <strong>다중채팅방</strong>
                <p className="text-gray-500 text-xs">여러 에이전트와 동시 대화</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-2 bg-gray-50 rounded">
              <Building2 className="w-5 h-5 text-indigo-500" />
              <div>
                <strong>비즈니스 관리</strong>
                <p className="text-gray-500 text-xs">고객, 채널, 일정 통합 관리</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-2 bg-gray-50 rounded">
              <Globe className="w-5 h-5 text-indigo-500" />
              <div>
                <strong>IndieNet</strong>
                <p className="text-gray-500 text-xs">P2P 네트워크로 다른 사용자와 연결</p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-2 bg-gray-50 rounded">
              <ScrollText className="w-5 h-5 text-indigo-500" />
              <div>
                <strong>로그 뷰어</strong>
                <p className="text-gray-500 text-xs">시스템 동작 실시간 확인</p>
              </div>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '시작하기',
      icon: <span className="text-4xl">🚀</span>,
      content: (
        <div className="space-y-4">
          <p className="text-gray-600 text-center">
            이제 시작할 준비가 되었습니다!
          </p>
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 p-4 rounded-lg border border-amber-200">
            <p className="text-amber-800 font-medium mb-2">첫 번째로 해볼 것:</p>
            <ol className="text-amber-700 text-sm space-y-1">
              <li>1. 바탕화면의 <strong>🤖 시스템 AI</strong> 클릭</li>
              <li>2. "안녕, 넌 뭘 할 수 있어?" 라고 물어보기</li>
              <li>3. AI의 안내에 따라 탐험하기!</li>
            </ol>
          </div>
          <p className="text-center text-gray-500 text-sm">
            궁금한 점은 언제든 시스템 AI에게 물어보세요 😊
          </p>
        </div>
      )
    }
  ];

  if (!show) return null;

  const currentGuide = pages[currentPage];
  const isFirstPage = currentPage === 0;
  const isLastPage = currentPage === pages.length - 1;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-[480px] max-h-[90vh] overflow-hidden">
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
        <div className="p-6 min-h-[300px]">
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
