"""hls_ladder.py — 로컬 파일 HLS 적응형(화질 사다리) 단일 소스.

유튜브 릴레이(api_ytrelay)의 sidx→byterange HLS 를 로컬 파일(NAS·공개파일)에 이식.
유튜브는 사다리를 이미 제공하지만 로컬 파일은 우리가 만들어야 한다. 핵심 결정 셋:

  · **조각 파일 스프레이 금지** — 렌디션 = 전역 sidx 를 머리에 단 fMP4 한 파일
    (ftyp+moov+sidx+moof…, 유튜브 DASH 와 같은 구조. ffmpeg -movflags
    frag_…+global_sidx 실측). 같은 파일이 프로그레시브(FileResponse Range)와
    HLS 세그먼트(EXT-X-BYTERANGE)를 동시에 서빙 — 캐시 구조·LRU·R2 캐시 키가
    전부 '파일 하나' 그대로 남는다.
  · **렁 = 기존 캐시 슬롯**: tiny(480p ~0.7Mbps 신설) / low(720p ~1.3Mbps) / orig.
    lowh(HEVC)는 사다리 밖 — 변형 간 코덱 혼합 전환은 기기별 리스크라
    프로그레시브 토글 전용으로 남긴다(SPA mediaCapabilities 경로 유지).
  · **빌드 = 요청 기반 + 전역 단일 워커**: master.m3u8 요청 시 결핍 렁을 enqueue
    (중복 dedupe, 인코딩 동시 1개). orig 렁은 원본이 웹 코덱일 때만(-c copy
    리먹스=디스크 속도) — 풀 트랜스코드 orig 는 실제 시청(스트리밍 tee)이 만든다.
    옛 faststart 캐시(sidx 없음)는 reindex 잡(-c copy)으로 승격.

사다리가 아직 없으면 마스터가 404 — 표면은 기존 프로그레시브(생방송 트랜스코드)로
폴백하고, 그 시청의 tee 캐시가 첫 렁이 되어 다음 시청부터 적응형이 된다.
"""

import json
import os
import struct
import subprocess
import threading
import time

import thumbnails

# 렁 이름 → 캐시 파일 접미(<key>.mp4 / <key>.low.mp4 / … — 기존 명명 그대로)
# nano(360p ~0.45Mbps)=비상 바닥: 테슬라 시동=와이파이→LTE 전환 + 차 자체 트래픽과
# 회선 공유 — tiny(~0.7Mbps)조차 순간 굶는 상황의 마지노선.
_SUFFIX = {"orig": "", "low": ".low", "tiny": ".tiny", "nano": ".nano"}
RUNG_ORDER = ["nano", "tiny", "low", "orig"]  # 마스터 나열 순서(대역 오름차순)

_FRAG_SIDX_FLAGS = "frag_keyframe+empty_moov+default_base_moof+global_sidx"

_sidx_cache: dict = {}    # path -> (mtime, size, idx|None)
_meta_cache: dict = {}    # path -> (mtime, size, meta|None)


def rung_path(orig_cache: str, rung: str) -> str:
    """orig 캐시 경로(…/<key>.mp4)에서 형제 렁 경로를 유도."""
    base, ext = os.path.splitext(orig_cache)
    return base + _SUFFIX[rung] + ext


# ── sidx 파싱 (api_ytrelay._parse_boxes_sidx 의 로컬 파일 판) ────────────────

def parse_sidx_file(path: str):
    """파일 머리에서 init 경계(moov 끝)와 첫 sidx 조각 색인을 파싱.
    {"init_end", "segments":[(offset,size,dur)]} 또는 None(sidx 없음=HLS 부적격).

    트랙별 sidx 가 연달아 나오지만(비디오·오디오) 조각은 A/V 먹싱이라 첫 sidx
    (비디오 타임라인)만 쓰면 된다 — first_offset 이 뒤 sidx 들을 건너뛴다(실측)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    hit = _sidx_cache.get(path)
    if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2]
    idx = None
    try:
        with open(path, "rb") as f:
            head = f.read(1 << 20)          # 1MB — 3시간 영화도 sidx×2+moov 가 수십 KB
        pos, init_end, sidx_at = 0, 0, -1
        while pos + 8 <= len(head):
            size = struct.unpack(">I", head[pos:pos + 4])[0]
            tag = head[pos + 4:pos + 8]
            if size < 8:
                break
            if tag == b"moov":
                init_end = pos + size
            elif tag == b"sidx":
                sidx_at = pos
                break
            pos += size
        if init_end > 0 and sidx_at >= 0:
            p = sidx_at + 8
            version = head[p]
            p += 4                              # version+flags
            p += 4                              # reference_ID
            timescale = struct.unpack(">I", head[p:p + 4])[0]; p += 4
            if version == 0:
                p += 4
                first_offset = struct.unpack(">I", head[p:p + 4])[0]; p += 4
            else:
                p += 8
                first_offset = struct.unpack(">Q", head[p:p + 8])[0]; p += 8
            p += 2
            ref_count = struct.unpack(">H", head[p:p + 2])[0]; p += 2
            sidx_size = struct.unpack(">I", head[sidx_at:sidx_at + 4])[0]
            offset = sidx_at + sidx_size + first_offset
            segments = []
            for _ in range(ref_count):
                w1 = struct.unpack(">I", head[p:p + 4])[0]; p += 4
                dur = struct.unpack(">I", head[p:p + 4])[0]; p += 4
                p += 4                          # SAP
                if w1 >> 31:                    # 계층 색인 — ffmpeg 산출물엔 안 나옴
                    raise ValueError("계층 sidx")
                segments.append((offset, w1 & 0x7FFFFFFF, dur / timescale))
                offset += w1 & 0x7FFFFFFF
            if segments:
                idx = {"init_end": init_end, "segments": segments}
    except Exception:
        idx = None
    _sidx_cache[path] = (st.st_mtime, st.st_size, idx)
    return idx


# ── 렁 메타 (마스터의 BANDWIDTH/RESOLUTION/CODECS) ──────────────────────────

_PROFILE_HEX = {"Baseline": "42e0", "Constrained Baseline": "42c0",
                "Main": "4d40", "High": "6400"}


def rung_meta(path: str):
    """ffprobe 로 {bandwidth, width, height, codecs} — (mtime,size) 키 캐시."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    hit = _meta_cache.get(path)
    if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[2]
    meta = None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "stream=codec_type,codec_name,profile,level,width,height",
             "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, timeout=20)
        info = json.loads(r.stdout.decode("utf-8", "ignore"))
        v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        a = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        dur = float((info.get("format") or {}).get("duration") or 0)
        codecs = "avc1.%s%02x" % (_PROFILE_HEX.get(v.get("profile", ""), "6400"),
                                  int(v.get("level") or 31))
        if a is not None:
            codecs += ",mp4a.40.2"
        meta = {
            # 평균 비트레이트 ×1.15 — BANDWIDTH 는 피크 근사(hls.js ABR 판단 근거)
            "bandwidth": max(int(st.st_size * 8 / dur * 1.15), 100000) if dur > 0 else 500000,
            "width": int(v.get("width") or 0), "height": int(v.get("height") or 0),
            "codecs": codecs,
        }
    except Exception:
        meta = None
    _meta_cache[path] = (st.st_mtime, st.st_size, meta)
    return meta


def available_rungs(orig_cache: str) -> list:
    """사다리에 오를 수 있는 렁들 — 캐시가 존재하고 sidx 가 파싱되는 것만.
    [(rung, path)] (tiny→low→orig 순)."""
    out = []
    for rung in RUNG_ORDER:
        p = rung_path(orig_cache, rung)
        if os.path.isfile(p) and parse_sidx_file(p):
            out.append((rung, p))
    return out


# ── 플레이리스트 생성 ────────────────────────────────────────────────────────

def master_m3u8(rungs: list, variant_url) -> str:
    """마스터 — rungs=[(rung,path)], variant_url(rung)->URI. 조각이 A/V 먹싱이라
    오디오 그룹 분리 없음(유튜브와 다른 점)."""
    lines = ["#EXTM3U", "#EXT-X-VERSION:7"]
    for rung, path in rungs:
        m = rung_meta(path)
        if not m:
            continue
        res = f',RESOLUTION={m["width"]}x{m["height"]}' if m["width"] else ""
        lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={m["bandwidth"]}{res},CODECS="{m["codecs"]}"')
        lines.append(variant_url(rung))
    return "\n".join(lines) + "\n"


def variant_m3u8(idx: dict, seg_url: str) -> str:
    """변형 — sidx 조각 색인을 EXT-X-BYTERANGE 로. 세그먼트 URI 는 렌디션 파일을
    서빙하는 기존 미디어 URL 하나(byterange 만 다름)."""
    segs = idx["segments"]
    target = max(int(d + 0.999) for _, _, d in segs) if segs else 6
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-TARGETDURATION:{target}",
             "#EXT-X-PLAYLIST-TYPE:VOD",
             f'#EXT-X-MAP:URI="{seg_url}",BYTERANGE="{idx["init_end"]}@0"']
    for offset, size, dur in segs:
        lines.append(f"#EXTINF:{dur:.3f},")
        lines.append(f"#EXT-X-BYTERANGE:{size}@{offset}")
        lines.append(seg_url)
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


# ── 사다리 빌더 (전역 단일 워커) ─────────────────────────────────────────────

_QUEUE: list = []
_PENDING: set = set()          # 큐에 있거나 실행 중인 dst
_LOCK = threading.Lock()
_WORKER_ON = False
_PRUNE_TS: dict = {}           # root -> 마지막 prune 시각


def _enqueue(job) -> None:
    global _WORKER_ON
    with _LOCK:
        if job[1] in _PENDING:          # job=(kind, dst, ...)
            return
        _PENDING.add(job[1])
        _QUEUE.append(job)
        if not _WORKER_ON:
            _WORKER_ON = True
            threading.Thread(target=_worker, daemon=True).start()


def _worker() -> None:
    global _WORKER_ON
    while True:
        with _LOCK:
            if not _QUEUE:
                _WORKER_ON = False
                return
            job = _QUEUE.pop(0)
        try:
            if job[0] == "encode":
                _job_encode(job[1], job[2], job[3])
            elif job[0] == "reindex":
                _job_reindex(job[1])
            elif job[0] == "prune":
                prune_dir(job[1], job[2])
        except Exception:
            pass
        finally:
            with _LOCK:
                _PENDING.discard(job[1])


def _job_encode(dst: str, src: str, rung: str) -> None:
    """결핍 렁 인코딩 — 파일 출력이라 global_sidx 직행(리먹스 불요), 완성 후 duration
    패치 → 원자 교체. 4초 강제 키프레임 = HLS 세그먼트 입자(스트리밍 tee 캐시의
    GOP 250≈10초 세그먼트보다 잘게 — 전환 반응성)."""
    if os.path.exists(dst):
        return
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".build"
    dur = thumbnails.probe_video_duration(src)
    if rung == "orig":
        # 웹 코덱 원본만 온다(-c copy) — 오디오는 웹 코덱이면 copy, 아니면 AAC
        _, a = thumbnails._probe_av_codecs(src)
        acopy = a is not None and a.lower() in thumbnails._WEB_PLAYABLE_AUDIO_CODECS
        codec = ["-c:v", "copy"] + (["-c:a", "copy"] if acopy
                                    else ["-c:a", "aac", "-b:a", "128k", "-ac", "2"])
    else:
        video = {"nano": thumbnails._NANO_VIDEO, "tiny": thumbnails._TINY_VIDEO,
                 "low": thumbnails._LOW_VIDEO}[rung]
        codec = (list(video) + ["-force_key_frames", "expr:gte(t,n_forced*4)"]
                 + list(thumbnails._LOW_AUDIO))
    cmd = (["ffmpeg", "-v", "error", "-y", "-i", os.path.abspath(src)] + codec
           + ["-map", "0:v:0", "-map", "0:a:0?",
              "-f", "mp4", "-movflags", _FRAG_SIDX_FLAGS, tmp])   # -f: .build 확장자라 명시
    try:
        r = subprocess.run(cmd, capture_output=True,
                           timeout=max(1800, int(dur * 6) if dur else 0))
        if r.returncode == 0 and os.path.getsize(tmp) > 0:
            thumbnails.patch_file_duration(tmp)
            os.replace(tmp, dst)
            return
    except Exception:
        pass
    try:
        if os.path.exists(tmp):
            os.unlink(tmp)
    except OSError:
        pass


def _job_reindex(path: str) -> None:
    """옛 faststart 캐시(sidx 없음) → 전역 sidx fMP4 로 승격(-c copy, 디스크 속도).
    실패해도 원본 캐시는 무손상(프로그레시브 서빙 계속)."""
    tmp = path + ".build"
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", path, "-c", "copy",
             "-f", "mp4", "-movflags", _FRAG_SIDX_FLAGS, tmp],
            capture_output=True, timeout=1800)
        if r.returncode == 0 and os.path.getsize(tmp) > 0:
            thumbnails.patch_file_duration(tmp)
            os.replace(tmp, path)
            return
    except Exception:
        pass
    try:
        if os.path.exists(tmp):
            os.unlink(tmp)
    except OSError:
        pass


def ensure_ladder(src: str, orig_cache: str, prune_root: str = "",
                  prune_cap: int = 0) -> None:
    """결핍 렁을 빌드 큐에 올린다(중복 dedupe, 즉시 반환). 마스터 요청마다 불러도 싸다.
    · tiny/low: 항상(인코딩 — 전역 워커가 하나씩)
    · orig: 원본이 웹 코덱일 때만(-c copy 리먹스). 아니면 실제 시청이 만든다.
    · 기존 캐시가 sidx 없는 옛 판이면 reindex.
    prune_root 를 주면 10분에 한 번 LRU 정리도 같은 워커에 태운다."""
    for rung in RUNG_ORDER:
        p = rung_path(orig_cache, rung)
        if os.path.isfile(p):
            if not parse_sidx_file(p):
                _enqueue(("reindex", p))
            continue
        if rung == "orig" and not thumbnails.video_codec_web_playable(src):
            continue
        _enqueue(("encode", p, src, rung))
    if prune_root and time.time() - _PRUNE_TS.get(prune_root, 0) > 600:
        _PRUNE_TS[prune_root] = time.time()
        _enqueue(("prune", prune_root, prune_cap))


# ── LRU 정리 — 렌디션은 전부 파생물(원본에서 언제든 재생성) ─────────────────

def prune_dir(root: str, cap_bytes: int) -> None:
    """root 아래 캐시 총량이 cap 을 넘으면 오래 안 쓴 것(mtime)부터 삭제.
    재생·서빙 경로가 mtime 을 터치하므로 보던 것은 젊다."""
    if not cap_bytes:
        return
    files = []
    try:
        for dirpath, _, names in os.walk(root):
            for n in names:
                if n.startswith("."):
                    continue
                fp = os.path.join(dirpath, n)
                try:
                    files.append((fp, os.stat(fp)))
                except OSError:
                    pass
    except OSError:
        return
    total = sum(s.st_size for _, s in files)
    if total <= cap_bytes:
        return
    for fp, s in sorted(files, key=lambda x: x[1].st_mtime):
        try:
            os.unlink(fp)
            total -= s.st_size
        except OSError:
            pass
        if total <= cap_bytes * 0.8:
            break


def touch(path: str) -> None:
    """LRU 근거(mtime) 갱신 — 재생할 때마다 젊어진다(youtube_cache 선례)."""
    try:
        os.utime(path)
    except OSError:
        pass
