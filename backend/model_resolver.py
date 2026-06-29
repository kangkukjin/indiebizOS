"""
model_resolver.py - 모델 기어 단일 진실원
IndieBiz OS Core

흩어져 있던 모델 선택(lightweight_ai_call / _get_midtier_provider / load_system_ai_config)을
한 곳으로 모은다. 텍스트 역할은 4축 → 현재 기어 → 티어 → 모델로 해소한다:

    resolve(role) →
      1. 오버라이드(에이전트/역할 핀) 있으면 → 그 티어/모델
      2. role → axis        (data/model_gear.json: role_axis)
      3. axis → tier        (현재 기어 presets: 절약/균형/최대)
      4. tier → 모델        (경량=lightweight / 중급=midtier / 고급=system_ai config)

config 파일을 매 호출 읽으므로(작은 JSON) 기어 변경이 즉시 반영된다(핫리로드).
provider 객체는 (provider,model,key) 키로 캐시 — 기어가 바뀌면 캐시 키가 달라져 자동 교체.

모달리티(이미지/임베딩/동영상)는 기어 무관 — 여기서 다루지 않는다(핸들러 패스스루).
설계: docs/MODEL_GEAR_DESIGN.md
"""
import json
import hashlib
import logging
from typing import Optional, Dict, Any, Tuple

from runtime_utils import get_base_path

logger = logging.getLogger(__name__)

# claude_code/ollama는 자체 인증(OAuth/로컬)이라 api_key 불요.
_NO_KEY_PROVIDERS = {"claude_code", "claude-code", "claudecode", "ollama"}

# 파일 부재/손상 시 폴백 (data/model_gear.json 과 동일 구조).
_DEFAULT_GEAR = {
    "current_gear": "균형",
    "tiers": {
        "경량": "lightweight_ai_config.json",
        "중급": "midtier_ai_config.json",
        "고급": "system_ai_config.json",
    },
    "presets": {
        "절약": {"분류": "경량", "평가": "경량", "실행": "경량", "의식": "경량"},
        "균형": {"분류": "경량", "평가": "경량", "실행": "중급", "의식": "중급"},
        "최대": {"분류": "경량", "평가": "경량", "실행": "고급", "의식": "고급"},
    },
    "role_axis": {
        "classify": "분류", "background": "분류", "evaluate": "평가",
        "consciousness": "의식", "execution": "실행", "system_ai": "실행",
        "reflex": "실행", "translate": "실행", "content_text": "실행",
        "android": "실행", "auto_response": "실행",
    },
    "overrides": {},
}

# 미등록 역할/축의 보수적 기본값.
_DEFAULT_AXIS = "실행"      # role_axis 에 없는 역할 → 실행 축
_DEFAULT_TIER = "고급"      # preset 에 축이 없을 때 → 고급(품질 우선 보수)


def _data_path():
    return get_base_path() / "data"


def _gear_path():
    return _data_path() / "model_gear.json"


def _load_gear() -> dict:
    """model_gear.json 로드 (매 호출 — 핫리로드). 부재/손상 시 기본값."""
    p = _gear_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[model_resolver] gear 로드 실패, 기본값 사용: {e}")
    return _DEFAULT_GEAR


def _tier_file_map(gear: dict) -> dict:
    return gear.get("tiers", _DEFAULT_GEAR["tiers"])


def _load_tier_config(tier: str, gear: dict) -> dict:
    """티어(경량/중급/고급) → {provider, model, api_key, tier}.

    api_key 가 비고 provider 가 키-필요 계열이면 고급(system_ai) 키로 폴백
    (기존 _get_midtier_provider 동작 보존)."""
    tiers = _tier_file_map(gear)
    fname = tiers.get(tier) or tiers.get("고급", "system_ai_config.json")
    cfg = {}
    p = _data_path() / fname
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[model_resolver] 티어 설정 로드 실패 ({fname}): {e}")
    provider = (cfg.get("provider") or "anthropic").strip()
    model = (cfg.get("model") or "").strip()
    api_key = (cfg.get("apiKey") or cfg.get("api_key") or "").strip()

    if not api_key and provider.lower() not in _NO_KEY_PROVIDERS:
        sp = _data_path() / tiers.get("고급", "system_ai_config.json")
        if sp.exists():
            try:
                sc = json.loads(sp.read_text(encoding="utf-8"))
                api_key = (sc.get("apiKey") or sc.get("api_key") or "").strip()
            except Exception:
                pass
    return {"provider": provider, "model": model, "api_key": api_key, "tier": tier}


def resolve(role: str, agent_id: Optional[str] = None) -> dict:
    """역할(+선택 agent_id) → 해소된 모델 디스크립터.

    Returns: {provider, model, api_key, tier, axis, source}
      - source: 어떻게 해소됐는지 추적 문자열 (디버깅/계기판 표시용)
    """
    gear = _load_gear()
    overrides = gear.get("overrides", {}) or {}

    # 1. 오버라이드 — agent_id(구체 에이전트) 우선, 그다음 role(역할군)
    for key in (agent_id, role):
        if key and key in overrides:
            ov = overrides[key]
            if isinstance(ov, str):  # 티어 이름으로 핀
                d = _load_tier_config(ov, gear)
                d.update(axis="(override)", source=f"override:{key}→{ov}")
                return d
            if isinstance(ov, dict):  # 직접 모델 핀
                return {
                    "provider": (ov.get("provider") or "anthropic").strip(),
                    "model": (ov.get("model") or "").strip(),
                    "api_key": (ov.get("apiKey") or ov.get("api_key") or "").strip(),
                    "tier": "(custom)", "axis": "(override)",
                    "source": f"override:{key}(custom)",
                }

    # 2. role → axis
    axis = gear.get("role_axis", {}).get(role)
    if axis is None:
        axis = _DEFAULT_AXIS
        logger.warning(f"[model_resolver] 미등록 role '{role}' → '{axis}' 축 기본")

    # 3. axis → tier (현재 기어)
    gear_name = gear.get("current_gear", "균형")
    preset = gear.get("presets", {}).get(gear_name, {})
    tier = preset.get(axis, _DEFAULT_TIER)

    # 4. tier → 모델
    d = _load_tier_config(tier, gear)
    d.update(axis=axis, source=f"gear:{gear_name}|{axis}→{tier}")
    return d


# ============ 기어 조회/변경 ============

# UI·검증용 상수 — 프리셋 편집기가 고를 수 있는 축/티어.
AXES = ["분류", "평가", "실행", "의식"]
TIERS = ["경량", "중급", "고급"]


def get_gear() -> str:
    return _load_gear().get("current_gear", "균형")


def list_gears() -> list:
    return list(_load_gear().get("presets", {}).keys())


def api_key_for_provider(provider: str) -> str:
    """주어진 provider 와 같은 provider 를 쓰는 티어 config(경량/중급/고급)의 api_key 반환.

    에이전트 yaml 이 provider/model 만 핀하고 키를 생략했을 때 채운다 — 에이전트가 키를
    직접 들고 다니지 않아도 기어 티어에서 상속받게(개별 설정 불요). 없으면 빈 문자열."""
    if not provider:
        return ""
    gear = _load_gear()
    for fname in _tier_file_map(gear).values():
        p = _data_path() / fname
        if not p.exists():
            continue
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (c.get("provider") or "").lower() == provider.lower():
            k = (c.get("apiKey") or c.get("api_key") or "").strip()
            if k:
                return k
    return ""


def get_presets() -> dict:
    return _load_gear().get("presets", {}) or {}


def get_overrides() -> dict:
    return _load_gear().get("overrides", {}) or {}


def _write_gear(gear: dict):
    """gear dict 를 파일에 쓰고 provider 캐시 무효화(핫리로드)."""
    _gear_path().write_text(json.dumps(gear, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_provider_cache()


def set_gear(name: str) -> bool:
    """현재 기어 변경 + provider 캐시 무효화(핫리로드). 알 수 없는 기어면 False."""
    gear = _load_gear()
    if name not in gear.get("presets", {}):
        return False
    gear["current_gear"] = name
    _write_gear(gear)
    return True


def set_presets(presets: dict) -> bool:
    """기어 프리셋 정의 갱신(각 기어가 축→티어를 어떻게 매핑하는지). 캐시 무효화.

    presets 형식: {기어명: {축: 티어}}. 축은 AXES, 티어는 TIERS 만 허용(검증).
    빈/누락 축은 기존 값 보존하지 않고 그대로 덮어씀(호출측이 전체를 보냄)."""
    if not isinstance(presets, dict) or not presets:
        return False
    for gname, axismap in presets.items():
        if not isinstance(axismap, dict):
            return False
        for axis, tier in axismap.items():
            if axis not in AXES or tier not in TIERS:
                return False
    gear = _load_gear()
    gear["presets"] = presets
    # 현재 기어가 사라졌으면 첫 기어로 보정
    if gear.get("current_gear") not in presets:
        gear["current_gear"] = next(iter(presets))
    _write_gear(gear)
    return True


def set_overrides(overrides: dict) -> bool:
    """에이전트/역할 핀 갱신. {키(agent_id 또는 role): 티어명 또는 {provider,model,apiKey}}.
    티어명 핀은 TIERS 만 허용. 빈 dict 면 전부 해제."""
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        return False
    for key, val in overrides.items():
        if isinstance(val, str):
            if val not in TIERS:
                return False
        elif not isinstance(val, dict):
            return False
    gear = _load_gear()
    gear["overrides"] = overrides
    _write_gear(gear)
    return True


# ============ provider 객체 캐시 (핫리로드 친화) ============
# 캐시 키 = 버킷|provider|model|key해시. 기어/설정이 바뀌면 키가 달라져 자동으로 새 객체.
# system_prompt/tools 는 호출 시점에 전달되는 계약이라(provider.process 인자) 캐시 안전.
#
# ★버킷 분리(oneshot vs session): 옛 구조의 두 싱글턴(lightweight=원샷 / midtier=세션)을 재현.
#   - oneshot: 분류·평가·증류 — system_prompt 임시 스왑, 세션 비활성. 같은 객체를 변이하지 않음.
#   - session(reflex 등): provider 자체를 변이(system_prompt/tools/agent_id 복사)해 ai._provider 로 스왑.
#   둘이 같은 모델로 해소돼도 *다른 객체*여야 서로의 system_prompt/tools 를 짓밟지 않는다.

_provider_cache: Dict[str, Any] = {}


def clear_provider_cache():
    _provider_cache.clear()


def get_provider_for(role: str, agent_id: Optional[str] = None,
                     system_prompt: str = "", tools=None,
                     oneshot: bool = False) -> Tuple[Any, dict]:
    """역할에 맞는 provider 객체와 디스크립터 반환. 모델 없으면 (None, desc).

    oneshot=True: 원샷 버킷(세션 비활성). 변이형(reflex)과 캐시 객체를 분리.
    """
    d = resolve(role, agent_id)
    if not d.get("model"):
        return None, d
    keyhash = hashlib.md5((d["api_key"] or "").encode()).hexdigest()[:8]
    bucket = "oneshot" if oneshot else "session"
    cache_key = f"{bucket}|{d['provider']}|{d['model']}|{keyhash}"
    prov = _provider_cache.get(cache_key)
    if prov is None:
        try:
            from providers import get_provider
            prov = get_provider(d["provider"], api_key=d["api_key"], model=d["model"],
                                system_prompt=system_prompt, tools=tools or [])
            prov.init_client()
            # 원샷은 메인 에이전트와 session_key 충돌 방지(no-op on providers without the attr)
            if oneshot and hasattr(prov, "disable_session_persistence"):
                prov.disable_session_persistence = True
            _provider_cache[cache_key] = prov
        except Exception as e:
            logger.warning(f"[model_resolver] provider 생성 실패 ({d['provider']}/{d['model']}): {e}")
            return None, d
    return prov, d
