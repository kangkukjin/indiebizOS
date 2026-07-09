# 오디오 브리핑 제작 가이드 (레시피)

"오디오 브리핑 만들어줘" 위임을 받으면 이 절차대로 **오늘의 음성 브리핑**을 만들어
고정 파일에 저장한다. 데스크탑 앱·폰·원격이 모두 그 고정 파일을 읽어 재생한다.

## 핵심 원칙
1. **항상 고정 파일명에 저장** — mp3=`audio_briefing_current.mp3`, 스크립트=`audio_briefing_current.md`. "현재 판" 하나만(매번 덮어씀). 해시 이름 쓰지 말 것 — 폰이 고정명을 당긴다.
2. **저장 대상은 `project_id: "앱모드"`로 지정** — mp3·스크립트가 앱모드 프로젝트 outputs 에 떨어져야 폰/앱이 찾는다. `[engines:tts]`·`[self:write]` 에 `project_id: "앱모드"` 를 실으면 라우팅이 이를 존중해 `projects/앱모드/outputs/` 로 굽는다.
   - 이 레시피는 대개 위임(`[others:delegate]{scope:"system"}`)을 통해 시스템 AI가 실행하는데, **명시 project_id 는 호출자(시스템 AI)의 컨텍스트 경로보다 우선**한다(`ibl_routing._resolve_project_path`). 그래서 하드코딩 절대경로도 `self:move` 도 필요 없다 — 데스크탑 앱·MCP·위임 어느 경로든 `project_id: "앱모드"` 하나면 목적지에 바로 떨어진다.
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

### 3) 음성 생성 (mp3, 고정명) — 앱모드 outputs 에 바로 굽기
```
[engines:tts]{text: "<완성 대본 전체>", output_filename: "audio_briefing_current.mp3", project_id: "앱모드"}
```
(tts 는 `project_id` 로 지정한 프로젝트의 `outputs/` 에 곧장 굽는다 → move 불필요. 핵심원칙 2 참조.)

### 4) 스크립트 저장 (폰/원격 뷰어용)
```
[self:write]{path: "outputs/audio_briefing_current.md", content: "# 오디오 브리핑 · {날짜}\n\n<완성 대본>", project_id: "앱모드"}
```

## 완료 조건
- `projects/앱모드/outputs/audio_briefing_current.mp3` 갱신 (오늘 내용)
- `projects/앱모드/outputs/audio_briefing_current.md` 갱신 (같은 대본)
그러면 폰 "오디오 브리핑" 앱의 재생/저장, 데스크탑 앱이 최신 브리핑을 가리킨다.
