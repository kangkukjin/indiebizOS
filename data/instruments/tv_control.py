"""호환 진입점. 공용 구현 정본은 data/scripts/ 에 한 벌만 둔다."""
import os
from pathlib import Path

_root = Path(os.environ.get("INDIEBIZ_BASE_PATH") or Path(__file__).resolve().parents[2])
_source = _root / "data/scripts/tv_control.py"
# 현재 모듈 namespace를 유지해 과거 import·실행·검수 호출도 같은 구현을 쓴다.
__file__ = str(_source)
exec(compile(_source.read_text(encoding="utf-8"), str(_source), "exec"))
