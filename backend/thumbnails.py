"""
backend/thumbnails.py — 썸네일 생성 단일 소스.

api_photo.py 엔드포인트(REST 온디맨드)와 public-files showcase(로컬 스테이징 생성)가
같은 함수를 쓴다. 중복 재구현 금지(능력 1·구현 1). 순수 함수(src→dst 파일 쓰기),
캐싱·HTTP 는 호출자 몫.

- 이미지: PIL. EXIF 회전 적용, RGB 변환, LANCZOS 축소, JPEG 저장.
- 동영상: ffmpeg 1초 지점 프레임 캡처.
"""

import os
import subprocess

# photo-manager/scanner.py 와 동일 집합(단일 진실은 아니나 미디어 분류 표준).
PHOTO_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "heic", "heif", "tiff", "tif", "raw", "cr2", "nef", "arw", "dng",
}
VIDEO_EXTENSIONS = {
    "mp4", "mkv", "avi", "mov", "wmv", "flv",
    "webm", "mpg", "mpeg", "m4v", "mts", "3gp",
}


def classify(path: str) -> str | None:
    """확장자로 photo/video/None 판정."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def generate_image_thumbnail(src: str, dst: str, size: int = 512) -> bool:
    """이미지 → JPEG 썸네일. EXIF 회전 적용. 성공 시 True."""
    from PIL import Image

    try:
        with Image.open(src) as img:
            # EXIF 회전 정보 적용
            try:
                from PIL import ExifTags
                orientation = None
                for k in ExifTags.TAGS:
                    if ExifTags.TAGS[k] == "Orientation":
                        orientation = k
                        break
                exif = img._getexif() if hasattr(img, "_getexif") else None
                if exif and orientation is not None:
                    ov = exif.get(orientation)
                    if ov == 3:
                        img = img.rotate(180, expand=True)
                    elif ov == 6:
                        img = img.rotate(270, expand=True)
                    elif ov == 8:
                        img = img.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError):
                pass

            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            img.save(dst, "JPEG", quality=80)
        return os.path.exists(dst)
    except Exception:
        return False


def generate_video_thumbnail(src: str, dst: str, size: int = 512, timeout: int = 15) -> bool:
    """동영상 → 1초 지점 프레임 JPEG. ffmpeg 필요. 성공 시 True."""
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-ss", "00:00:01",
            "-vframes", "1",
            "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease",
            "-q:v", "5",
            dst,
        ]
        subprocess.run(cmd, capture_output=True, timeout=timeout)
        return os.path.exists(dst)
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def generate_thumbnail(src: str, dst: str, size: int = 512, kind: str | None = None) -> bool:
    """확장자(또는 kind)로 이미지/동영상 분기 → 썸네일 생성. 성공 시 True."""
    kind = kind or classify(src)
    if kind == "photo":
        return generate_image_thumbnail(src, dst, size)
    if kind == "video":
        return generate_video_thumbnail(src, dst, size)
    return False


# ── 웹 전송(공개 원본) 처리 ─────────────────────────────────────────────
# 공개 showcase 가 "원본"을 브라우저로 내보낼 때 쓰는 변환. 썸네일과 달리
# 풀 해상도를 유지하되, ①위치·기기 메타데이터(EXIF/GPS) 제거 ②브라우저가
# 못 여는 컨테이너(HEVC .mov 등) H.264 트랜스코드. 캐시·HTTP 는 호출자 몫.

# 카메라·폰이 GPS/EXIF 를 흔히 심는 포맷만 sanitize 대상(그 외 png/gif/webp 는
# 원본 그대로 두어 도표·스크린샷 화질 보존).
_EXIF_BEARING_EXTS = {"jpg", "jpeg", "heic", "heif", "tiff", "tif"}
# 브라우저가 대체로 그대로 재생 가능한 컨테이너(ffprobe 불가 시 폴백용).
_WEB_PLAYABLE_VIDEO_EXTS = {"mp4", "m4v", "webm"}
# 브라우저가 직접 디코딩 가능한 비디오 코덱(트랜스코드 불필요).
# HEVC 는 제외 — Safari 만 재생하고 Chrome/Firefox 는 대체로 못 여니 변환한다.
_WEB_PLAYABLE_VIDEO_CODECS = {"h264", "vp8", "vp9", "av1"}


def needs_exif_strip(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext in _EXIF_BEARING_EXTS


def _probe_video_codec(path: str) -> str | None:
    """ffprobe 로 첫 비디오 스트림 코덱명 반환. 실패 시 None."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
            capture_output=True, timeout=20,
        )
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "ignore").strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def needs_video_transcode(path: str) -> bool:
    """브라우저가 못 여는 동영상이면 True.

    확장자가 아니라 실제 비디오 코덱으로 판정한다. `.mp4` 껍데기여도
    알맹이가 mpeg4/HEVC 면 브라우저는 비디오를 못 읽어(소리만 남)
    트랜스코드가 필요하다. ffprobe 실패 시엔 확장자 기준으로 폴백."""
    if classify(path) != "video":
        return False
    codec = _probe_video_codec(path)
    if codec is not None:
        return codec.lower() not in _WEB_PLAYABLE_VIDEO_CODECS
    # ffprobe 불가 — 확장자 기준 보수적 폴백(기존 동작).
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext not in _WEB_PLAYABLE_VIDEO_EXTS


def sanitize_image_bytes(src: str, quality: int = 92):
    """원본 이미지 → EXIF/GPS 제거한 JPEG 바이트. 실패 시 None.

    orientation 은 픽셀로 구워 넣고(회전 보존) 나머지 메타는 전부 버림 —
    save 에 exif= 를 넘기지 않으므로 GPS·기기·촬영시각 모두 사라진다."""
    import io
    from PIL import Image, ImageOps

    try:
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)   # 회전 굽기 + orientation 태그 제거
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality)  # exif= 미지정 → 메타 전부 제거
            return buf.getvalue()
    except Exception:
        return None


def transcode_video_to_mp4(src: str, dst: str, timeout: int = 180) -> bool:
    """동영상 → H.264/AAC MP4(웹 재생용). faststart 로 스트리밍 가능. 성공 시 True."""
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", src,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            dst,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


# ── 스트리밍 트랜스코드 ────────────────────────────────────────────────
# 전체 변환을 기다리지 않고 재생을 시작해야 하는 긴 동영상용. tee 머서로
# ① fMP4 를 stdout 에 흘리고(뷰어가 수 초 안에 재생 시작) ② 같은 인코딩으로
# faststart 캐시도 쓴다(인코딩 1회). 캐시는 .part 로 쓰다 완성 시에만 rename —
# 다음 재생부터는 캐시 직행(Range·seek 완전).


def probe_video_duration(path: str) -> float:
    """ffprobe 로 총 길이(초). 실패 시 0.0."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, timeout=20,
        )
        if r.returncode == 0:
            return float(r.stdout.decode("utf-8", "ignore").strip() or 0)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
        pass
    return 0.0


def patch_fmp4_duration(head: bytes, duration_s: float) -> bytes:
    """fMP4 init 세그먼트(ftyp+moov)의 mvhd·tkhd·mdhd duration 을 실제 길이로 패치.

    empty_moov 생방송은 duration=0 이라 브라우저가 '버퍼된 만큼'을 총 길이로 표시
    (긴 영화가 몇 초짜리로 보임). 세 박스를 모두 박아야 Chrome(libavformat)이 총
    길이를 믿는다 — mvhd 만으론 트랙 duration 0 이 이겨 무시됨(실측). 박스 크기는
    안 바뀌므로 in-place 치환. 실패해도 원본 그대로 반환(재생엔 지장 없음)."""
    import struct
    if duration_s <= 0:
        return head
    try:
        buf = bytearray(head)
        moof = head.find(b"moof")
        end = moof if moof > 0 else len(head)

        def _find_all(tag):
            pos, out = 0, []
            while True:
                i = head.find(tag, pos, end)
                if i < 0:
                    return out
                out.append(i)
                pos = i + 4

        mvhd = _find_all(b"mvhd")
        if not mvhd:
            return head
        i = mvhd[0]
        if head[i + 4] == 0:
            movie_ts = struct.unpack(">I", head[i + 16:i + 20])[0]
            buf[i + 20:i + 24] = struct.pack(">I", int(duration_s * movie_ts))
        else:
            movie_ts = struct.unpack(">I", head[i + 24:i + 28])[0]
            buf[i + 28:i + 36] = struct.pack(">Q", int(duration_s * movie_ts))
        for i in _find_all(b"tkhd"):          # duration 단위 = 무비 타임스케일
            if head[i + 4] == 0:
                buf[i + 24:i + 28] = struct.pack(">I", int(duration_s * movie_ts))
            else:
                buf[i + 32:i + 40] = struct.pack(">Q", int(duration_s * movie_ts))
        for i in _find_all(b"mdhd"):          # duration 단위 = 그 트랙 타임스케일
            if head[i + 4] == 0:
                ts = struct.unpack(">I", head[i + 16:i + 20])[0]
                buf[i + 20:i + 24] = struct.pack(">I", int(duration_s * ts))
            else:
                ts = struct.unpack(">I", head[i + 24:i + 28])[0]
                buf[i + 28:i + 36] = struct.pack(">Q", int(duration_s * ts))
        return bytes(buf)
    except Exception:
        return head

def start_stream_transcode(src: str, cache_dst: str):
    """스트리밍 트랜스코드 시작. (proc, tmp경로) 반환 — 호출자가 proc.stdout 을 읽어
    흘리면서 같은 바이트를 tmp(.part)에 쓰고, 끝나면 finish_/중단하면
    detach_stream_transcode 를 불러야 한다(완주 시 faststart 리먹스로 캐시 완성).

    ★tee 머서 금지: tee 의 파이프 슬레이브엔 h264 extradata(avcC)가 빠져
    'missing picture in access unit' — 디코드 불가 스트림이 나온다(실측).
    단일 fMP4 출력 + 파이썬 tee 가 정답."""
    import uuid
    cache_dir = os.path.dirname(cache_dst) or "."
    os.makedirs(cache_dir, exist_ok=True)
    tmp = os.path.join(cache_dir, f".{uuid.uuid4().hex[:12]}.part.mp4")
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", os.path.abspath(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0", "-map", "0:a:0?",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return proc, tmp


def start_offset_stream(src: str, t: float, copy: bool = False):
    """t초 지점부터의 fMP4 오프셋 스트림(캐시 tee 없음 — 부분이라 캐시 부적격).
    copy=True 면 재인코딩 없이 스트림 복사(이미 H.264 캐시가 소스일 때, 즉시 시작).
    타임라인은 0 기준(mov 머서가 리베이스) — 자막은 subtitle?shift= 로 맞춘다."""
    if copy:
        codec = ["-c", "copy"]
    else:
        codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k"]
    cmd = (["ffmpeg", "-v", "error", "-ss", str(max(0.0, t)), "-i", os.path.abspath(src)]
           + codec + ["-map", "0:v:0", "-map", "0:a:0?", "-f", "mp4",
                      "-movflags", "frag_keyframe+empty_moov+default_base_moof", "pipe:1"])
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def kill_stream(proc) -> None:
    """오프셋 스트림 중단 — 캐시 완주 의무가 없으니 그냥 죽인다."""
    try:
        proc.kill()
    except Exception:
        pass


def finish_stream_transcode(proc, tmp: str, cache_dst: str) -> None:
    """ffmpeg 종료 대기 후 성공이면 tmp(fMP4)를 faststart 로 리먹스해 캐시 완성
    (-c copy, 초 단위), 실패면 tmp 폐기. 동시 시청으로 변환이 겹치면 tmp 가
    제각각이라 마지막 완주가 캐시가 된다(무해)."""
    try:
        rc = proc.wait()
        if rc == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", tmp,
                 "-c", "copy", "-movflags", "+faststart", cache_dst],
                capture_output=True, timeout=600)
            if not (r.returncode == 0 and os.path.exists(cache_dst)
                    and os.path.getsize(cache_dst) > 0):
                os.replace(tmp, cache_dst)   # 리먹스 실패 — fMP4 그대로도 재생 가능
            else:
                os.unlink(tmp)
            return
    except Exception:
        pass
    try:
        if os.path.exists(tmp):
            os.unlink(tmp)
    except OSError:
        pass


_DETACHED_ENCODES = set()   # 백그라운드 완주 중인 cache_dst — 같은 파일 중복 완주 방지


def detach_stream_transcode(proc, tmp: str, cache_dst: str) -> None:
    """시청 중단 — 데몬 스레드가 파이프의 남은 바이트를 tmp 에 마저 쓰며(ffmpeg 블록
    방지) 인코딩을 완주시켜 캐시를 완성한다(다음 재생은 즉시 시작).
    같은 캐시를 향한 완주가 이미 달리는 중이면(재시청·seek 재요청) 이 판은 죽인다."""
    import threading

    if cache_dst in _DETACHED_ENCODES:
        kill_stream(proc)
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        return
    _DETACHED_ENCODES.add(cache_dst)

    def _drain():
        try:
            with open(tmp, "ab") as f:
                while True:
                    chunk = proc.stdout.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception:
            pass
        finish_stream_transcode(proc, tmp, cache_dst)
        _DETACHED_ENCODES.discard(cache_dst)

    threading.Thread(target=_drain, daemon=True).start()
