/**
 * UserManualDialog - 사용자 메뉴얼 다이얼로그
 * 시스템의 상세한 사용 방법과 기능 안내
 *
 * 2026-07-05 전면 재작성 — 현재 시스템(런처 3표면·IBL 6노드·인지 파이프라인·
 * 메모리 7종·포식 브라우저·두 자아) 기준으로 재구성. 은퇴한 별도 창(이웃 관리창·
 * 빠른 연락처·비즈니스 관리창)과 낡은 수치를 제거.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  X, ChevronLeft, ChevronRight,
  Folder, Bot, Zap, Package,
  Users, Globe, Key,
  MessageSquare, FileText,
  BookOpen, HardDrive, Eye,
  Compass, Gauge, LayoutGrid,
  Network, Brain, Database, Search,
  Smartphone, Mail, Monitor, Sparkles
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
    // 0. 목차
    {
      title: '목차',
      icon: <BookOpen className="w-12 h-12 text-amber-600" />,
      content: (
        <div className="space-y-4">
          <p className="text-gray-800 text-base mb-4">
            IndieBiz OS는 데려다주는 <strong>자율주행차</strong>가 아니라, 입는 <strong>인지 외골격</strong>입니다.
            아래 순서대로 읽으면 전체가 잡힙니다.
          </p>
          <div className="grid grid-cols-2 gap-3 text-base">
            {[
              ['1. 무엇인가', '인지 외골격이라는 생각', 'bg-amber-50 hover:bg-amber-100'],
              ['2. 런처의 3표면', '자율주행 · 조종실 · 앱', 'bg-slate-50 hover:bg-slate-100'],
              ['3. 바탕화면 & 오브젝트', '프로젝트 · 스위치 · 폴더 · 앱', 'bg-yellow-50 hover:bg-yellow-100'],
              ['4. IBL — 신경계', '6개 노드 141개 액션', 'bg-green-50 hover:bg-green-100'],
              ['5. 자율주행 — 인지', '분류→의식→실행→평가→증류', 'bg-indigo-50 hover:bg-indigo-100'],
              ['6. 조종실', '감독·개입의 주권 기관', 'bg-cyan-50 hover:bg-cyan-100'],
              ['7. 앱 모드', '결정화된 계기 24종', 'bg-orange-50 hover:bg-orange-100'],
              ['8. 메모리 — 7종', '해마 · 심층 · 포식 기억', 'bg-blue-50 hover:bg-blue-100'],
              ['9. 포식 브라우저', '정답이 아닌 시야를 넓히는 검색', 'bg-teal-50 hover:bg-teal-100'],
              ['10. AI 프로바이더 설정', 'API 키 · 모델 기어', 'bg-red-50 hover:bg-red-100'],
              ['11. 도구 패키지', '설치 · 제작 · 공유', 'bg-purple-50 hover:bg-purple-100'],
              ['12. 소통 & 자동 비즈니스', 'Gmail · Nostr · IndieNet', 'bg-pink-50 hover:bg-pink-100'],
              ['13. 두 자아 (맥 & 폰)', '독립 자아 · CRDT 공유', 'bg-sky-50 hover:bg-sky-100'],
              ['14. 원격 접근', 'Cloudflare 터널 · 리모컨', 'bg-lime-50 hover:bg-lime-100'],
              ['15. 버전 정보', '현재 상태 · 철학 · 문서', 'bg-gray-100 hover:bg-gray-200'],
            ].map(([title, sub, cls], i) => (
              <button
                key={i}
                onClick={() => setCurrentPage(i + 1)}
                className={`p-3 rounded-lg text-left ${cls}`}
              >
                <strong className="text-base text-gray-900">{title}</strong>
                <p className="text-gray-700 text-sm">{sub}</p>
              </button>
            ))}
          </div>
        </div>
      )
    },

    // 1. 무엇인가 — 인지 외골격
    {
      title: '무엇인가 — 인지 외골격',
      icon: <Eye className="w-12 h-12 text-amber-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 p-4 rounded-lg border border-amber-200">
            <p className="text-xl font-bold text-amber-800 mb-2">
              데려다주는 자율주행차가 아니라, 입는 외골격
            </p>
            <p className="text-amber-700 text-sm">
              내 PC에서 도는 <strong>개인 소유 프로그램</strong>이 웨어러블 로봇의 <strong>몸</strong>이고,
              AI 모델은 그 <strong>두뇌</strong>(빌리는 것 · 언제든 교체됨)입니다.
              진짜 자산은 한 사람의 의지가 응고된 <strong>핏(fit)</strong> — 쓸수록 나에게 맞아 갑니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-gray-100 p-4 rounded-lg">
              <p className="font-bold text-gray-800 mb-1">정답 패러다임</p>
              <p className="text-gray-600 text-sm">
                업계 주류 · AI 브라우저. 명령 → <strong>정답 하나</strong> 도출.
                가능성을 <strong>줄여</strong> 시야를 좁힙니다.
              </p>
            </div>
            <div className="bg-green-50 p-4 rounded-lg border border-green-200">
              <p className="font-bold text-green-800 mb-1">시야 패러다임 (우리)</p>
              <p className="text-green-700 text-sm">
                인간 판단에 기반해 가능성을 <strong>늘립니다</strong>.
                힘은 AI가 대되, 어디로 뻗을지는 매 순간 <strong>사람이</strong> 정합니다.
              </p>
            </div>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-6 h-6 text-blue-600" />
              <strong className="text-blue-800">깊은 일에는 시야가 필요합니다</strong>
            </div>
            <p className="text-blue-700 text-sm">
              연구 · 집필 · 창업 · "뭘 원하는지 알아내기" 같은 일은 <strong>목적지가 루프 안에서 생성</strong>됩니다.
              한 방에 정답을 뽑는 게 아니라, 사람과 함께 좁혀 갑니다.
              그래서 IndieBiz OS의 모든 기관은 결국 이 한 신념의 파생입니다 —
              <strong> 도구는 인간의 시야를 가리기보다 넓혀야 한다.</strong>
            </p>
          </div>
        </div>
      )
    },

    // 2. 런처의 3표면
    {
      title: '런처의 3표면',
      icon: <Compass className="w-12 h-12 text-slate-600" />,
      content: (
        <div className="space-y-4 text-base">
          <p className="text-slate-700 text-sm">
            같은 IBL 신경계 위에, 직접 모는 세 표면이 있습니다.
            각각 <strong>{'{'}속도 · 표현력 · 주권{'}'}</strong> 중 둘을 갖고 하나를 내줍니다 (트릴레마).
            런처 상단의 <strong>3토글</strong>로 오갑니다.
          </p>

          <div className="bg-indigo-50 p-4 rounded-lg border border-indigo-200">
            <div className="flex items-center gap-2 mb-1">
              <Compass className="w-6 h-6 text-indigo-600" />
              <strong className="text-indigo-800">자율주행</strong>
              <span className="text-xs bg-indigo-200 text-indigo-800 px-2 py-0.5 rounded-full">비쌈 · AI 큐레이션</span>
            </div>
            <p className="text-indigo-700 text-sm">
              의도를 말하면 <strong>플래그십 AI가 다단계로</strong> 처리합니다 (5장의 인지 파이프라인).
              탐색적이고 애매한 일에 씁니다.
            </p>
          </div>

          <div className="bg-cyan-50 p-4 rounded-lg border border-cyan-200">
            <div className="flex items-center gap-2 mb-1">
              <Gauge className="w-6 h-6 text-cyan-600" />
              <strong className="text-cyan-800">조종실</strong>
              <span className="text-xs bg-cyan-200 text-cyan-800 px-2 py-0.5 rounded-full">거의 0 · 인간+언어</span>
            </div>
            <p className="text-cyan-700 text-sm">
              <strong>경량 모델</strong>이 자연어를 IBL로 번역 → dry-run 검수 → 실행.
              시스템 상태 · 모델 기어 · 프레즌스 · 주행기록이 모인 <strong>감독·개입의 주권 기관</strong>입니다.
            </p>
          </div>

          <div className="bg-orange-50 p-4 rounded-lg border border-orange-200">
            <div className="flex items-center gap-2 mb-1">
              <LayoutGrid className="w-6 h-6 text-orange-600" />
              <strong className="text-orange-800">앱</strong>
              <span className="text-xs bg-orange-200 text-orange-800 px-2 py-0.5 rounded-full">0 토큰 · 결정화</span>
            </div>
            <p className="text-orange-700 text-sm">
              증명된 워크플로를 <strong>아이콘/GUI로 직접</strong> 조작합니다 (부동산 · 도서검색 · 투자 등).
              AI 호출 없이 코드만 실행돼 공짜입니다.
            </p>
          </div>

          <div className="bg-amber-50 p-3 rounded-lg text-amber-700 text-sm">
            💡 <strong>생애주기</strong>: 새 일은 자율주행이 탐색 → IBL 흔적이 조종실 초안으로 →
            검증된 고빈도 워크플로가 앱으로 <strong>결정화</strong>. 굳히는 건 증명된 것만입니다.
          </div>
        </div>
      )
    },

    // 3. 바탕화면 & 오브젝트
    {
      title: '바탕화면 & 오브젝트',
      icon: <HardDrive className="w-12 h-12 text-slate-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-slate-50 p-4 rounded-lg">
            <p className="text-slate-800 font-medium mb-2">데스크탑 같은 공간</p>
            <p className="text-slate-700 text-sm">
              런처는 <strong>바탕화면처럼</strong> 아이콘을 자유롭게 배치하는 공간입니다.
              자율주행 · 앱 두 표면 모두 이 위에서 아이콘으로 조직됩니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-amber-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Folder className="w-6 h-6 text-amber-600" />
                <strong className="text-amber-800">프로젝트</strong>
              </div>
              <p className="text-amber-700 text-sm">
                에이전트들이 작업하는 독립된 공간. 대화·맥락이 서로 섞이지 않습니다. 더블클릭으로 열기.
              </p>
            </div>
            <div className="bg-yellow-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-6 h-6 text-yellow-600" />
                <strong className="text-yellow-800">스위치</strong>
              </div>
              <p className="text-yellow-700 text-sm">
                저장한 작업을 원클릭 실행. 원래 프로젝트를 삭제해도 독립적으로 남습니다.
              </p>
            </div>
            <div className="bg-blue-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <MessageSquare className="w-6 h-6 text-blue-600" />
                <strong className="text-blue-800">다중채팅방</strong>
              </div>
              <p className="text-blue-700 text-sm">
                여러 프로젝트의 에이전트를 한 방에 모아 그룹 대화. <strong>@멘션</strong>으로 지정,
                프로젝트 도구 자동 적용, 파일 첨부 지원.
              </p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Folder className="w-6 h-6 text-purple-600" />
                <strong className="text-purple-800">폴더</strong>
              </div>
              <p className="text-purple-700 text-sm">
                아이콘들을 정리하는 공간. 드래그해서 넣습니다.
              </p>
            </div>
          </div>

          <div className="bg-green-50 p-4 rounded-lg">
            <p className="font-medium text-green-800 mb-2">🖱️ 관리</p>
            <div className="text-sm text-green-700 space-y-1">
              <p>• <strong>드래그</strong>: 원하는 위치로 이동 (앱 아이콘도 자유 배치)</p>
              <p>• <strong>우클릭</strong>: 편집 · 이름 변경 · 삭제, 바탕화면 우클릭 → 새 프로젝트/스위치·정렬</p>
              <p>• <strong>휴지통</strong>: 필요없는 오브젝트를 드래그. 앱은 휴지통에서 되살리거나 앱 저장소에서 다시 꺼낼 수 있습니다</p>
            </div>
          </div>
        </div>
      )
    },

    // 4. IBL — 신경계
    {
      title: 'IBL — 신경계',
      icon: <Network className="w-12 h-12 text-green-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-green-50 p-4 rounded-lg">
            <p className="text-green-800 font-medium mb-2">하나의 문법으로 세계를 만진다</p>
            <p className="text-green-700 text-sm">
              세 표면이 무엇을 하든, 밑바닥에서는 전부 <strong>IBL(IndieBiz Logic)</strong> 한 문법으로 번역됩니다.
              API든 크롤링이든 안드로이드든 DB든 같은 형태로 요청 — 프로토콜 차이는 드라이버가 감춥니다.
            </p>
            <div className="bg-white p-2 rounded mt-2 font-mono text-sm text-gray-700">
              [node:action]{'{'}params{'}'} &nbsp;예){' '}
              [sense:search_ddg]{'{'}query: "AI 뉴스"{'}'}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-sm">
            {[
              ['sense', '지각 — 정보 수집', 'bg-blue-50 text-blue-700'],
              ['self', '내 자원 · 파일 · 일정', 'bg-green-50 text-green-700'],
              ['limbs', '장치 · 신체 제어', 'bg-purple-50 text-purple-700'],
              ['others', '소통 · 협업', 'bg-cyan-50 text-cyan-700'],
              ['engines', '콘텐츠 생성', 'bg-amber-50 text-amber-700'],
              ['table', '통화(데이터) 변환', 'bg-rose-50 text-rose-700'],
            ].map(([n, d, c], i) => (
              <div key={i} className={`p-2 rounded text-center ${c.split(' ')[0]}`}>
                <p className={`font-medium ${c.split(' ')[1]}`}>{n}</p>
                <p className="text-xs text-gray-600">{d}</p>
              </div>
            ))}
          </div>

          <div className="bg-indigo-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-6 h-6 text-indigo-600" />
              <strong className="text-indigo-800">왜 도구 더미가 아니라 언어인가</strong>
            </div>
            <p className="text-indigo-700 text-sm">
              표현력은 어휘 크기가 아니라 <strong>조합</strong>에서 나옵니다.
              적게 고른 프리미티브 <strong>6개 노드 · 141개 액션</strong>을
              <span className="font-mono"> {'>>'} </span>(순차) ·
              <span className="font-mono"> & </span>(병렬) ·
              <span className="font-mono"> ?? </span>(폴백)로 엮으면 사실상 무한한 워크플로가 됩니다.
            </p>
          </div>

          <div className="bg-gray-100 p-3 rounded-lg text-gray-700 text-sm">
            💡 조종실에서 자연어로 말하면 경량 AI가 알아서 IBL로 번역해 주니,
            문법을 외울 필요는 없습니다. 다만 이 언어가 있기에 표면 셋이 한 몸으로 움직입니다.
          </div>
        </div>
      )
    },

    // 5. 자율주행 — 인지 파이프라인
    {
      title: '자율주행 — 인지 파이프라인',
      icon: <Brain className="w-12 h-12 text-indigo-600" />,
      content: (
        <div className="space-y-3 text-base">
          <p className="text-gray-700 text-sm">
            자율주행 표면의 내부. 인간의 인지 과정을 모델링합니다 —
            <strong> 분류(반사) → 의식(계획) → 실행 → 평가(성찰) → 증류(학습)</strong>.
          </p>

          <div className="bg-white border rounded-lg p-3 space-y-2 text-sm">
            {[
              ['0 · 연상', '해마(과거 IBL 사례) + 심층메모리(사용자 사실)를 1회 검색', 'bg-slate-100 text-slate-700'],
              ['1 · 반사', '해마 점수 ≥ 0.85 → 곧장 실행(무의식 스킵). 미만이면 경량 AI가 EXECUTE/THINK 분류', 'bg-blue-100 text-blue-700'],
              ['2 · 의식', '(THINK만) 본격 AI가 "지금 무슨 문제를 풀어야 하나" 규정 + 달성 기준', 'bg-purple-100 text-purple-700'],
              ['3 · 실행', 'IBL 엔진 → 도구 실행', 'bg-green-100 text-green-700'],
              ['4 · 평가', '경량 AI가 달성 기준 대비 검증. 미달이면 재시도 (최대 3라운드)', 'bg-amber-100 text-amber-700'],
              ['5 · 증류', '성공 경험을 해마·심층메모리에 저장 → 다음엔 더 빠르게', 'bg-rose-100 text-rose-700'],
            ].map(([step, desc, c], i) => (
              <div key={i} className="flex items-start gap-2">
                <span className={`px-2 py-0.5 rounded font-medium flex-shrink-0 ${c}`}>{step}</span>
                <span className="text-gray-700">{desc}</span>
              </div>
            ))}
          </div>

          <div className="bg-cyan-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Gauge className="w-6 h-6 text-cyan-600" />
              <strong className="text-cyan-800">모델 기어 — 비용/속도를 한 손잡이로 변속</strong>
            </div>
            <p className="text-cyan-700 text-sm">
              <strong>절약 / 균형 / 최대</strong> 레버(조종실에 노출)가 4축(분류·평가·실행·의식)을
              티어(경량 / 중급 / 고급)로 매핑합니다. <strong>의식 토글</strong>을 끄면 THINK 경로를 차단해
              더 빠르고 싸게 돕니다.
            </p>
          </div>
        </div>
      )
    },

    // 6. 조종실
    {
      title: '조종실 — 주권 기관',
      icon: <Gauge className="w-12 h-12 text-cyan-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-cyan-50 p-4 rounded-lg">
            <p className="text-cyan-800 font-medium mb-2">감독하고 개입하는 곳</p>
            <p className="text-cyan-700 text-sm">
              조종실은 단순한 "수동 모드"가 아니라, 자율주행을 포함한 <strong>전체를 감독·개입하는 주권 기관</strong>입니다.
              토큰을 거의 쓰지 않으면서 시스템이 무엇을 하는지 들여다보고 직접 손댈 수 있습니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">⚙️ 자연어 → 실행까지</p>
            <div className="space-y-2 text-sm">
              {[
                ['번역', '경량 모델이 자연어를 IBL 코드로 컴파일'],
                ['검수', 'dry-run으로 무엇이 실행될지 먼저 보여줌'],
                ['실행', '확인 후 게이팅 실행'],
                ['증류', '성공한 실행을 해마에 학습'],
              ].map(([s, d], i) => (
                <div key={i} className="flex items-start gap-2">
                  <div className="bg-cyan-100 text-cyan-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">{i + 1}</div>
                  <p className="text-gray-800"><strong>{s}</strong> — {d}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-slate-50 p-4 rounded-lg">
            <p className="font-medium text-slate-800 mb-2">🎛️ 계기판에 모인 것들</p>
            <div className="text-sm text-slate-700 space-y-1">
              <p>• <strong>모델 기어 레버</strong>: 절약/균형/최대 + 의식 토글</p>
              <p>• <strong>시스템 상태</strong>: 서비스 건강 · 자가점검 결과</p>
              <p>• <strong>프레즌스</strong>: 지금 어떤 자아(맥/폰)가 깨어 있는지</p>
              <p>• <strong>액티브 프로젝트</strong>: 지금 일하는 대화창 (클릭하면 맨 앞으로)</p>
              <p>• <strong>주행기록</strong>: 최근 무엇을 실행했는지의 로그</p>
              <p>• <strong>둘러보기 팔레트</strong>: 쓸 수 있는 IBL 어휘를 훑어봄</p>
            </div>
          </div>
        </div>
      )
    },

    // 7. 앱 모드
    {
      title: '앱 모드 — 결정화된 계기',
      icon: <LayoutGrid className="w-12 h-12 text-orange-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="text-orange-800 font-medium mb-2">증명된 워크플로를 아이콘으로</p>
            <p className="text-orange-700 text-sm">
              자주 쓰는 IBL 호출은 <strong>계기(instrument)</strong>로 결정화되어, AI 호출 없이
              <strong> GUI로 직접</strong> 조작됩니다. 각 계기는 액션 정의 안의 <code>app:</code> 선언 하나로
              데스크탑·원격·폰 <strong>전 표면에 동시에</strong> 등장합니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">📦 현재 계기 (24종)</p>
            <div className="grid grid-cols-3 gap-1 text-sm text-center">
              {['부동산', '상가', '길찾기', '날씨', '맛집', '여행', '도서검색', '고전', '공연·전시',
                '투자', '라디오', 'YT음악', '신문', '리포트', '달력', '사진', '메신저', '커뮤니티',
                '비즈니스', '창업', '공모전', 'CCTV', '시스템(PC)', '파일'].map((m, i) => (
                <div key={i} className="bg-orange-50 text-orange-700 p-1 rounded">{m}</div>
              ))}
            </div>
          </div>

          <div className="bg-green-50 p-3 rounded-lg text-green-700 text-sm">
            💡 예: <strong>부동산</strong> 계기에서 지역·전세/월세를 고르면 국토부 실거래가와 직방 현재 매물이
            지도 위에 뜹니다 — 대화 한 줄 없이, 0토큰으로.
          </div>

          <div className="bg-amber-50 p-3 rounded-lg text-amber-700 text-sm">
            자율주행에서 반복적으로 쓰던 일이 어느새 계기가 되어 있는 것 — 그게 "핏"이 굳는 방식입니다.
          </div>
        </div>
      )
    },

    // 8. 메모리 — 7종
    {
      title: '메모리 — 7종',
      icon: <Database className="w-12 h-12 text-blue-600" />,
      content: (
        <div className="space-y-4 text-base">
          <p className="text-gray-700 text-sm">
            메모리는 곧 <strong>속도·비용 최적화 장치이자 개인화의 엔진</strong>입니다.
            인간 기억 분류에 대응하는 7종이 있습니다.
          </p>

          <div className="bg-white border rounded-lg overflow-hidden text-sm">
            <table className="w-full">
              <thead className="bg-gray-100 text-gray-800">
                <tr><th className="p-2 text-left">인간 기억</th><th className="p-2 text-left">IndieBiz OS</th></tr>
              </thead>
              <tbody className="text-gray-700">
                {[
                  ['의미 (정적 지식)', '시스템 문서'],
                  ['작업 (단기)', '대화 이력'],
                  ['일화 (경험)', '에피소드 로그'],
                  ['절차 (방법)', 'IBL 액션 + 해마 (자연어→IBL 자기학습)'],
                  ['관계 (사용자 사실)', '심층메모리 (선호·결정·중요날짜 자동 흡수)'],
                  ['자기상태 (항상성)', 'World Pulse + Self-Check'],
                  ['공간 (포식)', '포식 기억 (냄새지도 — 어디에 무엇이 사는가)'],
                ].map(([h, v], i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2">{h}</td>
                    <td className="p-2 font-medium">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Sparkles className="w-6 h-6 text-blue-600" />
              <strong className="text-blue-800">핵심은 사실이 아니라 직관(감)</strong>
            </div>
            <p className="text-blue-700 text-sm">
              요리사의 손이 소금에서 알아서 멈추듯, <strong>해마 점수</strong>(과거에 해본 일인가)가
              인지 라우팅을 가릅니다. 두 자기학습 루프(해마 증류 / 심층메모리 증류)가
              <strong> 쓸수록</strong> 시스템을 빠르고 개인적으로 만듭니다 — 이게 핏이 쌓이는 방식입니다.
            </p>
          </div>
        </div>
      )
    },

    // 9. 포식 브라우저
    {
      title: '포식 브라우저',
      icon: <Search className="w-12 h-12 text-teal-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-teal-50 p-4 rounded-lg">
            <p className="text-teal-800 font-medium mb-2">철학이 기능 하나로 응축된 곳</p>
            <p className="text-teal-700 text-sm">
              구글 검색창처럼 보이지만 작동이 다릅니다. 정답 하나를 주는 대신,
              <strong> 판(board)</strong>을 채워 시야를 넓힙니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <div className="space-y-2 text-sm">
              {[
                '판의 크기 N을 정한다 (예: 10).',
                '키워드에 대해 AI가 정답 하나가 아니라 후보 N개를 판에 올린다.',
                '마음에 안 드는 것을 지운다. 들어가 보기도 한다.',
                'AI는 지운 수만큼 새 후보로 채운다 — 남은 것에서 취향을 읽어.',
                '반복하는 가운데 판의 분위기가 바뀌고, 새로운 것을 발견한다.',
              ].map((t, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div className="bg-teal-100 text-teal-700 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0">{i + 1}</div>
                  <p className="text-gray-800">{t}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-purple-50 p-3 rounded-lg">
              <strong className="text-purple-800">📋 판 도서관</strong>
              <p className="text-purple-700">마음에 든 판을 통째로 저장해 나중에 돌아옵니다.</p>
            </div>
            <div className="bg-green-50 p-3 rounded-lg">
              <strong className="text-green-800">🔒 개인화</strong>
              <p className="text-green-700">내 PC의 파일·사실을 참고해 후보를 개인화 — 구글이 못 하는 일.</p>
            </div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            정답 AI가 가능성을 줄인다면, 이 브라우저는 <strong>빈칸을 채워야 하므로</strong> 계속 가능성을 늘립니다.
          </div>
        </div>
      )
    },

    // 10. AI 프로바이더 설정
    {
      title: 'AI 프로바이더 설정',
      icon: <Key className="w-12 h-12 text-red-500" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-red-50 p-2 rounded-lg border border-red-200">
            <p className="text-red-700 font-medium text-center">
              ⚠️ API 키(또는 로컬 모델) 없이는 AI를 사용할 수 없습니다
            </p>
          </div>

          <div className="bg-white border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-100">
                <tr><th className="p-3 text-left text-gray-900 font-bold">프로바이더</th><th className="p-3 text-left text-gray-900 font-bold">발급처</th></tr>
              </thead>
              <tbody className="text-gray-900">
                {[
                  ['Google Gemini (추천 · 무료 등급)', 'aistudio.google.com'],
                  ['Anthropic Claude', 'console.anthropic.com'],
                  ['OpenAI GPT', 'platform.openai.com'],
                  ['Ollama (로컬)', 'API 키 불필요'],
                ].map(([p, s], i) => (
                  <tr key={i} className="border-t">
                    <td className="p-3">{p}</td>
                    <td className="p-3 text-blue-700">{s}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-amber-50 p-4 rounded-lg">
            <p className="text-amber-800 font-medium mb-2">📍 설정 방법</p>
            <div className="text-sm text-amber-700 space-y-1">
              <p>1. 런처 상단 <strong>로고(안경) 메뉴</strong> → <strong>설정</strong></p>
              <p>2. <strong>AI 프로바이더</strong> 탭에서 프로바이더 선택 → API 키 입력</p>
              <p>3. 사용할 모델 선택 (프로바이더가 제공하는 <strong>최신 모델</strong>을 고르면 됩니다)</p>
              <p>4. 프로젝트 에이전트는 <strong>프로젝트 설정</strong>에서 별도 지정 가능</p>
            </div>
          </div>

          <div className="bg-cyan-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Gauge className="w-6 h-6 text-cyan-600" />
              <strong className="text-cyan-800">모델 기어 — 티어별로 나눠 쓰기</strong>
            </div>
            <p className="text-cyan-700 text-sm">
              분류·평가 같은 가벼운 판단은 <strong>경량 모델</strong>이, 복잡한 계획은 <strong>본격 모델</strong>이
              맡도록 자동 배분됩니다. 경량 모델 키가 비어 있으면 시스템 AI 키를 자동으로 씁니다.
            </p>
          </div>

          <div className="bg-green-50 p-3 rounded-lg text-sm text-green-700">
            🔌 <strong>도구도 API가 필요할 수 있습니다</strong> — 뉴스·주식·날씨·지도 등.
            시스템 AI에게 "이 키를 <strong>환경변수로</strong> 저장해줘"라고 하면 안전하게 설정합니다.
          </div>
        </div>
      )
    },

    // 11. 도구 패키지
    {
      title: '도구 패키지',
      icon: <Package className="w-12 h-12 text-green-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-green-50 p-4 rounded-lg">
            <p className="text-green-800 font-medium mb-2">IBL 노드의 실제 구현체</p>
            <p className="text-green-700 text-sm">
              6개 노드 141개 액션의 실제 능력은 <strong>도구 패키지</strong>(폴더 기반 동적 로딩)에서 옵니다.
              현재 <strong>36개</strong>가 설치되어 있고, 설치/철거가 <strong>코드와 어휘를 원자적으로</strong> 넣고 뺍니다.
            </p>
          </div>

          <div className="bg-white border rounded-lg p-3">
            <p className="font-medium text-gray-700 mb-2">🔧 직접 만들고 수리하기</p>
            <div className="text-sm text-gray-800 space-y-2">
              <p>• 시스템 AI에게 <strong>"○○ 도구 패키지 만들어줘"</strong> — 정의와 실행 로직을 생성</p>
              <p>• 작동하지 않으면 <strong>"왜 안 되는지 알려줘 / 고쳐줘"</strong> — 도구는 Python이라 수리 가능</p>
              <p>• 자신이 쓸 도구를 직접 만들고 고칠 수 있다는 건 <strong>AI 시대의 특징</strong>입니다</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-purple-50 p-3 rounded-lg">
              <strong className="text-purple-800">🌐 공유 (Nostr)</strong>
              <p className="text-purple-700">
                내 패키지를 <strong>#indiebizOS-package</strong> 해시태그로 게시.
                프로그램이 아닌 <strong>설명·구조·의존성</strong>만 공유합니다.
              </p>
            </div>
            <div className="bg-blue-50 p-3 rounded-lg">
              <strong className="text-blue-800">🔍 검색·설치</strong>
              <p className="text-blue-700">
                Nostr에 공개된 패키지를 검색 → 시스템 AI가 보안·호환성 검토 후 설치.
              </p>
            </div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            📦 로고(안경) 메뉴 → <strong>도구 상점</strong>에서 설치/제거/검색/공개
          </div>
        </div>
      )
    },

    // 12. 소통 & 자동 비즈니스
    {
      title: '소통 & 자동 비즈니스',
      icon: <Mail className="w-12 h-12 text-pink-600" />,
      content: (
        <div className="space-y-4 text-base max-h-[440px] overflow-y-auto pr-1">
          <div className="bg-pink-50 p-4 rounded-lg">
            <p className="text-pink-800 font-medium mb-2">AI가 사람을 잇는 미디어</p>
            <p className="text-pink-700 text-sm">
              <strong>Gmail</strong> · <strong>Nostr</strong>(NIP-17 암호화 DM) · 탈중앙 망 <strong>IndieNet</strong>으로
              AI와, 이웃과, 에이전트끼리 소통합니다. 이 채널들은 앱 모드의
              <strong> 메신저 · 커뮤니티 · 비즈니스 계기</strong>로 다뤄집니다.
            </p>
          </div>

          <div className="bg-blue-100 p-4 rounded-lg border-2 border-blue-300">
            <div className="flex items-center gap-2 mb-1">
              <Smartphone className="w-6 h-6 text-blue-700" />
              <strong className="text-blue-800">🎯 원격 명령 (사용자 → 에이전트)</strong>
            </div>
            <div className="text-sm text-blue-700 space-y-1">
              <p>• <strong>등록된 내 연락처</strong>에서 오는 메시지는 명령으로 인식</p>
              <p>• 외출 중에도 Gmail/Nostr 앱으로 PC의 에이전트에게 지시</p>
              <p className="bg-white p-2 rounded mt-1 text-blue-600">예: "오늘 뉴스 정리해서 이메일로 보내줘" → 실행 후 결과 회신</p>
            </div>
          </div>

          <div className="bg-green-100 p-4 rounded-lg border-2 border-green-300">
            <div className="flex items-center gap-2 mb-1">
              <Bot className="w-6 h-6 text-green-700" />
              <strong className="text-green-800">🤖 자동응답 (외부인 → 에이전트)</strong>
            </div>
            <div className="text-sm text-green-700 space-y-1">
              <p>• 사용자가 아닌 외부인의 메시지는 자동응답 또는 기록 (명령은 실행 안 함)</p>
              <p>• AI가 <strong>비즈니스 문서·근무지침</strong>을 참조해 응대</p>
              <p>• 모든 수신 메시지는 저장되어 나중에 확인 가능</p>
              <p className="bg-white p-2 rounded mt-1 text-green-600"><strong>💼 자동 비즈니스의 핵심</strong> — 고객 문의·예약·상담을 24시간 자동 처리</p>
            </div>
          </div>

          <div className="bg-orange-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Users className="w-6 h-6 text-orange-600" />
              <strong className="text-orange-800">🏪 비즈니스 계기</strong>
            </div>
            <div className="text-sm text-orange-700 space-y-1">
              <p>• 내 비즈니스와 아이템을 정의하고, 이웃(연락처)마다 <strong>정보 레벨</strong>을 부여</p>
              <p>• 레벨별 <strong>공개 문서</strong>를 자동 생성 → 자동응답이 이를 참조</p>
              <p>• 예전의 "비즈니스 관리창 · 이웃 관리창 · 빠른 연락처"는 이제 앱 모드의 계기로 통합되었습니다</p>
            </div>
          </div>

          <div className="bg-cyan-50 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-1">
              <Globe className="w-6 h-6 text-cyan-600" />
              <strong className="text-cyan-800">🌐 IndieNet (탈중앙 커뮤니티)</strong>
            </div>
            <div className="text-sm text-cyan-700 space-y-1">
              <p>• Nostr 기반 <strong>P2P 네트워크</strong> — 중앙 서버 없이 신원(npub)만으로 참여</p>
              <p>• 공개 피드 · 해시태그 게시판(반공개) · 암호화 DM</p>
              <p>• 접속: 앱 모드 → <strong>커뮤니티</strong> 계기, DM은 <strong>메신저</strong> 계기</p>
            </div>
          </div>
        </div>
      )
    },

    // 13. 두 자아 (맥 & 폰)
    {
      title: '두 자아 (맥 & 폰)',
      icon: <Smartphone className="w-12 h-12 text-sky-600" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-sky-50 p-4 rounded-lg">
            <p className="text-sky-800 font-medium mb-2">맥과 폰, 각각 독립된 자아</p>
            <p className="text-sky-700 text-sm">
              IndieBiz OS는 PC(맥)뿐 아니라 <strong>폰에서도 온디바이스 두뇌로</strong> 돕니다.
              둘은 각각 독립된 자아 — 케이블 없이도 폰 스스로 감각하고 판단합니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-green-50 p-3 rounded-lg">
              <strong className="text-green-800">🔄 공유되는 것</strong>
              <p className="text-green-700">
                세계-데이터(연락처·일정·비즈니스)는 <strong>CRDT로 동기화</strong> — 어느 자아에서 고쳐도 합쳐집니다.
              </p>
            </div>
            <div className="bg-purple-50 p-3 rounded-lg">
              <strong className="text-purple-800">🔒 사적인 것</strong>
              <p className="text-purple-700">
                각 자아의 <strong>주관적 기억</strong>(대화·해마)은 사적입니다 — 몸마다 다른 경험이 쌓입니다.
              </p>
            </div>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="font-medium text-blue-800 mb-2">📱 폰만의 온디맨드 감각</p>
            <div className="text-sm text-blue-700 space-y-1">
              <p>• <strong>위치</strong>(here) · <strong>마이크 받아쓰기/녹음</strong>(listen) · <strong>카메라 촬영</strong>(see)</p>
              <p>• 상시 수집이 아니라 <strong>필요할 때만</strong> — 프라이버시 우선</p>
              <p>• 폰이 자기 하드웨어(알림·진동·클립보드 등)를 직접 만질 수 있습니다</p>
            </div>
          </div>

          <div className="bg-amber-50 p-2 rounded-lg text-amber-700 text-sm">
            💡 어느 자아가 지금 깨어 있는지는 <strong>조종실의 프레즌스</strong>에서 확인합니다.
          </div>
        </div>
      )
    },

    // 14. 원격 접근
    {
      title: '원격 접근',
      icon: <Monitor className="w-12 h-12 text-lime-600" />,
      content: (
        <div className="space-y-4 text-base max-h-[440px] overflow-y-auto pr-1">
          <div className="bg-lime-50 p-4 rounded-lg">
            <p className="text-lime-800 font-medium mb-2">집 PC를 어디서든 접근하는 개인 서버로</p>
            <p className="text-lime-700 text-sm">
              <strong>Cloudflare Tunnel</strong>로 포트 포워딩·DDNS 없이 HTTPS 보호된 외부 접근이 가능합니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-cyan-50 p-4 rounded-lg border border-cyan-200">
              <div className="flex items-center gap-2 mb-1">
                <Folder className="w-6 h-6 text-cyan-600" />
                <strong className="text-cyan-800">📁 원격 Finder</strong>
              </div>
              <p className="text-cyan-700 text-sm">파일 탐색 · 동영상 스트리밍 · 다운로드</p>
            </div>
            <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
              <div className="flex items-center gap-2 mb-1">
                <Bot className="w-6 h-6 text-purple-600" />
                <strong className="text-purple-800">🤖 원격 런처</strong>
              </div>
              <p className="text-purple-700 text-sm">3표면을 웹으로 — AI 채팅 · 앱 계기 · 스위치 실행</p>
            </div>
          </div>

          <div className="bg-orange-50 p-4 rounded-lg">
            <p className="font-medium text-orange-800 mb-2">📋 설정 순서</p>
            <div className="text-sm text-orange-700 space-y-1">
              <p>1. <strong>dash.cloudflare.com</strong>에서 무료 가입 + 도메인 연결</p>
              <p>2. <strong>API 토큰</strong>과 <strong>Account ID</strong> 발급</p>
              <p>3. 시스템 AI에게 "cloudflare 환경변수를 설정해줘" (토큰·ID 전달)</p>
              <p>4. 재시작 후 "원격 접근 터널을 설정해줘" — 도메인은 AI가 자동 조회</p>
              <p>5. 설정 → 원격 Finder/런처 탭에서 활성화 + <strong>비밀번호</strong> 설정</p>
            </div>
          </div>

          <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-700">
            📖 자세한 절차: <strong>data/system_docs/remote_access.md</strong> ·
            시스템 AI에게 "원격 접근 문서 보여줘"
          </div>

          <div className="bg-red-50 p-2 rounded-lg text-red-700 text-sm">
            ⚠️ 원격은 <strong>웹 브라우저</strong>에서 도는 경량 리모컨입니다 — 무거운 작업은 집 PC(맥 자아)가 수행합니다.
            외부 노출되니 <strong>복잡한 비밀번호</strong>를 쓰고 민감한 폴더는 제외하세요.
          </div>
        </div>
      )
    },

    // 15. 버전 정보
    {
      title: '버전 정보',
      icon: <FileText className="w-12 h-12 text-gray-800" />,
      content: (
        <div className="space-y-4 text-base">
          <div className="bg-gray-50 p-4 rounded-lg">
            <h3 className="font-bold text-lg text-gray-800 mb-3">IndieBiz OS — 현재 상태</h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">IBL 노드</p>
                <p className="text-xl font-bold text-purple-600">6개</p>
              </div>
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">IBL 액션</p>
                <p className="text-xl font-bold text-indigo-600">141개</p>
              </div>
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">도구 패키지</p>
                <p className="text-xl font-bold text-green-600">36개</p>
              </div>
              <div className="bg-white p-2 rounded">
                <p className="text-gray-700">앱 계기</p>
                <p className="text-xl font-bold text-orange-600">24종</p>
              </div>
            </div>
          </div>

          <div className="bg-amber-50 p-4 rounded-lg">
            <p className="text-amber-800 font-medium mb-2">철학</p>
            <p className="text-amber-700 text-sm italic">
              "도구는 인간의 시야를 가리기보다 넓혀야 한다."
            </p>
            <p className="text-amber-600 text-sm mt-2">
              IndieBiz OS는 모두가 같은 방식으로 쓰는 제품이 아니라,
              당신의 고유한 필요에 맞게 적응하는 <strong>기반</strong>입니다.
            </p>
          </div>

          <div className="bg-blue-50 p-4 rounded-lg">
            <p className="text-blue-800 font-medium mb-1">📚 더 자세한 내용</p>
            <p className="text-blue-700 text-sm">
              상세 문서는 <strong>data/system_docs/</strong>에 있습니다.
              (해부도 <code>anatomy.md</code>가 전체 지도, 그 아래로 비전·아키텍처·IBL·메모리 문서로 이어집니다.)
              시스템 AI에게 <strong>"시스템 문서 보여줘"</strong>라고 요청하세요.
            </p>
          </div>

          <div className="text-center text-gray-700 text-sm">
            <p>MIT License</p>
            <p className="mt-1"><strong>IndieBiz OS</strong> — 인지 외골격</p>
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
