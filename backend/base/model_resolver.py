"""
model_resolver.py - 모델 기어 단일 진실원
IndieBiz OS Core

흩어져 있던 모델 선택(oneshot_ai_call / _get_midtier_provider / load_system_ai_config)을
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
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from runtime_utils import get_base_path


def _nfc(s):
    """핀 키 정규화 — 한글 프로젝트명이 출처마다 NFD(파일시스템 d.name)/NFC(projects.json·URL)로
    갈려 키가 안 맞는 이음매를 없앤다. 모든 override 키 비교/저장을 NFC로 통일."""
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s

logger = logging.getLogger(__name__)

# claude_code(Claude 구독 OAuth)·codex(ChatGPT 구독 로그인)·ollama(로컬)는
# 자체 인증 경로를 갖고 있어 api_key 가 불요다.
_NO_KEY_PROVIDERS = {
    "claude_code", "claude-code", "claudecode",
    "codex", "codex_cli", "codex-cli",
    "ollama",
}


def provider_needs_api_key(provider) -> bool:
    """이 프로바이더가 api_key 를 필요로 하는가.

    ★"키가 있나"로 "쓸 수 있나"를 판정하는 자리는 **전부 이 함수를 지날 것**.
    claude_code(중앙 OAuth)·ollama(로컬)는 키가 원래 없고, 그 자리에서 키를 요구하면
    멀쩡한 경로가 "API 키가 설정되지 않았습니다"라며 죽는다 — 2026-08-17 실사고:
    시스템 AI 채팅 3 진입점이 provider 를 안 보고 apiKey 만 봐서, 기어가 claude_code 인데도
    인사 한 마디에 2ms 만에 거절했다(엉뚱한 비-Anthropic 키가 그 칸에 들어 있던 동안만
    우연히 가려져 있었다).
    """
    return str(provider or "").strip().lower() not in _NO_KEY_PROVIDERS

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
        # 가이드 의미 순찰(주 6건)은 '전제가 뒤집혔는가' 판단이라 경량으로는 못 한다 —
        # 실측: 최소 형태 질문에도 경량 모델이 []를 뱉었다(2026-08-17). 빈도가 낮아 실행 축이 감당된다.
        "guide_audit": "실행",
    },
    "overrides": {},
    "consciousness_enabled": True,
    # 차선별 추론 예산 — 모델·티어가 아니라 무의식 관문의 판정에 걸린 규칙(2026-09-02).
    # EXECUTE 는 확장 추론 없이(실측: 품질 동일, 지연 1/3), THINK/REPAIR 는 프로바이더 기본.
    "lane_reasoning": {"EXECUTE": "off", "THINK": "default", "REPAIR": "default"},
}

# 미등록 역할/축의 보수적 기본값.
_DEFAULT_AXIS = "실행"      # role_axis 에 없는 역할 → 실행 축
_DEFAULT_TIER = "고급"      # preset 에 축이 없을 때 → 고급(품질 우선 보수)


def _data_path():
    return get_base_path() / "data"


# AI 티어 설정 파일 경로 정본 — api_config 에서 이동 (2026-08-05 감사 ⑦).
# 인지층(consciousness_agent)이 라우터를 import 하지 않도록 여기(기저층)가 정본.
SYSTEM_AI_CONFIG_PATH = _data_path() / "system_ai_config.json"
LIGHTWEIGHT_AI_CONFIG_PATH = _data_path() / "lightweight_ai_config.json"
MIDTIER_AI_CONFIG_PATH = _data_path() / "midtier_ai_config.json"
# 하위호환: 기존 unconscious_ai_config.json 경로
UNCONSCIOUS_AI_CONFIG_PATH = _data_path() / "unconscious_ai_config.json"


# ── 모델 프로바이더 자격증명 = `.env` 단일 보관소 (2026-08-17) ──────────────
# ★원칙: **API 키는 `.env` 말고 어디에도 있으면 안 된다.** 이 시스템의 도구·데이터 키
# (KAKAO/NAVER/DART/GEMINI…)는 이미 전부 `.env` 한 곳에 사는데, *모델* 키만 티어 설정
# json 에 따로 살아 보관소가 둘로 갈려 있었다. 그 결과 ①같은 키가 여러 파일에 복사되고
# ②티어의 provider 를 바꿔도 옛 프로바이더의 키가 남아 엉뚱한 벤더로 실려 가고
# ③키가 늘어난 파일 수만큼 유출면이 넓어졌다(실측: claude_code 티어가 Gemini 키를 나름).
# `.env` 는 gitignore 되어 있고 부팅 시 load_dotenv 로 올라온다.
_PROVIDER_ENV = {
    "google": "GEMINI_API_KEY", "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def env_var_for_provider(provider: str) -> str:
    """프로바이더 → `.env` 변수 이름. 키가 필요 없는 프로바이더는 빈 문자열."""
    p = (provider or "").strip().lower()
    if p in _NO_KEY_PROVIDERS:
        return ""
    return _PROVIDER_ENV.get(p, "")


def env_key_for_provider(provider: str) -> str:
    """프로바이더의 키를 `.env`(환경)에서 읽는다. 없으면 빈 문자열."""
    name = env_var_for_provider(provider)
    return (os.environ.get(name, "") or "").strip() if name else ""


def _env_file() -> Path:
    return get_base_path() / ".env"


def set_env_key(provider: str, api_key: str) -> bool:
    """프로바이더 키를 `.env` 에 upsert (설정 UI 저장 경로용).

    키가 티어 json 이 아니라 여기로 가야 보관소가 하나로 유지된다. 기존 줄은 값만
    교체하고(주석·순서 보존), 없으면 끝에 덧붙인다. 현재 프로세스 환경에도 즉시 반영."""
    name = env_var_for_provider(provider)
    if not name:
        return False
    key = (api_key or "").strip()
    if not key:
        return False
    p = _env_file()
    try:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True) if p.exists() else []
        hit = False
        for i, ln in enumerate(lines):
            if re.match(rf"^\s*{re.escape(name)}\s*=", ln):
                lines[i] = f"{name}={key}\n"
                hit = True
                break
        if not hit:
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(f"{name}={key}\n")
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text("".join(lines), encoding="utf-8")
        os.replace(tmp, p)
        os.environ[name] = key          # 재부팅 없이 즉시 유효
        logger.info(f"[model_resolver] {name} 을(를) .env 에 저장했습니다.")
        return True
    except Exception as e:
        logger.warning(f"[model_resolver] .env 저장 실패 ({name}): {e}")
        return False


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

    키는 `.env` 의 프로바이더별 변수에서 온다(티어 json 은 provider/model 만 나른다)."""
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

    # ★키는 `.env` 가 정본 — 프로바이더별 변수에서 읽는다(위 _PROVIDER_ENV 절 참조).
    # 티어 json 에 남은 apiKey 는 이관 전 레거시일 뿐이라 폴백으로만 본다.
    # ★옛 폴백("키 없으면 고급 티어 키를 빌려온다")은 제거했다 — 그게 claude_code
    #   티어의 Gemini 키가 엉뚱한 프로바이더로 실려 나가던 경로다. 프로바이더가 다르면
    #   키도 다르다. 빌려주지 않는다.
    api_key = env_key_for_provider(provider)
    if not api_key and provider.lower() not in _NO_KEY_PROVIDERS:
        legacy = (cfg.get("apiKey") or cfg.get("api_key") or "").strip()
        if legacy:
            logger.warning(
                f"[model_resolver] {fname} 에 남은 레거시 키를 사용합니다 — "
                f"{env_var_for_provider(provider) or 'ENV'} 로 옮기세요(.env 가 정본).")
            api_key = legacy
    return {"provider": provider, "model": model, "api_key": api_key, "tier": tier}


def resolve(role: str, agent_id: Optional[str] = None) -> dict:
    """역할(+선택 agent_id) → 해소된 모델 디스크립터.

    Returns: {provider, model, api_key, tier, axis, source}
      - source: 어떻게 해소됐는지 추적 문자열 (디버깅/계기판 표시용)
    """
    gear = _load_gear()
    overrides = gear.get("overrides", {}) or {}
    # 키를 NFC로 통일 — 저장된 핀이 NFD(한글 프로젝트명)여도 NFC 조회 키와 매칭된다.
    overrides = {_nfc(k): v for k, v in overrides.items()}

    # 1. 오버라이드 — agent_id(구체 에이전트) 우선, 그다음 role(역할군)
    for key in (_nfc(agent_id), _nfc(role)):
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

    # reflex(해마 고확신)는 기어와 무관하게 *언제나 경량* — "이미 찾은 답을 그대로 내보냄"이라
    # 가장 싼 티어로 충분(설계 확정 2026-06-30). 기어는 '경량'이 어느 모델인지만 정한다.
    # (위 override 루프가 reflex 핀을 먼저 처리하므로, 명시 핀이 있으면 그게 이긴다.)
    if role == "reflex":
        d = _load_tier_config("경량", gear)
        d.update(axis="(reflex)", source="reflex→경량(고정)")
        return d

    # 시스템 수리(system_repair)는 기어와 무관하게 *언제나 고급* — 자기 몸(RED) 수정은
    # 최고 모델만 한다(헌법 2026-08-05, reflex→경량 고정의 역방향). 기어가 절약이어도
    # REPAIR 태스크의 실행 모델은 여기서 고급으로 승격된다.
    if role == "system_repair":
        d = _load_tier_config("고급", gear)
        d.update(axis="(system_repair)", source="system_repair→고급(고정)")
        return d

    # 포식(forage) 에이전트는 기본 *경량* — 빈도 높은 가벼운 검색이라 최저 티어로 충분.
    # 계기판 설정의 overrides["forage"] 핀으로 변경(위 override 루프가 먼저 처리하므로 핀이 이긴다).
    if role == "forage":
        d = _load_tier_config("경량", gear)
        d.update(axis="(forage)", source="forage→경량(기본)")
        return d

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


REASONING_MODES = ("off", "default")


def reasoning_for_lane(lane: str) -> str:
    """차선(EXECUTE/THINK/REPAIR) → 추론 예산 모드("off"|"default"). 정본=model_gear.json lane_reasoning.

    모델·티어가 아니라 작업의 모양(무의식 관문의 판정)에 걸린 규칙이라 모델을 바꿔도 남는다.
    미설정·미지 값이면 "default"(프로바이더 기본) — 부재가 동작을 바꾸지 않는다."""
    try:
        table = (_load_gear().get("lane_reasoning") or {})
        mode = str(table.get(str(lane or "").upper(), "default")).strip().lower()
        return mode if mode in REASONING_MODES else "default"
    except Exception:
        return "default"


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
        if (c.get("provider") or "").lower() == provider.lower():  # vj-ok: 프로바이더 설정 식별자 대조
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
    # 쓰기 관문 원장 — 기어·핀 변경은 실행 모델을 바꾸는 사건(관측, 실패 무해)
    try:
        from write_ledger import log_write
        log_write(_gear_path(), event="write", gate="model_gear")
    except Exception:
        pass


def set_gear(name: str) -> bool:
    """현재 기어 변경 + provider 캐시 무효화(핫리로드). 알 수 없는 기어면 False."""
    gear = _load_gear()
    if name not in gear.get("presets", {}):
        return False
    gear["current_gear"] = name
    _write_gear(gear)
    return True


def consciousness_enabled() -> bool:
    """의식(THINK 경로) 토글 — model_gear.json 의 consciousness_enabled (기본 True, 핫리로드).

    False 면 인지 파이프라인이 무의식 분류(THINK 판정)를 건너뛰고 바로 EXECUTE 로 간다.
    반사(Reflex, 해마 고확신)는 토글과 무관하게 유지된다 — OFF 는 'THINK 차단'이지 'Reflex 차단'이 아니다."""
    v = _load_gear().get("consciousness_enabled", True)
    return bool(v) if isinstance(v, bool) else True


def set_consciousness(enabled: bool) -> bool:
    """의식 토글 on/off 저장 + 캐시 무효화(핫리로드). 항상 True 반환."""
    gear = _load_gear()
    gear["consciousness_enabled"] = bool(enabled)
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
    # 키를 NFC로 저장 — 출처(파일시스템 NFD / json·URL NFC)와 무관하게 일관 매칭.
    overrides = {_nfc(k): v for k, v in overrides.items()}
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


def _provider_from_desc(d: dict, system_prompt: str = "", tools=None,
                        oneshot: bool = False):
    """디스크립터({provider, model, api_key}) → 캐시된 provider 객체 (실패/모델 없음=None).

    get_provider_for 와 get_vision_provider 가 같은 구성·캐시를 쓴다 — 사본이면 드리프트."""
    if not d.get("model"):
        return None
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
            # 원샷 계약(분류·평가·증류·번역)=짧은 JSON 응답 — 하이브리드 thinking 차단.
            # 지원 프로바이더(DeepSeek 등)만 해석, 나머진 무시(base 기본 False 속성).
            if oneshot:
                prov.disable_thinking = True
                # 원샷은 도구를 쓰지 않는다(execute_tool=None) — 도구 스키마 적재 생략(비용 7배 차).
                prov.no_tools = True
            _provider_cache[cache_key] = prov
        except Exception as e:
            logger.warning(f"[model_resolver] provider 생성 실패 ({d['provider']}/{d['model']}): {e}")
            return None
    return prov


def get_provider_for(role: str, agent_id: Optional[str] = None,
                     system_prompt: str = "", tools=None,
                     oneshot: bool = False) -> Tuple[Any, dict]:
    """역할에 맞는 provider 객체와 디스크립터 반환. 모델 없으면 (None, desc).

    oneshot=True: 원샷 버킷(세션 비활성). 변이형(reflex)과 캐시 객체를 분리.
    """
    d = resolve(role, agent_id)
    prov = _provider_from_desc(d, system_prompt=system_prompt, tools=tools, oneshot=oneshot)
    return prov, d


def get_vision_provider(oneshot: bool = True) -> Tuple[Any, dict]:
    """비전(이미지 입력) 모달리티 프로바이더 — gear `modality.image` 가 단독 결정.

    텍스트 4축(분류/평가/실행/의식)의 티어 모델은 비전이 없을 수 있다(경량 deepseek 실측).
    모달리티는 기어 축과 무관한 별도 슬롯(model_gear._doc 의 예약석)이며, 값은 티어 json 과
    같은 모양({provider, model})의 설정 파일 이름이다. 키는 티어와 같은 규약(.env 정본).
    미설정(None)이면 (None, desc) — 호출자는 role-축 프로바이더로 폴백한다(고급 티어처럼
    그 축 모델이 비전을 지원할 수 있으므로). 벤더는 코드가 아니라 이 데이터에 산다
    (2026-08-27 비전 벤더 중립화 — 구 gemini_vision.py/_gemini_vision_json 직호출 폐지).
    """
    gear = _load_gear()
    fname = str(((gear.get("modality") or {}).get("image")) or "").strip()
    if not fname:
        return None, {"provider": "", "model": "", "api_key": "",
                      "tier": "(modality)", "axis": "(vision)", "source": "modality.image 미설정"}
    cfg = {}
    p = _data_path() / fname
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[model_resolver] 비전 설정 로드 실패 ({fname}): {e}")
    provider = (cfg.get("provider") or "").strip()
    model = (cfg.get("model") or "").strip()
    api_key = env_key_for_provider(provider)
    if not api_key and provider.lower() not in _NO_KEY_PROVIDERS:
        legacy = (cfg.get("apiKey") or cfg.get("api_key") or "").strip()
        if legacy:
            api_key = legacy
    d = {"provider": provider, "model": model, "api_key": api_key,
         "tier": "(modality)", "axis": "(vision)", "source": f"modality.image→{fname}"}
    return _provider_from_desc(d, oneshot=oneshot), d


def resolve_agent_ai(base_ai: Optional[dict], project_id: str, agent_id: str) -> dict:
    """에이전트 실행 ai_config = **모델 기어가 단독 결정**한다 (공용 단일 출처).

    ★per-agent 모델 설정(agents.yaml `ai.provider/model/api_key/apiKey`)은 폐지됐다 —
    런처의 모델 티어(경량/중급/고급)가 유일한 모델 설정이다. 그런데 그 폐지가 러너
    한 곳에만 적용돼, 에이전트를 *자기 자리에서 직접 세우는* 경로들(동기 위임·스위치·
    멀티채팅)은 계속 옛 yaml 을 읽고 있었다 — 같은 에이전트가 부르는 길에 따라 다른
    모델로 도는 드리프트. 이 함수가 그 해소를 한 곳으로 모은다.

    ★`api_key` 유무로 게이트하지 말 것 — 현재 기어의 고급 티어(claude_code)처럼 키가
    **원래 없는** 프로바이더가 있다(_NO_KEY_PROVIDERS). 키 없음은 오류가 아니다.

    base_ai 의 비-모델 필드(thinkingBudget 등)는 보존한다.
    Returns: ai_config(dict). 해소 실패 시 model 키가 없는 dict → 호출자가 정직하게 거절.
    """
    out = dict(base_ai or {})
    for k in ("provider", "model", "api_key", "apiKey"):
        out.pop(k, None)                     # 레거시 제거 — 기어가 전적으로 채운다
    pin = f"{project_id}:{agent_id}" if (project_id and agent_id) else (agent_id or "")
    try:
        d = resolve("execution", agent_id=pin)
    except Exception as e:
        logger.warning(f"[model_resolver] 에이전트 실행 축 해소 실패 ({pin}): {e}")
        return out
    if d.get("model"):
        out["provider"] = d.get("provider") or "anthropic"
        out["model"] = d["model"]
        out["api_key"] = d.get("api_key", "")
        out["_gear_source"] = d.get("source", "")
    return out
