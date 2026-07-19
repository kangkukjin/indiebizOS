/**
 * GuideDialog - 시작 가이드 다이얼로그
 * 처음 사용하는 사람들을 위한 앱 소개 및 사용법 안내
 */

import { useState, useEffect, useCallback } from 'react';
import {
  X, ChevronLeft, ChevronRight,
  Folder, Bot, Zap, Package,
  Users, Building2, Key,
  MessageSquare, FileText,
  Cloud, Mail, Smartphone,
  Compass, Gauge, LayoutGrid, Search,
  Warehouse, Map as MapIcon
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
            IndieBiz OS에는 두 개의 축이 있습니다.<br/>
            뭐든 세상에 내놓는 <strong>공유창고</strong>,<br/>
            그리고 그것을 채우고 읽는 <strong>AI 에이전트 시스템</strong>.
          </p>
          <p className="text-gray-500 text-sm text-center">
            창고는 한 페이지면 설명이 끝날 만큼 단순합니다.<br/>
            그래서 이 가이드는 <strong>창고부터</strong> 시작합니다 — 목적이 분명해야 나머지가 의미를 갖습니다.
          </p>
          <div className="rounded-lg overflow-hidden border border-gray-200 shadow-sm w-fit mx-auto">
            <img src={guideExampleImage} alt="IndieBiz OS 사용 예시 — 프로젝트와 스위치를 구성한 화면" className="max-h-48 w-auto" />
          </div>
        </div>
      )
    },
    {
      title: '공유창고 — 뭐든 내놓는 창고',
      icon: <Warehouse className="w-10 h-10 text-emerald-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            <strong>공유창고</strong>는 폴더에 파일을 던져 넣으면 <strong>세상에 발행</strong>되는 창고입니다.
            그게 전부입니다 — 그런데 그 전부가 꽤 큽니다.
          </p>
          <div className="bg-emerald-50 p-3 rounded-lg border border-emerald-200 text-sm text-emerald-800 space-y-1">
            <p>동영상을 넣으면 → <strong>유튜브</strong>가 하던 일</p>
            <p>글을 넣으면 → <strong>블로그</strong>가 하던 일</p>
            <p>상품 목록을 넣으면 → <strong>쇼핑몰</strong>이 하던 일</p>
            <p>서비스 목록을 넣으면 → <strong>프리랜서 마켓</strong>이 하던 일</p>
          </div>
          <p className="text-gray-600 text-sm">
            플랫폼이 종류별로 따로 있었던 건 <strong>인간용 매대</strong>가 각각 필요했기 때문입니다.
            읽는 쪽이 AI라면 매대는 필요 없습니다 — <strong>창고 하나면 됩니다.</strong>
          </p>
          <div className="bg-sky-50 p-3 rounded-lg border border-sky-200 text-sm text-sky-800 space-y-1">
            <p>• <strong>레벨 0~4 폴더</strong> — 어느 폴더에 넣느냐가 공개 범위 (0=누구나, 4=가장 가까운 이웃만)</p>
            <p>• <strong>이웃 피드</strong> — 이웃 창고의 새 파일이 내게 흘러들어오고, 리트윗으로 되소개</p>
            <p>• <strong>내 주소 = 내 정체</strong> — 플랫폼 계정이 아니라 내가 소유한 도메인 위에 섭니다</p>
          </div>
        </div>
      )
    },
    {
      title: '왜 AI 에이전트인가',
      icon: <Bot className="w-10 h-10 text-indigo-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            창고는 단순하지만, 두 가지를 <strong>요구</strong>합니다. 사람 손만으로는 둘 다 벅찹니다.
          </p>
          <div className="bg-amber-50 p-3 rounded-lg border border-amber-200 text-sm">
            <p className="text-amber-800 font-medium mb-1">① 채울 생산자</p>
            <p className="text-amber-700">
              창고는 채워져야 삽니다. IndieBiz OS의 에이전트는 보고서·신문·카탈로그를
              <strong> 매일 만들어 창고에 자동 발행</strong>합니다 — 생산이 곧 발행이 됩니다.
            </p>
          </div>
          <div className="bg-indigo-50 p-3 rounded-lg border border-indigo-200 text-sm">
            <p className="text-indigo-800 font-medium mb-1">② 읽을 지능</p>
            <p className="text-indigo-700">
              이웃 창고들은 매대 없는 raw 파일 더미입니다. 그걸 뒤져 이해하는 것은
              <strong> 내 AI의 몫</strong> — 이웃의 나눔·구함 목록을 대조하고, 필요한 것을 찾아냅니다.
            </p>
          </div>
          <p className="text-gray-600 text-sm">
            블로그가 글쓰기를, 유튜브가 동영상을 의미 있게 했듯 —
            <strong> 뭐든 내놓을 수 있는 창고는 뭐든 만들 수 있는 AI를 의미 있게 합니다.</strong>
          </p>
          <div className="bg-gray-50 p-3 rounded-lg text-sm text-gray-700">
            💡 AI 에이전트 시스템은 세상에 많습니다. IndieBiz OS가 다른 점은
            <strong> 배포·연결 채널과 한 몸</strong>이라는 것 — 이 목적을 쥐고 보면
            뒤에 나올 3표면·IBL·프로젝트가 전부 이 순환의 부품임이 보입니다.
          </div>
        </div>
      )
    },
    {
      title: '시작에 필요한 것',
      icon: <MapIcon className="w-10 h-10 text-emerald-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            가능한 일은 아주 많지만, <strong>시작에 필요한 것</strong>은 명확합니다.<br/>
            필수 기둥 둘, 준필수 하나 — 나머지는 자동이거나 선택입니다.
          </p>
          <div className="bg-red-50 p-3 rounded-lg border border-red-200 text-sm">
            <p className="text-red-800"><strong>기둥① AI API 키 + 외부 하네스</strong> (필수)</p>
            <p className="text-red-700">시스템 AI가 깨어납니다. 하네스(Claude Desktop 등)는 설치와 수리를 맡습니다.</p>
          </div>
          <div className="bg-sky-50 p-3 rounded-lg border border-sky-200 text-sm">
            <p className="text-sky-800"><strong>기둥② Cloudflare 계정 + 본인 도메인</strong> (강력 권장)</p>
            <p className="text-sky-700">공개 얼굴이 켜집니다 — 원격 접속·공유창고·포털. 없으면 시스템이 <strong>반쪽</strong>입니다.</p>
          </div>
          <div className="bg-violet-50 p-3 rounded-lg border border-violet-200 text-sm">
            <p className="text-violet-800"><strong>기둥③ 스마트폰</strong> (준필수)</p>
            <p className="text-violet-700">브라우저만으로 설치 0 — 안드로이드는 앱을 깔면 폰이 두 번째 노드가 됩니다.</p>
          </div>
          <div className="bg-gray-50 p-3 rounded-lg text-sm text-gray-700 space-y-1">
            <p>• <strong>Nostr 통신</strong>: 자동 — 키 생성이 곧 계정, 할 일이 없습니다</p>
            <p>• <strong>이메일·텔레그램 등</strong>: 선택 — 원할 때 추가</p>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg text-sm text-amber-700">
            💰 변동비는 AI API 사용량 하나, 고정비는 도메인 연 1~2만 원이 전부. 나머지는 무료입니다.
          </div>
        </div>
      )
    },
    {
      title: '기둥① AI 키 + 하네스',
      icon: <Key className="w-10 h-10 text-red-500" />,
      content: (
        <div className="space-y-3">
          <div className="bg-red-50 p-3 rounded-lg border border-red-200">
            <p className="text-red-800 text-sm">
              첫 관문은 <strong>AI API 키 1개</strong>입니다. Claude건 ChatGPT건 Gemini건 상관없지만, 추천은 있습니다.
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
            <p className="text-blue-800 text-sm font-medium mb-2">모델 선택</p>
            <div className="space-y-1 text-blue-700 text-sm">
              <p>• 프로바이더의 <strong>최신 모델</strong>을 고르면 됩니다. Flash 계열은 일상용, Pro 계열은 복잡한 작업용.</p>
              <p>• <strong>모델 기어</strong>가 가벼운 판단은 경량 모델에, 복잡한 계획은 본격 모델에 자동 배분합니다.</p>
            </div>
          </div>
          <div className="bg-purple-50 p-3 rounded-lg border border-purple-200">
            <p className="text-purple-800 text-sm font-medium mb-1">외부 하네스도 사실상 필수입니다</p>
            <p className="text-purple-700 text-sm">
              <strong>Claude Desktop</strong> 같은 외부 AI가 두 역할을 맡습니다:
              시스템을 지어주는 <strong>설치 대장장이</strong>, 그리고 시스템이 고장 나 스스로 못 고칠 때의
              <strong> 복구 경로</strong> — 의식을 잃은 환자는 자가 수술을 못 하니까요.
            </p>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg border border-amber-200">
            <p className="text-amber-800 text-sm">
              <strong>키를 넣었다면</strong> 시스템 AI에게 <strong>"필요한 라이브러리들을 깔아줘"</strong>라고 하세요
              (목록: <code>INSTALL_DEPENDENCIES.md</code>). ⏳ 처음엔 시간이 걸립니다.
            </p>
          </div>
        </div>
      )
    },
    {
      title: '기둥② Cloudflare + 도메인',
      icon: <Cloud className="w-10 h-10 text-sky-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            이게 없어도 에이전트 시스템은 돌지만, <strong>공개 얼굴 전부</strong>가 잠깁니다 —
            원격 런처·원격 Finder·<strong>공유창고</strong>·포털·가족신문·게시판.
            만드는 건 되는데 배포와 연결이 안 되는 <strong>반쪽 시스템</strong>이 됩니다.
          </p>
          <div className="bg-sky-50 p-3 rounded-lg border border-sky-200 text-sm">
            <p className="text-sky-800 font-medium mb-1">왜 Cloudflare인가</p>
            <p className="text-sky-700">
              터널(포트포워딩 없이 집 PC를 공개 인터넷에 연결)·엣지 서빙·캐시·DNS를
              <strong> 무료로 한 계정에</strong> 묶어주는 곳이 현재 여기뿐입니다. 서버비·대역폭비 0으로 운영됩니다.
            </p>
          </div>
          <div className="bg-orange-50 p-3 rounded-lg border border-orange-200 text-sm">
            <p className="text-orange-800 font-medium mb-1">본인 도메인이 필요합니다</p>
            <p className="text-orange-700">
              연 1~2만 원 — 시스템 전체의 <strong>유일한 고정비</strong>입니다. 그리고 도메인은 빌린 계정명이 아니라
              <strong> 내가 소유하는 주소</strong>입니다. 공유창고에서는 주소가 곧 나의 정체가 됩니다.
            </p>
          </div>
          <div className="bg-gray-100 p-3 rounded-lg text-sm">
            <div className="text-gray-700 space-y-1">
              <p>1. <span className="text-blue-600 underline">dash.cloudflare.com</span> 무료 가입</p>
              <p>2. 도메인 구매(원가 판매) 또는 보유 도메인 연결</p>
              <p>3. API 토큰·Account ID 발급 → 설정에 입력</p>
              <p>4. 나머지는 AI에게: <strong>"원격 접근 터널과 공유창고를 설정해줘"</strong></p>
            </div>
          </div>
          <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-700">
            📖 자세한 방법: <strong>data/system_docs/remote_access.md</strong>
          </div>
        </div>
      )
    },
    {
      title: '기둥③ 스마트폰',
      icon: <Smartphone className="w-10 h-10 text-violet-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            폰은 <strong>두 단계 사다리</strong>입니다. 1단만으로도 일상 사용에 충분합니다.
          </p>
          <div className="bg-cyan-50 p-3 rounded-lg border border-cyan-200 text-sm">
            <p className="text-cyan-800 font-medium mb-1">1단 — 아무 폰, 브라우저 (설치 0)</p>
            <p className="text-cyan-700">
              기둥②가 서면 <strong>자동으로 열립니다</strong>. 아이폰이든 안드로이드든 주소 하나로
              원격 런처(집 시스템 리모컨)·원격 Finder·공유창고에 접속합니다. 설치할 게 없습니다.
            </p>
          </div>
          <div className="bg-violet-50 p-3 rounded-lg border border-violet-200 text-sm">
            <p className="text-violet-800 font-medium mb-1">2단 — 안드로이드 앱 (폰 = 두 번째 노드)</p>
            <p className="text-violet-700">
              폰 자체에 IndieBiz OS가 돌아 리모컨이 아니라 <strong>독립된 몸</strong>이 됩니다 —
              위치·마이크·카메라 감각, 폰 하드웨어 조작, 클립보드로 카카오톡 직결,
              집 PC가 꺼져 있어도 동작합니다.
            </p>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg text-sm text-amber-700">
            💡 2단 설치는 USB 연결이 필요해 다소 번거롭습니다 — 하네스에게
            <strong> "폰에 IndieBiz 설치해줘"</strong>라고 맡기세요.
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
      title: '런처의 3표면',
      icon: <Compass className="w-10 h-10 text-slate-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600">
            같은 시스템을 <strong>세 가지 방식</strong>으로 모십니다.<br/>
            런처 상단의 3토글로 오갑니다.
          </p>
          <div className="bg-indigo-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Compass className="w-5 h-5 text-indigo-600" />
              <strong className="text-indigo-800">자율주행</strong>
            </div>
            <p className="text-indigo-700 text-sm">
              의도를 말하면 <strong>AI가 다단계로</strong> 알아서 처리. 탐색적이고 애매한 일에.
            </p>
          </div>
          <div className="bg-cyan-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Gauge className="w-5 h-5 text-cyan-600" />
              <strong className="text-cyan-800">조종실</strong>
            </div>
            <p className="text-cyan-700 text-sm">
              경량 모델이 자연어를 명령으로 <strong>번역·검수·실행</strong>. 시스템을 감독하고 개입하는 곳 (거의 무료).
            </p>
          </div>
          <div className="bg-orange-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <LayoutGrid className="w-5 h-5 text-orange-600" />
              <strong className="text-orange-800">앱</strong>
            </div>
            <p className="text-orange-700 text-sm">
              자주 쓰는 일을 <strong>아이콘/GUI로 직접</strong> (부동산·도서·투자 등). AI 호출 없이 0토큰.
            </p>
          </div>
          <div className="bg-amber-50 p-3 rounded-lg text-sm text-amber-700">
            💡 새 일은 자율주행이 탐색 → 손에 익으면 조종실 → 굳으면 앱으로 <strong>결정화</strong>됩니다.
          </div>
        </div>
      )
    },
    {
      title: 'IBL 노드 & 도구 패키지',
      icon: <Package className="w-10 h-10 text-green-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600">
            에이전트는 <strong>IBL(IndieBiz Logic)</strong>이라는 통합 명령어로<br/>
            6개 노드의 <strong>157개 액션</strong>을 실행합니다.
          </p>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div className="bg-blue-50 p-2 rounded text-center">
              <p className="text-blue-700 font-medium">sense</p>
              <p className="text-blue-600 text-xs">감각 (정보 수집)</p>
            </div>
            <div className="bg-green-50 p-2 rounded text-center">
              <p className="text-green-700 font-medium">self</p>
              <p className="text-green-600 text-xs">자기 관리/소통</p>
            </div>
            <div className="bg-purple-50 p-2 rounded text-center">
              <p className="text-purple-700 font-medium">limbs</p>
              <p className="text-purple-600 text-xs">장치 제어/미디어</p>
            </div>
            <div className="bg-cyan-50 p-2 rounded text-center">
              <p className="text-cyan-700 font-medium">others</p>
              <p className="text-cyan-600 text-xs">협업/통신</p>
            </div>
            <div className="bg-amber-50 p-2 rounded text-center">
              <p className="text-amber-700 font-medium">engines</p>
              <p className="text-amber-600 text-xs">콘텐츠 생성</p>
            </div>
            <div className="bg-rose-50 p-2 rounded text-center">
              <p className="text-rose-700 font-medium">table</p>
              <p className="text-rose-600 text-xs">통화(데이터) 변환</p>
            </div>
          </div>
          <div className="bg-gray-50 p-3 rounded-lg text-sm">
            <p className="text-gray-700">
              각 노드는 <strong>도구 패키지</strong>로 확장됩니다.<br/>
              현재 <strong>40개</strong>의 도구 패키지가 설치되어 있습니다.
            </p>
          </div>
          <div className="bg-green-50 p-3 rounded-lg text-sm text-green-700">
            📦 안경 메뉴 → <strong>도구 상점</strong>에서 설치/제거
          </div>
        </div>
      )
    },
    {
      title: '스위치 & 메모',
      icon: <Zap className="w-10 h-10 text-yellow-600" />,
      content: (
        <div className="space-y-3">
          <p className="text-gray-600 text-sm">
            <strong>스위치</strong>는 반복 작업을 저장해두고 원클릭으로 실행하는 버튼입니다.
          </p>
          <div className="flex items-center gap-2 p-2 bg-yellow-50 rounded text-gray-900 text-sm">
            <Zap className="w-4 h-4 text-yellow-600" />
            <div>
              <strong>오늘의 뉴스</strong>
              <p className="text-gray-700">"AI, 블록체인 뉴스 5줄 요약해줘"</p>
            </div>
          </div>
          <div className="bg-yellow-50 p-3 rounded-lg text-sm text-yellow-700">
            ⚡ 바탕화면 우클릭 → <strong>새 스위치</strong>로 생성
          </div>
          <p className="text-gray-600 text-sm pt-1">
            <FileText className="w-4 h-4 inline mr-1 text-blue-600" />
            <strong>메모</strong>는 AI가 항상 기억하는 내용입니다 — 대화가 길어져도 계속 전달됩니다.
          </p>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div className="bg-blue-50 p-2 rounded text-center text-blue-700">시스템 메모</div>
            <div className="bg-purple-50 p-2 rounded text-center text-purple-700">노트</div>
            <div className="bg-indigo-50 p-2 rounded text-center text-indigo-700">근무지침</div>
          </div>
          <div className="bg-orange-50 p-3 rounded-lg text-sm text-orange-700">
            ⚠️ <strong>짧을수록 좋습니다!</strong> 5~10줄 이내로, 정말 중요한 것만.
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
              <p className="text-gray-700 text-sm">여러 프로젝트의 에이전트를 모아 그룹 대화. @멘션, 프로젝트 도구 자동 적용, 파일 첨부 지원</p>
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
            <Mail className="w-5 h-5 text-red-500" />
            <div>
              <strong>통신 채널</strong>
              <p className="text-gray-700 text-sm">Gmail, Nostr DM으로 외부 소통 & 자동응답</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-2 bg-gray-50 rounded text-gray-900">
            <Building2 className="w-5 h-5 text-blue-500" />
            <div>
              <strong>비즈니스 계기</strong>
              <p className="text-gray-700 text-sm">이웃(파트너)·아이템 관리, 자동응답 AI (앱 모드)</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-2 bg-gray-50 rounded text-gray-900">
            <Search className="w-5 h-5 text-teal-500" />
            <div>
              <strong>포식 브라우저</strong>
              <p className="text-gray-700 text-sm">정답 하나가 아니라 후보 여럿으로 시야를 넓히는 개인 검색</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '시작하기',
      icon: <span className="text-4xl">🚀</span>,
      content: (
        <div className="space-y-3">
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 p-3 rounded-lg border border-amber-200">
            <p className="text-amber-800 font-medium">Step 1: AI API 키</p>
            <p className="text-amber-700 text-sm">
              안경 메뉴 → <strong>설정</strong> → API 키 입력. 여기까지가 최소 동작입니다.
            </p>
          </div>
          <div className="bg-blue-50 p-3 rounded-lg border border-blue-200">
            <p className="text-blue-800 font-medium">Step 2: 시스템 AI와 대화</p>
            <div className="bg-white p-2 rounded border border-blue-300 text-blue-900 text-sm mt-1">
              "나는 이게 처음이야. 필요한 것들을 하나씩 설치해줘."
            </div>
          </div>
          <div className="bg-sky-50 p-3 rounded-lg border border-sky-200">
            <p className="text-sky-800 font-medium">Step 3: 공개 얼굴 켜기 (강력 권장)</p>
            <p className="text-sky-700 text-sm">
              Cloudflare 가입 + 도메인 연결 후 AI에게:
              <strong> "원격 접근 터널과 공유창고를 설정해줘"</strong>
            </p>
          </div>
          <div className="bg-violet-50 p-3 rounded-lg border border-violet-200">
            <p className="text-violet-800 font-medium">Step 4: 폰과 프로젝트</p>
            <p className="text-violet-700 text-sm">
              폰 브라우저로 원격 런처 접속 · 바탕화면 <strong>우클릭</strong> → "새 프로젝트"
            </p>
          </div>
          <div className="bg-orange-50 p-3 rounded-lg border border-orange-200">
            <p className="text-orange-800 text-sm">
              <strong>⏳ 처음에는 시간이 걸립니다!</strong> 나머지는 전부 시스템 AI와 대화로 해나가면 됩니다.
            </p>
          </div>
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
      <div className="bg-white rounded-2xl shadow-2xl w-[640px] max-h-[90vh] overflow-hidden flex flex-col">
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
        <div className="p-6 h-[420px] min-h-0 overflow-y-auto">
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
