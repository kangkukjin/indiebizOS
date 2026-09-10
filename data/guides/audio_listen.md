# 소리 듣기 — 파일·마이크·전사·음악 검수

`[sense:listen]`은 소리를 듣는 입구다. **path가 있으면 오디오/영상 파일**을 읽으며 마이크를 켜지 않는다.
파일을 듣는 능력이 없다고 단정하거나 임시 API 스크립트를 만들기 전에 이 액션을 확인한다.
상대경로는 현재 프로젝트, `~workspace/`는 IndieBiz OS 루트다.

```ibl
[sense:listen]{path:"강연.m4a", op:"transcribe"}
[sense:listen]{path:"인터뷰.mp4", op:"transcribe", timestamps:true}
[sense:listen]{path:"편집본.mp3", question:"대화가 남아 있는가? 노래와 말하기를 구분해줘.", ranges:[{start:0,end:15},{start:120,end:140}]}
[sense:listen]{path:"편집본.mp3", op:"inspect", start:120, end:140}
```

- **transcribe**: 전사문을 파일에 저장. `transcript_path`로 전문, `result_path`로 구조화된 원문을 읽는다. 기본 시간 입도는 chunk, `timestamps:true`면 전사 모델에 단어 시각을 요청한다.
- **analyze**: 소리에 질문한다. question을 지정하면 기본 transcribe도 analyze로 해석된다. `speech/singing/music/silence/mixed/unknown`, 답변과 `uncertain`을 반환한다. 모델의 시각은 추정값이다.
- **inspect**: 모델 호출 없이 원본 채널별 peak/RMS·최대 인접 샘플 차이·무음 구간을 측정한다. 무음은 -50dBFS/0.3초 임계값이다. 대화 유무·음악의 자연스러움·클릭 발생 여부를 측정값 하나만으로 확정하지 않는다.
- **record**: path 없이 기존 마이크 녹음. 기존 `[sense:listen]`(path 생략)은 마이크 받아쓰기다. 파일에 FFmpeg/FFprobe가 없는 몸이면 파일 처리 불능을 반환한다. 하드웨어 미지원과 파일 청취 미지원을 혼동하지 않는다.

## 비용과 증거 재사용

파일 내용 해시·구간·목적·질문·모델 설정이 같으면 기존 구간 분석을 사용한다. 실행자가 얻은 결과를 감독자가 다시 조회해도 모델을 재호출하지 않는다. 재분석이 필요한 경우만 `refresh:true`.
전사문과 긴 결과는 저장소에 한 번 쓴다. 반환 `items`는 최대 20행/약 6000자 미리보기이며 `truncated`/`total_items`를 표시한다. 원문을 더 보려면 result_path를 읽고 오디오를 다시 보내지 않는다.
`model_calls`/`usage_this_call`은 이번 호출 비용이고 캐시 사용량은 `cached_chunks`다. 전사 API의 출력 토큰 0은 공급자 보고값이며 원시 사용량도 chunk 증거에 보존한다. usage가 없는 응답은 null이다.

기본 분할은 120초(5~300초 지정 가능). 매 구간 시작/완료와 실제 처리한 초를 로그에 남긴다. 호출 시간 예산은 240초, API 대기는 최대 90초다. 취소는 요청 사이에서 확인한다. 진행 중인 HTTP 요청을 원격에서 취소했다고 보장하지 않는다.
실패/예산 소진은 `success:false`, `status:partial|failed`와 완료 구간을 반환한다. 같은 인자로 재호출하면 완료된 구간을 건너뛰고 이어간다. 미완료 전사문을 완성 파일로 저장하지 않는다.

## 음악 편집 검수

먼저 편집 이력의 모든 접합부를 inspect하고, 접합 전후와 의심 구간을 analyze한다. 전체의 대화 제거를 확인하려면 그 범위를 모두 분석해야 한다. 앞뒤 몇 초의 검수로 파일 전체를 합격시키지 않는다.
`coverage`는 처리 범위이며 품질 합격 판정이 아니다. `requested_ranges`와 `completed_ranges`, source_hash로 어떤 버전을 검사했는지 확인한다.
모델 청취용 사본은 mono FLAC, 신호 측정은 원본 채널을 사용한다. 모델은 스테레오 품질을 보장하지 못한다.

모델 선택은 패키지 `audio_models.yaml`에서 전사/내용 분석을 따로 설정한다. 키는 기존 .env 단일 저장소다. 등록 스크립트 `음성받아쓰기`는 동일 구현을 부르는 호환 래퍼이며 새 작업에서는 listen을 쓴다.
