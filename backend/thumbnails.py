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
# 브라우저가 대체로 그대로 재생 가능한 컨테이너(트랜스코드 불필요).
_WEB_PLAYABLE_VIDEO_EXTS = {"mp4", "m4v", "webm"}


def needs_exif_strip(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext in _EXIF_BEARING_EXTS


def needs_video_transcode(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return classify(path) == "video" and ext not in _WEB_PLAYABLE_VIDEO_EXTS


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
