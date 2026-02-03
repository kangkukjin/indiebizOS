/**
 * UserManualDialog - 사용자 메뉴얼 다이얼로그
 * 시스템의 상세한 사용 방법과 기능 안내
 */

import { useState, useEffect, useCallback } from 'react';
import {
  X, ChevronLeft, ChevronRight,
  Folder, Bot, Zap, Package,
  Users, Globe, Building2, Key,
  MessageSquare, FileText, Settings,
  Wrench, BookOpen, HardDrive, Scale,
  Video, ShoppingCart, GraduationCap, Music,
  Camera, Newspaper, Heart, Home, TrendingUp,
  Smartphone, Share2, Hash, Send, Contact,
  Mail, Bell, UserPlus, Search, Upload,
  Download, Shield, MessageCircle, Radio,
  ToggleLeft, Clock, List, Edit, Trash2,
  Plus, Eye, Lock, Unlock
} from 'lucide-react';

interface UserManualDialogProps {
  show: boolean;
  onClose: () => void;
}

interface ManualPage {
  title: string;
  icon: React.ReactNode;
  content: React.ReactNode;
}

export function UserManualDialog({ show, onClose }: UserManualDialogProps) {
  const [currentPage, setCurrentPage] = useState(0);

  const pages: ManualPage[] = [
    {
      title: '목차',
      icon: <BookOpen className="w-12 h-12 text-amber-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-800 text-base mb-4">
            IndieBiz OS의 전체 기능과 사용법을 안내합니다.
          </p>
          <div className="grid grid-cols-2 gap-3 text-base">
            <button onClick={() => setCurrentPage(1)} className="p-3 bg-amber-50 rounded-lg hover:bg-amber-100 text-left">
              <strong className="text-base text-gray-900">1. 핵심 개념</strong>
              <p className="text-gray-700 text-sm">프로젝트, 에이전트, 도구</p>
            </button>
            <button onClick={() => setCurrentPage(2)} className="p-3 bg-slate-50 rounded-lg hover:bg-slate-100 text-left">
              <strong className="text-base text-gray-900">2. 런처 오브젝트</strong>
              <p className="text-gray-700 text-sm">프로젝트, 스위치, 폴더</p>
            </button>
            <button onClick={() => setCurrentPage(3)} className="p-3 bg-yellow-50 rounded-lg hover:bg-yellow-100 text-left">
              <strong className="text-base text-gray-900">3. 업무자동화</strong>
              <p className="text-gray-700 text-sm">스위치 & 스케줄러</p>
            </button>
            <button onClick={() => setCurrentPage(4)} className="p-3 bg-indigo-50 rounded-lg hover:bg-indigo-100 text-left">
              <strong className="text-base text-gray-900">4. 원격 명령 & 자동 비지니스</strong>
              <p className="text-gray-700 text-sm">원격 명령, 자동응답</p>
            </button>
            <button onClick={() => setCurrentPage(5)} className="p-3 bg-cyan-50 rounded-lg hover:bg-cyan-100 text-left">
              <strong className="text-base text-gray-900">5. IndieNet</strong>
              <p className="text-gray-700 text-sm">P2P 네트워크, 게시판</p>
            </button>
            <button onClick={() => setCurrentPage(6)} className="p-3 bg-orange-50 rounded-lg hover:bg-orange-100 text-left">
              <strong className="text-base text-gray-900">6. 비즈니스 관리창</strong>
              <p className="text-gray-700 text-sm">메시지, 자동응답, 채널</p>
            </button>
            <button onClick={() => setCurrentPage(7)} className="p-3 bg-blue-50 rounded-lg hover:bg-blue-100 text-left">
              <strong className="text-base text-gray-900">7. 이웃 관리창</strong>
              <p className="text-gray-700 text-sm">연락처, 정보레벨, 이력</p>
            </button>
            <button onClick={() => setCurrentPage(8)} className="p-3 bg-teal-50 rounded-lg hover:bg-teal-100 text-left">
              <strong className="text-base text-gray-900">8. 빠른 연락처</strong>
              <p className="text-gray-700 text-sm">즉시 메시지 전송</p>
            </button>
            <button onClick={() => setCurrentPage(9)} className="p-3 bg-red-50 rounded-lg hover:bg-red-100 text-left">
              <strong className="text-base text-gray-900">9. AI 설정</strong>
              <p className="text-gray-700 text-sm">API 키, 모델 선택</p>
            </button>
            <button onClick={() => setCurrentPage(10)} className="p-3 bg-green-50 rounded-lg hover:bg-green-100 text-left">
              <strong className="text-base text-gray-900">10. 도구 패키지</strong>
              <p className="text-gray-700 text-sm">사용, 제작, 공유</p>
            </button>
            <button onClick={() => setCurrentPage(11)} className="p-3 bg-purple-50 rounded-lg hover:bg-purple-100 text-left">
              <strong className="text-base text-gray-900">11. 위임 체인</strong>
              <p className="text-gray-700 text-sm">내부 위임, 시스템 위임</p>
            </button>
            <button onClick={() => setCurrentPage(12)} className="p-3 bg-pink-50 rounded-lg hover:bg-pink-100 text-left">
              <strong className="text-base text-gray-900">12. 사용 예시</strong>
              <p className="text-gray-700 text-sm">16가지 실제 활용법</p>
            </button>
            <button onClick={() => setCurrentPage(13)} className="p-3 bg-gray-100 rounded-lg hover:bg-gray-200 text-left col-span-2">
              <strong className="text-base text-gray-900">13. 버전 정보</strong>
              <p className="text-gray-700 text-sm">현재 상태, 철학, 시스템 문서 안내</p>
            </button>
          </div>
        </div>
      )
    },
    {
      title: '핵심 개념',
      icon: <Folder className="w-12 h-12 text-amber-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 p-4 rounded-lg border border-amber-200">
            <p className="text-xl font-bold text-amber-800 mb-2">
              필요한 건 오직 연결 (Connection is all you need)
            </p>
            <p className="text-amber-700">
              우리는 모든 것이 모든 것과 더 잘 연결되게 하기 위해서 IndieBiz OS를 만들었습니다.
            </p>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Package className="w-6 h-6 text-green-600" />
              <strong className="text-green-800">🔧 도구와 AI 에이전트의 연결</strong>
            </div>
            <p className="text-green-700 text-sm">
              우리가 여러 가지 일들을 하기 위해서는 수많은 도구가 필요하고, 그걸 잘 관리하는 것이 필요합니다.
              그래서 우리는 <strong>프로젝트마다, 에이전트마다</strong> 지정한 도구만 쓰도록 했습니다.
              필요할 때 도구를 직접 만들어 시스템에 더할 수 있고, 원하는 에이전트만 쓰게 할 수 있습니다.
            </p>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Bot className="w-6 h-6 text-blue-600" />
              <strong className="text-blue-800">🧑‍💻 인간과 AI 에이전트의 연결</strong>
            </div>
            <p className="text-blue-700 text-sm">
              인간과 AI 에이전트를 더 잘 이어주기 위해 <strong>2차원 데스크탑 형태의 GUI</strong>를 만들었고,
              정보채널을 통해 외부에서 명령을 받을 수 있게 했습니다.
              지금은 Nostr와 Gmail을 통해 소통하지만, 이 정보채널은 더 확장될 수 있습니다.
            </p>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Users className="w-6 h-6 text-purple-600" />
              <strong className="text-purple-800">🤝 인간과 인간의 연결</strong>
            </div>
            <div className="text-purple-700 text-sm space-y-2">
              <p>
                우리는 AI가 복잡한 세상에서 <strong>인간을 잇는 미디어</strong>가 되어야 한다고 믿습니다.
                정보채널은 도구를 공유하는 데 쓰일 수도 있고, AI 에이전트끼리 이어서
                인간 대신 <strong>자동 비즈니스</strong>를 하는 데 쓸 수도 있습니다.
              </p>
              <p>
                스마트폰이 사람과 사람을 통신으로 연결한다면, IndieBiz OS는 그 연결을
                <strong>AI 에이전트의 도움을 받아 더 스마트하게</strong> 만들려고 합니다.
              </p>
            </div>
          </div>

          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="font-medium text-orange-800 mb-2">💡 예를 들면</p>
            <div className="text-sm text-orange-700 space-y-1">
              <p>• 공유하고 싶은 물품을 등록하면 찾는 사람에게 <strong>자동으로 연락</strong></p>
              <p>• 내가 찾는 물건을 <strong>AI 에이전트가 자동으로 검색</strong></p>
              <p>• 내 AI가 지인의 AI에게 물어서 <strong>정보를 찾아오게</strong> 하기</p>
            </div>
            <p className="text-orange-600 text-sm mt-2">
              Nostr 같은 탈중앙화 연결을 사용하면 <strong>플랫폼에서 독립된 방식</strong>으로 이뤄질 수 있습니다.
            </p>
          </div>

          <div className="bg-gray-100 p-3 rounded-lg text-center">
            <p className="text-gray-700 text-sm italic">
              IndieBiz OS는 이 같은 방식의 연결이 <strong>실제로 가능하다</strong>는 것을 보이기 위해 만든 것입니다.
            </p>
          </div>
        </div>
      )
    },
    {
      title: '런처 오브젝트',
      icon: <HardDrive className="w-12 h-12 text-slate-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-slate-50 p-4 rounded-lg">
            <p className="text-slate-800 font-medium mb-2">데스크탑 같은 공간</p>
            <p className="text-slate-700 text-sm">
              런처는 <strong>바탕화면처럼</strong> 아이콘을 배치할 수 있는 공간입니다.
              4가지 종류의 오브젝트를 만들고 관리할 수 있습니다.
            </p>
          </div>

          <div className="rounded-lg overflow-hidden border border-gray-200 shadow-sm">
            <img
              src="/example1.jpg"
              alt="IndieBiz OS 런처 화면"
              className="w-full h-auto"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-amber-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Folder className="w-6 h-6 text-amber-600" />
                <strong className="text-amber-800">프로젝트</strong>
              </div>
              <p className="text-amber-700 text-sm">
                에이전트들이 작업하는 독립된 공간. 더블클릭으로 열기.
              </p>
            </div>
            <div className="bg-yellow-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-6 h-6 text-yellow-600" />
                <strong className="text-yellow-800">스위치</strong>
              </div>
              <p className="text-yellow-700 text-sm">
                저장된 작업을 원클릭 실행. 더블클릭으로 즉시 실행.
              </p>
            </div>
            <div className="bg-blue-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <MessageSquare className="w-6 h-6 text-blue-600" />
                <strong className="text-blue-800">다중채팅방</strong>
              </div>
              <p className="text-blue-700 text-sm">
                여러 에이전트와 동시 대화. 협업 작업에 유용.
              </p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Folder className="w-6 h-6 text-purple-600" />
                <strong className="text-purple-800">폴더</strong>
              </div>
              <p className="text-purple-700 text-sm">
                아이콘들을 정리하는 공간. 드래그해서 넣기.
              </p>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="font-medium text-green-800 mb-2">🖱️ 아이콘 관리</p>
            <div className="text-sm text-green-700 space-y-2">
              <p>• <strong>드래그</strong>: 아이콘을 원하는 위치로 이동</p>
              <p>• <strong>우클릭</strong>: 편집, 이름 변경, 삭제 메뉴</p>
              <p>• <strong>아이콘 정렬</strong>: 바탕화면 우클릭 → 정렬 옵션</p>
              <p>• <strong>폴더에 넣기</strong>: 아이콘을 폴더로 드래그</p>
            </div>
          </div>

          <div className="bg-red-50 p-4 rounded-lg">
            <p className="font-medium text-red-800 mb-2">🗑️ 삭제</p>
            <div className="text-sm text-red-700 space-y-2">
              <p>• 필요없는 오브젝트는 <strong>휴지통</strong>에 드래그</p>
              <p>• 또는 우클릭 → 삭제 선택</p>
              <p>• 프로젝트 삭제 시 내부 대화/설정도 함께 삭제됨</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '업무자동화 : 스위치&스케줄러',
      icon: <Zap className="w-12 h-12 text-yellow-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-yellow-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-6 h-6 text-yellow-600" />
              <strong className="text-yellow-800">스위치란?</strong>
            </div>
            <p className="text-yellow-700">
              반복 작업을 저장해두고 <strong>원클릭으로 실행</strong>하는 버튼입니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">🔧 스위치 만들기</p>
            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <div className="bg-yellow-100 text-yellow-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">1</div>
                <p className="text-gray-800"><strong>프로젝트</strong>를 열고 에이전트와 대화</p>
              </div>
              <div className="flex items-start gap-2">
                <div className="bg-yellow-100 text-yellow-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">2</div>
                <p className="text-gray-800">반복하고 싶은 작업을 <strong>프롬프트로 작성</strong></p>
              </div>
              <div className="flex items-start gap-2">
                <div className="bg-yellow-100 text-yellow-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">3</div>
                <p className="text-gray-800">채팅창 상단의 <strong>⚡ 스위치 저장</strong> 버튼 클릭</p>
              </div>
              <div className="flex items-start gap-2">
                <div className="bg-yellow-100 text-yellow-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">4</div>
                <p className="text-gray-800">이름과 아이콘 설정 후 저장</p>
              </div>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="font-medium text-green-800 mb-2">✨ 스위치의 특징</p>
            <div className="text-sm text-green-700 space-y-2">
              <p>• 프로젝트 안에서 만들지만 <strong>런처 바탕화면</strong>에 아이콘 생성</p>
              <p>• <strong>원래 프로젝트를 삭제해도</strong> 스위치는 독립적으로 남음</p>
              <p>• 어떤 프로젝트, 어떤 에이전트가 실행할지 자유롭게 변경 가능</p>
              <p>• 더블클릭하면 즉시 실행, 우클릭으로 편집</p>
            </div>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-6 h-6 text-blue-600" />
              <strong className="text-blue-800">스케줄러</strong>
            </div>
            <p className="text-blue-700 mb-2 text-sm">
              스위치를 <strong>자동으로 예약 실행</strong>합니다. 상단 툴바 → 예약작업
            </p>
            <div className="text-sm text-blue-600">
              • 매일 8시: <code>0 8 * * *</code><br/>
              • 매주 금요일 6시: <code>0 18 * * 5</code><br/>
              • 2시간마다: <code>0 */2 * * *</code>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '원격 명령 & 자동 비지니스',
      icon: <Mail className="w-12 h-12 text-indigo-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-indigo-50 p-4 rounded-lg">
            <p className="text-indigo-800 font-medium mb-2">지원 채널</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-white p-2 rounded">
                <strong className="text-red-600">Gmail</strong>
                <p className="text-gray-800 text-sm">OAuth2 인증, 폴링 방식</p>
              </div>
              <div className="bg-white p-2 rounded">
                <strong className="text-purple-600">Nostr</strong>
                <p className="text-gray-800 text-sm">탈중앙화, 실시간 WebSocket</p>
              </div>
            </div>
          </div>

          <div className="bg-blue-100 p-4 rounded-lg border-2 border-blue-300">
            <div className="flex items-center gap-2 mb-2">
              <Smartphone className="w-6 h-6 text-blue-700" />
              <strong className="text-blue-800">🎯 원격 명령 (사용자 → 에이전트)</strong>
            </div>
            <div className="text-sm text-blue-700 space-y-2">
              <p>• <strong>등록된 내 연락처</strong>에서 오는 메시지는 <strong>명령으로 인식</strong></p>
              <p>• 외출 중에도 Gmail/Nostr 앱으로 PC의 에이전트에게 지시 가능</p>
              <p>• 시스템 AI가 명령을 받아 적절한 프로젝트에 위임/실행</p>
            </div>
            <div className="bg-white p-2 rounded mt-2 text-sm text-blue-600">
              예: "오늘 뉴스 정리해서 이메일로 보내줘" → 자동 실행 후 결과 회신
            </div>
          </div>

          <div className="bg-green-100 p-4 rounded-lg border-2 border-green-300">
            <div className="flex items-center gap-2 mb-2">
              <Bot className="w-6 h-6 text-green-700" />
              <strong className="text-green-800">🤖 자동응답 (외부인 → 에이전트)</strong>
            </div>
            <div className="text-sm text-green-700 space-y-2">
              <p>• 사용자가 아닌 <strong>외부인의 메시지</strong>는 자동응답 또는 기록</p>
              <p>• AI가 비즈니스 문서를 검색하여 <strong>자동으로 응대</strong></p>
              <p>• 모든 수신 메시지는 <strong>데이터베이스에 저장</strong>되어 나중에 확인 가능</p>
            </div>
            <div className="bg-white p-2 rounded mt-2 text-sm text-green-600">
              <strong>💼 자동 비즈니스의 핵심!</strong> 고객 문의, 예약, 상담을 24시간 자동 처리
            </div>
          </div>

          <div className="bg-gray-50 p-4 rounded-lg">
            <p className="font-medium text-gray-700 mb-2">🔌 채널 확장</p>
            <div className="text-sm text-gray-800 space-y-2">
              <p>• 현재는 <strong>Gmail</strong>과 <strong>Nostr</strong> 두 채널 지원</p>
              <p>• 더 많은 통신 채널을 추가하는 것이 가능</p>
              <p>• 원한다면 <strong>직접 새 채널을 개발</strong>할 수도 있습니다</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: 'IndieNet (P2P 네트워크)',
      icon: <Globe className="w-12 h-12 text-cyan-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-cyan-50 p-4 rounded-lg">
            <p className="text-cyan-800 font-medium mb-2">IndieNet이란?</p>
            <p className="text-cyan-700 text-sm">
              Nostr 프로토콜 기반의 <strong>탈중앙화 P2P 네트워크</strong>입니다.
              중앙 서버 없이 다른 IndieBiz 사용자들과 연결됩니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">🔑 신원 (Identity)</p>
            <div className="text-sm text-gray-800 space-y-2">
              <p>• <strong>공개키 (npub)</strong>: 다른 사용자에게 공유하는 주소</p>
              <p>• <strong>비밀키 (nsec)</strong>: 절대 공유하면 안 되는 개인키</p>
              <p>• 처음 실행 시 자동 생성되며, 설정에서 가져오기/내보내기 가능</p>
            </div>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <p className="font-medium text-purple-800 mb-2">📋 공개 게시판</p>
            <div className="text-sm text-purple-700 space-y-2">
              <p>• 모든 IndieBiz 사용자가 볼 수 있는 공개 글 게시</p>
              <p>• 도구 패키지 공유, 공지사항, 질문/답변</p>
              <p>• <strong>#indiebizOS-package</strong> 해시태그로 도구 검색</p>
            </div>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="font-medium text-blue-800 mb-2">#️⃣ 해시태그 게시판</p>
            <div className="text-sm text-blue-700 space-y-2">
              <p>• 특정 해시태그로 <strong>반공개 커뮤니티</strong> 형성</p>
              <p>• 해시태그를 아는 사람만 접근 가능</p>
              <p>• 관심사 모임, 소그룹 소통에 활용</p>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="font-medium text-green-800 mb-2">🔒 암호화 DM</p>
            <div className="text-sm text-green-700 space-y-2">
              <p>• NIP-04 암호화로 1:1 비밀 대화</p>
              <p>• 송신자와 수신자만 내용 확인 가능</p>
            </div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            📍 접속: 상단 툴바 → <strong>IndieNet</strong> 버튼
          </div>
        </div>
      )
    },
    {
      title: '비즈니스 관리창',
      icon: <Building2 className="w-12 h-12 text-orange-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="text-orange-800 font-medium mb-2">비즈니스 관리창이란?</p>
            <p className="text-orange-700 text-sm">
              <strong>내 비즈니스를 정의</strong>하고 <strong>비즈니스 아이템을 올리는</strong> 곳입니다.
              비즈니스는 "이웃"이라 부르는 사람들과 하게 되며, 이웃들은 각각 다른 <strong>정보 레벨</strong>을 부여받습니다.
            </p>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-6 h-6 text-blue-600" />
              <strong className="text-blue-800">🔐 정보 레벨 기반 비즈니스</strong>
            </div>
            <div className="text-sm text-blue-700 space-y-2">
              <p>• 이웃마다 <strong>다른 정보 레벨</strong>을 부여</p>
              <p>• 레벨이 다르면 <strong>다른 비즈니스</strong>를 하게 됨</p>
              <p>• 예: 가족에게만 최고 레벨 → 공유 비즈니스는 가족만 접근</p>
            </div>
            <div className="bg-white p-2 rounded mt-2 text-blue-600 text-sm">
              💡 가족과만 물건 공유를 하고 싶다면? 가족에게 최고 레벨을 주고,
              공유 비즈니스를 최고 레벨 전용으로 정의하면 됩니다.
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="w-6 h-6 text-green-600" />
              <strong className="text-green-800">📄 비즈니스 문서</strong>
            </div>
            <div className="text-sm text-green-700 space-y-2">
              <p>• 내가 <strong>어떤 비즈니스를 하는지</strong> 레벨별로 정의한 문서</p>
              <p>• 다른 사람이 요청하면 <strong>답변할 때 참조</strong></p>
              <p>• <strong>자동응답</strong> 시 AI 에이전트가 이 문서를 검색하여 응대</p>
            </div>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Bot className="w-6 h-6 text-purple-600" />
              <strong className="text-purple-800">📋 근무지침</strong>
            </div>
            <div className="text-sm text-purple-700 space-y-2">
              <p>• 자동응답하는 AI 에이전트가 <strong>특별히 알아야 할 내용</strong></p>
              <p>• 예: "예의바르게 답하라", "특정인에게는 응답하지 마라"</p>
              <p>• AI의 응대 방식, 톤, 정책을 세밀하게 조정</p>
            </div>
          </div>

          <div className="bg-gray-50 p-4 rounded-lg">
            <p className="font-medium text-gray-700 mb-2">📝 참고</p>
            <p className="text-sm text-gray-800">
              메시지 송수신 관리는 <strong>이웃 관리창</strong>에서 합니다.
              비즈니스 관리창은 비즈니스 정의와 AI 응대 설정에 집중합니다.
            </p>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            📍 접속: 상단 툴바 → <strong>비즈니스</strong> 버튼
          </div>
        </div>
      )
    },
    {
      title: '이웃 관리창',
      icon: <Users className="w-12 h-12 text-blue-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="text-blue-800 font-medium mb-2">이웃이란?</p>
            <p className="text-blue-700 text-sm">
              IndieBiz OS에서 <strong>외부 연락처</strong>를 "이웃"이라고 부릅니다.
              고객, 거래처, 파트너 등 모든 외부인을 이웃으로 등록하여 관리합니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">👤 이웃 정보 관리</p>
            <div className="text-sm text-gray-800 space-y-2">
              <p>• <strong>기본 정보</strong>: 이름, 별명, 프로필 이미지</p>
              <p>• <strong>연락처</strong>: Gmail 주소, Nostr 공개키(npub) 등록</p>
              <p>• <strong>메모</strong>: 해당 이웃에 대한 자유로운 기록</p>
              <p>• <strong>태그</strong>: 고객/거래처/VIP 등 분류용 태그</p>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-6 h-6 text-green-600" />
              <strong className="text-green-800">🔐 정보 레벨 설정</strong>
            </div>
            <div className="text-sm text-green-700 space-y-2">
              <p>• 이웃마다 <strong>공개할 정보의 수준</strong>을 다르게 설정</p>
              <p>• 자동응답 시 AI가 정보 레벨에 맞춰 응대</p>
              <p>• 예: VIP 고객에게는 상세 정보, 일반 문의에는 기본 정보만</p>
            </div>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-6 h-6 text-purple-600" />
              <strong className="text-purple-800">📜 대화 이력</strong>
            </div>
            <div className="text-sm text-purple-700 space-y-2">
              <p>• 각 이웃과의 <strong>전체 메시지 기록</strong> 확인</p>
              <p>• 수신/발신/자동응답 모두 시간순 정렬</p>
              <p>• 과거 대화 맥락 파악 후 응대 가능</p>
            </div>
          </div>

          <div className="bg-cyan-50 p-4 rounded-lg border border-cyan-200">
            <p className="font-medium text-cyan-800 mb-2">🍗 예시: AI가 이웃에게 메시지 보내기</p>
            <div className="text-sm text-cyan-700 space-y-2">
              <p>시스템 AI는 이웃 목록의 정보를 알고 있습니다. 예를 들어:</p>
              <div className="bg-white p-3 rounded mt-2 space-y-2">
                <p><strong>"통닭집"</strong>이 이웃 목록에 있다면?</p>
                <p>→ AI에게 <em>"통닭 한 마리 주문해줘"</em>라고 말하면, AI가 통닭집에게 주문 메시지를 보낼 수 있습니다.</p>
                <p className="text-cyan-600 mt-2">만약 통닭집도 IndieBiz OS를 사용한다면?</p>
                <p>→ 통닭집의 AI가 자동으로 주문을 접수하고 응답할 수 있습니다!</p>
              </div>
              <p className="text-cyan-600 mt-2">💡 이웃 목록 = AI가 연락할 수 있는 대상</p>
            </div>
          </div>

          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="font-medium text-orange-800 mb-2">➕ 이웃 추가 방법</p>
            <div className="text-sm text-orange-700 space-y-2">
              <p>• <strong>직접 추가</strong>: 이웃 관리창에서 + 버튼</p>
              <p>• <strong>메시지에서 추가</strong>: 새 발신자 자동 감지 → 이웃 등록</p>
              <p>• <strong>IndieNet에서 추가</strong>: 게시판/DM 상대를 이웃으로 저장</p>
            </div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            📍 접속: 비즈니스 창 → <strong>이웃 관리</strong> 탭 또는 상단 이웃 아이콘
          </div>
        </div>
      )
    },
    {
      title: '빠른 연락처',
      icon: <Contact className="w-12 h-12 text-teal-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-teal-50 p-4 rounded-lg">
            <p className="text-teal-800 font-medium mb-2">빠른 연락처란?</p>
            <p className="text-teal-700 text-sm">
              자주 연락하는 사람들에게 <strong>원클릭으로 메시지를 보내는</strong> 기능입니다.
              비즈니스 창을 열지 않고도 즉시 연락할 수 있습니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">사용 방법</p>
            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <div className="bg-teal-100 text-teal-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">1</div>
                <p className="text-gray-800">상단 툴바에서 <strong>빠른 연락처</strong> 버튼 클릭</p>
              </div>
              <div className="flex items-start gap-2">
                <div className="bg-teal-100 text-teal-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">2</div>
                <p className="text-gray-800">등록된 연락처 목록에서 <strong>상대방 선택</strong></p>
              </div>
              <div className="flex items-start gap-2">
                <div className="bg-teal-100 text-teal-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">3</div>
                <p className="text-gray-800">메시지 입력 후 <strong>전송</strong></p>
              </div>
            </div>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="font-medium text-blue-800 mb-2">연락처 추가</p>
            <div className="text-sm text-blue-700 space-y-2">
              <p>• 빠른 연락처 창에서 <strong>+ 추가</strong> 버튼</p>
              <p>• 이름, 연락처 유형(Gmail/Nostr), 주소 입력</p>
              <p>• 또는 비즈니스 창의 이웃 목록에서 추가</p>
            </div>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <p className="font-medium text-purple-800 mb-2">지원 채널</p>
            <div className="grid grid-cols-2 gap-2 text-sm mt-2">
              <div className="bg-white p-2 rounded">
                <Mail className="w-4 h-4 text-red-500 mb-1" />
                <p className="text-gray-700"><strong>Gmail</strong></p>
                <p className="text-gray-700">이메일 주소로 전송</p>
              </div>
              <div className="bg-white p-2 rounded">
                <Radio className="w-4 h-4 text-purple-500 mb-1" />
                <p className="text-gray-700"><strong>Nostr DM</strong></p>
                <p className="text-gray-700">npub 주소로 암호화 전송</p>
              </div>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="font-medium text-green-800 mb-2">활용 예시</p>
            <div className="text-sm text-green-700 space-y-2">
              <p>• 거래처에 빠른 확인 요청</p>
              <p>• 팀원에게 간단한 알림 전송</p>
              <p>• 자주 연락하는 고객에게 안내 발송</p>
            </div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            📍 접속: 상단 툴바 → <strong>빠른 연락처</strong> 버튼
          </div>
        </div>
      )
    },
    {
      title: 'AI 프로바이더 설정',
      icon: <Key className="w-12 h-12 text-red-500" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-red-50 p-2 rounded-lg border border-red-200">
            <p className="text-red-700 font-medium text-center">
              ⚠️ API 키 없이는 AI를 사용할 수 없습니다!
            </p>
          </div>
          <div className="bg-white border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-3 text-left text-gray-900 font-bold">프로바이더</th>
                  <th className="p-3 text-left text-gray-900 font-bold">발급처</th>
                </tr>
              </thead>
              <tbody className="text-gray-900">
                <tr className="border-t">
                  <td className="p-3"><strong>Google Gemini</strong> (추천)</td>
                  <td className="p-3 text-blue-700">aistudio.google.com</td>
                </tr>
                <tr className="border-t">
                  <td className="p-3">Anthropic Claude</td>
                  <td className="p-3 text-blue-700">console.anthropic.com</td>
                </tr>
                <tr className="border-t">
                  <td className="p-3">OpenAI GPT</td>
                  <td className="p-3 text-blue-700">platform.openai.com</td>
                </tr>
                <tr className="border-t">
                  <td className="p-3">Ollama (로컬)</td>
                  <td className="p-3 text-gray-900">API 키 불필요</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="text-blue-800 font-medium mb-2">Gemini 모델 (2026.1 현재)</p>
            <div className="space-y-2 text-blue-700">
              <p>• <strong>gemini-2.5-flash-preview</strong> - 빠르고 경제적 (추천)</p>
              <p>• <strong>gemini-2.5-pro-preview</strong> - 더 강력, 느리고 비쌈</p>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="text-green-800 font-medium mb-2">🔌 도구도 API가 필요합니다</p>
            <div className="text-sm text-green-700 space-y-2">
              <p>에이전트가 제대로 작동하려면 <strong>정보 소스</strong>가 필요합니다. 많은 도구들이 외부 API를 사용합니다.</p>
              <div className="bg-white p-2 rounded mt-2 text-green-600">
                예: 뉴스 검색(NewsAPI), 주식 시세(금융 API), 날씨(OpenWeather), 지도(Google Maps) 등
              </div>
            </div>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <p className="text-purple-800 font-medium mb-2">🔐 API 키 관리 방법</p>
            <div className="text-sm text-purple-700 space-y-2">
              <p>• API 키는 <strong>별도 문서에 안전하게 보관</strong>하세요</p>
              <p>• 시스템 AI에게 "이 API 키로 도구 설정해줘"라고 요청 가능</p>
              <p>• <strong>중요:</strong> "환경변수로 저장해줘"라고 꼭 말하세요</p>
              <p>• 하드코딩하면 키를 잊어버리거나 노출 위험이 있습니다</p>
            </div>
          </div>

          <div className="bg-amber-50 p-4 rounded-lg">
            <p className="text-amber-800 font-medium mb-2">📍 시스템 AI 프로바이더 설정</p>
            <div className="text-sm text-amber-700 space-y-2">
              <p>1. 런처 상단의 <strong>안경 메뉴</strong> 클릭</p>
              <p>2. <strong>설정</strong> 선택</p>
              <p>3. <strong>AI 프로바이더</strong> 탭에서 원하는 프로바이더 선택</p>
              <p>4. API 키 입력 후 저장</p>
              <p>5. 사용할 모델 선택 (예: gemini-2.5-flash-preview)</p>
            </div>
            <div className="bg-white p-2 rounded mt-2 text-amber-600 text-sm">
              💡 설정 후 시스템 AI와 대화하면 API가 정상 작동하는지 확인할 수 있습니다
            </div>
          </div>

          <div className="bg-slate-50 p-4 rounded-lg">
            <p className="text-slate-800 font-medium mb-2">📁 프로젝트 에이전트 프로바이더 설정</p>
            <div className="text-sm text-slate-700 space-y-2">
              <p>• 프로젝트 내부 에이전트의 AI는 <strong>프로젝트 설정</strong>에서 별도로 설정</p>
              <p>• 프로젝트 열기 → 상단 메뉴 → <strong>프로젝트 설정</strong></p>
              <p>• 프로젝트별로 다른 프로바이더/모델 사용 가능</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '도구 패키지',
      icon: <Package className="w-12 h-12 text-green-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-green-50 p-4 rounded-lg">
            <p className="text-green-800 font-medium mb-2">도구 패키지란?</p>
            <p className="text-green-700 text-sm">
              에이전트가 실제 "행동"하는 능력입니다.
              <strong>있는 것만 쓰는 게 아니라</strong>, 필요하면 <strong>직접 만들 수도</strong> 있습니다.
            </p>
            <p className="text-green-700 text-sm mt-2">
              자신이 쓸 도구를 직접 만들고 수리할 수 있다는 것은 <strong>AI 시대의 특징</strong>입니다.
              시스템 AI와 상담하세요. 더 좋은 AI가 있다면 그것과 상담해도 됩니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">🔧 도구 패키지 직접 만들기</p>
            <div className="text-sm text-gray-800 space-y-2">
              <p>• 시스템 AI에게 <strong>"○○ 도구 패키지 만들어줘"</strong>라고 요청</p>
              <p>• AI가 <code>tool.json</code> (도구 정의)와 <code>handler.py</code> (실행 로직) 생성</p>
              <p>• 필요한 Python 라이브러리도 자동 설치</p>
              <p>• 나만의 워크플로우에 맞는 커스텀 도구 제작 가능</p>
            </div>
          </div>

          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="font-medium text-orange-800 mb-2">🛠️ 도구가 작동하지 않을 때</p>
            <div className="text-sm text-orange-700 space-y-2">
              <p>• 시스템 AI에게 <strong>"왜 안 되는지 알려줘"</strong>라고 물어보기</p>
              <p>• <strong>"고쳐줘"</strong>라고 요청하면 AI가 코드를 수정</p>
              <p>• 도구는 <strong>Python 프로그램</strong>이므로 다른 AI(Claude, ChatGPT 등)에게 도움을 요청할 수도 있음</p>
            </div>
          </div>

          <div className="bg-purple-50 p-4 rounded-lg">
            <p className="font-medium text-purple-800 mb-2">🌐 Nostr에 공개하기</p>
            <div className="text-sm text-purple-700 space-y-2">
              <p>• 도구 상점에서 내 패키지의 <strong>"Nostr에 공개"</strong> 버튼 클릭</p>
              <p>• AI가 설치 방법을 자동 생성 (다른 AI도 구현 가능한 정보)</p>
              <p>• <strong>#indiebizOS-package</strong> 해시태그로 네트워크에 게시</p>
            </div>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="font-medium text-blue-800 mb-2">🔍 다른 사람의 도구 검색/설치</p>
            <div className="text-sm text-blue-700 space-y-2">
              <p>• 도구 상점 → <strong>"도구 검색"</strong> 버튼</p>
              <p>• Nostr에 공개된 패키지 검색 및 상세 정보 확인</p>
              <p>• 시스템 AI가 보안/품질/호환성 검토 후 설치</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-1 text-sm max-h-[100px] overflow-y-auto">
            <div className="bg-gray-50 p-1 rounded text-center">web</div>
            <div className="bg-gray-50 p-1 rounded text-center">investment</div>
            <div className="bg-gray-50 p-1 rounded text-center">youtube</div>
            <div className="bg-gray-50 p-1 rounded text-center">legal</div>
            <div className="bg-gray-50 p-1 rounded text-center">health-record</div>
            <div className="bg-gray-50 p-1 rounded text-center">+21개 더</div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            📦 안경 메뉴 → <strong>도구 상점</strong>에서 설치/제거/검색/공개
          </div>
        </div>
      )
    },
    {
      title: '위임 체인',
      icon: <MessageSquare className="w-12 h-12 text-purple-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-purple-50 p-4 rounded-lg">
            <p className="text-purple-800 font-medium mb-2">위임이란?</p>
            <p className="text-purple-700 text-sm">
              에이전트가 다른 에이전트에게 작업을 맡기는 것입니다.
              위임은 <strong>체인(연쇄)</strong> 형태로 이루어집니다.
            </p>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="font-medium text-blue-800 mb-2">📁 유형 1: 프로젝트 내부 위임</p>
            <div className="text-sm text-blue-700 space-y-2">
              <p>• 같은 프로젝트 안의 에이전트끼리 협업</p>
              <p>• 예: 리서처 → 분석가 → 작성자 순으로 작업</p>
              <div className="bg-white p-2 rounded mt-2 font-mono text-blue-600">
                에이전트A → call_agent(B) → 에이전트B → 결과 → A
              </div>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="font-medium text-green-800 mb-2">🌐 유형 2: 시스템 AI → 프로젝트 위임</p>
            <div className="text-sm text-green-700 space-y-2">
              <p>• <strong>시스템 AI</strong>가 적합한 프로젝트를 선택해 작업 위임</p>
              <p>• 프로젝트가 많아지고 <strong>신뢰도가 높아지면</strong> 자동 선택</p>
              <p>• 시스템 AI에게 명령 → 프로젝트 자동 활성화 → 작업 수행</p>
              <div className="bg-white p-2 rounded mt-2 font-mono text-green-600">
                사용자 → 시스템AI → (프로젝트 선택/활성화) → 작업 완료
              </div>
            </div>
          </div>

          <div className="bg-amber-50 p-4 rounded-lg">
            <p className="font-medium text-amber-800 mb-2">✨ 자동 위임의 장점</p>
            <div className="text-sm text-amber-700 space-y-2">
              <p>• 프로젝트를 직접 열 필요 없이 <strong>시스템 AI에게만 명령</strong></p>
              <p>• AI가 <strong>가장 적합한 프로젝트와 에이전트</strong>를 자동 선택</p>
              <p>• 여러 프로젝트가 협력하는 복잡한 작업도 가능</p>
            </div>
          </div>

          <div className="bg-gray-50 p-4 rounded-lg">
            <p className="font-medium text-gray-700 mb-2">💬 대화 기록</p>
            <div className="text-sm text-gray-800 space-y-2">
              <p>• 시스템 AI, 프로젝트 에이전트와의 <strong>모든 대화가 기록</strong>됩니다</p>
              <p>• 프로젝트 → 대화 기록에서 언제든 <strong>검색/열람</strong> 가능</p>
              <p>• 과거 작업 내용 확인, 이어서 작업할 때 유용</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '실제 사용 예시',
      icon: <Wrench className="w-12 h-12 text-pink-600" />,
      content: (
        <div className="space-y-3 text-base max-h-[420px] overflow-y-auto pr-1">
          <div className="bg-blue-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <HardDrive className="w-5 h-5 text-blue-700" />
              <strong className="text-blue-900">🔧 하드웨어 관리</strong>
            </div>
            <div className="text-sm text-blue-800 space-y-1">
              <p>• <strong>PC 파일 관리</strong>: 에이전트와 대화로 파일 정리 — AI가 삭제 필요성과 위험도 평가</p>
              <p>• <strong>안드로이드 폰 제어</strong>: 에이전트를 통한 기기 관리</p>
              <p>• <strong>ESP32 IoT</strong>: 에이전트가 ESP32에 코드 업로드 + 웹앱 생성 → 폰에서 LED 스위치 제어</p>
            </div>
          </div>

          <div className="bg-amber-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Scale className="w-5 h-5 text-amber-700" />
              <strong className="text-amber-900">⚖️ 법률 연구</strong>
            </div>
            <div className="text-sm text-amber-800 space-y-1">
              <p>• <strong>법령 검증</strong>: 특정 세금 감면법이 실제로 제정되었는지 정부 입법 DB에서 확인</p>
              <p>• <strong>상속세 검색</strong>: 상속세 규정 검색 및 상담</p>
              <p>• 뉴스 기사가 아닌 <strong>정부 공식 자료</strong> 기반의 신뢰할 수 있는 답변</p>
            </div>
          </div>

          <div className="bg-pink-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Video className="w-5 h-5 text-pink-700" />
              <strong className="text-pink-900">🎬 영상 / 슬라이드 / 홈페이지 제작</strong>
            </div>
            <div className="text-sm text-pink-800 space-y-1">
              <p>• <strong>빠른 영상</strong>: 가족 사진 + YouTube BGM → 사진 슬라이드쇼 영상</p>
              <p>• <strong>전문 영상</strong>: 책 리뷰 기반 소개 영상 (React/Remotion)</p>
              <p>• <strong>프레젠테이션</strong>: 슬라이드 덱 빠르게 생성</p>
              <p>• <strong>홈페이지 관리</strong>: 여러 웹사이트 파일 위치 기억, 최신 Tailwind CSS로 업데이트</p>
            </div>
          </div>

          <div className="bg-green-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <ShoppingCart className="w-5 h-5 text-green-700" />
              <strong className="text-green-900">🛒 스마트 쇼핑</strong>
            </div>
            <div className="text-sm text-green-800 space-y-1">
              <p>• 네이버 쇼핑 + 다나와 가격 비교를 <strong>AI 판단</strong>과 결합</p>
              <p>• "아내 생일 선물로 뭘 사지?" 같은 모호한 질문 → AI가 아이템 선정 → 실제 상품 검색 및 비교</p>
            </div>
          </div>

          <div className="bg-indigo-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <GraduationCap className="w-5 h-5 text-indigo-700" />
              <strong className="text-indigo-900">📚 심층 학습 & 연구</strong>
            </div>
            <div className="text-sm text-indigo-800 space-y-1">
              <p>• 여러 소스 연결 (학술 논문, The Guardian 등)로 심층 학습 대화</p>
              <p>• "왜 한국에 미세먼지가 심해?" → <strong>최신 논문 검색</strong> 기반 답변</p>
              <p>• "트럼프 재선 후 한국 정책 변화" → <strong>1차 자료 기반</strong> 보고서 작성</p>
            </div>
          </div>

          <div className="bg-purple-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Music className="w-5 h-5 text-purple-700" />
              <strong className="text-purple-900">🎵 음악</strong>
            </div>
            <div className="text-sm text-purple-800 space-y-1">
              <p>• <strong>ABC 기보법 작곡</strong>: "경쾌한 2분짜리 왈츠를 4중주로 연주해줘" → LLM이 악보 생성 및 재생</p>
              <p>• <strong>YouTube 음악 재생</strong>: "아이유 노래 3곡 틀어줘" → AI가 선곡 → 재생. 무한 플레이리스트 같은 경험</p>
            </div>
          </div>

          <div className="bg-cyan-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Camera className="w-5 h-5 text-cyan-700" />
              <strong className="text-cyan-900">📷 사진 관리</strong>
            </div>
            <div className="text-sm text-cyan-800 space-y-1">
              <p>• 사진 폴더 스캔 → 시간순 보기, 지도 보기</p>
              <p>• "2024년 10월에 어디 갔었지?" → <strong>사진의 GPS 데이터</strong>로 답변</p>
              <p>• "수원 갔을 때 사진 보여줘" → 일치하는 사진을 브라우저에 표시</p>
            </div>
          </div>

          <div className="bg-orange-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Newspaper className="w-5 h-5 text-orange-700" />
              <strong className="text-orange-900">📰 개인 신문</strong>
            </div>
            <div className="text-sm text-orange-800 space-y-1">
              <p>• 스위치 한 번 클릭 → 설정된 키워드로 구글 뉴스 검색 → 신문 형식 자동 편집 → 브라우저 표시</p>
              <p>• <strong>매일 클릭 한 번</strong>으로 맞춤형 뉴스 브리핑</p>
            </div>
          </div>

          <div className="bg-red-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Heart className="w-5 h-5 text-red-700" />
              <strong className="text-red-900">🏥 건강 관리</strong>
            </div>
            <div className="text-sm text-red-800 space-y-1">
              <p>• 여러 전문의 에이전트 (내과, 외과 등)</p>
              <p>• 대화에서 건강 정보 <strong>자동 기록</strong> → 축적된 기록 기반 맞춤형 건강 상담</p>
            </div>
          </div>

          <div className="bg-teal-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Home className="w-5 h-5 text-teal-700" />
              <strong className="text-teal-900">🏠 부동산 분석</strong>
            </div>
            <div className="text-sm text-teal-800 space-y-1">
              <p>• 아파트/다세대 실거래가, 월세/전세 조회 + <strong>지도 시각화</strong></p>
              <p>• "청주 오송역 상권 어때?" 같은 지역 분석</p>
            </div>
          </div>

          <div className="bg-emerald-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-5 h-5 text-emerald-700" />
              <strong className="text-emerald-900">📈 투자 상담</strong>
            </div>
            <div className="text-sm text-emerald-800 space-y-1">
              <p>• 보유 주식 포트폴리오 기반 투자 상담</p>
              <p>• 주가, 금, 암호화폐 가격 <strong>그래프 시각화</strong></p>
            </div>
          </div>

          <div className="bg-violet-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Radio className="w-5 h-5 text-violet-700" />
              <strong className="text-violet-900">📱 원격 명령 & 자동응답</strong>
            </div>
            <div className="text-sm text-violet-800 space-y-1">
              <p>• 외출 중 Gmail이나 Nostr 앱으로 PC의 IndieBiz OS에 명령 전송</p>
              <p>• 예: "신문 발행해서 첨부파일로 보내줘" → 시스템 AI가 실행</p>
              <p>• <strong>자동응답 시스템</strong>: 주인 외의 메시지에 AI가 적절히 응답 (명령은 실행 안 함)</p>
              <p>• 이 시스템이 고객 문의 처리, 예약 안내 등 <strong>자동화 비즈니스의 기반</strong></p>
            </div>
          </div>

          <div className="bg-slate-100 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Share2 className="w-5 h-5 text-slate-700" />
              <strong className="text-slate-900">🔄 도구 패키지 공유</strong>
            </div>
            <div className="text-sm text-slate-800 space-y-1">
              <p>• Nostr 공개 메시지로 도구 패키지 설치 정보 공유</p>
              <p>• 다른 사용자는 정보를 받아 자신의 시스템 AI에게 설치 요청</p>
              <p>• 프로그램 자체가 아닌 <strong>정보(설명, 구조, 의존성)</strong>만으로 시스템 AI가 빌드 및 설치</p>
            </div>
          </div>

          <div className="bg-fuchsia-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Hash className="w-5 h-5 text-fuchsia-700" />
              <strong className="text-fuchsia-900">#️⃣ 해시태그 게시판</strong>
            </div>
            <div className="text-sm text-fuchsia-800 space-y-1">
              <p>• IndieNet 해시태그 기반 게시판: 참여 희망자들 간 <strong>아무 해시태그로나 게시판 생성</strong></p>
              <p>• 반공개 구조 — 해시태그 아는 사람에겐 공개, 모르면 접근 불가</p>
              <p>• 관심 기반 커뮤니티, 소규모 그룹 소통, 도구 패키지 공유 채널로 활용</p>
            </div>
          </div>

          <div className="bg-rose-50 p-3 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <MessageSquare className="w-5 h-5 text-rose-700" />
              <strong className="text-rose-900">💬 멀티 채팅방</strong>
            </div>
            <div className="text-sm text-rose-800 space-y-1">
              <p>• 아무 프로젝트의 에이전트들을 <strong>하나의 채팅방에 자유롭게</strong> 모으기</p>
              <p>• 창의적 활용: 이순신 장군, 원균 장군, 나의 3자 대화 같은 것도 가능</p>
            </div>
          </div>
        </div>
      )
    },
    {
      title: '버전 정보',
      icon: <FileText className="w-12 h-12 text-gray-800" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-gray-50 p-4 rounded-lg">
            <h3 className="font-bold text-lg text-gray-800 mb-3">IndieBiz OS</h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">활성 프로젝트</p>
                <p className="text-xl font-bold text-amber-600">16개</p>
              </div>
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">도구 패키지</p>
                <p className="text-xl font-bold text-green-600">26개</p>
              </div>
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">확장 패키지</p>
                <p className="text-xl font-bold text-blue-600">9개</p>
              </div>
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">마지막 업데이트</p>
                <p className="text-lg font-bold text-gray-800">2026-02</p>
              </div>
            </div>
          </div>
          <div className="bg-amber-50 p-4 rounded-lg">
            <p className="text-amber-800 font-medium mb-2">철학</p>
            <p className="text-amber-700 text-sm italic">
              "하나의 범용 AI보다 여러 목적별 AI가 낫다"
            </p>
            <p className="text-amber-600 text-sm mt-2">
              IndieBiz OS는 모든 사용자가 같은 방식으로 사용하는 제품이 아닙니다.
              당신의 고유한 필요에 맞게 적응하는 기반입니다.
            </p>
          </div>
          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="text-blue-800 font-medium mb-1">📚 더 자세한 내용</p>
            <p className="text-blue-700 text-sm">
              시스템의 상세한 기술 문서는 <strong>data/system_docs/</strong> 폴더에 있습니다.
              시스템 AI에게 "시스템 문서 보여줘"라고 요청하면 확인할 수 있습니다.
            </p>
          </div>
          <div className="text-center text-gray-700 text-sm">
            <p>MIT License</p>
            <p className="mt-1">
              <strong>IndieBiz OS</strong> - Design. Automate. Connect.
            </p>
          </div>
        </div>
      )
    }
  ];

  // 키보드 방향키 네비게이션
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!show) return;

    if (e.key === 'ArrowLeft') {
      setCurrentPage(p => Math.max(0, p - 1));
    } else if (e.key === 'ArrowRight') {
      setCurrentPage(p => Math.min(pages.length - 1, p + 1));
    } else if (e.key === 'Escape') {
      onClose();
    }
  }, [show, pages.length, onClose]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!show) return null;

  const currentGuide = pages[currentPage];
  const isFirstPage = currentPage === 0;
  const isLastPage = currentPage === pages.length - 1;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-[900px] max-h-[95vh] overflow-hidden">
        {/* 헤더 */}
        <div className="flex items-center justify-between p-5 border-b bg-gradient-to-r from-blue-50 to-indigo-50">
          <div className="flex items-center gap-4">
            {currentGuide.icon}
            <h2 className="text-2xl font-bold text-gray-800">{currentGuide.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-blue-100 rounded-full transition-colors"
          >
            <X className="w-6 h-6 text-gray-700" />
          </button>
        </div>

        {/* 콘텐츠 */}
        <div className="p-8 min-h-[500px] max-h-[65vh] overflow-y-auto">
          {currentGuide.content}
        </div>

        {/* 페이지 인디케이터 */}
        <div className="flex justify-center gap-2 pb-4">
          {pages.map((_, index) => (
            <button
              key={index}
              onClick={() => setCurrentPage(index)}
              className={`w-2.5 h-2.5 rounded-full transition-colors ${
                index === currentPage ? 'bg-blue-500' : 'bg-gray-300 hover:bg-gray-400'
              }`}
            />
          ))}
        </div>

        {/* 푸터 (네비게이션) */}
        <div className="flex items-center justify-between p-5 border-t bg-gray-50">
          <button
            onClick={() => setCurrentPage(p => p - 1)}
            disabled={isFirstPage}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg transition-colors text-base ${
              isFirstPage
                ? 'text-gray-300 cursor-not-allowed'
                : 'text-gray-800 hover:bg-gray-200'
            }`}
          >
            <ChevronLeft className="w-6 h-6" />
            이전
          </button>

          <span className="text-base text-gray-400">
            {currentPage + 1} / {pages.length}
          </span>

          {isLastPage ? (
            <button
              onClick={onClose}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors text-base"
            >
              닫기
            </button>
          ) : (
            <button
              onClick={() => setCurrentPage(p => p + 1)}
              className="flex items-center gap-2 px-5 py-2.5 text-gray-800 hover:bg-gray-200 rounded-lg transition-colors text-base"
            >
              다음
              <ChevronRight className="w-6 h-6" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
