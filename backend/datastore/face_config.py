"""공개 얼굴 설정 상태부 — public_face 에서 이동 (2026-08-05 감사 ⑦).

data/public_face.json 의 로드·저장·캐시와 파생 getter(get_public_base·get_moved_to·
is_direct_host). 창고 매니페스트(portal_warehouse)가 이사 공지를 읽는 등 여러 표면이
이 *상태*만 필요한데, 서빙 모듈(public_face) 전체를 import 하면 표면 삼각
(public_face ↔ launcher ↔ portal) 매듭의 한 변이 됐다. 상태는 데이터층의 것.
"""
import json
import threading
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _ROOT / "data" / "public_face.json"

_DEFAULT_CONFIG = {
    "provider": "cloudflare",
    "direct_hosts": [],
    "public_base": "",
    "moved_to": "",
}

_lock = threading.Lock()
_config_cache: Optional[dict] = None
_config_mtime: float = -1.0


def load_config() -> dict:
    """설정 로드 (mtime 캐시 — 미들웨어가 매 요청 부르므로 디스크 재읽기 최소화)."""
    global _config_cache, _config_mtime
    try:
        mtime = _CONFIG_PATH.stat().st_mtime
    except OSError:
        mtime = -1.0
    with _lock:
        if _config_cache is not None and mtime == _config_mtime:
            return dict(_config_cache)
        cfg = dict(_DEFAULT_CONFIG)
        try:
            cfg.update(json.loads(_CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
        _config_cache = dict(cfg)
        _config_mtime = mtime
        return cfg


def save_config(cfg: dict) -> dict:
    global _config_cache, _config_mtime
    merged = dict(_DEFAULT_CONFIG)
    merged.update(cfg)
    merged["direct_hosts"] = sorted({(h or "").split(":")[0].strip().lower()
                                     for h in (merged.get("direct_hosts") or []) if (h or "").strip()})
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        tmp = _CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_CONFIG_PATH)
        _config_cache = dict(merged)
        try:
            _config_mtime = _CONFIG_PATH.stat().st_mtime
        except OSError:
            _config_mtime = -1.0
    return merged


def get_public_base() -> str:
    return (load_config().get("public_base") or "").rstrip("/")


def get_moved_to() -> str:
    return (load_config().get("moved_to") or "").rstrip("/")


def is_direct_host(host: str) -> bool:
    """이 Host 를 직접 서빙(공개 얼굴)으로 받는가 — 미들웨어의 유일한 질문."""
    h = (host or "").split(":")[0].strip().lower()
    if not h:
        return False
    return h in set(load_config().get("direct_hosts") or [])


