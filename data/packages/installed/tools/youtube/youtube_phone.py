"""Android substrate for the existing YouTube player; no hub or PC fallback.

The Python queue remains in tool_youtube. MediaPlayer supplies the process-shaped
playback handle, while an isolated WebView runs yt-dlp's verified EJS scripts.
"""
import json
import os
import threading
import time

_registered = False
_registration_lock = threading.Lock()


def is_phone():
    return os.environ.get("INDIEBIZ_PROFILE") == "phone"


def bridge():
    from java import jclass
    return jclass("com.indiebiz.phoneagent.PhoneActions")


def prepare():
    """Register the pinned yt-dlp EJS integration once, only on Android."""
    global _registered
    if not is_phone() or _registered:
        return
    with _registration_lock:
        if _registered:
            return
        from yt_dlp.extractor.youtube.jsc._builtin.ejs import EJSBaseJCP
        from yt_dlp.extractor.youtube.jsc.provider import (
            JsChallengeProviderError, register_preference, register_provider,
        )

        @register_provider
        class AndroidWebViewJCP(EJSBaseJCP):
            PROVIDER_NAME = "indiebiz-webview"
            PROVIDER_VERSION = "1.0.0"
            JS_RUNTIME_NAME = "android-webview"

            def is_available(self):
                return is_phone() and self._available

            def _run_js_runtime(self, stdin):
                from java import jclass
                runtime = jclass("com.indiebiz.phoneagent.PhoneJavascript")
                result = json.loads(str(runtime.evaluate(stdin)))
                if result.get("error"):
                    raise JsChallengeProviderError(result["error"])
                return result["stdout"]

        @register_preference(AndroidWebViewJCP)
        def preference(provider, requests):
            return 2000

        _registered = True


class Playback:
    """Minimal Popen contract used by the shared queue, with playback ownership."""

    def __init__(self, url, seek=0):
        self._bridge = bridge()
        self.returncode = None
        self.replaced = False
        result = json.loads(str(self._bridge.playStream(url, 70)))
        if result.get("error") or not result.get("playing"):
            raise RuntimeError(result.get("error") or "폰 재생기가 시작되지 않았습니다")
        self.playback_id = result["playback_id"]
        if seek:
            result = json.loads(str(self._bridge.seekStream(self.playback_id, float(seek))))
            if result.get("error"):
                self.terminate()
                raise RuntimeError(result["error"])

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        state = json.loads(str(self._bridge.streamStatus()))
        if state.get("playback_id") != self.playback_id:
            self.replaced = True
            self.returncode = -1
        elif state.get("error"):
            self.returncode = 1
        elif not state.get("playing"):
            self.returncode = 0
        return self.returncode

    def wait(self, timeout=None):
        deadline = time.monotonic() + timeout if timeout is not None else None
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("폰 재생 종료 대기 시간 초과")
            time.sleep(0.25)
        return self.returncode

    def terminate(self):
        result = json.loads(str(self._bridge.stopStreamIf(self.playback_id)))
        if result.get("error"):
            raise RuntimeError(result["error"])
        self.returncode = -1

    kill = terminate


def open_video(url):
    """Launching a player is not evidence that its video is playing."""
    result = json.loads(str(bridge().openMediaUrl(url)))
    if result.get("error"):
        return {"success": False, "error": result["error"]}
    return {"success": True, "opened": True, "playing": None,
            "output": "phone", "control": "external", "url": url,
            "message": "폰의 유튜브 앱 또는 브라우저에 영상을 열었습니다. 재생 상태는 확인되지 않았습니다."}
