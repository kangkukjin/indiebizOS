"""오디오 파일 받아쓰기 (Gemini) — IBL 에 없는 '파일 STT' 를 등록 스크립트로 결정화.

why: [sense:listen] 은 마이크 1회 입력이라 *파일* 에 못 쓴다. 2026-08-19 ep1251 에서
     매번 /tmp 에 일회용 스크립트를 떨궈 쓰다 세션과 함께 사라졌다 — 그 자리를 메운다.

args (stdin JSON):
  path            (필수) 오디오/영상 파일 경로. ffmpeg 이 읽는 건 무엇이든.
  out             전사문 저장 경로. 생략 시 outputs/transcripts/<원본이름>.transcript.txt
  segment_seconds 분할 길이(초, 기본 300). 긴 파일은 나눠 보내야 출력이 안 잘린다.
  prompt          받아쓰기 지시문 override (기본=축약 금지·인사말 보존 verbatim)
  model           기본 gemini-2.5-flash

stdout: {"items":[{청크별 결과}], "transcript_path":..., "chars":..., "duration_sec":...}
실패는 예외로 죽는다(비정상 종료 + stderr) — 반쪽 전사문을 성공인 척 남기지 않는다.
"""
import base64
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request

_ROOT = pathlib.Path(__file__).resolve().parents[2]  # indiebizOS/

_DEFAULT_PROMPT = (
    "이 오디오는 한국어 녹음입니다. 들리는 말을 빠짐없이 그대로 받아쓰세요.\n"
    "규칙:\n"
    "- 요약하지 말고 전문(verbatim)을 그대로 옮길 것.\n"
    "- 인사말, 도입 멘트, 마무리 멘트도 절대 생략하지 말 것.\n"
    "- 화자 표시나 타임스탬프 없이, 문단만 나누어 순수 텍스트로 출력할 것.\n"
    "- 명백한 말더듬(어, 음)은 정리해도 되지만 문장 내용은 바꾸지 말 것.\n"
    "- 설명이나 머리말 없이 받아쓴 본문만 출력할 것."
)


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    env = _ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GEMINI_API_KEY 를 환경변수에서도 .env 에서도 못 찾았습니다.")


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float((out.stdout or "").strip())
    except ValueError:
        raise SystemExit(f"길이를 못 읽었습니다(오디오 아님?): {path}\n{out.stderr.strip()[:400]}")


def _split(path: str, workdir: str, seconds: int) -> list:
    """mono 16k 48kbps mp3 로 분할 — inline 업로드 한도(25MB) 안에 넉넉히 들어온다."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", path, "-ac", "1", "-ar", "16000",
         "-b:a", "48k", "-f", "segment", "-segment_time", str(seconds),
         os.path.join(workdir, "part_%03d.mp3")],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg 분할 실패 (rc={proc.returncode})\n{proc.stderr.strip()[:800]}")
    return sorted(pathlib.Path(workdir).glob("part_*.mp3"))


def _transcribe(chunk: pathlib.Path, url: str, prompt: str):
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "audio/mpeg",
                             "data": base64.b64encode(chunk.read_bytes()).decode()}},
        ]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 32768,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.loads(r.read().decode())
    cands = data.get("candidates") or []
    if not cands:
        raise SystemExit(f"{chunk.name}: 응답에 candidates 가 없습니다 — {json.dumps(data)[:400]}")
    cand = cands[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    return text.strip(), cand.get("finishReason")


def main():
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}
    src = (args.get("path") or "").strip()
    if not src:
        raise SystemExit("path 는 필수입니다 — 받아쓸 오디오 파일 경로.")
    src = os.path.expanduser(src)
    if not os.path.exists(src):
        raise SystemExit(f"파일이 없습니다: {src}")

    seconds = int(args.get("segment_seconds") or 300)
    prompt = args.get("prompt") or _DEFAULT_PROMPT
    model = args.get("model") or "gemini-2.5-flash"
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={_api_key()}")

    out_path = args.get("out")
    if out_path:
        out_path = pathlib.Path(os.path.expanduser(out_path))
    else:
        out_path = (_ROOT / "outputs" / "transcripts" /
                    f"{pathlib.Path(src).stem}.transcript.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    duration = _duration(src)
    workdir = tempfile.mkdtemp(prefix="stt_")
    try:
        chunks = _split(src, workdir, seconds)
        if not chunks:
            raise SystemExit("분할 결과가 비었습니다 — 오디오 트랙이 없는 파일일 수 있습니다.")
        items, texts = [], []
        for c in chunks:
            text, finish = _transcribe(c, url, prompt)
            # ★잘림을 성공으로 넘기지 않는다 — 뒤에서 조용히 내용이 빈다.
            if finish and finish != "STOP":
                raise SystemExit(f"{c.name}: 응답이 정상 종료가 아닙니다(finishReason={finish}). "
                                 f"segment_seconds 를 줄여 다시 시도하세요.")
            items.append({"title": c.name, "chars": len(text), "finish": finish})
            texts.append(text)
            print(f"[{c.name}] chars={len(text)} finish={finish}", file=sys.stderr)
        full = "\n\n".join(texts)
        out_path.write_text(full, encoding="utf-8")
        print(json.dumps({
            "items": items,
            "transcript_path": str(out_path),
            "chars": len(full),
            "duration_sec": round(duration, 1),
            "source": src,
        }, ensure_ascii=False))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
