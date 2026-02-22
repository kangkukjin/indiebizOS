# Browser Action 사용 가이드

## 핵심 원리: Snapshot → Ref → Action

이 패키지는 비전 모델 없이 **Accessibility Snapshot**으로 페이지를 구조화합니다.

```
browser_navigate(url) → browser_snapshot() → ref 확인 → browser_click/type(ref) → browser_snapshot() → 반복
```

### ref란?
- `browser_snapshot` 호출 시 각 요소에 `e1`, `e2`, `e3` ... 형태의 고유 ID가 부여됨
- 이후 `browser_click(ref="e5")`, `browser_type(ref="e3")` 등으로 정확한 요소를 지정
- 페이지가 변경되면(네비게이션, 동적 콘텐츠) **반드시 `browser_snapshot`을 다시 호출**하여 새 ref를 받아야 함

### snapshot vs screenshot vs get_content
| 도구 | 용도 | 반환 |
|------|------|------|
| `browser_snapshot` | 상호작용용 (ref 포함) | 요소 구조 + ref |
| `browser_screenshot` | 시각적 확인용 | PNG 파일 경로 |
| `browser_get_content` | 텍스트 읽기용 | 페이지 텍스트 |

**원칙**: 상호작용이 목적이면 항상 `browser_snapshot`을 사용. screenshot은 시각 확인이 필요할 때만.

---

## 다중 탭 사용법

### 기본 흐름
```
browser_navigate(url="site-a.com")     → t1 탭에서 열림
browser_tab_new(url="site-b.com")      → t2 탭 생성 + 자동 전환
browser_tab_list()                     → 열린 탭 목록 확인
browser_tab_switch(tab_id="t1")        → t1로 복귀
browser_tab_close(tab_id="t2")         → t2 닫기
```

### 팝업/새 탭 자동 감지
링크 클릭으로 새 탭이 열리면 자동으로 감지되어 `_pages`에 등록됩니다. `browser_tab_list`로 확인 가능.

### 주의사항
- 탭 전환 시 ref가 초기화됨 → 전환 후 반드시 `browser_snapshot` 호출
- 활성 탭을 닫으면 가장 최근 탭으로 자동 전환

---

## iframe 작업

### 기본 흐름
```
browser_iframe_list()                      → 페이지 내 iframe 목록 확인
browser_iframe_switch(name="content")      → iframe 진입 (name, index, url 중 택1)
browser_snapshot()                         → iframe 내부 구조 파악
browser_click(ref="e3")                    → iframe 내부에서 클릭
browser_iframe_reset()                     → 메인 페이지로 복귀
browser_snapshot()                         → 메인 페이지 구조 재파악
```

### 식별 방법 우선순위
1. `name` — iframe에 name 속성이 있으면 가장 정확
2. `url` — URL 패턴의 부분 일치로 검색
3. `index` — 위치 기반 (페이지 구조 변경 시 깨질 수 있음)

---

## 쿠키/로그인 상태 관리

### 저장
```
# 로그인 완료 후
browser_cookies_save(name="naver")
```
- name을 생략하면 현재 도메인명 자동 사용
- 쿠키 + localStorage 모두 저장
- 만료된 쿠키는 자동 제외
- 저장 위치: `indiebizOS/data/browser_cookies/{name}.json`

### 복원
```
# 새 세션에서
browser_navigate(url="naver.com")
browser_cookies_load(name="naver")
# → 자동으로 페이지 리로드되며 로그인 상태 복원
```

### 주의사항
- 쿠키 파일에 인증 토큰이 포함되므로 Git에 커밋하지 말 것
- localStorage 복원은 같은 도메인에서만 작동 (다른 도메인이면 자동으로 해당 URL로 이동 후 복원)
- 일부 사이트는 서버측 세션이 만료되면 쿠키만으로 복원 불가

---

## 폼 조작 (드롭다운, 입력)

### 드롭다운(select) 선택 — browser_select_option 사용
```
1. browser_snapshot()                          → select 요소의 ref 확인 (role: combobox)
2. browser_select_option(ref="e5", values=["옵션텍스트"])  → 옵션 선택
```
- `browser_evaluate`로 JS 직접 조작하지 말 것 — Playwright의 `select_option`이 프레임워크 호환성이 높음
- `values`에는 옵션의 **텍스트** 또는 **value** 사용 가능

### 연계 select (시/도 → 시/군/구 → 읍/면/동)
상위 선택에 따라 하위 옵션이 동적으로 바뀌는 cascading dropdown:
```
1. browser_select_option(ref="시도ref", values=["부산광역시"])
2. browser_wait_for(timeout=1500)              → 하위 옵션 로드 대기
3. browser_snapshot()                          → 하위 select의 새 ref 확인
4. browser_select_option(ref="시군구ref", values=["동래구"])
5. browser_wait_for(timeout=1500)
6. browser_snapshot()
7. browser_select_option(ref="읍면동ref", values=["명장동"])
```
- 각 단계마다 **wait → snapshot** 필수 (하위 옵션이 비동기 로드됨)
- snapshot 없이 이전 ref를 재사용하면 실패함

### browser_evaluate 사용 원칙
`browser_evaluate`는 **전용 도구로 해결 불가능한 경우에만** 사용:
- 클릭 → `browser_click` 우선
- 텍스트 입력 → `browser_type` 우선
- 드롭다운 선택 → `browser_select_option` 우선
- 페이지 데이터 추출 → `browser_get_content` 또는 `browser_evaluate`
- WebSquare 등 특수 프레임워크에서 전용 도구가 안 될 때만 `browser_evaluate` 사용

### 결과 검증 패턴
검색/폼 제출 후 반드시 결과를 확인:
```
1. 검색 실행 후 browser_snapshot() 또는 browser_get_content()
2. 결과가 기대와 다르면:
   - select 값이 제대로 적용되었는지 확인 (snapshot에서 selected 상태)
   - 같은 방법 반복하지 말고 대안 시도 (evaluate → select_option, 또는 반대)
   - 3회 이상 같은 방법이 실패하면 전략을 바꿀 것
```

---

## 에러 대응

### "ref를 찾을 수 없습니다"
→ `browser_snapshot`을 다시 호출하여 최신 ref를 확보

### "요소를 찾을 수 없습니다"
→ 페이지가 동적으로 변경되었을 수 있음. `browser_snapshot` 재호출 후 새 ref로 재시도

### "브라우저가 열려있지 않습니다"
→ 120초 비활성으로 자동 종료됨. `browser_navigate`로 재시작

### 스냅샷에 원하는 요소가 없을 때
1. `browser_scroll`로 해당 영역까지 스크롤 후 다시 스냅샷
2. `browser_wait_for`로 동적 콘텐츠 로드 대기
3. iframe 내부 요소라면 `browser_iframe_switch` 후 스냅샷

### 클릭 후 새 페이지/팝업이 열렸을 때
→ `browser_tab_list`로 새 탭 확인 → `browser_tab_switch`로 전환

---

## 키보드 키 이름 참조

| 분류 | 키 |
|------|----|
| 일반 | Enter, Tab, Escape, Backspace, Delete, Space |
| 방향 | ArrowUp, ArrowDown, ArrowLeft, ArrowRight |
| 조합 | Control+a, Control+c, Control+v, Shift+Tab, Alt+F4 |
| 특수 | F1~F12, Home, End, PageUp, PageDown |

---

## 실전 워크플로우 예시

### 검색 후 결과 수집
```
1. browser_navigate(url="google.com")
2. browser_snapshot()                          → 검색창 ref 확인 (예: e3)
3. browser_type(ref="e3", text="검색어", submit=true)
4. browser_snapshot()                          → 결과 링크 ref 확인
5. browser_get_content()                       → 검색 결과 텍스트 추출
```

### 로그인이 필요한 사이트 작업
```
1. browser_navigate(url="site.com/login")
2. browser_cookies_load(name="site")           → 저장된 상태 복원 시도
3. (로그인 안되어있으면) 수동 로그인 진행
4. browser_cookies_save(name="site")           → 상태 저장
5. 이후 작업 수행
```

### 여러 사이트 동시 비교
```
1. browser_navigate(url="site-a.com/product")  → t1
2. browser_get_content()                       → 정보 수집
3. browser_tab_new(url="site-b.com/product")   → t2
4. browser_get_content()                       → 정보 수집
5. browser_tab_switch(tab_id="t1")             → 필요시 t1로 복귀
```
