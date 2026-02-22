"""
CCTV 화면 캡처 모듈

4가지 캡처 방법을 자동으로 시도:
  1. 이미지 URL 직접 다운로드 (가장 빠름)
  2. ffmpeg HLS 스트림 프레임 추출
  3. Playwright headless 브라우저 스크린샷 (HTML 사이트용)
  4. auto: 1→2→3 순서로 자동 시도

AI가 CCTV 화면을 분석할 때 사용합니다.
브라우저로 사이트에 직접 접속할 필요 없이 이 모듈 하나로 처리.

의존성:
  - ffmpeg (HLS 스트림 캡처용, brew install ffmpeg)
  - requests (이미지 다운로드용)
  - playwright (브라우저 캡처용, 선택)
"""

import asyncio
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

    # HTML 사이트 (스트리밍 플레이어가 내장된 웹페이지)
    if any(domain in url_lower for domain in [
        "skylinewebcams.com", "earthcam.com", "insecam.org",
        "webcamtaxi.com", "opentopia.com", "windy.com/webcams",
        "youtube.com/watch", "youtu.be",
    ]):
        return "browser"

    # 일반 웹페이지 URL이면 브라우저 캡처 시도
    if url_lower.startswith("http") and not any(
        ext in url_lower for ext in [".m3u8", ".mp4", ".ts", ".jpg", ".png"]
    ):
        return "browser"

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
        return {"success": False, "error": "스트림 캡처 시간 초과 (30초)"}
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


async def _capture_browser_async(url: str, output_path: str, wait_seconds: int = 8) -> dict:
    """Playwright headless 브라우저로 웹페이지 스크린샷 캡처.

    CCTV/웹캠 사이트에 접속하여 스트리밍 플레이어가 로드된 후 스크린샷을 찍는다.
    domcontentloaded만 기다리고 짧은 sleep 후 캡처 — 절대 load를 기다리지 않음.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "error": "playwright가 설치되어 있지 않습니다."}

    browser = None
    pw = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--autoplay-policy=no-user-gesture-required',
                '--no-first-run',
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            locale='ko-KR',
        )
        page = await context.new_page()

        # domcontentloaded만 기다림 — load를 기다리면 스트리밍 사이트에서 멈춤
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as nav_err:
            # 타임아웃이어도 페이지가 일부 로드되었으면 계속 진행
            print(f"[CCTV 브라우저] 네비게이션 경고: {str(nav_err)[:100]}")

        # 스트리밍 플레이어 로드 대기 (짧게)
        await asyncio.sleep(wait_seconds)

        # 쿠키/팝업 닫기 시도 (일반적인 패턴)
        for dismiss_selector in [
            'button:has-text("Accept")', 'button:has-text("Close")',
            'button:has-text("확인")', 'button:has-text("닫기")',
            '[class*="cookie"] button', '[class*="consent"] button',
            '[class*="popup"] button[class*="close"]',
        ]:
            try:
                btn = page.locator(dismiss_selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click(timeout=1000)
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        # 스크린샷
        # .png로 캡처 후 필요 시 변환
        png_path = output_path.rsplit('.', 1)[0] + '.png'
        await page.screenshot(path=png_path, full_page=False)

        # png → jpg 변환 (용량 절약)
        if output_path.lower().endswith('.jpg') or output_path.lower().endswith('.jpeg'):
            try:
                from PIL import Image
                img = Image.open(png_path)
                img = img.convert('RGB')
                img.save(output_path, 'JPEG', quality=85)
                os.remove(png_path)
            except ImportError:
                # PIL 없으면 png 그대로 사용
                if png_path != output_path:
                    os.rename(png_path, output_path)
        else:
            if png_path != output_path:
                os.rename(png_path, output_path)

        await context.close()
        await browser.close()
        await pw.stop()

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {"success": False, "error": "브라우저 스크린샷이 비어있습니다."}

        return {
            "success": True,
            "method": "browser_screenshot",
            "file_size": os.path.getsize(output_path)
        }
    except Exception as e:
        # 정리
        try:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
        except Exception:
            pass
        return {"success": False, "error": f"브라우저 캡처 오류: {str(e)}"}


def _capture_browser(url: str, output_path: str, wait_seconds: int = 8) -> dict:
    """브라우저 캡처 (sync wrapper)"""
    try:
        # 이미 실행 중인 이벤트 루프 확인
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 이벤트 루프가 실행 중이면 별도 스레드에서 실행
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run,
                    _capture_browser_async(url, output_path, wait_seconds)
                ).result(timeout=60)
        else:
            return asyncio.run(
                _capture_browser_async(url, output_path, wait_seconds)
            )
    except Exception as e:
        return {"success": False, "error": f"브라우저 캡처 실행 오류: {str(e)}"}


def capture_cctv(url: str, source_type: str = "auto", filename: str = None,
                 project_path: str = None, wait_seconds: int = 8) -> str:
    """CCTV/웹캠 화면 캡처.

    source_type:
      - auto: 이미지 → HLS → 브라우저 순으로 자동 시도
      - image: 이미지 URL 직접 다운로드
      - hls: ffmpeg HLS 스트림 캡처
      - browser: Playwright headless 브라우저 스크린샷
    """
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
        print(f"[CCTV 캡처] url={url[:80]}..., type={source_type}")

        # 캡처 실행
        if source_type == "hls":
            if not ffmpeg_path:
                # ffmpeg 없으면 브라우저로 폴백
                result = _capture_browser(url, output_path, wait_seconds)
            else:
                result = _capture_hls(url, output_path, ffmpeg_path)

        elif source_type == "image":
            result = _capture_image(url, output_path)

        elif source_type == "browser":
            result = _capture_browser(url, output_path, wait_seconds)

        else:
            # auto: 이미지 → HLS → 브라우저 순서로 시도
            result = _capture_image(url, output_path)
            if not result["success"] and ffmpeg_path:
                print(f"[CCTV 캡처] 이미지 실패, HLS 시도...")
                result = _capture_hls(url, output_path, ffmpeg_path)
            if not result["success"]:
                print(f"[CCTV 캡처] HLS 실패, 브라우저 시도...")
                result = _capture_browser(url, output_path, wait_seconds)

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
    print("CCTV 캡처 모듈 v2.1.0")
    ffmpeg = _find_ffmpeg()
    print(f"ffmpeg: {'발견 (' + ffmpeg + ')' if ffmpeg else '미설치'}")
    print(f"출력 디렉토리: {get_output_dir()}")

    # Playwright 확인
    try:
        from playwright.async_api import async_playwright
        print("playwright: 설치됨")
    except ImportError:
        print("playwright: 미설치 (브라우저 캡처 불가)")
