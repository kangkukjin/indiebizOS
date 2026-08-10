"""TTS 엔진 층 — 기본 Gemini, 명시하면 Edge.

2026-08-10 기본 엔진 전환(사용자 판정: 제미나이 음질 채택, 화자 Charon).
Edge TTS 는 은퇴가 아니라 *무과금 경로*로 존치한다 — 한국어 목소리 3개가 천장이지만
문자 수 과금이 없다. engine 파라미터로 언제든 되돌아갈 수 있다.

두 엔진의 축이 다르다:
  - edge   : voice/rate/pitch (기계적 조절). 무료.
  - gemini : voice 30종 + **자연어 연기 지시(style)**. rate/pitch 축이 아예 없다.
             문자 수 과금. 응답은 raw PCM(audio/l16)이라 ffmpeg 로 목적 확장자에 굽는다.

★함정(2026-08-10 실측): Gemini interactions 응답에서 오디오는 문서 예제의
`interaction.output_audio` 가 아니라 `steps[*].content[*].data` 에 있다. output_audio 는
SDK 편의 속성이고 REST 응답 구조는 다르다 — 이걸 몰라 첫 시도가 전부 조용히 빈손이었고
그때도 토큰은 과금됐다. 그래서 아래는 steps 를 훑고, 못 찾으면 *정직하게* 예외를 낸다.
"""
import os
import re
import subprocess

GEMINI_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

GEMINI_DEFAULT_VOICE = "Charon"
EDGE_DEFAULT_VOICE = "ko-KR-SunHiNeural"

VALID_ENGINES = ("gemini", "edge")

# 실측 확인된 화자 일부(참고용 — 게이트가 아니다. 모르는 이름도 그대로 API 에 넘겨
# 실패하면 서버 오류를 그대로 보여준다. 여기서 막으면 새 화자가 나와도 못 쓴다).
GEMINI_VOICE_HINTS = ("Charon(정보전달)", "Sulafat(따뜻함)", "Achird(친근함)", "Enceladus(숨소리)")

_EDGE_VOICE_RE = re.compile(r'^[a-z]{2}-[A-Z]{2}-\w+$')


def looks_like_edge_voice(voice: str) -> bool:
    """`ko-KR-SunHiNeural` 모양이면 Edge 화자."""
    return bool(_EDGE_VOICE_RE.match((voice or "").strip()))


def resolve(engine=None, voice=None):
    """(engine, voice) 확정.

    engine 을 안 주면 voice 이름 *모양*으로 추론한다 — 옛 호출이 `ko-KR-InJoonNeural`
    하나만 넘기던 걸 engine 없이도 계속 살리기 위해서다. 둘 다 없으면 gemini/Charon.
    """
    e = (engine or "").strip().lower()
    v = (voice or "").strip()

    if not e:
        e = "edge" if looks_like_edge_voice(v) else "gemini"
    if e not in VALID_ENGINES:
        raise ValueError(f"알 수 없는 engine '{e}' — gemini(기본) | edge")

    if not v:
        v = GEMINI_DEFAULT_VOICE if e == "gemini" else EDGE_DEFAULT_VOICE
    return e, v


def _pluck_audio(payload: dict) -> dict:
    """steps 를 훑어 첫 오디오 content 를 찾는다. 없으면 None."""
    for step in (payload.get("steps") or []):
        for content in (step.get("content") or []):
            mime = content.get("mime_type") or content.get("mimeType") or ""
            if content.get("data") and str(mime).startswith("audio"):
                return content
    return None


def _write_pcm(pcm: bytes, output_path: str, sample_rate: int, channels: int) -> None:
    """raw PCM(s16le)을 목적 확장자로 굽는다. ffmpeg 없으면 wav 로 폴백."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels),
           "-i", "pipe:0", output_path]
    try:
        proc = subprocess.run(cmd, input=pcm, capture_output=True)
    except FileNotFoundError:
        proc = None

    if proc is not None and proc.returncode == 0:
        return

    # 폴백: ffmpeg 부재/실패 → wav 로 직접 쓴다(확장자가 mp3 여도 내용은 wav 라
    # 재생은 되지만 정직하게 알리려고 경로를 .wav 로 바꿔 돌려준다 — 호출측이 처리).
    import wave
    wav_path = os.path.splitext(output_path)[0] + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    if wav_path != output_path:
        err = (proc.stderr.decode()[:200] if proc is not None else "ffmpeg 없음")
        raise RuntimeError(f"ffmpeg 인코딩 실패({err}) — WAV 로 저장했습니다: {wav_path}")


def synthesize_gemini(text, output_path, voice=GEMINI_DEFAULT_VOICE, style=None,
                      api_key=None, model=GEMINI_MODEL, timeout=180.0) -> dict:
    """Gemini TTS 합성. 성공하면 {voice, model, sample_rate, channels, seconds}.

    style = 자연어 연기 지시("차분하고 신뢰감 있는 강의 나레이션 톤으로, 또박또박 읽어줘").
    Edge 에는 없는 축이고, 이 엔진을 채택한 이유다.
    """
    import json
    import base64
    import httpx

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다. "
                           'engine: "edge" 로 무과금 경로를 쓸 수 있습니다.')
    if not (text or "").strip():
        raise ValueError("text는 필수입니다.")

    prompt = f"{style.strip()}:\n{text}" if (style or "").strip() else text
    payload = {
        "model": model,
        "input": prompt,
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }

    with httpx.Client(timeout=timeout) as client:
        r = client.post(GEMINI_ENDPOINT, json=payload,
                        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"Gemini TTS 오류 {r.status_code}: {r.text[:300]}")

    data = r.json()
    audio = _pluck_audio(data)
    if not audio:
        # 과금은 이미 됐다 — 무엇이 왔는지 그대로 보여준다(조용한 빈손 금지).
        raise RuntimeError("Gemini TTS 응답에 오디오가 없습니다. "
                           f"status={data.get('status')} 응답={json.dumps(data, ensure_ascii=False)[:300]}")

    pcm = base64.b64decode(audio["data"])
    sample_rate = int(audio.get("sample_rate") or audio.get("sampleRate") or 24000)
    channels = int(audio.get("channels") or 1)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    _write_pcm(pcm, output_path, sample_rate, channels)

    return {
        "voice": voice,
        "model": model,
        "sample_rate": sample_rate,
        "channels": channels,
        "seconds": round(len(pcm) / 2 / channels / sample_rate, 2),
        "styled": bool((style or "").strip()),
    }
