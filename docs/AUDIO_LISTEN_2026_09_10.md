# 듣기 어휘의 파일 확장

문제: 파일 전사가 등록 스크립트에만 있고 listen 교재가 마이크로 한정되어, 실행자가 파일을 들을 수 없다고 오판했다.

같은 `[sense:listen]`에 path·question·구간을 연결한다. 어휘 개수는 늘리지 않는다. 기본 transcribe/record의 마이크 경로를 보존하고, 파일 입력은 transcribe/analyze/inspect로 처리한다. 의미와 실제 인자 계약은 패키지 android의 ibl_actions.yaml이 소유한다. 상대경로는 프로젝트, ~workspace는 공통 루트.

구현: android_audio(구간·캐시·증거·진척), android_audio_provider(전사/내용 API), android_audio_signal(파일 디코딩·원본 신호 측정). 스크립트와 데스크톱 마이크 전사는 같은 경로를 부른다. 폰 마이크의 SpeechRecognizer/MediaRecorder 동작은 유지한다.

설정: audio_models.yaml. Gemini 전사용 Interactions API와 내용 분석용 Generate Content를 별도 어댑터로 지원한다. 현재 기본은 gemini-3.5-transcribe / gemini-3.8-flash. 키는 model_resolver의 .env 해소기를 사용하고 요청 헤더로 보내며 로그에는 남기지 않는다.

사용량: ProviderMetrics.record_usage 경유로 턴 원장에 기록. IBL sync worker가 contextvars도 승계하도록 하여 도구 내부의 모델 호출이 원장/에피소드에서 빠지지 않게 했다. 캐시 적중은 모델 호출 0이며 API가 미제공한 사용량을 0으로 꾸미지 않는다.

캐시: data/audio_cache/<내용해시>/ 아래 구간별 성공 결과 및 요청별 result.json. 프로세스 간 구간 잠금으로 같은 검사의 중복 발송을 막는다. 실패한 구간은 성공 캐시를 만들지 않으며 같은 호출로 재개할 수 있다. 상세·제약은 data/guides/audio_listen.md.

검증: 합성 한국어 음성의 실 API 전사/분석, 합성 스테레오 파일의 실제 FFmpeg 무음·채널·부분 구간 측정, 캐시 재사용/소스·질문 변경 무효화, 부분 실패 재개, 긴 결과 저장, 모델 잘림·범위 밖 시각 거부, 파일 분기에서 마이크 비활성 회귀를 사용한다. 음악 청취의 주관적 품질 자체를 이 테스트가 인증하지는 않는다.

공식 계약 확인(2026-09-10): https://ai.google.dev/gemini-api/docs/transcribe · https://ai.google.dev/gemini-api/docs/audio · https://ffmpeg.org/ffmpeg-filters.html
