"""
collector.py - Web Collector v2: 사이트 가이드 관리 + DB 저장
=============================================================
사이트별 가이드(SITE_CONFIG) 로딩/등록, 수집 데이터 저장.
브라우저 자동화는 browser-action 도구가 담당하므로 여기에는 없음.
"""

import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent
SITES_DIR = CURRENT_DIR / "sites"

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))


# =============================================================================
# 사이트 가이드 레지스트리
# =============================================================================

_guide_cache: Dict[str, Any] = {}


def _discover_sites() -> Dict[str, dict]:
    """sites/ 폴더 스캔, SITE_CONFIG가 있는 사이트 목록 반환."""
    sites = {}
    if not SITES_DIR.exists():
        return sites

    for py_file in SITES_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        site_id = py_file.stem
        try:
            module = _load_site(site_id)
            if module and hasattr(module, "SITE_CONFIG"):
                sites[site_id] = module.SITE_CONFIG
        except Exception as e:
            logger.warning(f"[WebCollector] 사이트 로드 실패 ({site_id}): {e}")
    return sites


def _load_site(site_id: str):
    """사이트 가이드 모듈 로드 (캐시 사용)."""
    if site_id in _guide_cache:
        return _guide_cache[site_id]

    site_path = SITES_DIR / f"{site_id}.py"
    if not site_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        f"wc_site_{site_id}", str(site_path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    _guide_cache[site_id] = module
    return module


def _invalidate_cache(site_id: str = None):
    """가이드 캐시 리셋."""
    if site_id:
        _guide_cache.pop(site_id, None)
    else:
        _guide_cache.clear()


# =============================================================================
# 공개 함수: manage_sites (wc_sites 도구)
# =============================================================================

def manage_sites(action: str = "list", site_id: str = None,
                 guide_code: str = None) -> dict:
    """사이트 가이드 관리 (list/info/register)."""

    if action == "list":
        sites_map = _discover_sites()
        sites = []
        for sid, config in sites_map.items():
            sites.append({
                "id": sid,
                "name": config.get("name", sid),
                "url": config.get("url", ""),
                "description": config.get("description", ""),
                "key_field": config.get("key_field", ""),
                "fields": list(config.get("fields", {}).keys()),
                "search_params": list(config.get("search_params", {}).keys()),
            })
        return {"success": True, "count": len(sites), "sites": sites}

    elif action == "info":
        if not site_id:
            return {"success": False, "error": "site_id가 필요합니다."}
        module = _load_site(site_id)
        if not module:
            available = list(_discover_sites().keys())
            return {
                "success": False,
                "error": f"사이트를 찾을 수 없습니다: {site_id}",
                "available_sites": available
            }
        config = module.SITE_CONFIG
        return {
            "success": True,
            "site": {
                "id": config.get("id", site_id),
                "name": config.get("name", site_id),
                "url": config.get("url", ""),
                "description": config.get("description", ""),
                "key_field": config.get("key_field", ""),
                "fields": config.get("fields", {}),
                "search_params": config.get("search_params", {}),
                "guide": config.get("guide", "가이드가 작성되지 않았습니다."),
            }
        }

    elif action == "register":
        if not guide_code:
            # 템플릿 반환
            template_path = SITES_DIR / "_template.py"
            if template_path.exists():
                template = template_path.read_text(encoding="utf-8")
            else:
                template = "# 템플릿 없음. SITE_CONFIG dict을 작성하세요."
            return {
                "success": True,
                "action": "template",
                "template": template,
                "message": "SITE_CONFIG을 작성한 코드를 guide_code로 전달하세요."
            }

        # 검증
        if "SITE_CONFIG" not in guide_code:
            return {"success": False, "error": "guide_code에 SITE_CONFIG dict이 없습니다."}

        # site_id 추출
        id_match = re.search(r'"id"\s*:\s*"([a-zA-Z0-9_-]+)"', guide_code)
        if not id_match:
            id_match = re.search(r"'id'\s*:\s*'([a-zA-Z0-9_-]+)'", guide_code)
        if not id_match:
            return {"success": False, "error": "SITE_CONFIG에서 id를 추출할 수 없습니다."}

        new_site_id = id_match.group(1)
        site_path = SITES_DIR / f"{new_site_id}.py"

        # 저장
        SITES_DIR.mkdir(parents=True, exist_ok=True)
        site_path.write_text(guide_code, encoding="utf-8")
        _invalidate_cache(new_site_id)

        # 로드 테스트
        try:
            loaded = _load_site(new_site_id)
            if not loaded or not hasattr(loaded, "SITE_CONFIG"):
                return {"success": False, "error": "저장되었으나 로드 실패. 코드를 확인하세요."}
        except Exception as e:
            site_path.unlink(missing_ok=True)
            _invalidate_cache(new_site_id)
            return {"success": False, "error": f"로드 오류: {str(e)}"}

        return {
            "success": True,
            "site_id": new_site_id,
            "path": str(site_path),
            "action": "registered",
            "config_summary": {
                "name": loaded.SITE_CONFIG.get("name"),
                "url": loaded.SITE_CONFIG.get("url"),
                "key_field": loaded.SITE_CONFIG.get("key_field"),
                "fields": list(loaded.SITE_CONFIG.get("fields", {}).keys()),
            }
        }

    else:
        return {"success": False, "error": f"지원하지 않는 action: {action}. (list, info, register)"}


# =============================================================================
# 공개 함수: save_items (wc_save 도구)
# =============================================================================

def save_items(site_id: str, items: list) -> dict:
    """
    AI가 browser-action으로 수집한 데이터를 DB에 저장.

    Args:
        site_id: 사이트 ID (등록된 사이트여야 함)
        items: 저장할 데이터 목록 (list[dict])

    Returns:
        {success, site_id, new, updated, skipped, total}
    """
    if not site_id:
        return {"success": False, "error": "site_id가 필요합니다."}
    if not items:
        return {"success": False, "error": "저장할 items가 비어있습니다."}

    # 사이트 가이드 확인
    module = _load_site(site_id)
    if not module:
        available = list(_discover_sites().keys())
        return {
            "success": False,
            "error": f"등록되지 않은 사이트: {site_id}",
            "available_sites": available
        }

    config = module.SITE_CONFIG
    key_field = config.get("key_field", "id")

    # key_field 유효성 검사
    valid_items = []
    skipped_no_key = 0
    for item in items:
        key_value = str(item.get(key_field, "")).strip()
        if not key_value:
            skipped_no_key += 1
            continue
        valid_items.append(item)

    if not valid_items:
        return {
            "success": False,
            "error": f"모든 항목에 key_field({key_field})가 비어있습니다.",
            "skipped": skipped_no_key
        }

    # DB 저장
    import collector_db as db
    result = db.upsert_items_batch(site_id, valid_items, key_field)

    if skipped_no_key > 0:
        result["skipped_no_key"] = skipped_no_key

    result["site_id"] = site_id
    result["site_name"] = config.get("name", site_id)
    return result
