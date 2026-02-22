"""
api_engine.py - API 레지스트리 기반 실행 엔진

IBL Phase 1의 핵심.
api_registry.yaml을 읽고, 도구 이름으로 API를 자동 호출합니다.

사용법:
    from api_engine import execute_tool, is_registry_tool, list_registry_tools

    # 도구 실행
    result = execute_tool("search_laws", {"query": "임대차"})

    # 레지스트리에 등록된 도구인지 확인
    if is_registry_tool("search_laws"):
        ...
"""

import os
import re
import yaml
import requests
import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from xml.etree import ElementTree

from common.api_client import api_call, api_call_raw
from common.auth_manager import get_api_key, get_api_headers, get_auth_query_params, check_api_key


# === 레지스트리 로딩 ===

_registry: Optional[Dict] = None
_registry_path: Optional[Path] = None


def _get_registry_path() -> Path:
    """api_registry.yaml 경로"""
    global _registry_path
    if _registry_path:
        return _registry_path
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        _registry_path = Path(env_path) / "data" / "api_registry.yaml"
    else:
        _registry_path = Path(__file__).parent.parent / "data" / "api_registry.yaml"
    return _registry_path


def _load_registry() -> Dict:
    """레지스트리 로드 (캐싱)"""
    global _registry
    if _registry is not None:
        return _registry

    path = _get_registry_path()
    if not path.exists():
        _registry = {"services": {}, "tools": {}}
        return _registry

    with open(path, "r", encoding="utf-8") as f:
        _registry = yaml.safe_load(f) or {"services": {}, "tools": {}}
    return _registry


def reload_registry():
    """레지스트리 강제 리로드"""
    global _registry
    _registry = None
    _load_registry()


# === 공개 API ===

def is_registry_tool(tool_name: str) -> bool:
    """도구가 레지스트리에 등록되어 있는지 확인"""
    reg = _load_registry()
    return tool_name in reg.get("tools", {})


def list_registry_tools() -> List[str]:
    """레지스트리에 등록된 모든 도구 이름"""
    reg = _load_registry()
    return list(reg.get("tools", {}).keys())


def get_tool_config(tool_name: str) -> Optional[Dict]:
    """도구 설정 조회"""
    reg = _load_registry()
    return reg.get("tools", {}).get(tool_name)


def get_service_config(service_name: str) -> Optional[Dict]:
    """서비스 설정 조회"""
    reg = _load_registry()
    return reg.get("services", {}).get(service_name)


def execute_tool(tool_name: str, tool_input: dict, project_path: str = ".") -> Any:
    """
    레지스트리 기반으로 도구 실행

    Args:
        tool_name: 도구 이름 (api_registry.yaml의 tools 섹션 키)
        tool_input: 도구 파라미터 (AI가 전달하는 파라미터)
        project_path: 프로젝트 경로

    Returns:
        API 응답 (dict, list, str 등)
    """
    reg = _load_registry()
    tool_config = reg.get("tools", {}).get(tool_name)
    if not tool_config:
        return {"error": f"레지스트리에 등록되지 않은 도구: {tool_name}"}

    # 0. 파이프라인 도구인 경우 별도 처리
    pipeline_config = tool_config.get("pipeline")
    if pipeline_config:
        from api_pipeline import execute_pipeline
        result = execute_pipeline(
            pipeline_config,
            tool_config.get("merge", {}),
            tool_input,
            reg.get("services", {}),
        )
        return _apply_post_process(tool_config, result, tool_input)

    # 0.5. for_each 루프: 여러 값에 대해 반복 호출 후 결과 집계
    for_each_config = tool_config.get("for_each")
    if for_each_config:
        return _execute_for_each(tool_name, tool_config, tool_input, for_each_config, reg)

    service_name = tool_config.get("service")
    service_config = reg.get("services", {}).get(service_name)
    if not service_config:
        return {"error": f"알 수 없는 서비스: {service_name}"}

    # 1. 인증 확인
    auth_config = service_config.get("auth", {})
    auth_type = auth_config.get("type", "none")

    if auth_type != "none":
        auth_ok, auth_err = _check_auth(service_name, auth_config, tool_config)
        if not auth_ok:
            return {"error": auth_err}

    # 2. URL 구성 (도구별 base_url 오버라이드 지원)
    base_url = tool_config.get("base_url") or service_config.get("base_url", "")
    endpoint = tool_config.get("endpoint", "")

    # 동적 엔드포인트 처리 (예: "/{endpoint}")
    endpoint = _resolve_dynamic_endpoint(endpoint, tool_input)

    url = f"{base_url}{endpoint}"

    # 3. 파라미터 구성
    params = _build_params(tool_config, tool_input, auth_config)

    # 4. 헤더 구성
    headers = _build_headers(auth_config)
    # 도구별 추가 헤더
    extra_headers = tool_config.get("headers")
    if extra_headers and isinstance(extra_headers, dict):
        headers.update(extra_headers)

    # 5. Body 구성 (POST JSON/form)
    json_body = _build_json_body(tool_config, tool_input)
    form_data = _build_form_data(tool_config, tool_input)

    # 6. HTTP 호출
    method = tool_config.get("method", "GET")
    timeout = tool_config.get("timeout") or service_config.get("timeout", 10)
    response_type = tool_config.get("response_type",
                                     service_config.get("response_format", "json"))

    # retry 설정 (도구 또는 서비스 레벨)
    retry_config = tool_config.get("retry") or service_config.get("retry")

    raw_result = _do_request(method, url, headers, params, timeout, response_type,
                             json_body=json_body, form_data=form_data,
                             retry_config=retry_config)

    # 7. 에러 확인
    if isinstance(raw_result, dict) and "error" in raw_result:
        return raw_result

    # 8. 응답 변환 (선언적 response: 우선, 없으면 기존 transform:)
    response_config = tool_config.get("response")
    if response_config:
        from api_transforms import apply_declarative_transform
        result = apply_declarative_transform(raw_result, response_config, tool_input)
        return _apply_post_process(tool_config, result, tool_input)

    transform_name = tool_config.get("transform")
    if transform_name:
        result = _apply_transform(transform_name, raw_result, tool_input)
        return _apply_post_process(tool_config, result, tool_input)

    return _apply_post_process(tool_config, raw_result, tool_input)


# === for_each 반복 실행 ===

def _execute_for_each(
    tool_name: str,
    tool_config: dict,
    tool_input: dict,
    for_each_config: dict,
    reg: dict,
) -> Any:
    """for_each 블록 실행: 여러 값에 대해 API를 반복 호출하고 결과를 집계

    YAML 예시:
        for_each:
          param: deal_date              # 반복할 파라미터 이름
          values: {from_input: months}  # tool_input에서 리스트 가져오기
          # 또는 values: ["202401", "202402", "202403"]  # 직접 리스트
          aggregate: concat             # concat | last | first_success
          delay: 0.5                    # 호출 간 딜레이 (초, 선택)
          on_error: continue            # continue | stop (기본: continue)

    집계 모드:
      - concat: 모든 결과를 하나의 리스트로 병합 (기본)
      - last: 마지막 성공 결과만 반환
      - first_success: 첫 번째 성공 결과 반환
    """
    import time as _time

    param_name = for_each_config.get("param")
    if not param_name:
        return {"error": "for_each.param이 설정되지 않았습니다."}

    # 반복 값 결정
    values_config = for_each_config.get("values")
    if isinstance(values_config, list):
        values = values_config
    elif isinstance(values_config, dict) and "from_input" in values_config:
        values = tool_input.get(values_config["from_input"], [])
        if isinstance(values, str):
            # 콤마 구분 문자열도 지원
            values = [v.strip() for v in values.split(",") if v.strip()]
    else:
        return {"error": "for_each.values가 올바르지 않습니다. 리스트 또는 {from_input: key} 형식이어야 합니다."}

    if not values:
        return {"error": "for_each.values가 비어있습니다."}

    aggregate = for_each_config.get("aggregate", "concat")
    delay = for_each_config.get("delay", 0)
    on_error = for_each_config.get("on_error", "continue")

    # for_each 제거한 tool_config 복사 (재귀 방지)
    single_config = {k: v for k, v in tool_config.items() if k != "for_each"}

    all_results = []
    errors = []

    for i, value in enumerate(values):
        # 반복 파라미터를 tool_input에 주입
        iter_input = dict(tool_input)
        iter_input[param_name] = value
        # _for_each_index 제공 (디버깅/템플릿용)
        iter_input["_for_each_index"] = i
        iter_input["_for_each_value"] = value

        # 단일 실행 (재귀 호출 대신 직접 실행)
        result = _execute_single_tool(single_config, iter_input, reg)

        is_err = isinstance(result, dict) and "error" in result

        if is_err:
            errors.append({"index": i, "value": value, "error": result.get("error")})
            if on_error == "stop":
                break
        else:
            if aggregate == "first_success":
                return _apply_post_process(tool_config, result, tool_input)
            all_results.append(result)

        # 호출 간 딜레이
        if delay and i < len(values) - 1:
            _time.sleep(delay)

    if aggregate == "last" and all_results:
        return _apply_post_process(tool_config, all_results[-1], tool_input)

    # concat: 리스트 데이터 병합
    combined = []
    for result in all_results:
        if isinstance(result, list):
            combined.extend(result)
        elif isinstance(result, dict):
            # dict 안의 리스트 찾기
            found_list = False
            for key in ("data", "items", "results"):
                if key in result and isinstance(result[key], list):
                    combined.extend(result[key])
                    found_list = True
                    break
            if not found_list:
                combined.append(result)
        else:
            combined.append(result)

    final = {
        "success": True,
        "count": len(combined),
        "data": combined,
    }
    if errors:
        final["errors"] = errors
        final["error_count"] = len(errors)

    return _apply_post_process(tool_config, final, tool_input)


def _execute_single_tool(tool_config: dict, tool_input: dict, reg: dict) -> Any:
    """단일 API 호출 실행 (for_each 내부용, execute_tool의 핵심 로직)"""
    service_name = tool_config.get("service")
    service_config = reg.get("services", {}).get(service_name)
    if not service_config:
        return {"error": f"알 수 없는 서비스: {service_name}"}

    # 인증
    auth_config = service_config.get("auth", {})
    auth_type = auth_config.get("type", "none")
    if auth_type != "none":
        auth_ok, auth_err = _check_auth(service_name, auth_config, tool_config)
        if not auth_ok:
            return {"error": auth_err}

    # URL
    base_url = tool_config.get("base_url") or service_config.get("base_url", "")
    endpoint = tool_config.get("endpoint", "")
    endpoint = _resolve_dynamic_endpoint(endpoint, tool_input)
    url = f"{base_url}{endpoint}"

    # 파라미터, 헤더, Body
    params = _build_params(tool_config, tool_input, auth_config)
    headers = _build_headers(auth_config)
    extra_headers = tool_config.get("headers")
    if extra_headers and isinstance(extra_headers, dict):
        headers.update(extra_headers)
    json_body = _build_json_body(tool_config, tool_input)
    form_data = _build_form_data(tool_config, tool_input)

    # HTTP 호출
    method = tool_config.get("method", "GET")
    timeout = tool_config.get("timeout") or service_config.get("timeout", 10)
    response_type = tool_config.get("response_type",
                                     service_config.get("response_format", "json"))
    retry_config = tool_config.get("retry") or service_config.get("retry")

    raw_result = _do_request(method, url, headers, params, timeout, response_type,
                             json_body=json_body, form_data=form_data,
                             retry_config=retry_config)

    if isinstance(raw_result, dict) and "error" in raw_result:
        return raw_result

    # 응답 변환
    response_config = tool_config.get("response")
    if response_config:
        from api_transforms import apply_declarative_transform
        return apply_declarative_transform(raw_result, response_config, tool_input)

    transform_name = tool_config.get("transform")
    if transform_name:
        return _apply_transform(transform_name, raw_result, tool_input)

    return raw_result


# === post_process 훅 ===

def _apply_post_process(tool_config: dict, result: Any, tool_input: dict) -> Any:
    """post_process 훅: Python 함수 참조로 결과 후처리

    YAML 예시:
        post_process: "investment.tool_fmp.enrich_stock_data"
        # 또는 패키지 경로 자동 해석:
        post_process: "tool_fmp.enrich_stock_data"

    함수 시그니처:
        def enrich_stock_data(result: Any, tool_input: dict) -> Any:
            # result 가공 후 반환
            return modified_result

    패키지 경로 검색 순서:
        1. 절대 경로 (예: investment.tool_fmp.func)
        2. data/packages/installed/tools/ 하위 (예: tool_fmp → investment/tool_fmp.py)
    """
    post_process = tool_config.get("post_process")
    if not post_process:
        return result

    try:
        func = _resolve_post_process_func(post_process)
        if func:
            return func(result, tool_input)
        else:
            # 함수를 찾지 못해도 원본 결과는 반환
            return result
    except Exception as e:
        # post_process 실패 시 원본 결과 + 경고
        if isinstance(result, dict):
            result["_post_process_warning"] = f"후처리 실패: {str(e)}"
        return result


def _resolve_post_process_func(func_path: str):
    """post_process 함수 참조를 실제 함수로 해석

    지원 형식:
      - "module.submodule.func_name" — importlib로 로딩
      - "tool_module.func_name" — packages/installed/tools/ 에서 검색
    """
    if not func_path or not isinstance(func_path, str):
        return None

    parts = func_path.rsplit(".", 1)
    if len(parts) != 2:
        return None

    module_path, func_name = parts

    # 1. 직접 import 시도
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, func_name, None)
    except ImportError:
        pass

    # 2. packages/installed/tools/ 하위에서 검색
    import sys
    base = Path(__file__).parent.parent / "data" / "packages" / "installed" / "tools"
    if base.exists():
        # module_path가 "tool_fmp" 형태인 경우 → 모든 패키지 폴더에서 찾기
        for pkg_dir in base.iterdir():
            if not pkg_dir.is_dir():
                continue
            candidate = pkg_dir / f"{module_path}.py"
            if candidate.exists():
                # sys.path에 패키지 디렉토리 추가
                pkg_str = str(pkg_dir)
                if pkg_str not in sys.path:
                    sys.path.insert(0, pkg_str)
                try:
                    mod = importlib.import_module(module_path)
                    return getattr(mod, func_name, None)
                except ImportError:
                    pass

    return None


# === 내부 헬퍼 ===

def _check_auth(service_name: str, auth_config: dict, tool_config: dict) -> tuple:
    """인증 확인"""
    auth_type = auth_config.get("type")

    if auth_type == "query_param":
        env_var = auth_config.get("env_var", "")
        key = os.environ.get(env_var, "")
        if not key and auth_config.get("config_fallback"):
            # 패키지 config.json에서 fallback
            key = _try_config_fallback(service_name, env_var)
        if not key:
            return False, f"{env_var} 환경변수가 설정되지 않았습니다."
        return True, ""

    elif auth_type == "header":
        if auth_config.get("static_value"):
            return True, ""
        env_var = auth_config.get("env_var", "")
        if not os.environ.get(env_var, ""):
            return False, f"{env_var} 환경변수가 설정되지 않았습니다."
        return True, ""

    elif auth_type == "header_pair":
        missing = []
        for _, env_var in auth_config.get("headers", {}).items():
            if not os.environ.get(env_var, ""):
                missing.append(env_var)
        if missing:
            return False, f"{', '.join(missing)} 환경변수가 설정되지 않았습니다."
        return True, ""

    elif auth_type == "oauth2":
        missing = []
        for _, env_var in auth_config.get("env_vars", {}).items():
            if not os.environ.get(env_var, ""):
                missing.append(env_var)
        if missing:
            return False, f"{', '.join(missing)} 환경변수가 설정되지 않았습니다."
        return True, ""

    return True, ""


def _try_config_fallback(service_name: str, env_var: str) -> Optional[str]:
    """패키지 config.json에서 API 키 fallback 조회"""
    # tool_loader의 도구 경로를 사용
    try:
        from tool_loader import get_tools_path
        tools_path = get_tools_path()
        # 서비스 이름으로 패키지 디렉토리 추정
        for pkg_dir in tools_path.iterdir():
            config_path = pkg_dir / "config.json"
            if config_path.exists():
                import json
                config = json.loads(config_path.read_text(encoding="utf-8"))
                key = config.get("api_key") or config.get(env_var)
                if key:
                    return key
    except Exception:
        pass
    return None


def _resolve_dynamic_endpoint(endpoint: str, tool_input: dict) -> str:
    """동적 엔드포인트 변환 (예: "/{endpoint}" → "/weather")"""
    def replacer(match):
        key = match.group(1)
        return str(tool_input.get(key, ""))
    return re.sub(r'\{(\w+)\}', replacer, endpoint)


def _build_params(tool_config: dict, tool_input: dict, auth_config: dict) -> dict:
    """API 쿼리 파라미터 구성"""
    params = {}

    # 1. 기본 파라미터
    default_params = tool_config.get("default_params", {})
    params.update(default_params)

    # 2. 인증 파라미터 (query_param 방식)
    auth_type = auth_config.get("type")
    if auth_type == "query_param":
        env_var = auth_config.get("env_var", "")
        key = os.environ.get(env_var, "")
        if not key and auth_config.get("config_fallback"):
            key = _try_config_fallback("", env_var) or ""
        key_name = auth_config.get("key_name", "apiKey")
        params[key_name] = key

    # 3. 파라미터 매핑 (tool_input 키 → API 파라미터 키)
    param_map = tool_config.get("param_map", {})
    defaults = tool_config.get("defaults", {})

    for input_key, api_key in param_map.items():
        if api_key == "_spread":
            # _spread: tool_input[input_key]가 dict면 풀어서 전달
            spread_val = tool_input.get(input_key, {})
            if isinstance(spread_val, dict):
                params.update(spread_val)
        else:
            val = tool_input.get(input_key)
            if val is None:
                val = defaults.get(input_key)
            if val is not None:
                params[api_key] = val

    # 4. defaults에서 param_map에 없는 키도 직접 반영
    for key, default_val in defaults.items():
        if key not in param_map:
            # default가 있고 params에 없으면 추가
            if key not in params:
                params[key] = default_val

    return params


def _build_json_body(tool_config: dict, tool_input: dict) -> Any:
    """JSON 요청 바디 구성

    YAML 예시:
        json_body:
          defaults: {format: "json"}
          param_map: {query: searchQuery, limit: maxResults}
    """
    body_config = tool_config.get("json_body")
    if not body_config:
        return None
    if not isinstance(body_config, dict):
        return body_config

    body = dict(body_config.get("defaults", {}))
    param_map = body_config.get("param_map", {})
    for input_key, body_key in param_map.items():
        val = tool_input.get(input_key)
        if val is not None:
            body[body_key] = val
    return body if body else None


def _build_form_data(tool_config: dict, tool_input: dict) -> Any:
    """Form 요청 바디 구성 (application/x-www-form-urlencoded)

    YAML 예시:
        form_body:
          grant_type: client_credentials
          client_id: {env: AMADEUS_API_KEY}
    """
    form_config = tool_config.get("form_body")
    if not form_config or not isinstance(form_config, dict):
        return None

    form = {}
    for key, val in form_config.items():
        if isinstance(val, dict) and "env" in val:
            form[key] = os.environ.get(val["env"], "")
        elif isinstance(val, dict) and "from_input" in val:
            form[key] = tool_input.get(val["from_input"], "")
        else:
            form[key] = val
    return form if form else None


def _build_headers(auth_config: dict) -> dict:
    """API 요청 헤더 구성"""
    headers = {}
    auth_type = auth_config.get("type")

    if auth_type == "header":
        if auth_config.get("static_value"):
            headers[auth_config["header_name"]] = auth_config["static_value"]
        else:
            env_var = auth_config.get("env_var", "")
            key = os.environ.get(env_var, "")
            prefix = auth_config.get("prefix", "")
            headers[auth_config["header_name"]] = f"{prefix}{key}"

    elif auth_type == "header_pair":
        for header_name, env_var in auth_config.get("headers", {}).items():
            headers[header_name] = os.environ.get(env_var, "")

    return headers


def _do_request(method: str, url: str, headers: dict, params: dict,
                timeout: int, response_type: str,
                json_body: Any = None, form_data: Any = None,
                retry_config: dict = None) -> Any:
    """HTTP 요청 실행 (query params + JSON body + form data + retry 지원)

    Args:
        retry_config: 재시도 설정 (선택)
            max_attempts: 최대 시도 횟수 (기본 1 = 재시도 없음)
            backoff: 대기 전략 - "fixed" | "exponential" (기본 "exponential")
            delay: 기본 대기 시간 초 (기본 1.0)
            retry_on: 재시도할 HTTP 상태 코드 (기본 [429, 500, 502, 503, 504])

    YAML 예시:
        retry:
          max_attempts: 3
          backoff: exponential
          delay: 1.0
          retry_on: [429, 500, 502, 503]
    """
    import time as _time

    max_attempts = 1
    backoff = "exponential"
    delay = 1.0
    retry_on = {429, 500, 502, 503, 504}

    if retry_config and isinstance(retry_config, dict):
        max_attempts = retry_config.get("max_attempts", 3)
        backoff = retry_config.get("backoff", "exponential")
        delay = retry_config.get("delay", 1.0)
        codes = retry_config.get("retry_on", [429, 500, 502, 503, 504])
        retry_on = set(codes) if isinstance(codes, list) else {429, 500, 502, 503, 504}

    last_error = None

    for attempt in range(max_attempts):
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params if params else None,
                json=json_body,
                data=form_data,
                timeout=timeout,
            )

            # 재시도 가능한 에러인지 확인
            if response.status_code in retry_on and attempt < max_attempts - 1:
                wait = delay * (2 ** attempt) if backoff == "exponential" else delay
                _time.sleep(wait)
                continue

            # HTTP 에러 처리 (재시도 불가 또는 마지막 시도)
            if response.status_code == 401:
                return {"error": f"API 인증 실패 (HTTP 401)"}
            elif response.status_code == 400:
                return {"error": f"잘못된 요청: {response.text[:300]} (HTTP 400)"}
            elif response.status_code == 403:
                return {"error": "접근 거부 (HTTP 403)"}
            elif response.status_code == 429:
                return {"error": "API 요청 한도 초과 (HTTP 429)"}
            elif response.status_code >= 500:
                return {"error": f"서버 오류 (HTTP {response.status_code})"}
            elif response.status_code != 200:
                return {"error": f"API 오류: HTTP {response.status_code}"}

            # 응답 파싱
            if response_type == "raw":
                return response.text
            elif response_type == "xml":
                return _parse_xml(response.text)
            else:
                # JSON
                try:
                    data = response.json()
                except ValueError:
                    # JSONP 형식 처리
                    text = response.text
                    if text.startswith("(") and text.endswith(")"):
                        text = text[1:-1]
                    try:
                        import json
                        data = json.loads(text)
                    except:
                        return response.text
                return data

        except requests.exceptions.Timeout:
            last_error = f"API 요청 시간 초과 ({timeout}초)"
            if attempt < max_attempts - 1:
                wait = delay * (2 ** attempt) if backoff == "exponential" else delay
                _time.sleep(wait)
                continue
            return {"error": last_error}
        except requests.exceptions.ConnectionError:
            last_error = "네트워크 연결 실패"
            if attempt < max_attempts - 1:
                wait = delay * (2 ** attempt) if backoff == "exponential" else delay
                _time.sleep(wait)
                continue
            return {"error": last_error}
        except Exception as e:
            return {"error": f"API 호출 실패: {str(e)}"}

    return {"error": last_error or "최대 재시도 횟수 초과"}


def _parse_xml(text: str) -> dict:
    """XML 응답을 dict로 변환"""
    try:
        root = ElementTree.fromstring(text)
        return _xml_to_dict(root)
    except ElementTree.ParseError:
        return {"raw_text": text}


def _xml_to_dict(element) -> dict:
    """ElementTree 요소를 dict로 재귀 변환"""
    result = {}

    # 속성
    if element.attrib:
        result["@attributes"] = dict(element.attrib)

    # 자식 요소
    children = list(element)
    if children:
        child_dict = {}
        for child in children:
            child_data = _xml_to_dict(child)
            tag = child.tag
            # 네임스페이스 제거
            if "}" in tag:
                tag = tag.split("}")[-1]

            if tag in child_dict:
                # 같은 태그가 여러 개면 리스트로
                if not isinstance(child_dict[tag], list):
                    child_dict[tag] = [child_dict[tag]]
                child_dict[tag].append(child_data)
            else:
                child_dict[tag] = child_data
        result.update(child_dict)
    elif element.text and element.text.strip():
        # 텍스트만 있는 요소는 문자열로
        return element.text.strip()

    return result


# === 응답 변환 (transforms) ===
# 레거시 Python transform 함수들은 api_transforms_legacy.py로 분리됨.
# 모든 도구가 YAML response: 블록(api_transforms.py)으로 전환 완료.
# 하위 호환을 위해 transform: 키워드도 여전히 동작함.

_transforms: Dict[str, callable] = {}


def register_transform(name: str, func: callable):
    """응답 변환 함수 등록 (외부 확장용)"""
    _transforms[name] = func


def _apply_transform(name: str, data: Any, tool_input: dict) -> Any:
    """레거시 응답 변환 적용"""
    if name in _transforms:
        try:
            return _transforms[name](data, tool_input)
        except Exception as e:
            return {"error": f"응답 변환 실패 ({name}): {str(e)}", "raw_data": data}
    return data


# 레거시 변환 함수 등록 (하위 호환 — 현재 사용되지 않음)
try:
    from api_transforms_legacy import register_legacy_transforms
    register_legacy_transforms(_transforms)
except ImportError:
    pass
