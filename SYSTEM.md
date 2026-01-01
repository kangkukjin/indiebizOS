# IndieBiz OS - 시스템 문서

**버전:** 0.1.0
**최종 업데이트:** 2025-12-31

## 개요

IndieBiz OS는 AI 에이전트 플랫폼으로, 사용자가 다양한 도구를 통해 AI 에이전트를 활용할 수 있는 데스크톱 애플리케이션입니다.

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron Desktop App                      │
├─────────────────────────────────────────────────────────────┤
│  Frontend (React + TypeScript + Vite)                       │
│  - 런처 UI (Launcher)                                        │
│  - 프로젝트 관리 (Manager)                                    │
│  - 채팅 인터페이스 (Chat)                                     │
│  - 폴더 뷰 (FolderView)                                      │
│  - IndieNet (P2P 커뮤니티)                                   │
├─────────────────────────────────────────────────────────────┤
│  Backend (Python FastAPI)                                    │
│  - REST API (포트 8765)                                      │
│  - 프로젝트/스위치 관리                                        │
│  - 패키지 시스템                                              │
│  - AI 에이전트 실행                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 디렉토리 구조

```
indiebizOS/
├── backend/                 # Python 백엔드
│   ├── api.py              # 메인 FastAPI 서버
│   ├── api_*.py            # API 라우터들
│   ├── *_manager.py        # 비즈니스 로직 매니저
│   └── data/               # 백엔드 데이터 (비어있음)
│
├── frontend/               # React 프론트엔드
│   ├── electron/           # Electron 메인/프리로드
│   │   ├── main.js         # Electron 메인 프로세스
│   │   └── preload.js      # IPC 브릿지
│   └── src/
│       ├── components/     # React 컴포넌트
│       ├── lib/            # 유틸리티 (api.ts 등)
│       └── types/          # TypeScript 타입 정의
│
├── data/                   # 런타임 데이터
│   ├── packages/           # 패키지 저장소
│   │   ├── available/      # 설치 가능한 패키지
│   │   │   └── tools/      # 도구 패키지 (17개)
│   │   ├── installed/      # 설치된 패키지
│   │   └── registry.json   # 패키지 메타데이터
│   ├── system_docs/        # 시스템 AI 문서
│   └── system_ai_memory.db # 시스템 AI 메모리
│
├── projects/               # 사용자 프로젝트
│   └── projects.json       # 프로젝트 목록
│
├── templates/              # 프로젝트 템플릿
│   ├── 기본/               # 기본 템플릿
│   └── 프로젝트1/          # 사용자 정의 템플릿
│
├── outputs/                # 출력 파일
├── tokens/                 # API 토큰 저장
└── start.sh                # 시작 스크립트
```

---

## 백엔드 API 구조

### 주요 라우터

| 라우터 | 파일 | 설명 |
|--------|------|------|
| projects | api_projects.py | 프로젝트 CRUD, 템플릿 관리 |
| switches | api_switches.py | 스위치(에이전트 구성) 관리 |
| config | api_config.py | 시스템 설정 |
| system-ai | api_system_ai.py | 시스템 AI 대화 |
| agents | api_agents.py | AI 에이전트 실행 |
| conversations | api_conversations.py | 대화 기록 |
| websocket | api_websocket.py | 실시간 통신 |
| indienet | api_indienet.py | P2P 커뮤니티 |
| packages | api_packages.py | 패키지 설치/관리 |

### 주요 매니저

| 매니저 | 파일 | 역할 |
|--------|------|------|
| ProjectManager | project_manager.py | 프로젝트 생성/관리/템플릿 |
| SwitchManager | switch_manager.py | 스위치 설정 관리 |
| PackageManager | package_manager.py | 패키지 등록/설치/제거 |

---

## 패키지 시스템

### 설계 철학

- **형식 강제 없음**: manifest.yaml 같은 형식 파일 불필요
- **AI 친화적**: 코드와 README만으로 AI가 이해 가능
- **폴더 기반 탐지**: 폴더 존재만으로 패키지 인식

### 도구 패키지 (Tools) - 17개

에이전트가 사용할 수 있는 유틸리티

| ID | 이름 | 설명 |
|----|------|------|
| android | Android | ADB 안드로이드 기기 관리 |
| blog | Blog | 네이버 블로그 검색/분석 |
| browser | Browser | 웹 브라우저 조작 |
| browser-automation | Browser Automation | AI 웹 브라우저 자동화 |
| file-manager | File Manager | 파일 관리 |
| file-ops | File Ops | 파일 읽기/쓰기 |
| file-search | File Search | 파일 검색 |
| image-generation | Image Generation | 이미지 생성 |
| newspaper-magazine | Newspaper Magazine | 뉴스 수집/신문 생성 |
| nodejs | Node.js | Node.js 코드 실행 |
| pc-manager | PC Manager | 로컬 컴퓨터 저장소 분석 |
| python-exec | Python Exec | Python 코드 실행 |
| time | Time | 시간/날짜 유틸리티 |
| web-crawl | Web Crawl | 웹페이지 크롤링 |
| web-request | Web Request | HTTP 요청 |
| web-search | Web Search | DuckDuckGo/Google News 검색 |
| youtube | Youtube | YouTube 동영상 관련 기능 |

### 패키지 관리 API

```
GET  /packages                    # 전체 패키지 목록
GET  /packages/available          # 설치 가능 목록
GET  /packages/installed          # 설치됨 목록
GET  /packages/{id}               # 패키지 상세 정보
POST /packages/{id}/install       # 패키지 설치
POST /packages/{id}/uninstall     # 패키지 제거
POST /packages/analyze-folder     # 폴더 분석 (등록 전)
POST /packages/register           # 외부 폴더를 패키지로 등록
DELETE /packages/{id}/remove      # 패키지 삭제 (available에서)
```

---

## 프론트엔드 구조

### 주요 컴포넌트

| 컴포넌트 | 경로 | 역할 |
|----------|------|------|
| Launcher | /launcher | 메인 런처 화면 |
| Manager | /manager | 프로젝트 관리 |
| Chat | /chat/{id} | 채팅 인터페이스 |
| FolderView | /folder/{id} | 폴더 내용 보기 |
| IndieNet | /indienet | P2P 커뮤니티 |

### Electron IPC API

```javascript
window.electron = {
  getApiPort()              // API 포트 조회
  openExternal(url)         // 외부 URL 열기
  getAppInfo()              // 앱 정보
  openProjectWindow(id, name)   // 프로젝트 창 열기
  openFolderWindow(id, name)    // 폴더 창 열기
  openIndieNetWindow()          // IndieNet 창 열기
  selectFolder()            // 네이티브 폴더 선택 다이얼로그
  // ... 드래그앤드롭 관련 API
}
```

---

## 템플릿 시스템

프로젝트 생성 시 사용할 수 있는 템플릿:

- **기본**: 빈 프로젝트 템플릿
- **프로젝트1**: 사용자 정의 템플릿

템플릿 위치: `templates/{템플릿명}/`

---

## 실행 방법

### 개발 모드

```bash
# 터미널 1: 백엔드
cd backend
python3 api.py

# 터미널 2: 프론트엔드
cd frontend
npm run dev

# 터미널 3: Electron
cd frontend
npm run electron
```

### 시작 스크립트

```bash
./start.sh
```

---

## 기술 스택

### 백엔드
- Python 3.x
- FastAPI
- SQLite (시스템 AI 메모리)

### 프론트엔드
- React 18
- TypeScript
- Vite
- TailwindCSS
- Zustand (상태 관리)

### 데스크톱
- Electron
- IPC (프로세스 간 통신)

---

## 포트 구성

| 서비스 | 포트 | 용도 |
|--------|------|------|
| Backend API | 8765 | FastAPI REST API |
| Frontend Dev | 5173 | Vite 개발 서버 |
