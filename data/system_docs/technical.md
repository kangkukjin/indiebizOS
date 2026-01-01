# IndieBiz OS 기술 문서

## API 엔드포인트
(생략: 이전 문서와 동일)

## 설정 파일 위치
- **시스템 AI 설정**: `data/system_ai_config.json`
- **스위치 목록**: `data/switches.json`
- **프로젝트 목록**: `projects/projects.json` (각 프로젝트의 세부 설정은 `projects/{id}/project_config.json`)
- **시스템 AI 메모리**: `data/system_ai_memory.db` (SQLite)

## 지원 AI 프로바이더
- Anthropic Claude (claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022)
- OpenAI GPT (gpt-4o, gpt-4o-mini)
- Google Gemini (gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash)
- Ollama (로컬 실행 모델)

## 기술 스택
- **백엔드**: Python 3.x, FastAPI
- **프론트엔드**: React 18, TypeScript, Vite, TailwindCSS
- **데스크톱**: Electron (IPC를 통한 백엔드 통신)

## 물리적 구조 (주요 경로)
- `backend/`: 서버 소스 코드
- `data/`: 시스템 설정 및 데이터
- `data/packages/`: 도구 패키지 (installed, not_installed, dev)
- `projects/`: 사용자 프로젝트 데이터
- `templates/`: 프로젝트 생성용 템플릿

---
*마지막 업데이트: 2026-01-02 22:50*
