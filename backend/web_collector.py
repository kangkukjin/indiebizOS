"""
web_collector.py - 사이트 프로필 기반 구조화된 웹 데이터 수집

IBL Phase 3 - [web:collect] 액션의 엔진.
사이트 프로필(YAML)에 정의된 셀렉터/전략으로 구조화된 데이터를 수집합니다.

전략:
  - html: BeautifulSoup CSS 셀렉터 (기본)
  - api: JSON API 엔드포인트 호출
  - browser: Playwright 기반 동적 페이지 (browser-action 재사용)

사용법:
    from web_collector import collect_with_profile, collect_ad_hoc, list_profiles

    # 프로필 기반 수집
    result = collect_with_profile("example_hn")

    # 일회성 수집
    result = collect_ad_hoc(
        "https://news.ycombinator.com",
        {"items": ".athing", "title": ".titleline > a"},
        max_items=5
    )
"""

import os
import re
import json
import yaml
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup


# === 경로 ===

def _get_profiles_path() -> Path:
    """사이트 프로필 디렉토리"""
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent
    profiles_path = base / "data" / "site_profiles"
    profiles_path.mkdir(parents=True, exist_ok=True)
    return profiles_path


# === 프로필 CRUD ===

def list_profiles() -> List[Dict]:
    """사이트 프로필 목록 조회"""
    profiles_path = _get_profiles_path()
    profiles = []
    for f in sorted(profiles_path.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            profiles.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "url": data.get("url", ""),
                "strategy": data.get("strategy", "html"),
                "description": data.get("description", ""),
                "category": data.get("category", ""),
            })
        except Exception:
            pass
    return profiles


def get_profile(profile_id: str) -> Optional[Dict]:
    """프로필 조회"""
    profile_path = _get_profiles_path() / f"{profile_id}.yaml"
    if not profile_path.exists():
        return None
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        data["id"] = profile_id
        return data
    except Exception:
        return None


def save_profile(profile: dict) -> str:
    """프로필 저장"""
    profile_id = profile.get("id") or re.sub(
        r'[^\w가-힣\s-]', '', profile.get("name", "profile")
    ).replace(' ', '_').strip('_') or "profile"

    profile_path = _get_profiles_path() / f"{profile_id}.yaml"
    save_data = {k: v for k, v in profile.items() if k != "id"}

    profile_path.write_text(
        yaml.dump(save_data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )
    return profile_id


def delete_profile(profile_id: str) -> bool:
    """프로필 삭제"""
    profile_path = _get_profiles_path() / f"{profile_id}.yaml"
    if profile_path.exists():
        profile_path.unlink()
        return True
    return False


# === 수집 실행 ===

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


def collect_with_profile(profile_id: str, override_params: dict = None) -> dict:
    """
    프로필 기반 데이터 수집

    Args:
        profile_id: 사이트 프로필 ID
        override_params: 프로필 설정 오버라이드 (url, max_items 등)
    """
    profile = get_profile(profile_id)
    if not profile:
        return {
            "success": False,
            "error": f"프로필을 찾을 수 없습니다: {profile_id}",
            "available_profiles": [p["id"] for p in list_profiles()]
        }

    if override_params:
        if "url" in override_params:
            profile["url"] = override_params["url"]
        if "max_items" in override_params:
            profile.setdefault("transform", {})["max_items"] = override_params["max_items"]

    strategy = profile.get("strategy", "html")

    if strategy == "html":
        return _collect_html(profile)
    elif strategy == "api":
        return _collect_api(profile)
    elif strategy == "browser":
        return _collect_browser(profile)
    else:
        return {"success": False, "error": f"알 수 없는 전략: {strategy}"}


def collect_ad_hoc(url: str, selectors: dict, max_items: int = 20) -> dict:
    """
    프로필 없이 직접 수집 (일회성)

    Args:
        url: 수집 대상 URL
        selectors: CSS 셀렉터 딕셔너리 {items, title, link?, summary?, ...}
        max_items: 최대 아이템 수
    """
    if not selectors or not selectors.get("items"):
        # 셀렉터 없이 URL만 주어지면 기존 크롤링으로 폴백
        return _crawl_fallback(url, max_items)

    profile = {
        "url": url,
        "strategy": "html",
        "selectors": selectors,
        "transform": {"max_items": max_items}
    }
    return _collect_html(profile)


def _crawl_fallback(url: str, max_length: int = 10000) -> dict:
    """셀렉터 없이 기존 크롤링 로직으로 폴백"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'html.parser')

        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return {
            "success": True,
            "strategy": "html_fallback",
            "url": url,
            "data": text
        }
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def _collect_html(profile: dict) -> dict:
    """HTML 전략 - CSS 셀렉터 기반 수집"""
    url = profile.get("url", "")
    if not url:
        return {"success": False, "error": "URL이 필요합니다."}

    selectors = profile.get("selectors", {})
    items_selector = selectors.get("items")
    if not items_selector:
        return _crawl_fallback(url)

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, 'html.parser')
        containers = soup.select(items_selector)

        transform = profile.get("transform", {})
        max_items = transform.get("max_items", 20)
        include_fields = transform.get("include_fields")

        collected = []
        for container in containers[:max_items]:
            item = {}

            for field, selector in selectors.items():
                if field == "items":
                    continue

                el = container.select_one(selector)
                if el:
                    if field == "link":
                        item[field] = el.get("href", "")
                    elif field == "image":
                        item[field] = el.get("src", "")
                    else:
                        item[field] = el.get_text(strip=True)

            if item:
                if include_fields:
                    item = {k: v for k, v in item.items() if k in include_fields}
                collected.append(item)

        return {
            "success": True,
            "strategy": "html",
            "url": url,
            "profile": profile.get("name", profile.get("id", "")),
            "count": len(collected),
            "data": collected
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "요청 시간 초과 (15초)", "url": url}
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def _collect_api(profile: dict) -> dict:
    """API 전략 - JSON API 호출"""
    url = profile.get("url", "")
    if not url:
        return {"success": False, "error": "API URL이 필요합니다."}

    api_config = profile.get("api", {})
    method = api_config.get("method", "GET").upper()
    headers = {**HEADERS, **api_config.get("headers", {})}
    query_params = api_config.get("params", {})
    json_body = api_config.get("body")
    data_path = api_config.get("data_path", "")

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=query_params, timeout=15)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_body, timeout=15)
        else:
            return {"success": False, "error": f"지원하지 않는 메서드: {method}"}

        response.raise_for_status()
        data = response.json()

        # data_path로 중첩 데이터 접근 (예: "results.items")
        if data_path:
            for key in data_path.split("."):
                if isinstance(data, dict):
                    data = data.get(key, {})
                elif isinstance(data, list) and key.isdigit():
                    idx = int(key)
                    data = data[idx] if idx < len(data) else {}

        transform = profile.get("transform", {})
        max_items = transform.get("max_items", 20)

        if isinstance(data, list):
            data = data[:max_items]

        return {
            "success": True,
            "strategy": "api",
            "url": url,
            "count": len(data) if isinstance(data, list) else 1,
            "data": data
        }

    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def _collect_browser(profile: dict) -> dict:
    """Browser 전략 - Playwright 기반 동적 페이지"""
    url = profile.get("url", "")
    if not url:
        return {"success": False, "error": "URL이 필요합니다."}

    try:
        from tool_loader import load_tool_handler
        handler = load_tool_handler("browser_navigate")
        if not handler:
            return {"success": False, "error": "browser-action 패키지가 설치되지 않았습니다."}

        import asyncio
        import inspect

        def _run(tool_name, params):
            result = handler.execute(tool_name, params, ".")
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            return pool.submit(asyncio.run, result).result()
                    else:
                        return loop.run_until_complete(result)
                except RuntimeError:
                    return asyncio.run(result)
            return result

        # 페이지 열기
        _run("browser_navigate", {"url": url})

        # 셀렉터가 있으면 JavaScript로 구조화 수집
        selectors = profile.get("selectors", {})
        if selectors.get("items"):
            js_code = _build_extraction_js(selectors, profile.get("transform", {}))
            eval_result = _run("browser_evaluate", {"code": js_code})

            # 결과 파싱
            try:
                if isinstance(eval_result, str):
                    data = json.loads(eval_result)
                elif isinstance(eval_result, dict) and "result" in eval_result:
                    data = json.loads(eval_result["result"]) if isinstance(eval_result["result"], str) else eval_result["result"]
                else:
                    data = eval_result
            except (json.JSONDecodeError, TypeError):
                data = eval_result

            return {
                "success": True,
                "strategy": "browser",
                "url": url,
                "count": len(data) if isinstance(data, list) else 1,
                "data": data
            }

        # 셀렉터 없으면 콘텐츠 텍스트 추출
        content = _run("browser_get_content", {})
        return {
            "success": True,
            "strategy": "browser",
            "url": url,
            "data": content,
            "note": "셀렉터 없이 페이지 텍스트만 추출했습니다."
        }

    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def _build_extraction_js(selectors: dict, transform: dict) -> str:
    """CSS 셀렉터 기반 JavaScript 추출 코드 생성"""
    items_sel = selectors.get("items", "")
    max_items = transform.get("max_items", 20)

    field_lines = []
    for field, selector in selectors.items():
        if field == "items":
            continue
        # JavaScript 문자열 이스케이프
        sel_escaped = selector.replace("'", "\\'")
        if field in ("link",):
            field_lines.append(
                f"    var {field}El = item.querySelector('{sel_escaped}');\n"
                f"    obj['{field}'] = {field}El ? {field}El.href || '' : '';"
            )
        elif field in ("image",):
            field_lines.append(
                f"    var {field}El = item.querySelector('{sel_escaped}');\n"
                f"    obj['{field}'] = {field}El ? {field}El.src || '' : '';"
            )
        else:
            field_lines.append(
                f"    var {field}El = item.querySelector('{sel_escaped}');\n"
                f"    obj['{field}'] = {field}El ? {field}El.textContent.trim() : '';"
            )

    fields_code = "\n".join(field_lines)
    items_escaped = items_sel.replace("'", "\\'")

    return f"""(function() {{
  var items = document.querySelectorAll('{items_escaped}');
  var results = [];
  for (var i = 0; i < Math.min(items.length, {max_items}); i++) {{
    var item = items[i];
    var obj = {{}};
{fields_code}
    results.push(obj);
  }}
  return JSON.stringify(results);
}})()"""


# === IBL 노드 액션 핸들러 ===

def execute_web_collect_action(action: str, target: str, params: dict,
                               project_path: str) -> Any:
    """
    ibl_engine에서 호출되는 web:collect 액션 핸들러

    Args:
        action: "collect"
        target: 사이트 프로필 ID 또는 URL
        params: 추가 파라미터 (selectors, max_items 등)
    """
    if action == "collect":
        # target이 URL이면 ad-hoc 수집
        if target and (target.startswith("http://") or target.startswith("https://")):
            selectors = params.get("selectors", {})
            max_items = params.get("max_items", 20)
            return collect_ad_hoc(target, selectors, max_items)

        # target이 프로필 ID이면 프로필 기반 수집
        if target:
            return collect_with_profile(target, params)

        # target이 없으면 프로필 목록 반환
        profiles = list_profiles()
        return {
            "message": "프로필 ID 또는 URL을 target으로 지정하세요.",
            "available_profiles": profiles,
            "count": len(profiles)
        }

    return {"error": f"web_collector에 '{action}' 액션이 없습니다."}
