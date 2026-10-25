"""Shared lifecycle policy block reader."""
import os
from typing import Any, Dict

_POLICY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "lifecycle_policy.yaml")
_block_cache = {}

def load_policy_block(name: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """lifecycle_policy.yaml 의 한 블록을 defaults 위에 덮어 읽는다(캐시). 파일·yaml 부재는 defaults."""
    # 캐시는 원 블록이다. 먼저 온 호출자의 defaults 키 집합이 다음 호출을 제한하면 안 된다.
    if name not in _block_cache:
        try:
            import yaml
            with open(_POLICY_PATH, encoding="utf-8") as f:
                block = (yaml.safe_load(f) or {}).get(name) or {}
            _block_cache[name] = block if isinstance(block, dict) else {}
        except Exception:
            _block_cache[name] = {}
    pol = dict(defaults)
    for key, value in defaults.items():
        if key in _block_cache[name]:
            try:
                pol[key] = type(value)(_block_cache[name][key])
            except (ValueError, TypeError):
                pass
    return pol
