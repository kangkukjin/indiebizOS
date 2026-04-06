# IndieBiz OS 인벤토리

## 프로젝트 (활성) - 20개 (에이전트 29개)

| ID | 이름 | 설명 |
|----|------|------|
| CCTV | CCTV | CCTV/웹캠 관리 |
| Hand on PC | Hand on PC | PC 원격 제어 |
| study | study | 학습 및 연구 프로젝트 |
| 건축 | 건축 | 건축 설계 |
| 구매 | 구매 | 상품 검색 및 구매 지원 |
| 법률 | 법률 | 법률 정보 및 법령 검색 |
| 부동산 | 부동산 | 건물 관리 및 부동산 투자 정보 분석 |
| 사진 | 사진 | 사진 관리 및 아카이빙 |
| 오락실 | 오락실 | 게임/엔터테인먼트 |
| 음악 | 음악 | 음악 작곡/관리 |
| 의료 | 의료 | 건강 정보 관리 및 병원/약국 행정 안내 |
| 정보센터 | 정보센터 | 정보 수집/분석 프로젝트 |
| 지역정보 | 지역정보 | 지역 정보 조회 |
| 창업 | 창업 | 새로운 비즈니스 모델 연구 및 창업 지원 |
| 추천 프로젝트 | 추천 프로젝트 | 추천 시스템 프로젝트 |
| 컨텐츠 | 컨텐츠 | 콘텐츠 제작 및 관리 |
| 투자 | 투자 | 주식 및 금융 데이터 분석, 글로벌 시장 조사 |
| 하드웨어 | 하드웨어 | 하드웨어 관리 프로젝트 |
| 학교 | 학교 | 학교 관련 프로젝트 |
| 행정_서비스 | 행정_서비스 | 정부24 및 민원 서비스 지원 |
| 홍보 | 홍보 | 홍보/마케팅 콘텐츠 제작 |

---

## 도구 패키지 (Tools) - 36개
에이전트가 사용할 수 있는 유틸리티. handler 라우팅(복잡 후처리) 또는 api_engine 라우팅(API+transform 자동 발견)으로 실행됩니다.

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | ADB를 통한 안드로이드 기기 관리 (SMS, 통화기록, 연락처, 앱) |
| blog | Blog | 블로그 RAG 검색 및 인사이트 분석 |
| browser-action | Browser Action | Playwright 기반 브라우저 자동화 v5.0 (클릭/입력/스크롤/콘텐츠 추출, 동적 콘텐츠 대기, 다단계 폴백, CDP 타임아웃) |
| business | Business | 비즈니스 관계 및 연락처(이웃) 관리 |
| cctv | CCTV | CCTV/웹캠 관련 도구 |
| cloudflare | Cloudflare | Cloudflare 서비스 통합 (Pages, Workers, R2, D1, Tunnel) |
| computer-use | Computer Use | 컴퓨터 사용 자동화 |
| context7 | Context7 | Context7 라이브러리 문서 검색 |
| culture | Culture | 공연(KOPIS), 도서(도서관 정보나루), Project Gutenberg 고전 원문, 한국고전종합DB 등 문화예술 정보 조회 |
| health-record | Health Record Manager | 건강 정보 기록/관리 (혈압, 혈당, 체중, 증상, 투약) |
| house-designer | House Designer | 건축 설계 (평면도, 3D뷰) |
| ibl-core | IBL Core | IBL 핵심 도구 |
| investment | Investment | 한국/미국 주가, 재무제표, 공시, 뉴스, 암호화폐 분석 |
| kosis | KOSIS | 통계청 KOSIS API 국가통계 조회 |
| legal | Legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙, 자치법규 등) |
| local-info | Local Info | 지역 정보 도구 |
| location-services | Location Services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보) |
| media_producer | Media Producer | 홍보용 슬라이드, HTML 기반 MP4 동영상, AI 이미지 생성 |
| memory | Memory | 대화 이력, 심층 메모리 관리 |
| music-composer | Music Composer | ABC 악보 기반 작곡, MIDI 생성, 오디오 변환 |
| nodejs | Nodejs | Node.js/JavaScript 코드 실행 |
| pc-manager | PC Manager | PC 파일 탐색, 외장하드 관리, 저장소 스캔 |
| photo-manager | Photo Manager | 사진/동영상 메타데이터 수집, 갤러리, 중복 탐지 |
| python-exec | Python Exec | Python 코드 실행 |
| radio | Radio | 인터넷 라디오 검색 및 재생 (Radio Browser API + 한국 방송사 직접 스트리밍) |
| real-estate | Real Estate | 국토교통부 부동산 실거래가 API |
| remotion-video | Remotion Video | React/Remotion 기반 프로그래밍 방식 동영상 생성 (TSX → MP4) |
| shopping-assistant | Shopping Assistant | 네이버 쇼핑, 다나와 가격 비교 |
| startup | Startup | 창업지원 사업공고 검색 (K-Startup, 중소벤처기업부) |
| study | Study Helper | 학술 논문 검색/다운로드 (OpenAlex, arXiv, Semantic Scholar 등) |
| system_essentials | System Essentials | 파일 읽기/쓰기/검색, PDF 읽기, todo, 계획 모드, 이웃 조회 |
| visualization | Visualization | 범용 데이터 시각화 (차트/그래프 PNG/HTML) |
| web | Web Tools | 웹 검색, 크롤링, 뉴스, 신문 생성, 즐겨찾기 |
| web-builder | Web Builder | 홈페이지 제작/관리/배포 통합 도구 |
| web-collector | Web Collector | 웹 데이터 수집/스크래핑 |
| youtube | Youtube | YouTube 영상 정보, 자막 추출, 다운로드 |

---

## 백엔드 코어 모듈 (extensions/) - 9개
에이전트가 호출하는 도구가 아니라 백엔드 시스템 내부에서 사용되는 코어 모듈입니다.

| ID | 설명 |
|----|------|
| ai-agent | AI 에이전트 실행 |
| conversation | 대화 DB 관리 |
| gmail | Gmail 연동 |
| indienet | 외부 메신저 연동 (Nostr 기반) |
| notification-system | 알림 시스템 |
| prompt-generator | 프롬프트 생성기 |
| scheduler | 스케줄러 |
| switch-runner | 스위치 실행기 |
| websocket-chat | WebSocket 채팅 |

---

> 위임 시스템은 `delegation.md`, 통신/자동응답은 `communication.md`, 패키지 상세는 `packages.md` 참조.

---
*마지막 업데이트: 2026-04-05 (중복 섹션 제거, 자동생성 목록만 유지)*
