# 오디오 브리핑 제작 가이드 (레시피)

"오디오 브리핑 만들어줘" 위임을 받으면 이 절차대로 **오늘의 음성 브리핑**을 만들어
고정 파일에 저장한다. 데스크탑 앱·폰·원격이 모두 그 고정 파일을 읽어 재생한다.

## 핵심 원칙
1. **항상 고정 파일명에 저장** — mp3=`audio_briefing_current.mp3`, 스크립트=`audio_briefing_current.md`. "현재 판" 하나만(매번 덮어씀). 해시 이름 쓰지 말 것 — 폰이 고정명을 당긴다.
2. **저장은 절대경로로 한다** — 이 레시피는 대개 위임(`[others:delegate]{scope:"system"}`)을 통해 **시스템 AI가 실행**한다. 그런데 위임된 시스템 AI는 IBL 실행 컨텍스트의 `project_path`가 `data/`로 **고정**돼 있고, 코드 안의 `project_id:`/`project_path:` 파라미터로는 이를 **바꿀 수 없다**(`ibl_routing._resolve_project_path` 4단 우선순위에서 호출자 project_path가 최우선 → params 무시). 즉 `[engines:tts]`/`[self:write]`에 `project_id:"앱모드"`를 실어도 산출물은 `data/outputs/`로 떨어져 **폰/앱이 못 찾는다**(실제 사고 이력).
   - **해결 = 절대경로 저장.** 목표 폴더 = `/Users/kangkukjin/Desktop/AI/indiebizOS/projects/앱모드/outputs/`.
     - `[self:write]`는 절대경로를 그대로 존중한다 → 목적지에 바로 저장(4단계).
     - `[engines:tts]`는 `output_filename`의 디렉토리를 떼어내고 항상 `project_path/outputs`(위임 시 `data/outputs/`)에 굽는다 → **TTS로 구운 뒤 `[self:move]`로 목적지로 옮긴다**(3단계).
   - (예외) out-of-process **MCP `execute_ibl`** 호출이면 대신 **최상위 `project_path` 파라미터**에 `projects/앱모드` 절대경로를 주면 TTS가 곧장 목적지에 굽는다(이땐 move 불필요). 데스크탑 앱(tsx)은 `iblExecuteApp`이 이미 최상위 project_id를 실어 정상 — **이 절대경로 절차는 위임 경로 전용**이다.
3. **귀로 듣는 글** — 번호·목록 기호 없이 자연스럽게 이어지는 라디오 진행자 멘트. 3~5문장 분량의 뉴스 소개.

## 절차

### 1) 데이터 수집 (오늘)
```
[sense:weather]{city: "청주"}
[sense:stock]{op: "quote", ticker: "^KS11"}          # 코스피 종합지수
[sense:stock]{op: "quote", ticker: "102110"}          # TIGER 200 ETF
[sense:search_gnews]{headlines: true, curate: 6}      # 오늘의 핫뉴스
```
(도시는 사용자 프로필 지역, 없으면 청주. 증시는 등락률 위주 — 절대값은 참고.)

### 2) 스크립트 작성
수집한 값으로 하나의 낭독 대본을 만든다. 구성:
- 인사: "안녕하세요, {오늘 날짜} 오디오 브리핑입니다."
- 날씨: "오늘 {지역} 날씨는 {상태}, 기온 {temp}도입니다."
- 증시: "코스피는 {등락률}% {상승/하락}, TIGER200은 {등락률}% {상승/하락}했습니다."
- 뉴스: 핫뉴스 6건을 라디오 진행자가 소개하는 자연스러운 한 문단(번호 없이, 5~7문장). 필요하면 `[self:ask]{prompt: "다음 뉴스를 라디오 진행자 멘트로 5~7문장, 목록기호 없이 한 문단으로", context: "<기사목록>"}` 로 생성.
- 마무리: "지금까지 오디오 브리핑이었습니다."

### 3) 음성 생성 (mp3, 고정명) — data/outputs 에 구운 뒤 앱모드로 이동
```
[engines:tts]{text: "<완성 대본 전체>", output_filename: "audio_briefing_current.mp3"} >> [self:move]{source: "/Users/kangkukjin/Desktop/AI/indiebizOS/data/outputs/audio_briefing_current.mp3", dest: "/Users/kangkukjin/Desktop/AI/indiebizOS/projects/앱모드/outputs/audio_briefing_current.mp3"}
```
(위임 실행이라 TTS 는 `data/outputs/`에 굽힌다 → move 로 앱모드 outputs 로 옮겨야 폰/앱이 찾는다. 핵심원칙 2 참조.)

### 4) 스크립트 저장 (폰/원격 뷰어용) — 절대경로로 바로 저장
```
[self:write]{path: "/Users/kangkukjin/Desktop/AI/indiebizOS/projects/앱모드/outputs/audio_briefing_current.md", content: "# 오디오 브리핑 · {날짜}\n\n<완성 대본>"}
```

## 완료 조건
- `projects/앱모드/outputs/audio_briefing_current.mp3` 갱신 (오늘 내용)
- `projects/앱모드/outputs/audio_briefing_current.md` 갱신 (같은 대본)
그러면 폰 "오디오 브리핑" 앱의 재생/저장, 데스크탑 앱이 최신 브리핑을 가리킨다.
