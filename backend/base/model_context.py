"""모델 문맥 예산: 조기 압축 대신 실제 한도 근처까지 작업 기록을 보존한다."""
from fnmatch import fnmatchcase
from functools import lru_cache
import json
import logging

import yaml

from runtime_utils import get_base_path


@lru_cache(maxsize=1)
def _catalog():
    return yaml.safe_load(
        (get_base_path() / "data/model_context_windows.yaml").read_text(encoding="utf-8"))


def context_window(provider):
    """실측/명시 한도 우선. 모델 이름과 한도는 데이터가 소유한다."""
    explicit = getattr(provider, "context_window_tokens", None)
    if explicit and int(explicit) > 0:
        return int(explicit)
    kind = provider.CONTEXT_PROVIDER
    model = (provider.model or "").lower()
    catalog = _catalog()
    # OpenRouter도 실제 모델의 창을 따른다. 공급자 메타데이터가 없을 때만 공개 규칙 사용.
    if kind == "openrouter" and "/" in model:
        vendor, model = model.split("/", 1)
        kind = catalog["router_vendors"].get(vendor, kind)
        model = model.split(":", 1)[0]
    if kind == "anthropic":
        model = model.replace(".", "-")  # OpenRouter의 4.6 표기와 직접 API의 4-6
    for rule in catalog["rules"]:
        if kind in rule["providers"] and any(fnmatchcase(model, p) for p in rule["models"]):
            return int(rule["tokens"])
    if not getattr(provider, "_context_fallback_warned", False):
        logging.getLogger(__name__).warning(
            "문맥 한도 미확인: %s/%s — 카탈로그 fallback 사용; context_window_tokens로 지정 가능",
            kind, model)
        provider._context_fallback_warned = True
    return int(catalog["fallback_tokens"].get(kind, 128000))


def input_budget(provider, output_tokens=None):
    window = context_window(provider)
    reserve = int(output_tokens if output_tokens is not None else
                  getattr(provider, "DEFAULT_MAX_TOKENS", 4096))
    # 50/80% 비용 최적화 문턱 폐기. 출력 공간과 추정 오차 여유만 확보한다.
    return max(1, min(window * 95 // 100, window - reserve - 1024))


def request_chars(provider, messages):
    """API 별 분리된 system/tools도 포함한다. 캐시는 문맥 용량을 줄이지 않는다."""
    size = provider._estimate_content_size(messages)
    if not any(isinstance(m, dict) and m.get("role") in ("system", "developer") for m in messages):
        size += len(provider.system_prompt or "")
    size += len(json.dumps(provider.tools or [], ensure_ascii=False, default=str))
    return size


def discover_context_window(provider):
    """모델 생성 없이 메타데이터만 조회. 실패하면 모델별 카탈로그를 사용한다."""
    if getattr(provider, "context_window_tokens", None):
        return
    try:
        import requests
        if provider.CONTEXT_PROVIDER == "openrouter":
            data = _router_models()
            for model in data:
                if model.get("id") == provider.model:
                    limit = model.get("context_length")
                    if limit and int(limit) > 0:
                        provider.context_window_tokens = int(limit)
                    return
        elif provider.CONTEXT_PROVIDER == "ollama":
            # 모델의 이론상 최대값이 아닌, 서버가 실제 할당한 창. 메모리 할당은 바꾸지 않는다.
            base = str(provider._client.base_url).rstrip("/").removesuffix("/v1")
            response = requests.get(base + "/api/ps", timeout=2)
            response.raise_for_status()
            for model in response.json().get("models", []):
                name = model.get("name") or model.get("model") or ""
                if name.removesuffix(":latest") == provider.model.removesuffix(":latest"):
                    limit = model.get("context_length")
                    if limit and int(limit) > 0:
                        provider.context_window_tokens = int(limit)
                    return
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logging.getLogger(__name__).warning("문맥 메타데이터 조회 실패: %s", type(exc).__name__)


@lru_cache(maxsize=1)
def _router_models():
    import requests
    response = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
    response.raise_for_status()
    return response.json().get("data", [])
