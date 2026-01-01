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
