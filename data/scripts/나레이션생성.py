#!/usr/bin/env python3
"""등록된 목소리로 나레이션 생성 (Qwen3-TTS 목소리 복제, Modal GPU)

[self:script]{op:"run", id:"나레이션생성", args:{...}} 로 호출한다.

args (stdin JSON):
  lecture_id : 강의 id — 덱의 장별 스피커 노트를 읽어
               outputs/lectures/<id>/narration/<slide_id>.wav 로 굽는다.
               (deck video 가 이 폴더를 먼저 보고, 있으면 TTS 대신 그 파일을 쓴다)
  texts      : {"이름": "문장"} — 임시 문장용. out_dir 과 함께 쓴다.
  out_dir    : texts 모드의 저장 폴더 (기본 outputs/narration)
  texts_file : 위 texts 를 담은 JSON 파일 경로 (원고가 길 때 args 대신 파일로)
  voice      : data/voice/voices.json 의 키·이름·별칭 (기본 = 원장에서 default: true 인 항목)
  gpu        : T4(기본). Modal 이 받는 GPU 이름 — A10G 는 확인됨. L4 는 2026-11-12 에 배정되지 않아 무소식으로 끊겼다
  containers : 동시에 띄울 컨테이너 수 (기본 = 분량에 맞춰 자동, 최대 6). 1 이면 하나에서 원고 순서대로.
  force      : true 면 이미 있는 wav 도 다시 굽는다 (기본 false)
  speed      : 낭독 속도 배율 (기본 1.0 = 원속도 — 표준). 0.9 면 10% 느리게.
  chunk      : 문장 단위 굽기 (기본 true — 2026-09-09 표준). false 면 장 하나를 한 호출에 통짜로.
  chunk_max_chars / chunk_gap / chunk_tail : 조각 상한 글자(70)·조각 사이 숨(0.35s)·장 끝 여운(0.40s).
  batch      : 컨테이너 한 호출에 굽는 조각 수 (기본 4 — 2026-09-10). 프롬프트는 컨테이너당 1회. OOM 이면 반으로.

산출: {"items":[{"title","meta","summary","url"}], "message": ..., "sec_per_char": 실측, "containers": n}
진행: stderr 로 `[  123s] …` 줄을 흘린다 — background 실행이면 로그 파일에 실시간으로 쌓여
      [self:script]{op:"status"} 가 '어디까지'를 보여 준다. 예산은 글자 수×실측 속도의 캡이고,
      실제 중단 기준은 "진행 줄이 STALL_GEN 초 동안 없음"이다.

설계 메모 — 왜 이 모양인가:
  · 전용 IBL 액션을 만들지 않는다. colab.md 의 반-어휘-증식 규약을 따른다.
  · 원격 부분(MODAL_APP)은 이 파일 안의 문자열이다 — 실행할 때 임시 파일로 써서 `modal run` 에 넘긴다.
    스크립트 하나가 파일 하나로 남는다.
  · 앱은 실행마다 새로 뜨고 끝나면 사라진다(배포해 두지 않는다). 저장소 밖에서 따로 낡아 가는 배포본이
    없고, 로컬 프로세스가 죽으면 Modal 이 앱을 멈춘다. 계정에 남는 것은 이미지 캐시와 공개 모델 가중치 볼륨뿐.
  · 조각은 구워지는 대로 로컬로 흘러온다 — 회수 단계가 따로 없고, 도중에 끊겨도 온전한 장은 건진다.
  · 레퍼런스 목소리는 코드가 아니라 data/voice/ 의 데이터다. 원격에는 함수 인자로만 넘긴다
    (볼륨·이미지에 저장하지 않는다 — 목소리는 생체정보다).
  · BF16 함정이 코드에 박혀 있다. 에러 없이 느려지기만 해서 알아채기 어렵다.
  · 속도는 모델에게 시키지 않고 **구운 뒤 타임스트레치**한다(ffmpeg atempo).
    Qwen3-TTS 에 속도 파라미터가 없고 "천천히 읽어" 같은 지시는 재현되지 않는다.
    atempo 는 피치를 보존한다 — 실측 스펙트럼 무게중심 비 0.98(리샘플이면 0.90).
  · 2026-11-12 콜랩에서 Modal 로 옮겼다. 같은 원고(11장 44조각 2,000자, T4·batch 4) 실측:
    콜랩 423초 → Modal 컨테이너 하나 238초 · 여섯 129초. 옛 콜랩 경로는 git 이력에 있다.
"""
import json
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
VOICE_DIR = ROOT / "data" / "voice"

# 표준 낭독 속도 (2026-09-01 사용자 판정: 보정을 없애고 본래 목소리 속도로)
# 값의 뜻 = 재생 배율. 1.0 = 무보정(retime 이 그대로 통과). 0.9 를 넘기면 10% 느리게.
DEFAULT_SPEED = 1.0

# 문장 단위 굽기 (2026-09-09 표준 — 문장 끝 뭉개짐의 원인 확정 실측에 따름)
# 긴 원고를 한 호출에 구우면 뒤로 갈수록 발화가 압축돼 문장 끝이 뭉개진다(같은 문장이 통짜 안에서는
# 1.10초, 단독이면 1.95초 — 1.77배). 처방은 텍스트 부호(마침표는 이미 다 있다)가 아니라 **호출 단위**:
# 문장(짧은 문장은 두엇)마다 따로 굽고 사이에 숨을 넣어 접합하며 끝에 여운을 붙인다. chunk:false = 옛 통짜.
DEFAULT_CHUNK = True
CHUNK_MAX_CHARS = 70   # 한 호출에 담을 최대 글자 수 — 이보다 짧은 연속 문장은 한 호출로 묶는다
CHUNK_GAP = 0.35       # 조각(호출) 사이 숨 (초)
CHUNK_TAIL = 0.40      # 장 끝 여운 (초)
SR = 24000             # 접합 시 통일할 샘플레이트 (Qwen3-TTS 출력·레퍼런스와 같은 자)

# 원격 호출 단위 (2026-09-10): 프롬프트는 컨테이너당 1회, 조각은 batch 개씩 한 호출에 굽는다.
# 조각당 고정 비용(참조 음성 인코딩 + 호출 왕복)이 165조각에서 55분을 만들던 뿌리.
DEFAULT_BATCH = 4

# 예산은 조각 수가 아니라 **실측 속도**로 잡는다(2026-11-12 실측, Modal T4·batch 4·컨테이너 하나:
# 2,023자 → 생성 190초 = 0.094초/자). 이 값은 상한(캡)일 뿐이고 실제 감시는 아래 STALL_* —
# "진행 줄이 멈추면" 끊는다. 캡은 넉넉히, 감시는 촘촘히.
SEC_PER_CHAR = 0.1
BUDGET_MARGIN = 1.5
LOAD_BUDGET = 600      # 앱 기동·컨테이너 준비. 평소 45초 안팎, 이미지를 새로 짓고 가중치를 처음 받는 날은 4~5분
STALL_LOAD = 600       # 준비 중 무소식 허용(초)
STALL_GEN = 300        # 생성 중 무소식 허용(초) — 한 배치는 20초 안팎이다

# 컨테이너 수 (2026-11-12 실측): 컨테이너마다 준비 46~72초를 따로 내고 전체 시간은 가장 느린 것이 정한다.
# 그래서 컨테이너 하나가 맡는 생성이 준비만큼은 되도록(약 60초) 나눈다. 여섯이 상한 — 그 위는 GPU 시간만 는다.
CONTAINER_TARGET_GEN = 60
MAX_CONTAINERS = 6


def fail(msg, **extra):
    print(json.dumps({"error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


_T0 = time.time()
_PROGRESS_STATE = {}


def progress(msg, phase=None, **metrics):
    """진행 줄 — stderr 로 흘린다. stdout 은 통화(JSON) 자리라 섞지 않는다.

    백그라운드 러너(_bg_runner)가 stderr 를 로그 파일에 **실시간**으로 쓰므로, status 폴링이
    '돌고 있다'만이 아니라 '어디까지'를 본다(2026-09-10 — 40분 동안 running 만 보던 문제의 처방).
    """
    _PROGRESS_STATE.update(metrics)
    if phase:
        _PROGRESS_STATE["phase"] = phase
    record = {**_PROGRESS_STATE, "elapsed_s": round(time.time() - _T0)}
    print(f"[{time.time() - _T0:6.0f}s] {msg} PROGRESS " + json.dumps(record, ensure_ascii=False),
          file=sys.stderr, flush=True)


def modal_bin():
    """백엔드 프로세스의 PATH 에 ~/.local/bin 이 없을 수 있다 → 절대경로 폴백."""
    found = shutil.which("modal")
    if found:
        return found
    cand = Path.home() / ".local" / "bin" / "modal"
    if cand.exists():
        return str(cand)
    fail("modal CLI 를 찾을 수 없습니다. `uv tool install modal` 후 `modal token new` 로 인증하고 재시도하세요.")


# ── 원격에서 돌 앱 ──────────────────────────────────────────────────────
# 임시 파일로 써서 `modal run` 에 넘긴다. 위쪽(클래스)은 컨테이너에서, main 은 로컬에서 돈다.
# 문장을 코드에 박지 않고 job.json 으로 넘기는 이유 = 따옴표·개행 지옥 회피.
MODAL_APP = r'''
import asyncio
import json
import time
from pathlib import Path

import modal

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

app = modal.App("narration")
# 판을 고정한다 — 이미지는 이 정의가 바뀔 때만 다시 지어지므로 재설치마다 깨지던 의존성 문제가 없다.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "sox", "libsndfile1")
    .uv_pip_install("qwen-tts==0.1.1", "soundfile")
    .env({"HF_HOME": "/cache/hf", "HF_HUB_DISABLE_TELEMETRY": "1"})
)
# 공개 모델 가중치만 담는다. 목소리는 여기 들어가지 않는다.
weights = modal.Volume.from_name("narration-weights", create_if_missing=True)


@app.cls(image=image, gpu="T4", volumes={"/cache": weights}, timeout=3600,
         startup_timeout=1800, scaledown_window=20)
class Narrator:
    @modal.enter()
    def load(self):
        t0 = time.time()
        import torch
        from qwen_tts import Qwen3TTSModel
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
        self.model = Qwen3TTSModel.from_pretrained(
            MODEL_ID, device_map="cuda:0", dtype=dtype, attn_implementation=attn)
        weights.commit()   # 처음 받은 가중치를 볼륨에 남긴다 (이미 있으면 할 일 없음)
        self.info = {"gpu": torch.cuda.get_device_name(0), "dtype": str(dtype), "attn": attn,
                     "ready_s": round(time.time() - t0)}
        self.prompts = {}
        print(f"[gen] 모델 적재 완료 {self.info}", flush=True)

    @modal.method()
    def generate(self, ref_bytes: bytes, ref_text: str, items: list, batch: int):
        """조각을 batch 개씩 굽고, 구워지는 대로 내보낸다(생성기)."""
        import hashlib
        import io
        import os
        import soundfile as sf
        import torch
        yield {"event": "loaded", **self.info}
        t0 = time.time()
        # [프롬프트 1회] 레퍼런스 음성의 화자 임베딩·코드는 조각마다 같다 — 한 번 만들어 재사용한다.
        # 레퍼런스는 인자로 받아 임시 파일로만 거치고 곧바로 지운다.
        key = hashlib.sha1(ref_bytes + ref_text.encode("utf-8")).hexdigest()
        prompt = self.prompts.get(key)
        if prompt is None:
            path = f"/tmp/ref_{key[:8]}.wav"
            with open(path, "wb") as f:
                f.write(ref_bytes)
            try:
                prompt = self.model.create_voice_clone_prompt(ref_audio=path, ref_text=ref_text)
            finally:
                os.remove(path)
            self.prompts[key] = prompt
        t1 = time.time()
        i, n = 0, len(items)
        while i < n:
            group = items[i:i + batch]
            try:
                wavs, sr = self.model.generate_voice_clone(
                    text=[g["text"] for g in group], language="Korean", voice_clone_prompt=prompt)
            except torch.cuda.OutOfMemoryError:
                # 배치가 GPU 메모리를 넘기면 반으로 줄여 다시 — 1까지 내려가면 그 조각은 홀로 굽는다.
                torch.cuda.empty_cache()
                if batch > 1:
                    batch = max(1, batch // 2)
                    print(f"[gen] OOM → batch {batch}", flush=True)
                    continue
                raise
            out = []
            for g, w in zip(group, wavs):
                buf = io.BytesIO()
                sf.write(buf, w, sr, format="WAV", subtype="PCM_16")
                out.append({"n": g["n"], "wav": buf.getvalue(), "seconds": round(len(w) / sr, 2)})
            i += len(group)
            yield {"event": "batch", "items": out}
        yield {"event": "end", "prompt_s": round(t1 - t0, 1), "gen_s": round(time.time() - t1, 1)}


def emit(**event):
    print("NARR " + json.dumps(event, ensure_ascii=False), flush=True)


@app.local_entrypoint()
async def main(job: str, out: str):
    spec = json.loads(Path(job).read_text(encoding="utf-8"))
    out_dir = Path(out)
    ref = Path(spec["ref_wav"]).read_bytes()
    emit(event="app", app_id=app.app_id)
    narrator = Narrator.with_options(gpu=spec["gpu"], timeout=int(spec["timeout"]))()
    total = sum(len(s) for s in spec["shards"])
    done = 0

    async def one(k, items):
        nonlocal done
        async for msg in narrator.generate.remote_gen.aio(ref, spec["ref_text"], items, int(spec["batch"])):
            if msg["event"] == "batch":
                for it in msg["items"]:
                    (out_dir / f"out_{int(it['n']):04d}.wav").write_bytes(it["wav"])
                done += len(msg["items"])
                emit(event="batch", shard=k, done=done, total=total,
                     audio_s=round(sum(it["seconds"] for it in msg["items"]), 1))
            else:
                emit(shard=k, **msg)

    await asyncio.gather(*(one(k, items) for k, items in enumerate(spec["shards"], 1)))
    emit(event="done", done=done, total=total)
'''

_APP_ID = re.compile(r"\bap-[A-Za-z0-9]{12,}\b")


def plan_containers(total_chars, n_jobs, requested=None):
    """컨테이너 수 — 지정이 있으면 그 값, 없으면 분량에 맞춘다(컨테이너 하나가 약 60초어치 생성)."""
    if requested not in (None, ""):
        return max(1, min(int(requested), n_jobs, MAX_CONTAINERS))
    estimated = SEC_PER_CHAR * total_chars
    return max(1, min(MAX_CONTAINERS, n_jobs, round(estimated / CONTAINER_TARGET_GEN)))


def make_shards(jobs, k):
    """조각을 k 묶음으로 나눈다. k==1 이면 원고 순서 그대로, 여럿이면 글자 수가 고르게(긴 것부터 가벼운 묶음에)."""
    if k <= 1:
        return [list(jobs)]
    bins, load = [[] for _ in range(k)], [0] * k
    for j in sorted(jobs, key=lambda j: -len(j["text"])):
        i = load.index(min(load))
        bins[i].append(j)
        load[i] += len(j["text"])
    return [b for b in bins if b]


def new_run_info():
    return {"app_id": None, "returncode": None, "loaded": 0, "done": 0, "gen_s": 0.0, "prompt_s": 0.0,
            "gpu": None, "stalled": None}


def _stop_child(p):
    """아직 도는 `modal run` 을 멈춘다 — SIGINT 를 받으면 Modal 클라이언트가 앱을 멈추고 나간다."""
    if p.poll() is not None:
        return
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=10)


def run_modal_streaming(modal, app_file, job_file, out_dir, info, stall_load=STALL_LOAD, stall_gen=STALL_GEN):
    """`modal run` 을 돌리며 `NARR {…}` 줄을 **오는 대로** 진행 채널로 넘긴다.

    끊는 기준은 숫자 예산이 아니라 **진행이 멈췄는가**다(2026-09-10):
      · 첫 컨테이너가 모델을 올리기 전엔 stall_load 초(그동안은 아무 출력이나 살아 있다는 표시로 친다),
        그 뒤엔 stall_gen 초 동안 조각이 안 오면 끊는다.
      · 예산 캡은 원격 함수의 timeout 으로만 쓴다(job.json 의 timeout).
    info(new_run_info) 를 **받아서 채운다** — 도중에 이 프로세스가 중단돼도 부른 쪽 finally 가 app_id 를 안다.
    반환: 출력 전문. 실패를 예외로 올리지 않는다 — 받은 조각으로 온전한 장을 건질지는 부른 쪽이 정한다.
    어떻게 나가든(정상·무소식·중단) `modal run` 은 여기서 끝낸다.
    """
    import queue
    import threading
    cmd = [modal, "run", f"{app_file}::main", "--job", str(job_file), "--out", str(out_dir)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         cwd=str(Path(app_file).parent))
    q = queue.Queue()

    def _pump():
        # 읽기 스레드 — select 로 파이프를 보면 TextIO 버퍼에 남은 줄을 놓친다(끝 줄·오류가 사라진다).
        for line in p.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    lines, last = [], time.time()
    try:
        while True:
            limit = stall_gen if info["loaded"] else stall_load
            try:
                line = q.get(timeout=5)
            except queue.Empty:
                line = ""
            if line is None:
                try:
                    p.wait(timeout=60)   # 출력이 닫혔다 — 스스로 끝나기를 기다린다
                except subprocess.TimeoutExpired:
                    pass
                break
            if line:
                lines.append(line)
                s = line.strip()
                if not info["loaded"]:
                    last = time.time()   # 준비 중에는 이미지 빌드·기동 로그도 살아 있다는 표시
                if not info["app_id"]:
                    found = _APP_ID.search(s)
                    if found:
                        info["app_id"] = found.group(0)
                        progress("Modal 앱 시작 — 컨테이너 준비 중", phase="model-load", resource=info["app_id"],
                                 resource_state="running", stall_after_s=stall_load)
                if s.startswith("NARR "):
                    try:
                        ev = json.loads(s[5:])
                    except ValueError:
                        continue
                    last = time.time()
                    kind = ev.get("event")
                    if kind == "loaded":
                        info["loaded"] += 1
                        info["gpu"] = ev.get("gpu")
                        progress(f"[gen] 컨테이너 {ev.get('shard')} 모델 적재 완료 ({ev.get('gpu')}, {ev.get('ready_s')}초)",
                                 phase="generate", stall_after_s=stall_gen)
                    elif kind == "batch":
                        info["done"] = ev["done"]
                        progress(f"[gen] {ev['done']}/{ev['total']} · 컨테이너 {ev.get('shard')} · {ev.get('audio_s')}s audio",
                                 phase="generate", completed=ev["done"], total=ev["total"], stall_after_s=stall_gen)
                    elif kind == "end":
                        info["gen_s"] += float(ev.get("gen_s") or 0)
                        info["prompt_s"] += float(ev.get("prompt_s") or 0)
            if time.time() - last > limit:
                info["stalled"] = f"{'생성' if info['loaded'] else '준비'} 단계에서 {limit}초 동안 무소식"
                break
    finally:
        _stop_child(p)   # 정상 종료면 할 일이 없다. 무소식·중단이면 여기서 끝낸다.
        info["returncode"] = p.returncode
    return "".join(lines)


def release_modal_app(modal, app_id):
    """실행이 끝난 뒤 그 앱이 정말 멈췄는지 본다. 살아 있으면 멈춘다. 반환: 'released' | 'not_started' | 'unknown'.

    평소엔 `modal run` 이 끝나면서 앱도 멈춘다 — 이 확인은 로컬 프로세스가 비정상으로 죽은 경우를 위한 것이다
    (2026-09-10 콜랩 실사고: 정지 실패로 VM 이 켜진 채 과금됐다). 남의 앱은 건드리지 않는다: 이 실행의 app_id 만.
    app_id 가 없으면 앱이 뜨기 전에 끝난 것이다 — 반납할 것이 없다.
    """
    if not app_id:
        return "not_started"
    try:
        listed = subprocess.run([modal, "app", "list", "--json"], capture_output=True, text=True, timeout=60)
        rows = json.loads(listed.stdout) if listed.returncode == 0 else []
        row = next((r for r in rows if r.get("app_id") == app_id), None)
        if row is not None and str(row.get("state") or "").lower() == "stopped":
            return "released"
        stopped = subprocess.run([modal, "app", "stop", "-y", app_id], capture_output=True, text=True, timeout=120)
        return "released" if stopped.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


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


_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text, max_chars=CHUNK_MAX_CHARS):
    """원고를 굽기 호출 단위로 나눈다 — 문장 경계(. ! ? …)로 자르고, 짧은 문장은 max_chars 까지 묶는다.

    왜 문장 단위인가(2026-09-09 실측): 긴 텍스트를 한 호출에 구우면 뒤로 갈수록 발화가 압축돼
    문장 끝이 뭉개진다. 같은 문장이 통짜 안에서는 1.10초, 단독이면 1.95초(1.77배).
    """
    parts = [p.strip() for p in _SENT_SPLIT.split(str(text).strip()) if p.strip()]
    groups, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > max_chars:
            groups.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        groups.append(cur)
    return groups or [str(text).strip()]


def _silence(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono",
                    "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", str(path)],
                   check=True, capture_output=True, text=True)


def concat_chunks(parts, target, gap=CHUNK_GAP, tail=CHUNK_TAIL):
    """문장 wav 들을 숨(gap)으로 잇고 끝에 여운(tail)을 붙여 target 으로 — 24kHz 모노 PCM 으로 통일.

    끝 여운을 붙이는 이유: 모델은 단독 굽기에서도 끝무음을 0.01~0.06초밖에 남기지 않아
    다음 장·인사말과 붙으면 마지막 음절이 잘려 들린다.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        gap_wav, tail_wav = td / "gap.wav", td / "tail.wav"
        _silence(gap_wav, gap)
        _silence(tail_wav, tail)
        seq = []
        for i, p in enumerate(parts):
            norm = td / f"p{i:03d}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ar", str(SR), "-ac", "1",
                            "-c:a", "pcm_s16le", str(norm)], check=True, capture_output=True, text=True)
            if i:
                seq.append(gap_wav)
            seq.append(norm)
        seq.append(tail_wav)
        lst = td / "list.txt"
        lst.write_text("".join(f"file '{s}'\n" for s in seq), encoding="utf-8")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:a", "pcm_s16le", str(target)], check=True, capture_output=True, text=True)


def _ledger():
    meta_path = VOICE_DIR / "voices.json"
    if not meta_path.exists():
        fail(f"목소리 원장이 없습니다: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def default_voice():
    """기본 목소리 키 — 원장에서 `default: true` 인 항목. 기본값은 코드가 아니라 데이터다.

    이 몸을 쓰는 사람이 누구든 스크립트는 같다: 표시가 없고 목소리가 하나뿐이면 그것,
    여럿인데 표시가 없으면 고르지 않고 거절한다(추측한 기본값은 남의 목소리다).
    """
    voices = _ledger()
    marked = [k for k, v in voices.items() if v.get("default")]
    if len(marked) == 1:
        return marked[0]
    if len(marked) > 1:
        fail(f"원장에 default 가 여럿입니다: {sorted(marked)} — voices.json 에서 하나만 남기세요.")
    if len(voices) == 1:
        return next(iter(voices))
    fail("기본 목소리가 없습니다 — voices.json 의 한 항목에 \"default\": true 를 표시하거나 voice 를 지정하세요.")


def load_voice(key):
    """원장에서 목소리 해소 — 키 · 이름 · 별칭(aliases) 순 (2026-09-02 별칭 개통).

    별칭은 코드가 아니라 원장(voices.json)의 데이터다 — 사람이 부르는 이름("홍길동")과
    파일 키("hgd")는 다른 층이고, 부르는 이름이 늘어난다고 코드가 늘면 안 된다.
    """
    voices = _ledger()

    def norm(s):
        return "".join(str(s or "").split()).lower()

    if key in voices:
        resolved = key
    else:
        want = norm(key)
        hits = [k for k, meta in voices.items()
                if want and (norm(k) == want or norm(meta.get("name")) == want
                             or want in [norm(a) for a in (meta.get("aliases") or [])])]
        if len(hits) > 1:
            fail(f"'{key}' 가 여러 목소리에 걸립니다: {sorted(hits)} — 키로 지정하세요.")
        if not hits:
            known = ", ".join(f"{k}({v.get('name')})" for k, v in sorted(voices.items()))
            fail(f"'{key}' 목소리가 없습니다. 등록된 것: {known}")
        resolved = hits[0]
        print(f"[voice] 별칭 해소: {key} → {resolved}")
    v = voices[resolved]
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
    # texts_file: 원고가 길면 args 에 통째로 싣지 않고 {"이름": "문장"} JSON 파일로 넘긴다
    if not texts and args.get("texts_file"):
        texts = json.loads(Path(args["texts_file"]).read_text(encoding="utf-8"))
    if not texts:
        fail("lecture_id 또는 texts(texts_file) 중 하나는 필요합니다.")
    out_dir = Path(args.get("out_dir") or (ROOT / "outputs" / "narration"))
    items = []
    for name, text in texts.items():
        target = out_dir / f"{name}.wav"
        if target.exists() and not force:
            continue
        items.append({"id": name, "text": str(text), "target": target})
    return items, out_dir


def _exit_on_signal(signum, _frame):
    sys.exit(128 + signum)


def main():
    # 종료 신호(러너의 취소·타임아웃)에도 finally 가 돌게 한다 — 그래야 `modal run` 을 끝내고 반납을 확인한다.
    signal.signal(signal.SIGTERM, _exit_on_signal)
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}

    ref_wav, ref_text = load_voice(args.get("voice") or default_voice())
    items, out_dir = collect_jobs(args)

    if not items:
        # 원격을 아예 열지 않는다 — 할 일이 없으면 과금도 0
        print(json.dumps({
            "items": [], "message": "생성할 나레이션이 없습니다 (이미 전부 있거나 노트가 비었습니다). "
                                    "다시 구우려면 force:true"}, ensure_ascii=False))
        return

    modal = modal_bin()
    out_dir.mkdir(parents=True, exist_ok=True)
    gpu = args.get("gpu") or "T4"
    speed = float(args.get("speed") or DEFAULT_SPEED)
    chunk = args.get("chunk")
    chunk = DEFAULT_CHUNK if chunk is None else bool(chunk)
    max_chars = int(args.get("chunk_max_chars") or CHUNK_MAX_CHARS)
    gap = float(args["chunk_gap"]) if args.get("chunk_gap") is not None else CHUNK_GAP
    tail = float(args["chunk_tail"]) if args.get("chunk_tail") is not None else CHUNK_TAIL
    batch = max(1, int(args.get("batch") or DEFAULT_BATCH))

    # 굽기 호출 단위 = 문장 조각(chunk). 조각은 번호(n)로 원격을 오가고, 받은 뒤 장 단위로 접합한다.
    jobs = []
    for it in items:
        it["pieces"] = split_sentences(it["text"], max_chars) if chunk else [it["text"]]
        for piece in it["pieces"]:
            jobs.append({"n": len(jobs), "text": piece, "parent": it})

    t0 = time.time()
    total_chars = sum(len(j["text"]) for j in jobs)
    containers = plan_containers(total_chars, len(jobs), args.get("containers"))
    shards = make_shards(jobs, containers)
    # 캡 = 준비 + 실측 속도×글자 수×여유. 조각 수는 캡에 안 들어간다 — 배치가 조각당 비용을 바꾸기 때문.
    cap = int(LOAD_BUDGET + SEC_PER_CHAR * total_chars * BUDGET_MARGIN)
    _PROGRESS_STATE.update(total=len(jobs), completed=0, total_chars=total_chars,
                           expected_seconds=cap, expected_sec_per_char=SEC_PER_CHAR,
                           resource="modal", resource_state="not_started", retrieval="pending", cleanup="pending")
    progress(f"{len(items)}장 {len(jobs)}조각 {total_chars}자 · batch {batch} · {gpu}×{len(shards)} · "
             f"예상 생성 {SEC_PER_CHAR * total_chars / len(shards) / 60:.0f}분(캡 {cap // 60}분, 무소식 {STALL_GEN}초면 중단)")

    info, started = new_run_info(), False
    try:
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            raw_dir = td / "out"
            raw_dir.mkdir()
            job = {"ref_wav": str(ref_wav), "ref_text": ref_text, "batch": batch, "gpu": gpu, "timeout": cap,
                   "shards": [[{"n": j["n"], "text": j["text"]} for j in s] for s in shards]}
            (td / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            (td / "narration_modal_app.py").write_text(MODAL_APP, encoding="utf-8")

            progress("Modal 앱 여는 중", phase="session-start", stall_after_s=STALL_LOAD)
            gen_t0 = time.time()
            started = True
            p_out = run_modal_streaming(modal, td / "narration_modal_app.py", td / "job.json", raw_dir, info)
            gen_secs = time.time() - gen_t0
            remote_error = None
            if info["returncode"] != 0 or info["stalled"]:
                remote_error = info["stalled"] or f"modal run 실패 (rc={info['returncode']})"

            # 조각은 오는 대로 raw_dir 에 쌓였다 — 따로 회수할 것이 없다. 조각이 다 있는 장만 접합한다.
            progress("조각 접합 중", phase="download", completed=info["done"], retrieval="running", stall_after_s=600)
            saved, failed = [], []
            for it in items:
                got = [raw_dir / f"out_{j['n']:04d}.wav" for j in jobs if j["parent"] is it]
                if not all(g.exists() for g in got):
                    failed.append(it["id"])
                    continue
                if chunk:
                    try:
                        concat_chunks(got, it["target"], gap, tail)
                    except subprocess.CalledProcessError as e:
                        failed.append(it["id"])
                        print(f"[concat] {it['id']} 접합 실패: {(e.stderr or '')[-300:]}", file=sys.stderr)
                        continue
                else:
                    shutil.copyfile(got[0], it["target"])
                saved.append(it)

        if not saved:
            raise RuntimeError((remote_error or "생성물을 받지 못했습니다.") + "\n" + (p_out or "")[-1500:])

        # 표준 낭독 속도 적용 — 접합 직후 제자리 타임스트레치(피치 보존).
        # 재실행 때 이미 있는 wav 는 건너뛰므로 두 번 늘어나지 않는다.
        progress(f"재타이밍 중 ({len(saved)}장)", phase="retime", retrieval="complete")
        retimed = sum(1 for it in saved if retime(it["target"], speed))

        elapsed = round(time.time() - t0)
        # 다음 예산 보정의 근거 — 컨테이너 수와 무관하게 "생성에 쓴 GPU 초 / 글자". SEC_PER_CHAR 와 대조한다.
        measured = round(info["gen_s"] / max(1, total_chars), 3) if info["gen_s"] else None
        mode = (f"문장 단위 {len(jobs)}조각 batch {batch}, 숨 {gap}s·여운 {tail}s" if chunk else f"통짜 batch {batch}")
        progress(f"완료 {elapsed}초 · 원격 {gen_secs:.0f}초 · 생성 {measured}초/자 (예산 상수 {SEC_PER_CHAR})",
                 phase="generated", measured_sec_per_char=measured)
        print(json.dumps({
            "items": [{
                "title": it["id"],
                "meta": f"{it['target'].stat().st_size // 1024} KB · {len(it['pieces'])}조각",
                "summary": it["text"][:60],
                "url": str(it["target"]),
            } for it in saved],
            "speed": speed,
            "chunk": chunk,
            "pieces": len(jobs),
            "batch": batch,
            "containers": len(shards),
            "gen_seconds": round(gen_secs),
            "sec_per_char": measured,
            "failed": failed,
            "message": (f"{len(saved)}개 나레이션 생성 완료 ({elapsed}초, {gpu}×{len(shards)}, {mode}, "
                        f"속도 {speed}x{'' if retimed == len(saved) else f' — 재타이밍 {retimed}/{len(saved)}'}"
                        f"{'' if not failed else f' — 실패 {len(failed)}장: {failed}'}"
                        f"{'' if not remote_error else f' — 원격 중단: {remote_error}'}) "
                        f"→ {out_dir}"),
        }, ensure_ascii=False))

    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
    finally:
        if started:
            # 앱이 정말 멈췄는지 본다 — 안 멈췄으면 멈춘다 (켜진 채 두면 과금된다).
            progress("자원 반납 확인 중", phase="cleanup", cleanup="running", stall_after_s=300)
            state = release_modal_app(modal, info.get("app_id"))
            ok = state in ("released", "not_started")
            progress("자원 반납 " + ("완료" if state == "released" else "할 것 없음" if ok else "확인 실패"),
                     phase="complete" if ok else "cleanup_failed",
                     cleanup="complete" if ok else "failed", resource_state=state)


if __name__ == "__main__":
    main()
