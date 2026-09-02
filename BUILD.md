# IndieBiz OS 빌드 가이드

## Windows 배포 패키지 빌드

### 준비물
- Node.js 18+
- Windows 10/11 (빌드 환경)

### 빌드 방법

#### 방법 1: Windows에서 직접 빌드

```powershell
# 1. 프로젝트 폴더로 이동
cd indiebizOS/frontend

# 2. 의존성 설치
npm install

# 3. Python 임베디드 환경 준비
npm run prepare:python:win

# 4. Windows 빌드
npm run electron:build:win
```

빌드 결과물: `frontend/release/IndieBiz Setup x.x.x.exe`

#### 방법 2: macOS에서 크로스 빌드 (제한적)

```bash
# 1. Python 임베디드 다운로드만 (패키지 설치는 안됨)
npm run prepare:python:win

# 2. Windows VM 또는 실제 Windows에서 패키지 설치 필요
```

**참고**: electron-builder는 크로스 빌드를 지원하지만, Python 패키지는 플랫폼별로 설치해야 합니다.

---

## macOS 배포 패키지 빌드

```bash
cd indiebizOS/frontend
npm install
npm run electron:build:mac
```

빌드 결과물: `frontend/release/IndieBiz-x.x.x.dmg`

**참고**: macOS 빌드는 시스템 Python3를 사용하거나, 별도로 Python을 번들링해야 합니다.

---

## 빌드 결과물 크기 (예상)

| 플랫폼 | 인스톨러 | 설치 후 |
|--------|---------|--------|
| Windows | ~150MB | ~450MB |
| macOS | ~120MB | ~400MB |

---

## 폴더 구조 (빌드 후)

```
IndieBiz/
├── IndieBiz.exe          # Electron 앱
├── resources/
│   ├── app/              # 프론트엔드 (Vite 빌드)
│   ├── backend/          # FastAPI 백엔드
│   ├── python/           # 임베디드 Python (Windows)
│   ├── data/             # 시스템 데이터
│   ├── projects/         # 프로젝트 데이터
│   ├── templates/        # 템플릿
│   └── tokens/           # 토큰 저장소
└── ...
```

---

## 릴리스 관문 (2026-09-02, docs/FIRST_SUCCESS_AND_UPGRADE_GATE_HANDOFF.md ②)

체크리스트가 아니라 **실패하는 테스트**다. 태그를 붙이기 전에 전부 초록이어야 한다(version-tag-sync 와 함께).

| 관문 | 무엇을 증명하나 | 명령 / CI 잡 |
|---|---|---|
| 빈 설치본 부팅 | 정본 레시피(bootstrap.py)로 설치한 빈 몸이 /health 200 | `python3 scripts/ci_boot_smoke.py` · `boot-smoke`(3 OS) |
| 노후 설치본 업그레이드 | 직전 태그로 설치·개인화한 몸이 지금 트리로 올라간 뒤 부팅 (git 경로 + 설치본 동기화 경로) | `python3 scripts/ci_upgrade_smoke.py` · `upgrade-smoke` |
| 사용자 소유물 보존 | 끈 패키지·자작 패키지·설정 json·DB 행·사용자 파일이 해시/행수 그대로 | (같은 스크립트) |
| 실패 시 원상복구 | 동기화가 도중에 죽으면 다음 기동이 저널로 되감고 재동기화 | (같은 스크립트 — `failAfterEntries` 재현) |
| 은퇴 코어 잔존 검사 | git 경로=사라진 추적 파일 삭제, 설치본 경로=매니페스트 `retired` 격리 이동 | (같은 스크립트) |
| git 경로 업그레이드 레시피 | `scripts/update.py`(배치 되돌림 → ff pull → 재적용)가 사용자가 옮긴 패키지를 상류 변경에도 살린다 | (같은 스크립트 — 깨끗한 트리면 진짜 레시피, 아니면 배치 함수+에뮬레이션) |
| 스키마 따라잡기 | 옛 DB 가 `user_version` 으로 마이그레이션(옛 액션명 행 정리) | (같은 스크립트) + `pytest backend/test_schema_migrations.py` |

로컬 실행은 `.venv` 와 `node` 가 필요하고 직전 태그를 `git worktree` 로 꺼내므로 2~5분 걸린다.
`--keep` 으로 산출물(worktree·userData·저널)을 남겨 디버그할 수 있다.

## 트러블슈팅

### Python 패키지 설치 오류
- Windows에서 직접 빌드해야 함
- `pip install` 시 Visual C++ Build Tools 필요할 수 있음

### 앱 실행 시 백엔드 연결 실패
- 포트 8765가 사용 가능한지 확인
- 방화벽 설정 확인

### 코드 서명
- 배포용으로는 코드 서명 인증서 필요
- 서명 없이 배포 시 Windows Defender 경고 발생
