"""
CCTV 화면 캡처 모듈

HLS 스트림(m3u8) 또는 이미지 URL에서 프레임을 캡처하여 이미지로 저장합니다.
AI가 CCTV 화면을 분석할 때 사용합니다.

의존성:
  - ffmpeg (HLS 스트림 캡처용, brew install ffmpeg)
  - requests (이미지 다운로드용)
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Optional

import requests

from common import success_response, error_response, get_output_dir, HEADERS


def _find_ffmpeg() -> Optional[str]:
    """ffmpeg 실행 파일 경로 탐색"""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    common_paths = [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for path in common_paths:
        if os.path.isfile(path):
            return path
    return None


def _detect_source_type(url: str) -> str:
    """URL에서 소스 타입 자동 감지"""
    url_lower = url.lower()

    if ".m3u8" in url_lower:
        return "hls"

    if any(url_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]):
        return "image"

    if "images-webcams.windy.com" in url_lower or "webcams.windy.com" in url_lower:
        return "image"

    if "cctvurl" in url_lower or "cctv" in url_lower:
        return "hls"

    # 기본: 이미지로 시도 후 실패시 HLS
    return "auto"


def _capture_hls(url: str, output_path: str, ffmpeg_path: str) -> dict:
    """HLS 스트림에서 프레임 캡처"""
    cmd = [
        ffmpeg_path,
        "-y",
        "-headers", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36\r\n",
        "-i", url,
        "-frames:v", "1",
        "-q:v", "2",
        "-an",
        output_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            stderr = result.stderr[-500:] if result.stderr else "알 수 없는 오류"
            return {"success": False, "error": f"ffmpeg 오류: {stderr}"}

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {"success": False, "error": "캡처 파일이 생성되지 않았습니다."}

        return {
            "success": True,
            "method": "ffmpeg_hls",
            "file_size": os.path.getsize(output_path)
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "스트림 캡처 시간 초과 (30초). 스트림이 응답하지 않습니다."}
    except Exception as e:
        return {"success": False, "error": f"HLS 캡처 오류: {str(e)}"}


def _capture_image(url: str, output_path: str) -> dict:
    """이미지 URL에서 다운로드"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            return {"success": False, "error": "URL이 이미지가 아닌 HTML 페이지입니다."}

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {"success": False, "error": "이미지 다운로드 실패 (빈 파일)"}

        return {
            "success": True,
            "method": "image_download",
            "file_size": os.path.getsize(output_path)
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "이미지 다운로드 시간 초과 (15초)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"HTTP 오류: {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"이미지 다운로드 오류: {str(e)}"}


def capture_cctv(url: str, source_type: str = "auto", filename: str = None,
                 project_path: str = None) -> str:
    """CCTV/웹캠 화면 캡처"""
    try:
        if not url:
            return error_response("url이 필요합니다.")

        # 출력 디렉토리 및 파일명
        output_dir = get_output_dir(project_path)
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cctv_capture_{timestamp}.jpg"

        if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            filename += ".jpg"

        output_path = os.path.join(output_dir, filename)

        # 소스 타입 결정
        if source_type == "auto":
            source_type = _detect_source_type(url)

        ffmpeg_path = _find_ffmpeg()

        # 캡처 실행
        if source_type == "hls":
            if not ffmpeg_path:
                return error_response("ffmpeg가 설치되어 있지 않습니다. HLS 스트림 캡처에 필요합니다. (brew install ffmpeg)")
            result = _capture_hls(url, output_path, ffmpeg_path)

        elif source_type == "image":
            result = _capture_image(url, output_path)

        else:
            # auto: 이미지 시도 후 실패시 HLS
            result = _capture_image(url, output_path)
            if not result["success"] and ffmpeg_path:
                result = _capture_hls(url, output_path, ffmpeg_path)

        if not result["success"]:
            return error_response(result.get("error", "캡처 실패"))

        return success_response(
            file_path=output_path,
            file_size=result.get("file_size", 0),
            capture_method=result.get("method", ""),
            timestamp=datetime.now().isoformat(),
            source_url=url,
            message=f"CCTV 화면을 캡처했습니다: {output_path}"
        )

    except Exception as e:
        return error_response(str(e))


if __name__ == "__main__":
    print("CCTV 캡처 모듈")
    ffmpeg = _find_ffmpeg()
    print(f"ffmpeg: {'발견 (' + ffmpeg + ')' if ffmpeg else '미설치'}")
    print(f"출력 디렉토리: {get_output_dir()}")
