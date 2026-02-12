# Computer Use 가이드

## 작업 패턴
```
computer_screenshot → 이미지 분석 → computer_click(x, y) → 결과 스크린샷 확인 → 반복
```

## 좌표 시스템
- 모든 좌표는 **1280x800** 가상 해상도 기준
- 스크린샷 이미지 위의 픽셀 좌표를 그대로 사용
- (0,0)은 좌상단, (1280,800)은 우하단

## 핵심 원칙

1. **항상 스크린샷부터**: 조작 전에 화면 상태를 먼저 확인
2. **요소 중앙 클릭**: 버튼, 아이콘은 중앙 좌표를 정확히 지정
3. **screenshot_after 활용**: click, scroll, drag는 기본적으로 결과 스크린샷을 반환
4. **대기 필요 시**: 로딩이 있으면 잠시 후 computer_screenshot을 다시 호출

## 텍스트 입력
- 영어: computer_type 직접 사용
- 한글: 자동으로 클립보드(Cmd+V) 방식 사용
- 특수키/단축키: computer_key 사용 (예: "command+c", "enter", "tab")

## 주요 단축키
| 키 | 설명 |
|---|---|
| command+c / command+v | 복사 / 붙여넣기 |
| command+a | 전체 선택 |
| command+z | 실행 취소 |
| command+tab | 앱 전환 |
| command+space | Spotlight 검색 |
| command+q | 앱 종료 |
| enter | 확인/실행 |
| tab | 다음 필드 이동 |
| escape | 취소/닫기 |

## 안전
- 마우스를 화면 모서리로 옮기면 긴급 정지 (FAILSAFE)
- 모든 좌표는 범위 검증 후 실행
