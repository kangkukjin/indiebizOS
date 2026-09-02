"""ai_candidates.py — 이 기계가 이미 가진 AI 후보 탐지 + 실응답 검증 (2026-09-02, 첫 성공 온보딩 ① B·C)

온보딩의 종료조건을 "키 입력"에서 "첫 응답"으로 옮기는 두 부품:
  detect_candidates()  이 기계에 이미 있는 것 — 환경변수/.env 의 키, 설치된 CLI 하네스
                       (claude/codex — 있으면 정비소도 있다는 뜻), 로컬 모델 서버(ollama).
                       새 로그인 경로를 **신설하지 않는다** — 기존 프로바이더가 이미 쓰는 인증만 본다.
  probe()              선택한 (provider, model, key) 가 **실제로 한 문장 답하는가**. 저장은 검증 뒤.
                       실패는 원인별로 다른 문장 — "설정되지 않았습니다" 하나로 뭉개지 않는다.

세계의 명사(어느 벤더의 어떤 환경변수·명령·URL)는 코드가 아니라 데이터에 산다:
data/ai_provider_catalog.yaml. 여기엔 탐지 절차만 있다(nouns_place).
"""
import glob
import json
import os
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import yaml

from runtime_utils import get_base_path


def catalog_path() -> Path:
    return get_base_path() / "data" / "ai_provider_catalog.yaml"


_catalog_cache = {"mtime": None, "data": None}


def load_catalog() -> list:
    """카탈로그 로드(mtime 캐시). 없거나 깨지면 빈 목록 + 로그 — 부재를 조용히 없음으로 만들되
    깨짐은 예외로 신고한다(corrupt ≠ absent)."""
    p = catalog_path()
    if not p.exists():
        return []
    mtime = p.stat().st_mtime
    if _catalog_cache["mtime"] == mtime and _catalog_cache["data"] is not None:
        return _catalog_cache["data"]
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    providers = data.get("providers") or []
    if not isinstance(providers, list):
        raise ValueError(f"ai_provider_catalog.yaml: providers 는 목록이어야 합니다 ({type(providers).__name__})")
    _catalog_cache.update(mtime=mtime, data=providers)
    return providers


def catalog_env_map() -> dict:
    """{provider 이름(별칭 포함): 환경변수 이름} — model_resolver 가 .env 보관소 이름을 여기서 얻는다."""
    out = {}
    for p in load_catalog():
        env = p.get("env")
        if not env:
            continue
        for name in [p.get("name")] + list(p.get("aliases") or []):
            if name:
                out[str(name).lower()] = env
    return out


def _expand(path_like: str) -> str:
    return os.path.expandvars(os.path.expanduser(str(path_like)))


def _fetch_json(url: str, timeout: float) -> Optional[dict]:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def detect_candidates(*, env: dict = None, which: Callable = None, fetch_json: Callable = None,
                      exists: Callable = None, glob_fn: Callable = None, timeout: float = 1.0,
                      max_local_models: int = 12) -> list:
    """후보 목록. 항목 = {provider, model, source, kind, needs_key, login?}

    주입 가능한 손(env/which/fetch_json/exists/glob_fn)은 시험용 — 실사용은 기본값.
    로컬 서버 다운·CLI 부재는 **후보 없음**이지 오류가 아니다(빈 목록·200).
    """
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    fetch_json = _fetch_json if fetch_json is None else fetch_json
    exists = (lambda p: Path(p).exists()) if exists is None else exists
    glob_fn = glob.glob if glob_fn is None else glob_fn

    items = []
    for p in load_catalog():
        name = str(p.get("name") or "").strip().lower()
        kind = str(p.get("kind") or "api")
        if not name:
            continue
        if kind == "api":
            var = p.get("env")
            val = (env.get(var) or "").strip() if var else ""
            if val:
                items.append({"provider": name, "model": p.get("default_model") or "",
                              "source": f"env:{var}", "kind": kind, "needs_key": False,
                              "label": p.get("label") or name})
        elif kind == "cli":
            cmd = p.get("command")
            found = which(cmd) if cmd else None
            if not found:
                for pattern in p.get("bundle_globs") or []:
                    hits = sorted(glob_fn(_expand(pattern)), reverse=True)
                    if hits:
                        found = hits[0]
                        break
            if not found:
                continue
            markers = [_expand(m) for m in (p.get("login_markers") or [])]
            login = "yes" if any(exists(m) for m in markers) else "unknown"   # 맥은 키체인이라 파일이 없을 수 있다
            items.append({"provider": name, "model": p.get("default_model") or "",
                          "source": f"cli:{found}", "kind": kind, "needs_key": False,
                          "login": login, "label": p.get("label") or name})
        elif kind == "local":
            url = p.get("tags_url")
            if not url:
                continue
            try:
                data = fetch_json(url, timeout) or {}
            except Exception:
                continue   # 서버가 없다 = 후보 없음
            models = [m.get("name") for m in (data.get("models") or []) if isinstance(m, dict) and m.get("name")]
            for m in models[:max_local_models]:
                items.append({"provider": name, "model": m, "source": f"local:{name}", "kind": kind,
                              "needs_key": False, "label": p.get("label") or name})
    return items


# ── 실응답 검증 ────────────────────────────────────────────────────────────

PROBE_PROMPT = "준비됐는지 확인 중입니다. 한 단어로만 답해 주세요: 준비됨"
PROBE_SYSTEM = "당신은 IndieBiz OS 시스템 AI 입니다. 이 호출은 연결 확인이므로 아주 짧게 답합니다."

# 실패 범주 → 사용자에게 보이는 문장. 범주 판정은 예외 문장의 휴리스틱이라 완벽하지 않다 —
# 그래서 원문(error)도 함께 돌려준다(정직).
_KIND_MESSAGES = {
    "input": "프로바이더와 모델을 지정해주세요.",
    "unknown_provider": "지원하지 않는 프로바이더입니다.",
    "no_key": "이 프로바이더는 API 키가 필요합니다. 키를 넣거나 .env 의 {env} 를 채워주세요.",
    "auth": "키가 거부됐습니다(인증 실패). 키 값·권한·잔액을 확인해주세요.",
    "model": "모델을 찾을 수 없습니다. 모델명을 확인해주세요 (은퇴한 모델일 수 있습니다).",
    "cli_missing": "CLI 실행 파일을 찾지 못했습니다. 설치돼 있는지, PATH 에 있는지 확인해주세요.",
    "cli_login": "CLI 가 로그인돼 있지 않습니다. 터미널에서 해당 CLI 의 login 을 먼저 해주세요.",
    "local_down": "로컬 모델 서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해주세요.",
    "timeout": "응답 대기 시간을 넘겼습니다. 네트워크 또는 모델 상태를 확인해주세요.",
    "network": "네트워크 오류로 서비스에 닿지 못했습니다.",
    "empty": "호출은 됐지만 빈 응답이 돌아왔습니다. 모델·설정을 확인해주세요.",
    "unknown": "알 수 없는 오류로 실패했습니다.",
}


def _classify(provider_kind: str, text: str) -> str:
    t = (text or "").lower()
    if "not logged in" in t or "/login" in t or "please run login" in t:
        return "cli_login"
    if any(k in t for k in ("401", "403", "unauthorized", "invalid api key", "invalid x-api-key",
                            "authentication", "permission denied", "api key not valid", "insufficient")):
        return "auth"
    if any(k in t for k in ("404", "not found", "does not exist", "no such model", "unknown model",
                            "model_not_found", "notfound", "unsupported model")):
        return "model"
    if any(k in t for k in ("timed out", "timeout")):
        return "timeout"
    if any(k in t for k in ("connection refused", "econnrefused", "11434", "failed to connect", "connect error")):
        return "local_down" if provider_kind == "local" else "network"
    if any(k in t for k in ("no such file", "not found on path", "executable", "which")) and provider_kind == "cli":
        return "cli_missing"
    if any(k in t for k in ("name or service not known", "temporary failure", "network", "ssl", "connection")):
        return "network"
    return "unknown"


def _fail(kind: str, error: str = "", **fmt) -> dict:
    msg = _KIND_MESSAGES.get(kind, _KIND_MESSAGES["unknown"]).format(**fmt) if fmt else \
        _KIND_MESSAGES.get(kind, _KIND_MESSAGES["unknown"])
    return {"ok": False, "kind": kind, "message": msg, "error": (error or "")[:500]}


def _provider_kind(provider: str) -> str:
    for p in load_catalog():
        names = [str(p.get("name") or "").lower()] + [str(a).lower() for a in (p.get("aliases") or [])]
        if provider in names:
            return str(p.get("kind") or "api")
    return "api"


def probe(provider: str, model: str, api_key: str = "", timeout_s: float = 60.0,
          make_provider: Callable = None) -> dict:
    """(provider, model, key) 로 1턴 실호출. 반환 {ok, kind, message, reply?, latency_ms?, error?}.

    make_provider 주입은 시험용(가짜 프로바이더). 저장하지 않는다 — 검증 → 저장은 호출자의 순서.
    """
    provider = (provider or "").strip().lower()
    model = (model or "").strip()
    if not provider or not model:
        return _fail("input")

    from model_resolver import provider_needs_api_key, env_key_for_provider, env_var_for_provider
    key = (api_key or "").strip() or env_key_for_provider(provider)
    if provider_needs_api_key(provider) and not key:
        return _fail("no_key", env=env_var_for_provider(provider) or "(해당 변수)")

    kind = _provider_kind(provider)
    try:
        if make_provider is None:
            from providers import get_provider
            prov = get_provider(provider, api_key=key, model=model, system_prompt=PROBE_SYSTEM,
                                tools=[], agent_name="onboarding-probe")
        else:
            prov = make_provider(provider, key, model)
    except ValueError as e:
        return _fail("unknown_provider", str(e))
    except Exception as e:
        return _fail(_classify(kind, str(e)), str(e))

    # 원샷 계약과 같은 스위치(있는 프로바이더만) — 도구 스키마 적재·thinking 차단
    for attr, val in (("no_tools", True), ("disable_thinking", True), ("disable_session_persistence", True)):
        try:
            setattr(prov, attr, val)
        except Exception:
            pass

    t0 = time.monotonic()
    try:
        ok = prov.init_client()
    except Exception as e:
        return _fail(_classify(kind, str(e)), str(e))
    if ok is False:
        default = {"cli": "cli_missing", "local": "local_down"}.get(kind, "auth")
        return _fail(default, "init_client() 가 False 를 돌려줌")

    result = {}

    def _run():
        try:
            result["reply"] = prov.process_message(message=PROBE_PROMPT, history=[], execute_tool=None)
        except Exception as e:   # noqa: BLE001 — 범주화해 정직하게 돌려준다
            result["exc"] = e

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout_s)
    latency_ms = int((time.monotonic() - t0) * 1000)
    if th.is_alive():
        return {**_fail("timeout"), "latency_ms": latency_ms}
    if "exc" in result:
        e = result["exc"]
        return {**_fail(_classify(kind, str(e)), str(e)), "latency_ms": latency_ms}
    reply = result.get("reply")
    if not reply or not str(reply).strip():
        fk = getattr(prov, "last_failure_kind", None)
        return {**_fail(_classify(kind, str(fk)) if fk else "empty", str(fk or "")), "latency_ms": latency_ms}
    return {"ok": True, "kind": "ok", "message": "응답을 받았습니다.", "reply": str(reply).strip()[:300],
            "latency_ms": latency_ms}
