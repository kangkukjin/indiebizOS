# 라이브러리 문서 검색 가이드 (Context7)

코드를 작성할 때 라이브러리/프레임워크의 최신 공식 문서를 참조하면 정확한 API를 사용할 수 있다.

## 1. 언제 쓰는가
- **코드를 작성하거나 수정할 때** — 사용할 라이브러리의 최신 API 확인
- **버전별 차이가 중요할 때** — "이 함수가 v3에서 바뀌었나?"
- **설정/설치 방법이 필요할 때** — 공식 문서 기준의 정확한 가이드
- **학습 데이터와 현재가 다를 수 있을 때** — 빠르게 변하는 프레임워크

## 2. 사용법
```
[sense:search_library_docs]{query: "useEffect cleanup", library_name: "react"}
[sense:search_library_docs]{query: "WebSocket endpoint", library_name: "fastapi"}
[sense:search_library_docs]{query: "dark mode setup", library_name: "tailwindcss"}
```

## 3. 일반 웹 검색과의 차이
- **search_ddg** — 블로그, 포럼, 다양한 출처. 정보의 정확도가 불균일
- **search_library_docs** — 공식 문서만. 정확하고 최신. 코드 예제 포함

**원칙: 코드 작성 시에는 search_library_docs를 먼저 쓰고, 부족하면 search_ddg로 보완하라.**

## 4. 라이브러리를 못 찾을 때
이름이 정확하지 않으면 먼저 ID를 조회:
```
[sense:resolve_library]{library_name: "tailwind"}
```
결과에서 정확한 ID를 확인한 뒤 search_library_docs에 사용.

## 5. 주의사항
- library_name은 영문으로 (예: "react", "fastapi", "nextjs")
- query는 구체적으로 (예: "middleware setup" > "middleware")
- 한 번에 하나의 라이브러리만 조회 — 여러 라이브러리가 필요하면 병렬 실행
