#!/usr/bin/env python3
"""내 목소리 나레이션 생성 (Qwen3-TTS 목소리 복제, 콜랩 GPU)

[self:script]{op:"run", id:"나레이션생성", args:{...}} 로 호출한다.

args (stdin JSON):
  lecture_id : 강의 id — 덱의 장별 스피커 노트를 읽어
               outputs/lectures/<id>/narration/<slide_id>.wav 로 굽는다.
               (deck video 가 이 폴더를 먼저 보고, 있으면 TTS 대신 그 파일을 쓴다)
  texts      : {"이름": "문장"} — 임시 문장용. out_dir 과 함께 쓴다.
  out_dir    : texts 모드의 저장 폴더 (기본 outputs/narration)
  voice      : data/voice/voices.json 의 키 (기본 kkj)
  gpu        : T4(기본)/L4/A100 — 계정 티어에 따라 가용성 다름
  force      : true 면 이미 있는 wav 도 다시 굽는다 (기본 false)
  speed      : 낭독 속도 배율 (기본 0.9 = 10% 느리게 — 표준). 1.0 이면 원속도.

산출: {"items":[{"title","meta","summary","url"}], "message": ...}

설계 메모 — 왜 이 모양인가:
  · 전용 IBL 액션을 만들지 않는다. colab.md 의 반-어휘-증식 규약을 따른다.
  · 함정 3종(아래 PIN/UPLOAD/BF16 주석)이 코드에 박혀 있다. 가이드로만 두면
    매번 다시 밟는다 — 특히 BF16 은 에러 없이 느려지기만 해서 알아채기 어렵다.
  · 레퍼런스 목소리는 코드가 아니라 data/voice/ 의 데이터다.
  · 속도는 모델에게 시키지 않고 **구운 뒤 타임스트레치**한다(ffmpeg atempo).
    Qwen3-TTS 에 속도 파라미터가 없고 "천천히 읽어" 같은 지시는 재현되지 않는다.
    atempo 는 피치를 보존한다 — 실측 스펙트럼 무게중심 비 0.98(리샘플이면 0.90).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
VOICE_DIR = ROOT / "data" / "voice"
SESSION = f"narr{os.getpid()}"

# 표준 낭독 속도 (2026-08-17 사용자 판정: 기본이 빠르다 → 10% 느리게를 표준으로)
# 값의 뜻 = 재생 배율. 0.9 면 길이가 1/0.9 = 약 1.11 배가 된다.
DEFAULT_SPEED = 0.9

# 함정 6(colab.md): 세션 상태 파일을 공유하면 다른 콜랩 작업과 얽힌다 → 전용 config
CFG = Path(tempfile.gettempdir()) / f"colab_{SESSION}.json"


def fail(msg, **extra):
    print(json.dumps({"error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


def colab_bin():
    """백엔드 프로세스의 PATH 에 ~/.local/bin 이 없을 수 있다 → 절대경로 폴백."""
    found = shutil.which("colab")
    if found:
        return found
    cand = Path.home() / ".local" / "bin" / "colab"
    if cand.exists():
        return str(cand)
    fail("colab CLI 를 찾을 수 없습니다. `uv tool install google-colab-cli` 후 재시도하세요.")


COLAB = colab_bin()


def run(args, timeout=600, check=True):
    p = subprocess.run([COLAB, "--config", str(CFG)] + args,
                       capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        blob = (p.stderr or "") + (p.stdout or "")
        # [PIN 함정] colab CLI 가 jupyter-kernel-client 를 버전 고정 없이 요구하는데
        # 1.0.0 에서 KernelClient → JupyterKernelClient 로 개명돼 모든 exec 이 죽는다.
        # 재설치(colab update 포함) 때마다 재발하므로 처방을 그대로 되돌려준다.
        if "has no attribute 'KernelClient'" in blob:
            raise RuntimeError(
                "colab CLI 의 의존성이 깨졌습니다 (jupyter-kernel-client 1.x). 처방:\n"
                "  uv pip install --python ~/.local/share/uv/tools/google-colab-cli/bin/python "
                "'jupyter-kernel-client<1.0'")
        raise RuntimeError(f"colab {' '.join(args[:2])} 실패 (rc={p.returncode})\n"
                           f"{blob[-1500:]}")
    return p


def remote(code, timeout=180):
    """짧은 파이썬 조각을 원격 커널에 흘려보낸다 (stdin 파이프)."""
    return subprocess.run([COLAB, "--config", str(CFG), "exec", "-s", SESSION,
                           "--timeout", "60"],
                          input=code, capture_output=True, text=True, timeout=timeout)


# ── 원격에서 돌 스크립트 ────────────────────────────────────────────────
# job.json 을 읽어 생성한다. 문장을 코드에 박지 않는 이유 = 따옴표·개행 지옥 회피.
REMOTE = r'''
import json, torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

job = json.load(open("/content/work/job.json", encoding="utf-8"))

# [BF16 함정] T4(sm_75)는 torch.cuda.is_bf16_supported() 가 True 를 반환하지만
# 네이티브 bf16 이 없다(에뮬레이션 — 에러 없이 느려지기만 한다).
# 아키텍처로 직접 판정한다: sm_80(Ampere) 이상만 진짜 bf16.
major, _ = torch.cuda.get_device_capability()
dtype = torch.bfloat16 if major >= 8 else torch.float16
try:
    import flash_attn  # noqa: F401
    attn = "flash_attention_2"
except ImportError:
    attn = "sdpa"
print(f"[gen] sm_{major}x dtype={dtype} attn={attn}", flush=True)

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0", dtype=dtype, attn_implementation=attn,
)

done = []
for it in job["items"]:
    wavs, sr = model.generate_voice_clone(
        text=it["text"], language="Korean",
        ref_audio="/content/work/ref.wav", ref_text=job["ref_text"],
    )
    out = f"/content/work/out_{it['id']}.wav"
    sf.write(out, wavs[0], sr)
    done.append({"id": it["id"], "seconds": round(len(wavs[0]) / sr, 2)})
    print(f"[gen] {it['id']} {done[-1]['seconds']}s", flush=True)

json.dump(done, open("/content/work/done.json", "w"), ensure_ascii=False)
print("[gen] 완료", flush=True)
'''


def retime(path, speed):
    """구운 wav 를 speed 배율로 타임스트레치 (피치 보존, 제자리 교체).

    ffmpeg atempo 는 0.5~100 만 받으므로 그 밖은 체인으로 나눈다.
    실패하면 원본을 그대로 두고 False — 속도 때문에 나레이션을 잃지 않는다.
    """
    if abs(speed - 1.0) < 0.001:
        return True
    chain, s = [], float(speed)
    while s < 0.5:
        chain.append(0.5)
        s /= 0.5
    while s > 100.0:
        chain.append(100.0)
        s /= 100.0
    chain.append(s)
    af = ",".join(f"atempo={c:.6f}" for c in chain)
    tmp = path.with_suffix(".retime.wav")
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-filter:a", af,
                        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
                       capture_output=True, text=True)
    if p.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True


def load_voice(key):
    meta_path = VOICE_DIR / "voices.json"
    if not meta_path.exists():
        fail(f"목소리 원장이 없습니다: {meta_path}")
    voices = json.loads(meta_path.read_text(encoding="utf-8"))
    if key not in voices:
        fail(f"'{key}' 목소리가 없습니다. 등록된 것: {sorted(voices)}")
    v = voices[key]
    wav = VOICE_DIR / v["audio"]
    if not wav.exists():
        fail(f"레퍼런스 오디오가 없습니다: {wav}")
    return wav, v["text"]


def collect_jobs(args):
    """(items, out_dir) — items = [{"id","text","target"}]"""
    force = bool(args.get("force"))
    lecture_id = args.get("lecture_id")

    if lecture_id:
        deck_path = ROOT / "outputs" / "lectures" / lecture_id / "deck.json"
        if not deck_path.exists():
            fail(f"강의를 찾을 수 없습니다: {deck_path}")
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        out_dir = deck_path.parent / "narration"
        items = []
        for sid in deck.get("slide_order") or []:
            note = ((deck.get("slides") or {}).get(sid) or {}).get("speaker_note") or ""
            note = note.strip()
            if not note:
                continue
            target = out_dir / f"{sid}.wav"
            if target.exists() and not force:
                continue
            items.append({"id": sid, "text": note, "target": target})
        return items, out_dir

    texts = args.get("texts") or {}
    if not texts:
        fail("lecture_id 또는 texts 중 하나는 필요합니다.")
    out_dir = Path(args.get("out_dir") or (ROOT / "outputs" / "narration"))
    items = []
    for name, text in texts.items():
        target = out_dir / f"{name}.wav"
        if target.exists() and not force:
            continue
        items.append({"id": name, "text": str(text), "target": target})
    return items, out_dir


def main():
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}

    ref_wav, ref_text = load_voice(args.get("voice") or "kkj")
    items, out_dir = collect_jobs(args)

    if not items:
        # 콜랩 세션을 아예 열지 않는다 — 할 일이 없으면 과금도 0
        print(json.dumps({
            "items": [], "message": "생성할 나레이션이 없습니다 (이미 전부 있거나 노트가 비었습니다). "
                                    "다시 구우려면 force:true"}, ensure_ascii=False))
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    gpu = args.get("gpu") or "T4"
    speed = float(args.get("speed") or DEFAULT_SPEED)
    t0 = time.time()
    started = False

    try:
        run(["new", "-s", SESSION, "--gpu", gpu], timeout=600)
        started = True
        run(["install", "-s", SESSION, "qwen-tts", "soundfile"], timeout=1200)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            job = {"ref_text": ref_text,
                   "items": [{"id": it["id"], "text": it["text"]} for it in items]}
            (td / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            (td / "gen.py").write_text(REMOTE, encoding="utf-8")

            remote("import os; os.makedirs('/content/work', exist_ok=True)")
            # [UPLOAD 함정] colab upload 의 상대경로는 /content 가 아니라 루트(/) 기준이다.
            # 반드시 절대경로로 목적지를 준다.
            run(["upload", "-s", SESSION, str(ref_wav), "/content/work/ref.wav"], timeout=600)
            run(["upload", "-s", SESSION, str(td / "job.json"), "/content/work/job.json"], timeout=300)

            # 문장당 40~60초(T4) + 모델 다운로드 5~10분
            budget = 1200 + 120 * len(items)
            p = run(["exec", "-s", SESSION, "-f", str(td / "gen.py"),
                     "--timeout", str(budget)], timeout=budget + 300)

        saved = []
        for it in items:
            r = run(["download", "-s", SESSION, f"/content/work/out_{it['id']}.wav",
                     str(it["target"])], timeout=300, check=False)
            if r.returncode == 0 and it["target"].exists():
                saved.append(it)

        if not saved:
            raise RuntimeError("생성물을 회수하지 못했습니다.\n" + (p.stdout or "")[-1000:])

        # 표준 낭독 속도 적용 — 회수 직후 제자리 타임스트레치(피치 보존).
        # 재실행 때 이미 있는 wav 는 건너뛰므로 두 번 늘어나지 않는다.
        retimed = sum(1 for it in saved if retime(it["target"], speed))

        elapsed = round(time.time() - t0)
        print(json.dumps({
            "items": [{
                "title": it["id"],
                "meta": f"{it['target'].stat().st_size // 1024} KB",
                "summary": it["text"][:60],
                "url": str(it["target"]),
            } for it in saved],
            "speed": speed,
            "message": (f"{len(saved)}개 나레이션 생성 완료 ({elapsed}초, {gpu}, "
                        f"속도 {speed}x{'' if retimed == len(saved) else f' — 재타이밍 {retimed}/{len(saved)}'}) "
                        f"→ {out_dir}"),
        }, ensure_ascii=False))

    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
    finally:
        if started:
            # 목소리는 생체정보다 — 원격 파일을 지우고 세션을 반납한다.
            # 실패해도 stop 은 반드시 시도한다 (안 끄면 최대 24시간 과금).
            try:
                remote("import glob, os\n"
                       "[os.remove(p) for p in glob.glob('/content/work/*')]")
            except Exception:
                pass
            subprocess.run([COLAB, "--config", str(CFG), "stop", "-s", SESSION],
                           capture_output=True, text=True, timeout=300)
        CFG.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
