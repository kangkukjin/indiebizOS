"""channel_settings_ops.py — 통신 채널(gmail·nostr)의 설정·폴러 낱말 `[others:channel]` (2026-10-05, 설치 목록 ⑩).

조종실 설정 창(api_business /channels)과 같은 함수: 저장은 business_manager.channel_settings, 수신 상태는
channel_poller. gmail 의 config.yaml 동기화도 여기(라우트와 IBL 이 같은 한 벌).
"""
import json
from typing import Any


SECRET_KEY_PARTS = ("secret", "token", "password", "key")   # 표면에 내지 않는 설정 키 조각


def _bm():
    from business_manager import BusinessManager
    return BusinessManager()


def _sanitize(ch: dict) -> dict:
    """비밀(client_secret·토큰)은 표면에 내지 않는다 — 조종실 라우트의 마스킹과 같은 뜻."""
    if not ch:
        return ch
    out = dict(ch)
    cfg = out.get("config")
    try:
        parsed = json.loads(cfg) if isinstance(cfg, str) and cfg else (cfg or {})
    except ValueError:
        parsed = {}
    if isinstance(parsed, dict):
        from common.value_semantics import normalized_text
        out["config"] = {k: ("***" if any(s in normalized_text(str(k)) for s in SECRET_KEY_PARTS) else v) for k, v in parsed.items()}
    return out


def set_channel(channel_type: str, enabled=None, config=None, polling_interval=None) -> dict:
    cfg_str = json.dumps(config, ensure_ascii=False) if isinstance(config, dict) else config
    channel = _bm().update_channel_setting(channel_type, enabled=enabled, config=cfg_str, polling_interval=polling_interval)
    if channel_type == "gmail" and cfg_str:
        try:
            import yaml
            from runtime_utils import get_base_path
            parsed = json.loads(cfg_str)
            gmail_path = get_base_path() / "data" / "packages" / "installed" / "extensions" / "gmail"
            gmail_path.mkdir(parents=True, exist_ok=True)
            (gmail_path / "config.yaml").write_text(yaml.dump({"gmail": {
                "client_id": parsed.get("client_id", ""), "client_secret": parsed.get("client_secret", ""),
                "email": parsed.get("email", "")}}, default_flow_style=False, allow_unicode=True), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"[channel] Gmail config.yaml 갱신 실패: {e}")
    try:
        from channel_poller import get_channel_poller
        get_channel_poller().refresh_channel(channel_type)
    except Exception as e:  # noqa: BLE001
        print(f"[channel] 폴러 새로고침 실패: {e}")
    return channel


def channel_op(params: dict) -> Any:
    op = (params.get("op") or "list").strip()
    if op == "list":
        rows = [_sanitize(c) for c in _bm().get_all_channel_settings()]
        return {"success": True, "items": rows, "count": len(rows)}
    if op == "status":
        from channel_poller import get_channel_poller
        p = get_channel_poller()
        return {"success": True, "running": bool(p.running), "active_channels": list(p.threads.keys())}
    ct = (params.get("channel_type") or params.get("channel") or "").strip()
    if not ct:
        return {"success": False, "error": f"{op} 에는 channel_type(gmail|nostr)이 필요합니다"}
    if op == "detail":
        ch = _bm().get_channel_setting(ct)
        return {"success": bool(ch), "channel": _sanitize(ch), **({} if ch else {"error": f"채널 없음: {ct}"})}
    if op == "set":
        enabled = params.get("enabled")
        interval = params.get("polling_interval")
        config = params.get("config")
        if enabled is None and interval is None and config is None:
            return {"success": False, "error": "set 에 바꿀 값(enabled|polling_interval|config)이 없습니다"}
        try:
            interval = int(interval) if interval is not None else None
            if interval is not None and interval < 5:
                return {"success": False, "error": "polling_interval 은 5초 이상"}
        except (TypeError, ValueError):
            return {"success": False, "error": "polling_interval 은 정수(초)"}
        ch = set_channel(ct, enabled=(bool(enabled) if enabled is not None else None), config=config, polling_interval=interval)
        return {"success": True, "channel": _sanitize(ch)}
    if op == "poll":
        from channel_poller import get_channel_poller
        return {"success": True, **(get_channel_poller().poll_now(ct) or {})}
    return {"success": False, "error": f"알 수 없는 op: {op} (list|detail|set|poll|status)"}
