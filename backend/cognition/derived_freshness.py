"""Read-only derived-file health checks; repair/build owns regeneration.

Boot and patrol must not rewrite an in-flight candidate's applied bytes using
an unrelated Git index. Report drift to the existing repair/build workflow.
"""
import sys
import time as _time
from pathlib import Path
from typing import Dict


def enforce_derived_freshness() -> Dict:
    """Observe freshness without starting an independent source mutation."""
    import os as _os
    import subprocess as _sp
    # Inspect canonical sources; neither canonical nor generation files are rewritten.
    from runtime_utils import get_source_root
    root = Path(get_source_root())
    build = root / "scripts" / "build_ibl_nodes.py"
    t0 = _time.time()
    ev = {"node": "__static__", "action": "derived_freshness", "success": True,
          "response_ms": 0, "data_quality": "ok", "error_message": None}
    if not build.exists():
        return ev
    try:
        env = dict(_os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("INDIEBIZ_CODE_ROOT", None)  # 빌더는 자기 트리(정본)를 본다
        chk = _sp.run([sys.executable, str(build), "--check"], cwd=str(root),
                      capture_output=True, text=True, timeout=300, env=env)
        if chk.returncode != 0:
            ev.update(success=False, data_quality="error",
                      error_message=("파생물 불일치 — 기존 수리/빌드 흐름에서 재생성이 필요합니다. "
                                     "점검은 파일을 변경하지 않았습니다: "
                                     + ((chk.stdout or "") + (chk.stderr or "")).strip()[-400:]))
        ev["response_ms"] = int((_time.time() - t0) * 1000)
    except Exception as e:
        ev.update(success=False, data_quality="error",
                  error_message=f"파생물 신선도 순찰 실패: {e}")
    return ev
