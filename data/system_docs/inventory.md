# IndieBiz OS 인벤토리

## 프로젝트 (활성) - 15개

| ID | 이름 | 설명 |
|----|------|------|
| study | study | 학습 및 연구 프로젝트 |
| 구매 | 구매 | 상품 검색 및 구매 지원 |
| 부동산 | 부동산 | 건물 관리 및 부동산 투자 정보 분석 |
| 사진 | 사진 | 사진 관리 및 아카이빙 |
| 오락실 | 오락실 | 게임/엔터테인먼트 |
| 의료 | 의료 | 건강 정보 관리 및 병원/약국 행정 안내 |
| 정보센터 | 정보센터 | 정보 수집/분석 프로젝트 |
| 창업 | 창업 | 새로운 비즈니스 모델 연구 및 창업 지원 |
| 추천 프로젝트 | 추천 프로젝트 | 추천 시스템 프로젝트 |
| 컨텐츠 | 컨텐츠 | 콘텐츠 제작 및 관리 |
| 투자 | 투자 | 주식 및 금융 데이터 분석, 글로벌 시장 조사 |
| 하드웨어 | 하드웨어 | 하드웨어 관리 프로젝트 |
| 해외 | 해외 | 한류 소식 및 해외 비즈니스 정보 수집 |
| 행정_서비스 | 행정_서비스 | 정부24 및 민원 서비스 지원 |
| 홍보 | 홍보 | 홍보/마케팅 콘텐츠 제작 |

---

## 도구 패키지 (Tools) - 21개
에이전트가 사용할 수 있는 유틸리티

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | 안드로이드 기기 관리 (adb) |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 |
| culture | Culture | KCISA 문화정보(전시, 축제) 조회 |
| health-record | Health Record Manager | 개인 건강 정보 저장/관리 |
| information | Information & Publishing | API Ninjas, 맛집 검색 등 |
| investment | Investment | KRX, DART, SEC 글로벌 금융 데이터 분석 |
| kosis | KOSIS | 통계청 데이터 조회 |
| media_producer | Media Producer | HTML 기반 슬라이드(12종 테마), 영상 제작, AI 이미지 생성 |
| nodejs | Nodejs | JavaScript/Node.js 코드 실행 |
| pc-manager | PC Manager | 파일 및 저장소 관리, 시스템 분석 |
| photo-manager | Photo Manager | 사진 라이브러리 관리 |
| python-exec | Python Exec | Python 코드 실행 |
| read-and-see | Read and See | 문서 읽기 및 시각적 분석 |
| real-estate | Real Estate | 부동산 실거래가 조회 |
| shopping-assistant | Shopping Assistant | 상품 검색 (네이버 쇼핑, 다나와) |
| startup | Startup | 창업 지원 정보 |
| study | Study Helper | 학습 및 논문 요약 지원 |
| system_essentials | System Essentials | 파일 관리, 시스템 유틸리티, 이웃 조회 |
| visualization | Visualization | 라인/막대/캔들스틱/파이/산점도/히트맵 차트 |
| web | Web Tools | 웹 검색 및 크롤링 |
| youtube | Youtube | 유튜브 동영상/오디오 관리 |

---

## 시스템 AI 위임 기능

시스템 AI는 프로젝트의 전문 에이전트에게 작업을 위임할 수 있습니다.

### 위임 도구
| 도구 | 설명 |
|------|------|
| `list_project_agents` | 모든 프로젝트와 에이전트 목록 조회 |
| `call_project_agent` | 프로젝트 에이전트에게 작업 위임 |

### 위임 조건
- **사용자가 명시적으로 요청한 경우에만** 위임
- "의료팀에게 물어봐" → 위임 O
- "두통이 있어" → 직접 답변 (위임 X)

### 위임 흐름
```
사용자 요청 → 시스템 AI 판단 → call_project_agent 호출
    → 프로젝트 에이전트들 자동 활성화 → 작업 수행
    → 결과 자동 보고 → 시스템 AI가 사용자에게 전달
```

### 병렬 위임
여러 프로젝트에 동시 위임 가능:
```python
call_project_agent("의료", "agent_001", "두통 증상 분석")
call_project_agent("study", "agent_001", "두통 관련 최신 연구 검색")
```

---

## 다중채팅방 시스템
여러 에이전트와 사용자가 함께 대화하는 그룹 채팅

### 주요 기능
- 채팅방 생성/삭제/아이콘 정렬
- 프로젝트 에이전트 소환 (원본 AI 설정 유지)
- @지목 또는 랜덤 응답
- 전체 시작/중단 버튼
- 도구 할당 기능
- 별도 창에서 운영 (창 닫으면 에이전트 비활성화)

---

## 비즈니스 관리 시스템

### 통신 채널
| 채널 | 방식 | 설명 |
|------|------|------|
| Gmail | 폴링 | 주기적으로 이메일 수신 |
| Nostr | WebSocket | 실시간 DM 수신 |

### 자동응답 V3 (Tool Use 통합)
AI 호출 1회로 판단, 검색, 발송을 한 번에 처리:
- `search_business_items`: 비즈니스 DB 검색
- `no_response_needed`: 응답 불필요 처리 (스팸/광고)
- `send_response`: 응답 즉시 발송

---

## 휴지통
런처에서 삭제한 프로젝트, 폴더, 스위치는 휴지통으로 이동합니다.

---

## 템플릿
- **기본** - 빈 프로젝트 템플릿
- **프로젝트1** - 에이전트 팀 템플릿 (집사, 직원1, 대장장이, 출판, 영상담당)

---

## 도구 상자 & 패키지 공유 (Nostr)
자신이 만든 도구 패키지를 Nostr 네트워크를 통해 공유하고, 다른 사용자의 패키지를 검색/설치할 수 있습니다.

### 주요 기능
- **패키지 공개**: AI가 패키지 전체를 분석하여 설치 방법 자동 생성
- **패키지 검색**: Nostr 네트워크에서 공개된 패키지 검색
- **설치 전 검토**: 시스템 AI가 보안/품질/호환성 검토

자세한 내용은 `packages.md` 참조.

---
*마지막 업데이트: 2026-01-26*
