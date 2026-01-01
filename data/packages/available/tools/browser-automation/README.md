# 브라우저 자동화 도구

## 목적

에이전트가 실제 웹 브라우저를 조작할 수 있게 합니다.
로그인이 필요한 사이트, JavaScript로 렌더링되는 페이지, 복잡한 웹 작업을 자동화합니다.

## 이 도구가 제공하는 것

- **자연어 브라우저 조작**: "구글에서 날씨 검색해줘" 같은 명령 실행
- **스크린샷 캡처**: 현재 화면 저장
- **폼 입력/클릭**: 웹 페이지와 상호작용
- **동적 페이지 처리**: JavaScript 렌더링 대기

## 설치 시 필요한 변경사항

### 1. 도구 함수 구현

**browser_action(instruction)**
- 자연어 명령을 받아 브라우저 조작
- AI가 명령을 해석하여 실행
- 결과 스크린샷 또는 텍스트 반환

또는 세부 도구들:
- **navigate(url)**: 페이지 이동
- **click(selector)**: 요소 클릭
- **type_text(selector, text)**: 텍스트 입력
- **screenshot(path)**: 스크린샷 저장
- **get_text(selector)**: 텍스트 추출

### 2. 도구 정의

```json
{
  "name": "browser_action",
  "description": "자연어로 브라우저 작업을 지시합니다. 웹 검색, 페이지 캡처 등",
  "input_schema": {
    "type": "object",
    "properties": {
      "instruction": {
        "type": "string",
        "description": "수행할 작업 (예: '구글에서 날씨 검색해서 결과 캡처')"
      }
    },
    "required": ["instruction"]
  }
}
```

### 3. 브라우저 엔진

실제 브라우저를 제어하는 엔진이 필요합니다.

선택지:
- **Playwright**: 추천. 빠르고 안정적
- **Selenium**: 오래된 표준
- **Puppeteer**: Node.js 환경

Playwright 설치:
```bash
pip install playwright
playwright install chromium
```

### 4. AI 연동 (자연어 모드)

자연어 명령을 브라우저 동작으로 변환하려면:

- 명령 해석 AI 필요
- 화면 상태 인식
- 다음 동작 결정
- 반복 실행

browser-use 같은 라이브러리 활용 가능:
```bash
pip install browser-use
```

### 5. 보안 고려

브라우저 자동화는 보안에 민감합니다.

- 비밀번호 입력 시 주의
- 악성 사이트 접근 방지
- 작업 로그 기록
- 사용자 확인 요청 (선택)

## 설계 고려사항

### 헤드리스 vs 헤드풀
- 헤드리스: 화면 없이 백그라운드 실행
- 헤드풀: 실제 브라우저 창 표시
- 디버깅 시 헤드풀 유용

### 세션 관리
- 로그인 상태 유지
- 쿠키 저장/복원
- 여러 탭 관리

### 대기 전략
- 페이지 로드 완료 대기
- 특정 요소 출현 대기
- 타임아웃 설정

## 참고 구현

이 폴더의 `tool_browser.py`는 Python + browser-use 기반 예시입니다.

```
tool_browser.py
├── browser_action()      - 자연어 브라우저 조작
├── _init_browser()       - 브라우저 초기화
└── BROWSER_TOOLS (도구 정의)
```

### 의존성 (Python 구현)
```bash
pip install browser-use playwright
playwright install chromium
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 설치 완료 확인

- [ ] Playwright 브라우저가 설치됨
- [ ] 에이전트가 도구를 호출할 수 있음
- [ ] 자연어 명령으로 브라우저 조작 가능
- [ ] 스크린샷 캡처 가능
- [ ] 결과가 에이전트에게 반환됨
