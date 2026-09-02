"""나레이션 주입 배선 회귀 테스트 (렌더 없이 분기만 찌른다).

실행: .venv/bin/python3 backend/test_narration_injection.py

★[3]·[4] 는 2026-08-15 실측 결함의 회귀 방어다 — 미리 구운 오디오 분기가
길이 측정을 빠뜨려 씬이 기본 5초에 머물고 260초 나레이션이 69초로 잘렸다.
"TTS 를 안 부른다"만 검사하면 이 결함을 못 잡는다. 씬 길이까지 봐야 한다.
"""
import importlib.util, json, shutil, sys, tempfile
from pathlib import Path

# 스크립트형 테스트(모듈 레벨 실행 + sys.exit) — pytest 수집이 임포트만 해도 본문이
# 돌아버리므로 pytest 아래서는 모듈 단위 스킵. 의존도 로컬 전용이다:
# 음성 참조 파일(data/voice/ 원장의 default 항목, 미추적 개인 데이터)·playwright(requirements-tools).
if __name__ != "__main__":
    import pytest
    pytest.skip("로컬 전용 스크립트 테스트 — .venv/bin/python3 backend/test_narration_injection.py 로 직접 실행",
                allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
def _default_ref() -> Path:
    """원장(voices.json)에서 default: true 인 목소리의 wav — 개인 파일 이름을 시험에 박지 않는다."""
    voices = json.loads((ROOT / "data" / "voice" / "voices.json").read_text(encoding="utf-8"))
    key = next((k for k, v in voices.items() if v.get("default")), next(iter(voices)))
    return ROOT / "data" / "voice" / voices[key]["audio"]


REF = _default_ref()
import wave as _wave
with _wave.open(str(REF)) as _w:
    REF_SECONDS = _w.getnframes() / _w.getframerate()
fails = []


def check(label, ok, detail=""):
    print(f"[{'OK ' if ok else '실패'}] {label}{('  — ' + detail) if detail else ''}")
    if not ok:
        fails.append(label)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mp = load("mp_handler", ROOT / "data/packages/installed/tools/media_producer/handler.py")

tts_calls = {"n": 0}


async def fake_tts(text, path, *a, **k):
    tts_calls["n"] += 1
    shutil.copy(REF, path)          # 실제 TTS 처럼 파일을 남긴다(길이 측정이 성립하도록)


class Sentinel(Exception):
    """렌더 단계 진입 = 나레이션 단계를 무사히 통과했다는 표식."""


mp.generate_tts = fake_tts
import playwright.sync_api as pw
pw.sync_playwright = lambda: (_ for _ in ()).throw(Sentinel())


def run(scenes, **extra):
    tts_calls["n"] = 0
    with tempfile.TemporaryDirectory() as td:
        try:
            mp.create_html_video({"scenes": scenes, **extra}, td)
        except Sentinel:
            pass
        except Exception as e:
            print(f"    (렌더 단계 중단: {type(e).__name__})")
    return scenes


# [1][2] 어느 오디오를 쓰는가
run([{"html": "<html></html>", "duration": 3}],
    narration_texts=["TTS 로 가면 안 된다"], narration_audio_paths=[str(REF)])
check("preset 있으면 TTS 안 부름", tts_calls["n"] == 0, f"호출 {tts_calls['n']}회")

run([{"html": "<html></html>", "duration": 3}], narration_texts=["이건 TTS 로"])
check("preset 없으면 종전대로 TTS", tts_calls["n"] == 1, f"호출 {tts_calls['n']}회")

# [3][4] ★길이를 쟀는가 = 씬이 나레이션에 맞춰 늘어났는가
s = run([{"html": "<html></html>", "duration": 3}],
        narration_texts=["노트"], narration_audio_paths=[str(REF)])
check("preset 나레이션 길이만큼 씬이 늘어남", s[0]["duration"] > REF_SECONDS,
      f"{s[0]['duration']:.2f}초 (기대 >{REF_SECONDS})")

s = run([{"html": "<html></html>", "duration": 3}], narration_texts=["노트"])
check("TTS 경로도 씬이 늘어남(회귀)", s[0]["duration"] > REF_SECONDS,
      f"{s[0]['duration']:.2f}초")

# [5] 혼용 — 1장은 preset, 1장은 TTS, 1장은 무나레이션
s = run([{"html": "<html></html>", "duration": 3} for _ in range(3)],
        narration_texts=["preset 장", "TTS 장", ""],
        narration_audio_paths=[str(REF), None, None])
ok = s[0]["duration"] > REF_SECONDS and s[1]["duration"] > REF_SECONDS and s[2]["duration"] == 3
check("혼용(preset/TTS/무나레이션) 각각 올바름", ok,
      f"{[round(x['duration'], 2) for x in s]}, TTS 호출 {tts_calls['n']}회")

# [6] lecture_workspace 가 narration/<sid>.wav 를 집어 넘기는가
#     (렌더 본체는 2026-08-17 분할로 handler._deck_video_build → deck_video.build)
lw = load("lw_handler", ROOT / "data/packages/installed/tools/lecture_workspace/handler.py")
dv = sys.modules["deck_video"]          # handler 가 import deck_video 로 이미 실어 놓음
with tempfile.TemporaryDirectory() as td:
    lec = Path(td) / "L"
    (lec / "slides").mkdir(parents=True)
    (lec / "narration").mkdir()
    for sid in ("s1", "s2"):
        (lec / "slides" / f"{sid}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 40)
    shutil.copy(REF, lec / "narration" / "s1.wav")
    deck = {"slide_order": ["s1", "s2"],
            "slides": {"s1": {"png_file": "slides/s1.png", "speaker_note": "노트1"},
                       "s2": {"png_file": "slides/s2.png", "speaker_note": "노트2"}}}
    (lec / "deck.json").write_text(json.dumps(deck), encoding="utf-8")
    dv.lecture_store.lecture_dir = lambda lid: lec
    dv.lecture_store.read_deck = lambda lid: deck
    dv._scene_html_from_png = lambda png, w, h: "<html></html>"
    cap = {}

    class FakeMedia:
        def create_html_video(self, tool_input, out):
            cap.update(tool_input)
            return "HTML 동영상 제작 완료: /tmp/x.mp4 (테스트)"

    dv._load_media_handler = lambda: FakeMedia()
    res = dv.build("L", {})

p = cap.get("narration_audio_paths")
check("narration/<sid>.wav 경로 조립", isinstance(p, list) and len(p) == 2
      and bool(p[0]) and p[0].endswith("narration/s1.wav") and p[1] is None, str(p))
check("preset_narration 집계", res.get("preset_narration") == 1, str(res.get("preset_narration")))

print("\n결과:", "전부 통과" if not fails else f"{len(fails)}건 실패 — {fails}")
sys.exit(1 if fails else 0)
