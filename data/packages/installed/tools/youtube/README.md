# YouTube 도구

## 목적

에이전트가 YouTube 동영상을 다루는 능력을 제공합니다.
음악 다운로드, 정보 조회, 자막 추출, AI 요약 등을 할 수 있습니다.

## 이 도구가 제공하는 것

- **음악 다운로드**: YouTube 영상에서 MP3 추출
- **정보 조회**: 제목, 길이, 조회수, 설명 등
- **자막 추출**: 자동 생성 또는 수동 자막 텍스트화
- **AI 요약**: 자막 기반으로 영상 내용 요약

## 설치 시 필요한 변경사항

### 1. 도구 함수 구현

에이전트가 호출할 수 있는 도구 함수들을 구현해야 합니다.

**download_youtube_music(url, output_path)**
- YouTube URL에서 음악만 추출
- MP3 또는 M4A 형식으로 저장
- 파일 경로 반환

**get_youtube_info(url)**
- 영상 메타데이터 조회
- 제목, 채널, 길이, 조회수, 설명 등 반환

**get_youtube_transcript(url, language)**
- 자막 텍스트 추출
- 언어 지정 가능 (ko, en 등)
- 시간 정보 포함/제외 선택

**list_available_transcripts(url)**
- 해당 영상에서 사용 가능한 자막 언어 목록

**summarize_youtube(url, ai_config)**
- 자막을 가져와서 AI로 요약
- 결과를 HTML 파일로 저장

### 2. 도구 정의

AI가 도구를 인식할 수 있도록 정의해야 합니다.

```json
{
  "name": "download_youtube_music",
  "description": "YouTube 영상에서 음악을 MP3로 다운로드합니다",
  "input_schema": {
    "type": "object",
    "properties": {
      "url": {"type": "string", "description": "YouTube URL"},
      "output_path": {"type": "string", "description": "저장 경로 (선택)"}
    },
    "required": ["url"]
  }
}
```

### 3. 에이전트 연동

설치된 도구를 에이전트가 사용할 수 있어야 합니다.

- 프로젝트 설정에서 이 도구를 에이전트에 배정
- AI 호출 시 도구 정의 포함
- tool_use 응답 처리

### 4. 출력 관리

다운로드된 파일과 생성된 결과를 관리해야 합니다.

- 기본 저장 경로 설정
- 파일명 중복 처리
- 용량 관리 (선택)

## 외부 의존성

이 도구는 외부 프로그램이 필요합니다.

**yt-dlp**: YouTube 다운로더
```bash
pip install yt-dlp
```

**ffmpeg**: 오디오 변환
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt install ffmpeg

# Windows
# ffmpeg.org에서 다운로드 후 PATH에 추가
```

**youtube-transcript-api**: 자막 추출
```bash
pip install youtube-transcript-api
```

## 참고 구현

이 폴더의 `tool_youtube.py`는 Python 기반 구현 예시입니다.

```
tool_youtube.py
├── download_youtube_music()
├── get_youtube_info()
├── get_youtube_transcript()
├── list_available_transcripts()
├── summarize_youtube()
└── YOUTUBE_TOOLS (도구 정의)
```

이 코드를 그대로 사용하지 말고, 현재 시스템에 맞게 구현하세요.

## 법적 고려사항

- 저작권이 있는 콘텐츠 다운로드 시 주의
- 개인 사용 목적으로만 사용 권장
- YouTube 이용약관 확인

## 설치 완료 확인

- [ ] 에이전트가 도구를 호출할 수 있음
- [ ] YouTube URL에서 음악 다운로드 가능
- [ ] 영상 정보 조회 가능
- [ ] 자막 추출 가능
- [ ] AI 요약 생성 가능
