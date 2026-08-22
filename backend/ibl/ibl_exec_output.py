"""
ibl_exec_output.py — 출력 핸들러 (gui/open/clipboard/download) + 파이프 경로 추출.

2026-08-23 ibl_executors.py(1471줄, 1500줄 규칙 직전)에서 이사. 공개 이름은 ibl_executors 가
그대로 재수출하므로 호출자(`from ibl_executors import _output_gui`)는 무변경.
"""
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _output_gui(content: str, params: dict, project_path: str) -> Any:
    """UI에 결과를 HTML/카드/테이블로 표시"""
    content = params.get("content", content or "")
    format_type = params.get("format", "html")  # html, card, table, markdown
    title = params.get("title", "결과")

    result = {
        "type": "gui_output",
        "title": title,
        "format": format_type,
        "content": content,
    }

    # WebSocket으로 프론트엔드에 전송 (동기·스레드 안전 헬퍼 — 워커 스레드에서 호출됨)
    try:
        from websocket_manager import broadcast_message
        broadcast_message({"type": "ibl_output", "data": result})
    except Exception:
        pass

    return {"ok": True, "output": result}


# (_output_file 은 2026-08-05 어휘 압축으로 삭제 — 파일 저장 정본은 [self:write]
#  (system_essentials write_file): RED 쓰기 안전판 경유 + 파이프 _prev_result 폴백.
#  이 함수는 안전판을 우회했고 파이프 입력도 무시해 빈 파일을 쓰던 반쪽 싱크였다.)


def _extract_path_from_prev(prev_result: str) -> Optional[str]:
    """_prev_result JSON에서 파일 경로 또는 URL을 추출

    1차: 명시적 키 매칭 (file, path, url 등)
    2차: 값 패턴 매칭 (*_path, *_file, *_url 키 또는 http/파일경로 값)
    """
    if not prev_result:
        return None
    _KEYS = ("file", "path", "url", "opened",
             "output_file", "output_path", "report_path",
             "html_path", "file_path", "filepath")
    try:
        data = json.loads(prev_result)
        if isinstance(data, dict):
            # 0차: items 통화 — file_find/list 등이 반환한 items[0]에서 경로 추출.
            # "방금 찾은 파일을 읽기"(file_find | take 1 >> read) 조합을 개통한다.
            items = data.get("items")
            if isinstance(items, list) and items and isinstance(items[0], dict):
                for key in _KEYS:
                    val = items[0].get(key)
                    if val and isinstance(val, str):
                        return val
            # 1차: 명시적 키 매칭 (우선순위순)
            for key in _KEYS:
                val = data.get(key)
                if val and isinstance(val, str):
                    return val
            # 2차: *_path, *_file, *_url 패턴 키 검색
            for key, val in data.items():
                if isinstance(val, str) and val and (
                    key.endswith("_path") or key.endswith("_file") or key.endswith("_url")
                ):
                    return val
            # 3차: 값이 http:// 또는 / 로 시작하는 첫 번째 문자열
            for key, val in data.items():
                if isinstance(val, str) and val and (
                    val.startswith("http://") or val.startswith("https://") or
                    (val.startswith("/") and "." in val.split("/")[-1])
                ):
                    return val
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _output_open(path: str, params: dict, project_path: str = ".") -> Any:
    """URL을 브라우저로, 파일을 Finder로 열기

    파이프라인에서 사용 시: >> [self:open]
    _prev_result에서 file/path/url 필드를 자동 추출하여 열어준다.
    상대경로는 project_path 기준으로 절대경로로 자동 변환된다.
    """
    import subprocess
    import platform
    from pathlib import Path

    # 파이프라인 자동 추출: path가 비어있으면 _prev_result에서 경로 추출
    if not path and "_prev_result" in params:
        extracted = _extract_path_from_prev(params.get("_prev_result", ""))
        if extracted:
            path = extracted
        else:
            prev = params.get("_prev_result", "")
            return {"error": "열 대상을 찾을 수 없습니다. 이전 step이 file/path/url 키를 포함한 결과를 반환해야 합니다.",
                    "hint": "파이프라인: [도구]{...} >> [self:open] — 이전 도구가 경로/URL을 반환해야 동작합니다.",
                    "_prev_result_preview": prev[:300] if prev else "(empty)"}

    if not path:
        return {"error": "path가 필요합니다. URL 또는 파일 경로를 지정하세요."}

    if path.startswith("http://") or path.startswith("https://"):
        # URL → 브라우저
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        elif platform.system() == "Windows":
            subprocess.Popen(["start", path], shell=True)
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "opened": path, "type": "url"}
    else:
        # 상대경로 → 절대경로 변환 (project_path 기준)
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = (Path(project_path) / file_path).resolve()
        path = str(file_path)

        # 파일/폴더 → Finder/Explorer
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        elif platform.system() == "Windows":
            subprocess.Popen(["explorer", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "opened": path, "type": "file"}


def _output_clipboard(content: str, params: dict) -> Any:
    """결과를 클립보드에 복사"""
    content = params.get("content", content or "")
    if not content:
        return {"error": "복사할 내용이 없습니다."}

    import subprocess
    import platform

    text = str(content) if not isinstance(content, str) else content

    if platform.system() == "Darwin":
        # ★pbcopy 는 LC_CTYPE locale 로 stdin 을 해석한다 — 백엔드 프로세스(런처/Electron 기동)엔
        # UTF-8 locale 이 없어 한글이 mojibake 로 박히던 함정. UTF-8 을 명시해야 비ASCII 가 살아남는다.
        env = {**os.environ, "LC_CTYPE": "en_US.UTF-8"}
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, env=env)
        p.communicate(text.encode("utf-8"))
    elif platform.system() == "Windows":
        p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    else:
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
        except FileNotFoundError:
            return {"error": "xclip이 설치되어 있지 않습니다."}

    return {"ok": True, "copied_length": len(text)}


def _output_download(url: str, params: dict, project_path: str) -> Any:
    """URL에서 파일 다운로드"""
    if not url:
        return {"error": "url(다운로드 URL)이 필요합니다."}

    import urllib.request
    from urllib.parse import urlparse

    # ★B11 (2026-08-17 상상훈련 12회차): 코퍼스 교본이 가르치는 `path`(전체 저장 경로)를
    # 핸들러가 안 읽어 침묵 무시 — "outputs/파일.html" 지정이 저장소 outputs/download 로
    # 뭉개졌다(파일명 상실+프로젝트 스코핑 미적용). path 를 1순위로 받는다:
    # 절대/~ 는 그대로, 상대 경로는 프로젝트 기준(write 와 동일 규약).
    raw_path = params.get("path")
    if raw_path:
        save_path = os.path.expanduser(str(raw_path))
        if not os.path.isabs(save_path):
            save_path = os.path.join(project_path or ".", save_path)
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    else:
        filename = params.get("filename")
        if not filename:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or "download"

        save_dir = params.get("save_dir")
        if not save_dir:
            base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            save_dir = os.path.join(base, "outputs")
        os.makedirs(save_dir, exist_ok=True)

        save_path = os.path.join(save_dir, filename)

    try:
        # UA 없는 urlretrieve 는 다수 사이트(한겨레 등)가 403 (2026-08-16 6회차 실측) —
        # crawl 과 같은 부류의 평범한 브라우저 UA 로 요청한다.
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(save_path, "wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
        return {"ok": True, "path": save_path, "size": os.path.getsize(save_path)}
    except Exception as e:
        return {"error": f"다운로드 실패: {str(e)}"}


# (2026-08-05) _execute_output_node 삭제 — 유일 호출자가 위의 죽은 _execute_node 였다.
# 출력 동작의 정본은 func:output_op(_output_gui/_output_clipboard). 파일 저장은 [self:write].

