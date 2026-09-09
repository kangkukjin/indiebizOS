#!/usr/bin/env python3
"""등록된 목소리로 나레이션 생성 (Qwen3-TTS 목소리 복제, 콜랩 GPU)

[self:script]{op:"run", id:"나레이션생성", args:{...}} 로 호출한다.

args (stdin JSON):
  lecture_id : 강의 id — 덱의 장별 스피커 노트를 읽어
               outputs/lectures/<id>/narration/<slide_id>.wav 로 굽는다.
               (deck video 가 이 폴더를 먼저 보고, 있으면 TTS 대신 그 파일을 쓴다)
  texts      : {"이름": "문장"} — 임시 문장용. out_dir 과 함께 쓴다.
  out_dir    : texts 모드의 저장 폴더 (기본 outputs/narration)
  texts_file : 위 texts 를 담은 JSON 파일 경로 (원고가 길 때 args 대신 파일로)
  voice      : data/voice/voices.json 의 키·이름·별칭 (기본 = 원장에서 default: true 인 항목)
  gpu        : T4(기본)/L4/A100 — 계정 티어에 따라 가용성 다름
  force      : true 면 이미 있는 wav 도 다시 굽는다 (기본 false)
  speed      : 낭독 속도 배율 (기본 1.0 = 원속도 — 표준). 0.9 면 10% 느리게.
  chunk      : 문장 단위 굽기 (기본 true — 2026-09-09 표준). false 면 장 하나를 한 호출에 통짜로.
  chunk_max_chars / chunk_gap / chunk_tail : 조각 상한 글자(70)·조각 사이 숨(0.35s)·장 끝 여운(0.40s).
  batch      : 원격 한 호출에 굽는 조각 수 (기본 4 — 2026-09-10). 프롬프트는 세션당 1회. OOM 이면 반으로.

산출: {"items":[{"title","meta","summary","url"}], "message": ..., "sec_per_char": 실측}
진행: stderr 로 `[  123s] …` 줄을 흘린다 — background 실행이면 로그 파일에 실시간으로 쌓여
      [self:script]{op:"status"} 가 '어디까지'를 보여 준다. 예산은 글자 수×실측 속도의 캡이고,
      실제 중단 기준은 "진행 줄이 STALL_GEN 초 동안 없음"이다.

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
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
VOICE_DIR = ROOT / "data" / "voice"
SESSION = f"narr{os.getpid()}"

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

# 원격 호출 단위 (2026-09-10): 프롬프트는 세션당 1회, 조각은 batch 개씩 한 호출에 굽는다.
# 조각당 고정 비용(참조 음성 인코딩 + 호출 왕복)이 165조각에서 55분을 만들던 뿌리.
DEFAULT_BATCH = 4

# 예산은 조각 수가 아니라 **실측 속도**로 잡는다(2026-09-10 실측, T4·batch 1: 8,775자 → 약 3,300초 = 0.38초/자).
# 이 값은 상한(캡)일 뿐이고 실제 감시는 아래 STALL_* — "진행 줄이 멈추면" 끊는다. 캡은 넉넉히, 감시는 촘촘히.
SEC_PER_CHAR = 0.38
BUDGET_MARGIN = 1.5
LOAD_BUDGET = 1200     # 세션 기동·모델 다운로드(5~10분)
STALL_LOAD = 1200      # 모델 적재 중 무소식 허용(초) — 다운로드 구간은 원래 조용하다
STALL_GEN = 600        # 생성 중 무소식 허용(초) — 한 배치가 이보다 오래 걸리면 죽은 것으로 본다

# 함정 6(colab.md): 세션 상태 파일을 공유하면 다른 콜랩 작업과 얽힌다 → 전용 config
CFG = Path(tempfile.gettempdir()) / f"colab_{SESSION}.json"


def fail(msg, **extra):
    print(json.dumps({"error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


_T0 = time.time()


def progress(msg):
    """진행 줄 — stderr 로 흘린다. stdout 은 통화(JSON) 자리라 섞지 않는다.

    백그라운드 러너(_bg_runner)가 stderr 를 로그 파일에 **실시간**으로 쓰므로, status 폴링이
    '돌고 있다'만이 아니라 '어디까지'를 본다(2026-09-10 — 40분 동안 running 만 보던 문제의 처방).
    """
    print(f"[{time.time() - _T0:6.0f}s] {msg}", file=sys.stderr, flush=True)


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


# [토큰 함정 — 2026-09-10 실사고] 콜랩 세션 토큰은 `new` 시점부터 **정확히 1시간**이면 만료된다.
# 열려 있는 exec 웹소켓은 살아서 생성은 끝까지 가지만, 그 뒤의 download·exec(정리)·stop 이 전부
# 401 로 죽는다 — 55분 굽고 165조각을 하나도 못 가져온 채 VM 만 켜 둔 채(과금) 끝났다.
# CLI 에 갱신 명령은 없고, 서버의 assignments 목록이 새 토큰(만료 3600초)을 준다. 그걸 CFG 에 되쓴다.
_REFRESH = r'''
import json, sys
from colab_cli.common import State
from colab_cli.state import StateStore
cfg, name = sys.argv[1:3]
st = State(); st.config_path = cfg
store = StateStore(cfg); s = store.get(name)
if s is None:
    print(json.dumps({"error": "local session missing"})); sys.exit(2)
match = [a for a in st.client.list_assignments() if a.endpoint == s.endpoint]
if not match:
    print(json.dumps({"error": "endpoint not assigned", "endpoint": s.endpoint})); sys.exit(2)
a = match[0]
s.token = a.runtime_proxy_info.token; s.url = a.runtime_proxy_info.url
store.add(s)
print(json.dumps({"ok": True, "expires_in": a.runtime_proxy_info.token_expires_in_seconds}))
'''


def refresh_session_token():
    """세션 토큰을 새로 받아 CFG 에 되쓴다 — 회수·정리·정지처럼 **세션 생성 뒤 오래 지나 부르는 호출 앞에** 부른다.

    CLI 의 파이썬(도구 설치본)으로 CLI 내부 client 를 그대로 쓴다. 실패해도 예외를 올리지 않고 False —
    갱신 실패는 곧 이어지는 호출의 401 로 정직하게 드러난다.
    """
    py = Path(COLAB).resolve().parent / "python"
    if not py.exists():
        progress(f"[token] CLI 파이썬이 없어 갱신 생략: {py}")
        return False
    p = subprocess.run([str(py), "-c", _REFRESH, str(CFG), SESSION], capture_output=True, text=True, timeout=120)
    tail = (p.stdout or p.stderr or "").strip().splitlines()
    progress(f"[token] 갱신 {'성공' if p.returncode == 0 else '실패'}: {tail[-1] if tail else ''}")
    return p.returncode == 0


def run_exec_streaming(script_path, cap, stall_load=STALL_LOAD, stall_gen=STALL_GEN):
    """원격 gen.py 를 돌리며 `[gen] …` 줄을 **오는 대로** 진행 채널로 넘긴다.

    끊는 기준은 숫자 예산이 아니라 **진행이 멈췄는가**다(2026-09-10):
      · 모델 적재 완료 줄이 오기 전엔 stall_load 초, 그 뒤엔 stall_gen 초 동안 줄이 없으면 죽인다.
      · cap 은 원격 커널 쪽 상한(colab exec --timeout)으로만 쓴다 — 실측 속도로 계산한 넉넉한 캡.
    종전엔 capture_output 으로 파이프에 가둬 두고 2시간 22분짜리 예산만 기다렸다.
    반환: (stdout 전문, 진행 줄 수). 실패·정지는 RuntimeError.
    """
    import queue
    import threading
    cmd = [COLAB, "--config", str(CFG), "exec", "-s", SESSION, "-f", str(script_path),
           "--timeout", str(int(cap))]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    q = queue.Queue()

    def _pump():
        # 읽기 스레드 — select 로 파이프를 보면 TextIO 버퍼에 남은 줄을 놓친다(끝 줄·오류가 사라진다).
        for line in p.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    lines, last, loaded, seen = [], time.time(), False, 0
    while True:
        limit = stall_gen if loaded else stall_load
        try:
            line = q.get(timeout=5)
        except queue.Empty:
            line = ""
        if line is None:
            break
        if line:
            lines.append(line)
            s = line.rstrip()
            if s.startswith("[gen]"):
                seen += 1
                last = time.time()
                if "모델 적재 완료" in s:
                    loaded = True
                progress(s)
        if time.time() - last > limit:
            p.kill()
            p.wait(timeout=30)
            raise RuntimeError(f"원격 생성이 {limit}초 동안 무소식 — "
                               f"{'생성' if loaded else '모델 적재'} 단계에서 멈춘 것으로 보고 끊었습니다.\n"
                               + "".join(lines)[-1200:])
    p.wait()
    out = "".join(lines)
    if p.returncode != 0:
        if "has no attribute 'KernelClient'" in out:
            raise RuntimeError(
                "colab CLI 의 의존성이 깨졌습니다 (jupyter-kernel-client 1.x). 처방:\n"
                "  uv pip install --python ~/.local/share/uv/tools/google-colab-cli/bin/python "
                "'jupyter-kernel-client<1.0'")
        raise RuntimeError(f"colab exec 실패 (rc={p.returncode})\n{out[-1500:]}")
    return out, seen


# ── 원격에서 돌 스크립트 ────────────────────────────────────────────────
# job.json 을 읽어 생성한다. 문장을 코드에 박지 않는 이유 = 따옴표·개행 지옥 회피.
REMOTE = r'''
import json, tarfile, time, torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

job = json.load(open("/content/work/job.json", encoding="utf-8"))
items, batch = job["items"], max(1, int(job.get("batch") or 1))
t0 = time.time()

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
print(f"[gen] sm_{major}x dtype={dtype} attn={attn} · 모델 적재 시작", flush=True)

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    device_map="cuda:0", dtype=dtype, attn_implementation=attn,
)
print(f"[gen] 모델 적재 완료 {time.time() - t0:.0f}s", flush=True)

# [프롬프트 1회] 레퍼런스 음성의 화자 임베딩·코드는 조각마다 같다 — 165조각이면 165번 인코딩하던 것을
# 한 번 만들어 재사용한다(2026-09-10: 조각당 고정 비용의 첫째 몫).
prompt = model.create_voice_clone_prompt(ref_audio="/content/work/ref.wav", ref_text=job["ref_text"])

def gen(texts):
    wavs, sr = model.generate_voice_clone(text=texts, language="Korean", voice_clone_prompt=prompt)
    return wavs, sr

done, n, i = [], len(items), 0
while i < n:
    group = items[i:i + batch]
    try:
        wavs, sr = gen([g["text"] for g in group])
    except torch.cuda.OutOfMemoryError:
        # 배치가 T4 메모리를 넘기면 반으로 줄여 다시 — 1까지 내려가면 그 조각은 홀로 굽는다.
        torch.cuda.empty_cache()
        if batch > 1:
            batch = max(1, batch // 2)
            print(f"[gen] OOM → batch {batch}", flush=True)
            continue
        raise
    for g, w in zip(group, wavs):
        sf.write(f"/content/work/out_{g['id']}.wav", w, sr)
        done.append({"id": g["id"], "seconds": round(len(w) / sr, 2)})
    i += len(group)
    el = time.time() - t0
    print(f"[gen] {i}/{n} {group[-1]['id']} {sum(len(w) for w in wavs) / sr:.1f}s audio · {el:.0f}s 경과", flush=True)

json.dump(done, open("/content/work/done.json", "w"), ensure_ascii=False)
# 회수는 파일 하나로 — 조각마다 colab download 프로세스를 띄우면 조각당 1.4초(실측)가 직렬로 붙는다.
with tarfile.open("/content/work/out.tar", "w") as tf:
    for d in done:
        tf.add(f"/content/work/out_{d['id']}.wav", arcname=f"out_{d['id']}.wav")
    tf.add("/content/work/done.json", arcname="done.json")
print(f"[gen] 완료 {len(done)}조각 {time.time() - t0:.0f}s", flush=True)
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


def main():
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}

    ref_wav, ref_text = load_voice(args.get("voice") or default_voice())
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
    chunk = args.get("chunk")
    chunk = DEFAULT_CHUNK if chunk is None else bool(chunk)
    max_chars = int(args.get("chunk_max_chars") or CHUNK_MAX_CHARS)
    gap = float(args["chunk_gap"]) if args.get("chunk_gap") is not None else CHUNK_GAP
    tail = float(args["chunk_tail"]) if args.get("chunk_tail") is not None else CHUNK_TAIL
    batch = max(1, int(args.get("batch") or DEFAULT_BATCH))

    # 굽기 호출 단위 = 문장 조각(chunk). 원격 id 는 "<장>__<번호>", 회수 뒤 장 단위로 접합한다.
    jobs = []
    for it in items:
        it["pieces"] = split_sentences(it["text"], max_chars) if chunk else [it["text"]]
        for n, piece in enumerate(it["pieces"], 1):
            jobs.append({"id": f"{it['id']}__{n:02d}" if chunk else it["id"], "text": piece, "parent": it})

    t0 = time.time()
    started = False
    total_chars = sum(len(j["text"]) for j in jobs)
    # 캡 = 기동·적재 + 실측 속도×글자 수×여유. 조각 수는 캡에 안 들어간다 — 배치가 조각당 비용을 바꾸기 때문.
    cap = int(LOAD_BUDGET + SEC_PER_CHAR * total_chars * BUDGET_MARGIN)
    progress(f"{len(items)}장 {len(jobs)}조각 {total_chars}자 · batch {batch} · {gpu} · "
             f"예상 생성 {SEC_PER_CHAR * total_chars / 60:.0f}분(캡 {cap // 60}분, 무소식 {STALL_GEN}초면 중단)")

    try:
        progress("콜랩 세션 여는 중")
        run(["new", "-s", SESSION, "--gpu", gpu], timeout=600)
        started = True
        progress("qwen-tts 설치 중")
        run(["install", "-s", SESSION, "qwen-tts", "soundfile"], timeout=1200)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            job = {"ref_text": ref_text, "batch": batch,
                   "items": [{"id": j["id"], "text": j["text"]} for j in jobs]}
            (td / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            (td / "gen.py").write_text(REMOTE, encoding="utf-8")

            remote("import os; os.makedirs('/content/work', exist_ok=True)")
            # [UPLOAD 함정] colab upload 의 상대경로는 /content 가 아니라 루트(/) 기준이다.
            # 반드시 절대경로로 목적지를 준다.
            run(["upload", "-s", SESSION, str(ref_wav), "/content/work/ref.wav"], timeout=600)
            run(["upload", "-s", SESSION, str(td / "job.json"), "/content/work/job.json"], timeout=300)

            progress("원격 생성 시작 (모델 다운로드 5~10분은 조용하다)")
            gen_t0 = time.time()
            p_out, _ = run_exec_streaming(td / "gen.py", cap)
            gen_secs = time.time() - gen_t0

        saved, failed = [], []
        # 생성이 1시간을 넘기면 세션 토큰이 이미 죽어 있다(위 [토큰 함정]) — 회수 앞에 무조건 갱신.
        refresh_session_token()
        with tempfile.TemporaryDirectory() as dl:
            dl = Path(dl)
            # 회수 = tar 하나 (조각별 download 는 조각당 1.4초 직렬 — 165조각이면 4분). tar 가 없으면 옛 경로.
            progress("생성물 회수 중 (out.tar)")
            tar_path = dl / "out.tar"
            r = run(["download", "-s", SESSION, "/content/work/out.tar", str(tar_path)], timeout=600, check=False)
            if r.returncode == 0 and tar_path.exists():
                import tarfile
                with tarfile.open(tar_path) as tf:
                    tf.extractall(dl, **({"filter": "data"} if sys.version_info >= (3, 12) else {}))
            for it in items:
                mine = [j for j in jobs if j["parent"] is it]
                got = []
                for j in mine:
                    dst = (dl / f"{j['id']}.wav") if chunk else it["target"]
                    src = dl / f"out_{j['id']}.wav"
                    if src.exists():
                        src.replace(dst)
                    else:
                        r = run(["download", "-s", SESSION, f"/content/work/out_{j['id']}.wav", str(dst)],
                                timeout=300, check=False)
                        if r.returncode != 0:
                            continue
                    if dst.exists():
                        got.append(dst)
                if len(got) != len(mine):
                    failed.append(it["id"])
                    continue
                if chunk:
                    try:
                        concat_chunks(got, it["target"], gap, tail)
                    except subprocess.CalledProcessError as e:
                        failed.append(it["id"])
                        print(f"[concat] {it['id']} 접합 실패: {(e.stderr or '')[-300:]}", file=sys.stderr)
                        continue
                saved.append(it)

        if not saved:
            raise RuntimeError("생성물을 회수하지 못했습니다.\n" + (p_out or "")[-1000:])

        # 표준 낭독 속도 적용 — 회수 직후 제자리 타임스트레치(피치 보존).
        # 재실행 때 이미 있는 wav 는 건너뛰므로 두 번 늘어나지 않는다.
        progress(f"접합·재타이밍 중 ({len(saved)}장)")
        retimed = sum(1 for it in saved if retime(it["target"], speed))

        elapsed = round(time.time() - t0)
        measured = round(gen_secs / max(1, total_chars), 3)   # 다음 예산 보정의 근거 — SEC_PER_CHAR 와 대조
        mode = (f"문장 단위 {len(jobs)}조각 batch {batch}, 숨 {gap}s·여운 {tail}s" if chunk else f"통짜 batch {batch}")
        progress(f"완료 {elapsed}초 · 생성 {gen_secs:.0f}초 = {measured}초/자 (예산 상수 {SEC_PER_CHAR})")
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
            "gen_seconds": round(gen_secs),
            "sec_per_char": measured,
            "failed": failed,
            "message": (f"{len(saved)}개 나레이션 생성 완료 ({elapsed}초, {gpu}, {mode}, "
                        f"속도 {speed}x{'' if retimed == len(saved) else f' — 재타이밍 {retimed}/{len(saved)}'}"
                        f"{'' if not failed else f' — 실패 {len(failed)}장: {failed}'}) "
                        f"→ {out_dir}"),
        }, ensure_ascii=False))

    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
    finally:
        if started:
            # 목소리는 생체정보다 — 원격 파일을 지우고 세션을 반납한다.
            # 실패해도 stop 은 반드시 시도한다 (안 끄면 최대 24시간 과금).
            # 실패 경로로 왔어도 토큰이 죽어 있을 수 있다 — 정리·정지 앞에 갱신(09-10: 정지 실패로 VM 이 켜진 채 남았다).
            try:
                refresh_session_token()
            except Exception:
                pass
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
