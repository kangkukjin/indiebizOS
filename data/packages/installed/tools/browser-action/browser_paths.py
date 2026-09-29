"""브라우저 산출물은 드라이버와 무관하게 공통 쓰기 경로 규약을 따른다."""
from datetime import datetime
from pathlib import Path

from tool_context import ToolContext


def output_path(params, project_path, *, folder, stem, ext):
    raw = (params.get("path") or "").strip()
    if raw:
        path = Path(raw)
        if path.suffix.lower() != ext:  # vj-ok: 호출자가 정한 파일 형식 확장자(.png/.pdf) 비교
            path = path.with_suffix(ext)
        raw = str(path)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw = f"outputs/{folder}/{stem}_{stamp}{ext}"
    resolved = ToolContext(project_path, "browser_op").resolve_output_path(raw)
    if resolved.get("error"):
        raise ValueError(resolved["error"])
    return Path(resolved["path"])
