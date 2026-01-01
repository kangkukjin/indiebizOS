# IndieBiz OS 아키텍처

## 시스템 구조

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드
│   ├── api.py           # 메인 서버 (포트 8765)
│   ├── api_*.py         # 각 모듈 라우터
│   ├── *_manager.py     # 비즈니스 로직 매니저
│   └── data/            # 백엔드 로컬 데이터
│
├── frontend/            # Electron + React 프론트엔드
│   ├── electron/        # Electron 메인/프리로드
│   │   ├── main.js      # 메인 프로세스
│   │   └── preload.js   # IPC 브릿지
│   └── src/
│       ├── components/  # React 컴포넌트
│       ├── lib/         # API 클라이언트
│       └── types/       # TypeScript 타입
│
├── data/                # 런타임 데이터
│   ├── packages/        # 패키지 저장소
│   │   ├── available/   # 설치 가능한 패키지
│   │   ├── installed/   # 설치된 패키지
│   │   └── registry.json
│   ├── system_docs/     # 시스템 AI 문서 (장기기억)
│   └── system_ai_memory.db
│
├── projects/            # 사용자 프로젝트
├── templates/           # 프로젝트 템플릿
└── outputs/             # 출력 파일
```

## 핵심 컴포넌트

### 시스템 AI
- IndieBiz의 관리자이자 안내자
- 시스템 설정의 AI 프로바이더 사용
- 사용자 정보(단기기억)와 시스템 문서(장기기억) 참조

### 프로젝트 매니저
- 프로젝트 생성, 수정, 삭제
- 템플릿 기반 프로젝트 생성
- 에이전트 관리
- 대화 이력 관리

### 패키지 시스템
- **형식 강제 없음**: manifest.yaml 같은 형식 파일 불필요
- **폴더 기반 탐지**: 폴더 존재만으로 패키지 인식
- **AI 친화적**: 코드와 README만으로 AI가 이해 가능
- **레지스트리**: registry.json에 메타데이터 저장
- **외부 폴더 등록**: 사용자 폴더를 패키지로 등록 가능

### Electron IPC
- 네이티브 폴더 선택 다이얼로그
- 외부 URL 열기
- 다중 창 관리 (프로젝트, 폴더, IndieNet)

## 설계 원칙
1. 최소주의: 핵심 기능만 코어에 포함
2. 확장성: 패키지로 기능 확장
3. 독립성: 각 컴포넌트는 독립적으로 동작
4. AI 친화적: 형식보다 내용, AI가 이해할 수 있는 구조

---
*마지막 업데이트: 2025-12-31 10:30*
