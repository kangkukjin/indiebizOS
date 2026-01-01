# IndieBiz OS 기술 문서

## API 엔드포인트

### 프로젝트
- GET /projects - 프로젝트 목록
- POST /projects - 프로젝트 생성
- GET /projects/{id} - 프로젝트 조회
- PUT /projects/{id} - 프로젝트 수정
- DELETE /projects/{id} - 프로젝트 삭제

### 템플릿
- GET /templates - 템플릿 목록
- POST /templates - 템플릿 생성
- POST /projects/from-template - 템플릿에서 프로젝트 생성

### 에이전트
- GET /projects/{id}/agents - 에이전트 목록
- POST /projects/{id}/agents - 에이전트 생성
- PUT /projects/{id}/agents/{agent_id} - 에이전트 수정
- DELETE /projects/{id}/agents/{agent_id} - 에이전트 삭제

### 시스템 AI
- POST /system-ai/chat - 시스템 AI와 대화
- GET /system-ai/status - 상태 확인
- GET /system-ai/conversations - 대화 이력

### IndieNet
- POST /indienet/generate - ID 생성
- GET /indienet/profile - 프로필 조회
- POST /indienet/post - 포스트 작성

### 패키지 관리
- GET /packages - 전체 패키지 목록
- GET /packages/available - 설치 가능 목록
- GET /packages/installed - 설치됨 목록
- GET /packages/{id} - 패키지 상세 정보
- POST /packages/{id}/install - 패키지 설치
- POST /packages/{id}/uninstall - 패키지 제거
- POST /packages/analyze-folder - 폴더 분석 (등록 전)
- POST /packages/register - 외부 폴더를 패키지로 등록
- DELETE /packages/{id}/remove - 패키지 삭제

## 설정 파일 위치
- 시스템 AI 설정: data/system_ai_config.json
- 사용자 프로필: data/my_profile.txt
- IndieNet 설정: data/indienet_config.json
- 패키지 레지스트리: data/packages/registry.json
- 프로젝트 목록: projects/projects.json
- 스위치 목록: data/switches.json

## 지원 AI 프로바이더
- Anthropic Claude (claude-sonnet-4, claude-3.5-sonnet, claude-3.5-haiku)
- OpenAI GPT (gpt-4o, gpt-4o-mini, gpt-4-turbo)
- Google Gemini (gemini-2.0-flash, gemini-1.5-pro, gemini-1.5-flash, gemini-3-flash-preview)

## 기술 스택

### 백엔드
- Python 3.x
- FastAPI
- SQLite (시스템 AI 메모리)
- 포트: 8765

### 프론트엔드
- React 18
- TypeScript
- Vite (개발 서버 포트: 5173)
- TailwindCSS
- Zustand (상태 관리)

### 데스크톱
- Electron
- IPC (프로세스 간 통신)

## Electron IPC API
```javascript
window.electron = {
  getApiPort()                    // API 포트 조회
  openExternal(url)               // 외부 URL 열기
  getAppInfo()                    // 앱 정보
  openProjectWindow(id, name)     // 프로젝트 창 열기
  openFolderWindow(id, name)      // 폴더 창 열기
  openIndieNetWindow()            // IndieNet 창 열기
  selectFolder()                  // 네이티브 폴더 선택 다이얼로그
  platform                        // 플랫폼 정보 (darwin/win32/linux)
}
```

---
*마지막 업데이트: 2025-12-31 10:30*
