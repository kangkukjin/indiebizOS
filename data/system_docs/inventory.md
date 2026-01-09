# IndieBiz OS 인벤토리

## 프로젝트 (활성) - 11개

| ID | 이름 | 설명 |
|----|------|------|
| 1 | 1 | 메인 프로젝트 |
| 하드웨어 | 하드웨어 | 하드웨어 관리 프로젝트 |
| 정보 | 정보 | 정보 수집/분석 프로젝트 |
| Youtube | Youtube | 유튜브 관련 프로젝트 |
| 나를 지키는 공간 | 나를 지키는 공간 | 개인 공간 |
| 행정_서비스 | 행정_서비스 | 정부24 및 민원 서비스 지원 |
| 자산관리 | 자산관리 | 주식, 채권, ETF 등 자산 관리 및 분석 |
| 의료 | 의료 | 건강 정보 관리 및 병원/약국 행정 안내 |
| 부동산 | 부동산 | 건물 관리 및 부동산 투자 정보 분석 |
| 창업 | 창업 | 새로운 비즈니스 모델 연구 및 창업 지원 |
| 해외 | 해외 | 한류 소식 및 해외 비즈니스 정보 수집 |

---

## 도구 패키지 (Tools) - 11개
에이전트가 사용할 수 있는 유틸리티

| ID | 이름 | 설명 | 상태 |
|----|------|------|------|
| android | Android | 안드로이드 기기 관리 (adb) | 설치됨 |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 | 설치됨 |
| browser-automation | Browser Automation | 웹 브라우저 자동화 (Playwright) | 설치됨 |
| information | Information & Publishing | API Ninjas, 여행 정보, 출판 도구 | 설치됨 |
| nodejs | Nodejs | JavaScript/Node.js 코드 실행 | 설치됨 |
| pc-manager | Pc Manager | 파일 및 저장소 관리 | 설치됨 |
| python-exec | Python Exec | Python 코드 실행 | 설치됨 |
| system_essentials | System Essentials | 파일 관리, 검색, 시스템 유틸리티 | 설치됨 |
| web-crawl | Web Crawl | 웹페이지 크롤링 | 설치됨 |
| web-search | Web Search | 웹 검색 엔진 (DuckDuckGo, Google News) | 설치됨 |
| youtube | Youtube | 유튜브 동영상/오디오 관리 | 설치됨 |

---

## 확장 패키지 (Extensions) - 9개
시스템 기능 확장

| ID | 설명 |
|----|------|
| ai-agent | AI 에이전트 코어 |
| conversation | 대화 관리 |
| gmail | Gmail 연동 |
| indienet | IndieNet (Nostr) 연동 |
| notification-system | 알림 시스템 |
| prompt-generator | 프롬프트 생성기 |
| scheduler | 스케줄러 |
| switch-runner | 스위치 실행기 |
| websocket-chat | WebSocket 채팅 |

---

## 비즈니스 관리 시스템
kvisual-mcp 기반 비즈니스 파트너 관리

### DB 테이블
| 테이블 | 설명 |
|--------|------|
| businesses | 비즈니스 항목 (레벨별) |
| business_items | 비즈니스 세부 항목 |
| neighbors | 이웃 (비즈니스 파트너) |
| contacts | 이웃 연락처 (email, nostr, phone) |
| messages | 수신/발송 메시지 |
| channel_settings | 통신채널 설정 (Gmail, Nostr) |
| my_business_documents | 비즈니스 문서 (레벨별) |
| work_guidelines | 근무지침 (레벨별) |

### 통신 채널
| 채널 | 방식 | 설명 |
|------|------|------|
| Gmail | 폴링 | 주기적으로 이메일 수신 |
| Nostr | WebSocket | 실시간 DM 수신 |

### 자동응답 V2
kvisual-mcp 방식의 2단계 처리:
1. **AI 판단** (ai_judgment.py): 메시지 분류 (NO_RESPONSE / BUSINESS_RESPONSE)
2. **비즈니스 검색**: 카테고리/키워드로 관련 아이템 검색
3. **응답 생성**: 컨텍스트 기반 응답 (근무지침, 비즈니스 문서, 대화 기록, 검색 결과)

---

## 휴지통

런처에서 삭제한 프로젝트, 폴더, 스위치는 휴지통으로 이동합니다.
- 휴지통에서 복구하거나 완전 삭제 가능
- API: `GET /trash`, `POST /trash/{item_id}/restore`, `DELETE /trash`

| 종류 | 항목 수 |
|------|---------|
| 프로젝트 | 0개 |
| 스위치 | 0개 |

---

## 템플릿
- **기본** - 빈 프로젝트 템플릿
- **프로젝트1** - 에이전트 팀 템플릿 (집사, 직원1, 대장장이, 출판, 영상담당)

---
*마지막 업데이트: 2026-01-09*
