"""Negotiated lossless leaf transport. Never retry an ambiguous execution POST."""
import json
import os

PROTOCOL = "ibl-script-call/1"


def receive(payload, project_path):
    import principal
    from ibl_registry import load_nodes_installed
    from ibl_engine import execute_ibl
    if not principal.current().is_owner:
        return {"success": False, "error_type": "permission", "error": "인증된 몸의 호출만 허용됩니다."}
    node, action, params = payload.get("node"), payload.get("action"), payload.get("params")
    if (payload.get("protocol") != PROTOCOL or not isinstance(params, dict)
            or not isinstance(node, str) or not isinstance(action, str)):
        return {"success": False, "error_type": "capability", "error": "지원하지 않는 호출 프로토콜입니다."}
    cfg = load_nodes_installed().get("nodes", {}).get(node, {}).get("actions", {}).get(action, {})
    contract = cfg.get("callable_contract", {})
    if contract.get("adapter", {}).get("protocol") != "ibl-script/2" or set(params) - set(contract.get("params", {})):
        return {"success": False, "error_type": "capability", "error": "등록된 스크립트 호출 계약과 다릅니다."}
    from ibl_v2_types import guard
    try:
        from ibl_v2_compat import plain_arguments
        plain_arguments(params)
        for key, value in params.items():
            guard(value, contract["params"][key], key)
        result = execute_ibl({"_node": node, "action": action, "params": {**params, "_ibl_edition": 2}},
                             project_path, agent_id=payload.get("agent_id"))
        return json.loads(result) if isinstance(result, str) else result
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def forward(url, node, action, params, agent_id, target):
    import requests
    from runtime_utils import mac_session_cache
    url = url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if target == "phone" and os.environ.get("INDIEBIZ_PHONE_TOKEN"):
        headers["X-Phone-Token"] = os.environ["INDIEBIZ_PHONE_TOKEN"]
    if target == "mac" and mac_session_cache.get("session"):
        headers["X-Launcher-Session"] = mac_session_cache["session"]
    try:
        caps = requests.get(url + "/ibl/capabilities", headers=headers, timeout=(4, 15))
        if target == "mac" and caps.status_code in (401, 403) and os.environ.get("INDIEBIZ_MAC_PASSWORD"):
            login = requests.post(url + "/launcher/auth/login", json={"password": os.environ["INDIEBIZ_MAC_PASSWORD"]}, timeout=15)
            if login.status_code == 200 and login.json().get("session_id"):
                mac_session_cache["session"] = login.json()["session_id"]
                headers["X-Launcher-Session"] = mac_session_cache["session"]
                caps = requests.get(url + "/ibl/capabilities", headers=headers, timeout=(4, 15))
        if caps.status_code != 200 or PROTOCOL not in caps.json().get("call_protocols", []):
            return {"success": False, "error_type": "capability", "error": ("소유자 Android의 IndieBiz Phone Agent APK를 업데이트해야 합니다." if target == "phone" else "소유자 Mac의 IndieBiz OS 백엔드를 업데이트하고 재시작해야 합니다.") + " ibl-script-call/1 지원을 확인하지 못해 실행을 보내지 않았습니다."}
    except Exception:
        return {"success": False, "error_type": "capability", "error": "받는 기기의 호출 프로토콜을 확인하지 못했습니다. 실행은 보내지 않았습니다."}
    payload = {"protocol": PROTOCOL, "node": node, "action": action,
               "params": {k: v for k, v in params.items() if not k.startswith("_")}, "agent_id": agent_id}
    try:
        response = requests.post(url + "/ibl/call", json=payload, headers=headers, timeout=(4, 320))
        if response.status_code != 200:
            raise ValueError("HTTP " + str(response.status_code))
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("invalid response")
        return {**result, "_forwarded_to": target}
    except Exception:
        return {"success": False, "error_type": "result_unknown", "error": "원격 실행의 결과를 확인하지 못했습니다. 같은 실행을 재전송하지 않습니다."}
