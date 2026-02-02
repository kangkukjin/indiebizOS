# IndieBiz OS 의존성 설치 가이드

다른 PC에 IndieBiz를 설치할 때 필요한 라이브러리들입니다.

---

## 1. 필수 설치 (Core)

### Python 3.10 이상
- 다운로드: https://www.python.org/downloads/
- **Windows 설치 시 "Add Python to PATH" 반드시 체크!**

### Node.js 18 이상
- 다운로드: https://nodejs.org/
- LTS 버전 권장

### 백엔드 핵심 패키지
```bash
pip install fastapi uvicorn pydantic python-dotenv pyyaml aiofiles
pip install anthropic openai google-genai
pip install pynostr websocket-client
```

또는 한 줄로:
```bash
pip install fastapi uvicorn pydantic python-dotenv pyyaml aiofiles anthropic openai google-genai pynostr websocket-client
```

---

## 2. 도구별 의존성

### 🌐 웹/브라우저 관련

**browser-action** (브라우저 자동화)
```bash
pip install playwright
playwright install chromium
```

**web** (웹 검색/크롤링)
```bash
pip install beautifulsoup4 duckduckgo-search requests nest-asyncio
pip install browser-use langchain-google-genai
```

**shopping-assistant** (쇼핑 도우미)
```bash
pip install playwright requests
playwright install chromium
```

---

### 📊 데이터/시각화

**visualization** (차트 생성)
```bash
pip install matplotlib plotly kaleido numpy
```

**investment** (투자/주식)
```bash
pip install finance-datareader yfinance
```

---

### 🎬 미디어 제작

**media_producer** (영상 제작)
```bash
pip install pillow moviepy edge-tts jinja2
```

**music-composer** (음악 작곡)
```bash
# Python 패키지
pip install midiutil

# 시스템 도구 (선택사항 - MIDI를 오디오로 변환)
# macOS: brew install fluidsynth timidity
# Windows: FluidSynth 또는 TiMidity++ 설치
# Linux: sudo apt install fluidsynth timidity
```

**remotion-video** (Remotion 영상)
```bash
# Node.js 패키지 (자동 설치됨)
cd data/packages/installed/tools/remotion-video/remotion_project
npm install
```

**photo-manager** (사진 관리)
```bash
pip install pillow requests
```

---

### 📱 모바일/기기

**android** (안드로이드 연결)
```bash
# ADB 설치 필요
# macOS: brew install android-platform-tools
# Windows: https://developer.android.com/studio/releases/platform-tools
# Linux: sudo apt install adb
```

---

### 📰 정보/검색

**blog** (블로그/RSS)
```bash
pip install beautifulsoup4 feedparser requests
```

**study** (학술 검색)
```bash
pip install arxiv feedparser requests
```

**youtube** (유튜브)
```bash
pip install yt-dlp
```

**location-services** (위치 서비스)
```bash
pip install requests feedparser jinja2 duckduckgo-search
```

---

### 🏢 비즈니스/공공데이터

**kosis** (통계청 데이터)
```bash
pip install requests
```

**real-estate** (부동산)
```bash
pip install requests
```

**legal** (법률 검색)
```bash
pip install requests
```

**startup** (스타트업 정보)
```bash
pip install requests
```

**culture** (문화/공연)
```bash
pip install requests
```

---

## 3. 전체 한 번에 설치 (권장)

### 필수 + 자주 사용하는 패키지
```bash
pip install fastapi uvicorn pydantic python-dotenv pyyaml aiofiles anthropic openai google-genai pynostr websocket-client beautifulsoup4 requests feedparser pillow matplotlib plotly kaleido numpy yt-dlp duckduckgo-search
```

### Playwright (브라우저 자동화 필요시)
```bash
pip install playwright
playwright install chromium
```

### 투자 도구 (필요시)
```bash
pip install finance-datareader yfinance
```

### 미디어 제작 (필요시)
```bash
pip install moviepy edge-tts jinja2 midiutil
```

---

## 4. 문제 해결

### "모듈을 찾을 수 없습니다" 에러
해당 도구의 의존성을 위 목록에서 찾아 설치하세요.

### Windows에서 pip 명령이 안 될 때
```bash
python -m pip install <패키지명>
```

### 권한 에러 (Permission denied)
```bash
pip install --user <패키지명>
```

### Playwright 브라우저 설치 실패
```bash
# 관리자 권한으로 실행
playwright install --with-deps chromium
```

---

## 5. API 키 설정

일부 도구는 API 키가 필요합니다. IndieBiz 설정에서 입력하세요:

| 서비스 | 용도 | 발급처 |
|--------|------|--------|
| OpenAI | GPT 모델 | https://platform.openai.com |
| Anthropic | Claude 모델 | https://console.anthropic.com |
| Google AI | Gemini 모델 | https://aistudio.google.com |
| DART | 기업 공시 | https://opendart.fss.or.kr |
| 공공데이터포털 | 각종 공공API | https://data.go.kr |

---

*최종 업데이트: 2025-02*
