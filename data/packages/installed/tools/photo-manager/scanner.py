"""
scanner.py - 사진/동영상 스캐너
EXIF 추출, MD5 해시 계산, 메타데이터 수집
"""

import os
import hashlib
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# 지원 확장자
PHOTO_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp',
    'heic', 'heif', 'tiff', 'tif', 'raw', 'cr2', 'nef', 'arw', 'dng'
}
VIDEO_EXTENSIONS = {
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv',
    'webm', 'mpg', 'mpeg', 'm4v', 'mts', '3gp'
}

# 제외 폴더
EXCLUDE_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    '.idea', '.vscode', '.DS_Store', 'dist', 'build',
    '.cache', '.npm', '.yarn', '@eaDir', '.Spotlight-V100',
    '.fseventsd', '.Trashes', 'Thumbs.db'
}


def calculate_md5(filepath: str, chunk_size: int = 65536) -> Optional[str]:
    """파일 MD5 해시 계산 (첫 64KB만 - 성능 최적화)"""
    try:
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            # 첫 64KB만 읽어서 해시 (대부분의 중복 탐지에 충분)
            chunk = f.read(chunk_size)
            if chunk:
                md5.update(chunk)
        return md5.hexdigest()
    except (IOError, OSError):
        return None


def extract_photo_metadata(filepath: str) -> Dict:
    """사진 EXIF 메타데이터 추출 (Pillow 사용)"""
    metadata = {
        'width': None,
        'height': None,
        'taken_date': None,
        'camera_make': None,
        'camera_model': None,
        'gps_lat': None,
        'gps_lon': None
    }

    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        with Image.open(filepath) as img:
            metadata['width'] = img.width
            metadata['height'] = img.height

            # EXIF 데이터 추출
            exif_data = img._getexif()
            if exif_data:
                exif = {}
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif[tag] = value

                # 촬영일
                if 'DateTimeOriginal' in exif:
                    try:
                        dt = datetime.strptime(exif['DateTimeOriginal'], '%Y:%m:%d %H:%M:%S')
                        metadata['taken_date'] = dt.isoformat()
                    except ValueError:
                        pass
                elif 'DateTime' in exif:
                    try:
                        dt = datetime.strptime(exif['DateTime'], '%Y:%m:%d %H:%M:%S')
                        metadata['taken_date'] = dt.isoformat()
                    except ValueError:
                        pass

                # 카메라 정보
                metadata['camera_make'] = exif.get('Make')
                metadata['camera_model'] = exif.get('Model')

                # GPS 정보
                if 'GPSInfo' in exif:
                    gps_info = {}
                    for key, val in exif['GPSInfo'].items():
                        gps_tag = GPSTAGS.get(key, key)
                        gps_info[gps_tag] = val

                    lat = _convert_gps_to_degrees(gps_info, 'GPSLatitude', 'GPSLatitudeRef')
                    lon = _convert_gps_to_degrees(gps_info, 'GPSLongitude', 'GPSLongitudeRef')
                    if lat is not None:
                        metadata['gps_lat'] = lat
                    if lon is not None:
                        metadata['gps_lon'] = lon

    except ImportError:
        # Pillow 없으면 기본값 유지
        pass
    except Exception:
        # 이미지 읽기 실패 시 기본값 유지
        pass

    return metadata


def _convert_gps_to_degrees(gps_info: Dict, coord_key: str, ref_key: str) -> Optional[float]:
    """GPS 좌표를 도(degrees)로 변환"""
    try:
        coord = gps_info.get(coord_key)
        ref = gps_info.get(ref_key)

        if coord is None or ref is None:
            return None

        # 도, 분, 초
        d = float(coord[0])
        m = float(coord[1])
        s = float(coord[2])

        degrees = d + (m / 60.0) + (s / 3600.0)

        if ref in ('S', 'W'):
            degrees = -degrees

        return round(degrees, 6)
    except (TypeError, IndexError, ValueError):
        return None


def extract_video_metadata(filepath: str) -> Dict:
    """동영상 메타데이터 추출 (ffprobe 사용)"""
    metadata = {
        'width': None,
        'height': None,
        'duration': None,
        'fps': None,
        'codec': None
    }

    try:
        # ffprobe로 메타데이터 추출
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            filepath
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            # 비디오 스트림 찾기
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    metadata['width'] = stream.get('width')
                    metadata['height'] = stream.get('height')
                    metadata['codec'] = stream.get('codec_name')

                    # FPS 계산
                    fps_str = stream.get('r_frame_rate', '0/1')
                    try:
                        num, den = fps_str.split('/')
                        if int(den) > 0:
                            metadata['fps'] = round(int(num) / int(den), 2)
                    except (ValueError, ZeroDivisionError):
                        pass
                    break

            # Duration
            if 'format' in data:
                duration_str = data['format'].get('duration')
                if duration_str:
                    try:
                        metadata['duration'] = round(float(duration_str), 2)
                    except ValueError:
                        pass

    except FileNotFoundError:
        # ffprobe가 설치되어 있지 않음
        pass
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    return metadata


def scan_media(path: str, scan_id: int, progress_callback=None) -> Dict:
    """
    폴더 스캔 - 사진/동영상 메타데이터 수집

    Args:
        path: 스캔할 폴더 경로
        scan_id: DB scan ID
        progress_callback: 진행 상황 콜백 함수 (current, total)

    Returns:
        스캔 결과 딕셔너리
    """
    import photo_db

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.exists(path):
        return {"success": False, "error": f"경로가 존재하지 않습니다: {path}"}

    # 기존 데이터 삭제 (재스캔)
    photo_db.clear_scan_data(scan_id)

    # 먼저 파일 목록 수집 (진행률 표시용)
    media_files = []
    for root, dirs, files in os.walk(path):
        # 제외 폴더 필터링
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]

        for filename in files:
            if filename.startswith('.'):
                continue

            ext = os.path.splitext(filename)[1].lower().lstrip('.')
            if ext in PHOTO_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                media_files.append(os.path.join(root, filename))

    total_files = len(media_files)
    photo_count = 0
    video_count = 0
    total_size = 0
    error_count = 0
    batch = []
    BATCH_SIZE = 1000

    for i, filepath in enumerate(media_files):
        try:
            stat = os.stat(filepath)
            filename = os.path.basename(filepath)
            ext = os.path.splitext(filename)[1].lower().lstrip('.')

            # 미디어 타입 결정
            if ext in PHOTO_EXTENSIONS:
                media_type = 'photo'
                photo_count += 1
            else:
                media_type = 'video'
                video_count += 1

            # mtime
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

            # 메타데이터 구성
            media_data = {
                'path': filepath,
                'filename': filename,
                'extension': ext,
                'size': stat.st_size,
                'mtime': mtime,
                'md5_hash': None,  # 중복 탐지 시 계산
                'media_type': media_type,
                'width': None,
                'height': None,
                'taken_date': None,
                'camera_make': None,
                'camera_model': None,
                'gps_lat': None,
                'gps_lon': None,
                'duration': None,
                'fps': None,
                'codec': None
            }

            # 사진이면 EXIF 메타데이터 추출 (GPS, 촬영일 등)
            if media_type == 'photo':
                photo_meta = extract_photo_metadata(filepath)
                media_data.update({
                    'width': photo_meta.get('width'),
                    'height': photo_meta.get('height'),
                    'taken_date': photo_meta.get('taken_date'),
                    'camera_make': photo_meta.get('camera_make'),
                    'camera_model': photo_meta.get('camera_model'),
                    'gps_lat': photo_meta.get('gps_lat'),
                    'gps_lon': photo_meta.get('gps_lon'),
                })
            # 동영상이면 동영상 메타데이터 추출
            elif media_type == 'video':
                video_meta = extract_video_metadata(filepath)
                media_data.update({
                    'width': video_meta.get('width'),
                    'height': video_meta.get('height'),
                    'duration': video_meta.get('duration'),
                    'fps': video_meta.get('fps'),
                    'codec': video_meta.get('codec'),
                })

            batch.append(media_data)
            total_size += stat.st_size

            # 배치 저장
            if len(batch) >= BATCH_SIZE:
                photo_db.save_media_batch(scan_id, batch)
                batch = []

            # 진행 콜백
            if progress_callback and (i + 1) % 100 == 0:
                progress_callback(i + 1, total_files)

        except (OSError, PermissionError):
            error_count += 1

    # 남은 배치 저장
    if batch:
        photo_db.save_media_batch(scan_id, batch)

    # 스캔 통계 업데이트
    photo_db.update_scan_stats(scan_id, photo_count, video_count, total_size)

    return {
        "success": True,
        "scan_id": scan_id,
        "total_files": total_files,
        "photo_count": photo_count,
        "video_count": video_count,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "errors_count": error_count
    }


def quick_scan(path: str) -> Dict:
    """
    빠른 스캔 - 메타데이터 없이 파일 목록만 수집

    Returns:
        파일 개수 및 예상 스캔 시간
    """
    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.exists(path):
        return {"success": False, "error": f"경로가 존재하지 않습니다: {path}"}

    photo_count = 0
    video_count = 0
    total_size = 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]

        for filename in files:
            if filename.startswith('.'):
                continue

            ext = os.path.splitext(filename)[1].lower().lstrip('.')
            if ext in PHOTO_EXTENSIONS:
                photo_count += 1
            elif ext in VIDEO_EXTENSIONS:
                video_count += 1
            else:
                continue

            filepath = os.path.join(root, filename)
            try:
                total_size += os.path.getsize(filepath)
            except OSError:
                pass

    total_files = photo_count + video_count
    # 예상 시간: 파일당 약 1ms (파일시스템 메타데이터만)
    estimated_seconds = total_files * 0.001

    return {
        "success": True,
        "photo_count": photo_count,
        "video_count": video_count,
        "total_files": total_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "estimated_seconds": round(estimated_seconds, 1)
    }
