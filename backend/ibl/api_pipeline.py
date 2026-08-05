"""
api_pipeline.py - 멀티 API 파이프라인 실행 엔진

단일 도구 호출에서 여러 API를 순차/병렬로 호출하고 결과를 병합합니다.
api_registry.yaml의 `pipeline:` 블록을 해석하여 실행합니다.

지원 패턴:
  1. 병렬 실행 + 결과 병합 (concat)
  2. 순차 실행 + 이전 결과 참조 ({step_id._result})
  3. 첫 성공 반환 (first_success)
  4. 에러 시 계속 (on_error: continue)

사용법:
    from api_pipeline import execute_pipeline

    pipeline_config = [
        {"id": "kakao", "service": "kakao", "endpoint": "/v2/local/search/keyword.json", ...},
        {"id": "naver", "service": "naver", "endpoint": "/v1/search/local.json", ...},
    ]
    merge_config = {"mode": "concat", "wrap": {"success": True, "data": "_results"}}
    result = execute_pipeline(pipeline_config, merge_config, tool_input, services)

YAML 예시:
    tools:
      search_restaurants_combined:
        pipeline:
          - id: kakao
            service: kakao
            endpoint: /v2/local/search/keyword.json
            param_map: {query: query, x: x, y: y}
            default_params: {category_group_code: FD6}
            response:
              extract: documents
              fields:
                name: {from: place_name}
                source: {value: "kakao"}
            on_error: continue

          - id: naver
            service: naver
            endpoint: /v1/search/local.json
            param_map: {query: query, display: naver_size}
            response:
              extract: items
              fields:
                name: {from: title, clean_html: true}
                source: {value: "naver"}
            on_error: continue

        merge:
          mode: concat
          source_tag: true
          wrap:
            success: true
            count: _count
            data: _results
            message: {template: "'{query}' 검색 결과 {_count}개"}
"""

import os
import re
import requests
from typing import Any, Dict, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed


def execute_pipeline(
    pipeline_config: list,
    merge_config: dict,
    tool_input: dict,
    services: dict,
) -> Any:
    """파이프라인 실행 메인 함수

    Args:
        pipeline_config: 파이프라인 단계 리스트
        merge_config: 결과 병합 설정
        tool_input: 도구 입력 파라미터
        services: api_registry의 services 섹션

    Returns:
        병합된 결과
    """
    if not pipeline_config or not isinstance(pipeline_config, list):
        return {"error": "파이프라인 설정이 비어있습니다."}

    mode = merge_config.get("mode", "concat")

    # 순차 의존성 확인: 이전 단계 참조가 있으면 순차 실행
    has_dependency = _has_step_references(pipeline_config)

    if has_dependency or mode == "sequential":
        results = _execute_sequential(pipeline_config, tool_input, services)
    else:
        results = _execute_parallel(pipeline_config, tool_input, services)

    # 결과 병합
    return _merge_results(results, merge_config, tool_input)


# === 병렬 실행 ===

def _execute_parallel(
    steps: list, tool_input: dict, services: dict
) -> Dict[str, Any]:
    """병렬로 모든 단계 실행"""
    results = {}

    with ThreadPoolExecutor(max_workers=min(len(steps), 5)) as executor:
        futures = {}
        for step in steps:
            step_id = step.get("id", f"step_{len(futures)}")
            future = executor.submit(
                _execute_step, step, tool_input, services, {}
            )
            futures[future] = step_id

        for future in as_completed(futures):
            step_id = futures[future]
            step_config = next(
                (s for s in steps if s.get("id") == step_id), {}
            )
            try:
                result = future.result()
                results[step_id] = {
                    "data": result,
                    "success": not _is_error(result),
                    "on_error": step_config.get("on_error", "stop"),
                }
            except Exception as e:
                results[step_id] = {
                    "data": {"error": str(e)},
                    "success": False,
                    "on_error": step_config.get("on_error", "stop"),
                }

    return results


# === 순차 실행 ===

def _execute_sequential(
    steps: list, tool_input: dict, services: dict
) -> Dict[str, Any]:
    """순차적으로 단계 실행 (이전 결과 참조 가능)"""
    results = {}
    step_outputs = {}  # {step_id: result} - 이전 단계 결과 저장

    for step in steps:
        step_id = step.get("id", f"step_{len(results)}")
        on_error = step.get("on_error", "stop")

        try:
            result = _execute_step(step, tool_input, services, step_outputs)
            is_err = _is_error(result)

            results[step_id] = {
                "data": result,
                "success": not is_err,
                "on_error": on_error,
            }

            # 성공 시 step_outputs에 저장
            if not is_err:
                step_outputs[step_id] = result
            elif on_error == "stop":
                break

        except Exception as e:
            results[step_id] = {
                "data": {"error": str(e)},
                "success": False,
                "on_error": on_error,
            }
            if on_error == "stop":
                break

    return results


# === 단일 단계 실행 ===

def _execute_step(
    step: dict,
    tool_input: dict,
    services: dict,
    step_outputs: dict,
) -> Any:
    """파이프라인 단일 단계 실행

    각 단계는 api_engine의 execute_tool과 유사하게 동작하지만,
    이전 단계 결과를 참조할 수 있습니다.
    """
    from api_engine import (
        _build_params, _build_headers, _build_json_body,
        _build_form_data, _do_request, _resolve_dynamic_endpoint,
        _check_auth,
    )

    service_name = step.get("service")
    service_config = services.get(service_name, {})

    if not service_config:
        return {"error": f"알 수 없는 서비스: {service_name}"}

    # 인증 확인
    auth_config = service_config.get("auth", {})
    auth_type = auth_config.get("type", "none")
    if auth_type != "none":
        auth_ok, auth_err = _check_auth(service_name, auth_config, step)
        if not auth_ok:
            return {"error": auth_err}

    # URL 구성
    base_url = step.get("base_url") or service_config.get("base_url", "")
    endpoint = step.get("endpoint", "")
    endpoint = _resolve_dynamic_endpoint(endpoint, tool_input)
    url = f"{base_url}{endpoint}"

    # 파라미터 구성
    params = _build_params(step, tool_input, auth_config)

    # 파라미터 내 이전 단계 참조 해결 ({step_id._result} 등)
    if step_outputs:
        resolved_params = {}
        for k, v in params.items():
            resolved_params[k] = _resolve_step_refs(v, step_outputs)
        params = resolved_params

    # 헤더 구성
    headers = _build_headers(auth_config)
    extra_headers = step.get("headers")
    if extra_headers and isinstance(extra_headers, dict):
        # 이전 단계 참조 해결 ({step_id._result})
        resolved_headers = {}
        for k, v in extra_headers.items():
            resolved_headers[k] = _resolve_step_refs(v, step_outputs)
        headers.update(resolved_headers)

    # Body 구성 (Body 내 참조도 해결)
    json_body = _build_json_body(step, tool_input)
    form_data = _build_form_data(step, tool_input)
    if step_outputs and json_body and isinstance(json_body, dict):
        json_body = {k: _resolve_step_refs(v, step_outputs) for k, v in json_body.items()}
    if step_outputs and form_data and isinstance(form_data, dict):
        form_data = {k: _resolve_step_refs(v, step_outputs) for k, v in form_data.items()}

    # HTTP 호출
    method = step.get("method", "GET")
    timeout = step.get("timeout") or service_config.get("timeout", 10)
    response_type = step.get("response_type",
                              service_config.get("response_format", "json"))

    # retry 설정 (단계 또는 서비스 레벨)
    retry_config = step.get("retry") or service_config.get("retry")

    raw_result = _do_request(
        method, url, headers, params, timeout, response_type,
        json_body=json_body, form_data=form_data,
        retry_config=retry_config
    )

    # 에러 확인
    if _is_error(raw_result):
        return raw_result

    # 선언적 응답 변환
    response_config = step.get("response")
    if response_config:
        from api_transforms import apply_declarative_transform
        return apply_declarative_transform(raw_result, response_config, tool_input)

    return raw_result


# === 결과 병합 ===

def _merge_results(
    results: Dict[str, Any],
    merge_config: dict,
    tool_input: dict,
) -> Any:
    """파이프라인 결과 병합"""
    mode = merge_config.get("mode", "concat")

    if mode == "first_success":
        return _merge_first_success(results, merge_config, tool_input)
    elif mode == "concat":
        return _merge_concat(results, merge_config, tool_input)
    elif mode == "last":
        return _merge_last(results)
    else:
        return _merge_concat(results, merge_config, tool_input)


def _merge_concat(
    results: Dict[str, Any],
    merge_config: dict,
    tool_input: dict,
) -> Any:
    """결과를 하나의 리스트로 병합"""
    combined = []
    source_tag = merge_config.get("source_tag", False)

    for step_id, step_result in results.items():
        if not step_result.get("success"):
            if step_result.get("on_error") == "stop":
                return step_result["data"]
            continue

        data = step_result["data"]

        # 리스트 데이터 추출
        items = _extract_list_data(data)

        # source 태그 추가
        if source_tag:
            for item in items:
                if isinstance(item, dict) and "source" not in item:
                    item["source"] = step_id

        combined.extend(items)

    # wrap 적용
    wrap_config = merge_config.get("wrap")
    if wrap_config:
        from api_transforms import _apply_wrap, _apply_template, _SafeDict
        count = len(combined)
        result = {}
        for key, config in wrap_config.items():
            if config == "_results":
                result[key] = combined
            elif config == "_count":
                result[key] = count
            elif isinstance(config, dict) and "template" in config:
                tmpl_data = dict(tool_input)
                tmpl_data["_count"] = count
                try:
                    result[key] = config["template"].format_map(_SafeDict(tmpl_data))
                except (KeyError, ValueError):
                    result[key] = config["template"]
            elif isinstance(config, dict) and "from_input" in config:
                result[key] = tool_input.get(config["from_input"], "")
            else:
                result[key] = config
        return result

    return combined


def _merge_first_success(
    results: Dict[str, Any],
    merge_config: dict,
    tool_input: dict,
) -> Any:
    """첫 번째 성공 결과 반환 (fallback 패턴)"""
    for step_id, step_result in results.items():
        if step_result.get("success"):
            data = step_result["data"]
            # wrap 적용
            wrap_config = merge_config.get("wrap")
            if wrap_config:
                items = _extract_list_data(data)
                from api_transforms import _SafeDict
                count = len(items) if isinstance(items, list) else 1
                result = {}
                for key, config in wrap_config.items():
                    if config == "_results":
                        result[key] = items if items else data
                    elif config == "_count":
                        result[key] = count
                    elif isinstance(config, dict) and "template" in config:
                        tmpl_data = dict(tool_input)
                        tmpl_data["_count"] = count
                        try:
                            result[key] = config["template"].format_map(
                                _SafeDict(tmpl_data)
                            )
                        except (KeyError, ValueError):
                            result[key] = config["template"]
                    else:
                        result[key] = config
                return result
            return data

    # 모든 단계 실패
    return {"error": "모든 파이프라인 단계가 실패했습니다.", "details": {
        sid: sr["data"] for sid, sr in results.items()
    }}


def _merge_last(results: Dict[str, Any]) -> Any:
    """마지막 성공 결과 반환 (순차 파이프라인 최종 결과)"""
    last_data = None
    for step_id, step_result in results.items():
        if step_result.get("success"):
            last_data = step_result["data"]

    if last_data is not None:
        return last_data
    return {"error": "파이프라인 결과가 없습니다."}


# === 헬퍼 함수 ===

def _extract_list_data(data: Any) -> list:
    """데이터에서 리스트 부분 추출"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # wrap된 결과에서 리스트 찾기
        for key in ("data", "items", "results", "restaurants", "combined"):
            val = data.get(key)
            if isinstance(val, list):
                return val
        # 단일 객체 → 리스트로
        return [data]
    return []


def _is_error(result: Any) -> bool:
    """에러 응답인지 확인"""
    return isinstance(result, dict) and "error" in result


def _has_step_references(steps: list) -> bool:
    """파이프라인 단계들이 이전 결과를 참조하는지 확인"""
    import json
    text = json.dumps(steps, default=str)
    # {step_id._result} 또는 {step_id.field} 패턴 찾기
    return bool(re.search(r'\{[a-zA-Z_]\w*\._\w+\}', text))


def _resolve_step_refs(value: Any, step_outputs: dict) -> Any:
    """문자열에서 이전 단계 참조를 해결

    "{auth._result}" → step_outputs["auth"]의 값
    "{auth.access_token}" → step_outputs["auth"]["access_token"]

    리스트 값은 콤마 구분 문자열로 변환:
      ["id1", "id2"] → "id1,id2"
    """
    if not isinstance(value, str):
        return value

    def _to_str(val):
        """값을 API 파라미터용 문자열로 변환"""
        if isinstance(val, str):
            return val
        if isinstance(val, list):
            # 리스트 → 콤마 구분 (PubMed ID 리스트 등)
            return ",".join(str(item) for item in val)
        return str(val)

    def replacer(match):
        ref = match.group(1)
        parts = ref.split(".", 1)
        if len(parts) != 2:
            return match.group(0)

        step_id, field = parts
        if step_id not in step_outputs:
            return match.group(0)

        output = step_outputs[step_id]
        if field == "_result":
            return _to_str(output)
        elif isinstance(output, dict):
            return _to_str(output.get(field, ""))
        return match.group(0)

    return re.sub(r'\{(\w+\.\w+)\}', replacer, value)
