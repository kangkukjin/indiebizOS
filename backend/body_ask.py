"""body_ask.py — 부탁 경로 (실험 2: 몸 독립 소통 연구)

명함(/nodes/card)만 아는 상대가 자연어로 부탁하면, 이 몸이 **자기 사전**으로
컴파일(조종실 번역기 재사용)하고 실행해 통화(items)로 돌려준다.

원칙:
- 상대의 코드는 받지 않는다 — 자연어 의도만. 컴파일은 전적으로 내 사전 + 내 AI 의 일.
  (사전 공유 RPC 의 반대편: 어휘는 전선을 건너지 않는다.)
- 응답에 compiled_ibl 병기 — 내가 부탁을 어떻게 이해했는지 투명하게(리터러시·감사).
- 컴파일 실패 = 정직한 거절("내 어휘에 없다"). 흉내내지 않는다.
- 모든 부탁을 data/body_ask_log.jsonl 에 적재 — 연구 계측(성공률·지연·컴파일 품질).
"""
import json
import os
import time
from typing import Any, Dict


def _log(rec: Dict[str, Any]) -> None:
    try:
        base = os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(base, "data", "body_ask_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _compile(message: str, correction: str = "") -> Dict[str, Any]:
    """자연어 부탁 → 내 사전의 IBL. 몸의 능력에 따라 컴파일러를 고른다.

    능력 축 = **해마**(용례 연상)다, 프로바이더 유무가 아니다 — 폰도 gemini_http
    프로바이더는 있지만(폰 AI config) 해마가 없어 조종실 번역이 문법 교재만으로
    폰-동사를 놓친다(실측: '지금 위치' CANNOT). 그래서:
      - 해마 용례 있음 → 조종실(용례 기반 — 그 몸의 축적이 최선의 근거)
      - 해마 용례 없음 → 사전-동봉 컴파일(_compile_gemini — 실물 사전이 근거라
        환각 불가, 사전 작은 몸일수록 싸고 빠름). Gemini 불가(키·네트워크)면 조종실 최후 폴백.

    correction: 직전 실행 실패의 에러+힌트 — 1회 자가교정 재컴파일용.
    (컴파일은 내 사전·내 책임이므로 교정도 내 쪽 일 — 부탁한 상대는 힌트를 이해할 수 없다.)
    """
    try:
        from ibl_usage_rag import IBLUsageRAG
        references = IBLUsageRAG().get_references(message)
    except Exception:
        references = ""

    if not references:
        r = _compile_gemini(message, correction)
        if r.get("ok") or r.get("compiler") == "gemini":
            return r  # 성공/정직한 CANNOT 은 신뢰. compiler 없는 실패=수단 부재 → 조종실로.

    return _compile_cockpit(message, correction, references)


def _compile_cockpit(message: str, correction: str, references: str) -> Dict[str, Any]:
    """조종실 번역기(해마 용례 + translate 기어) — 해마 있는 몸의 컴파일러."""
    from api_ibl import _IBL_TRANSLATE_TASK, _load_ibl_spec, _strip_code_fence
    from consciousness_agent import system_ai_call
    prompt = f'사용자 명령: "{message}"\n\n'
    if references:
        prompt += f"참고 용례 (이 액션 이름들만 사용하라):\n{references}\n\n"
    else:
        prompt += "(관련 과거 용례 없음 — 위 6개 노드 지식으로 직접 번역하라.)\n\n"
    if correction:
        prompt += f"직전 번역이 실행에 실패했다. 아래 에러/힌트에 맞춰 수정 번역하라:\n{correction}\n\n"
    prompt += ("위 명령을 IBL 코드로 번역하라. 내 어휘로 수행 불가능한 요청이면 "
               "코드 대신 정확히 CANNOT 이라고만 출력하라. IBL 코드만 출력.")

    spec = _load_ibl_spec()
    system_prompt = _IBL_TRANSLATE_TASK + (f"\n\n<ibl_spec>\n{spec}\n</ibl_spec>" if spec else "")
    raw = system_ai_call(prompt, system_prompt=system_prompt, role="translate")
    if not raw:
        return {"ok": False, "error": "이 몸에 컴파일 수단이 없습니다(번역 모델 무응답)."}
    if "CANNOT" in raw and "[" not in raw:
        return {"ok": False, "error": "내 어휘로 수행할 수 없는 부탁입니다.", "raw": raw.strip()[:200],
                "compiler": "cockpit"}
    code = _strip_code_fence(raw)
    if not code.startswith("["):
        return {"ok": False, "error": "컴파일 실패(내 어휘로 번역되지 않음)", "raw": raw.strip()[:200],
                "compiler": "cockpit"}
    return {"ok": True, "code": code, "had_references": bool(references), "compiler": "cockpit"}


def _own_vocab_lines() -> str:
    """이 몸의 전체 사전(표준 코어 포함)을 desc 한 줄씩 — 작은 몸의 컴파일 프롬프트용.

    명함(build_card)은 코어를 빼지만(공통어휘 전제) 컴파일러는 코어까지 알아야
    파이프(table)·자기관리(self)를 조립한다. 사전이 작은 몸일수록 이 프롬프트도 작다.
    """
    from capability_card import _registry, _self_can_run, _action_entry
    lines = []
    for node, ncfg in (_registry().get("nodes") or {}).items():
        for a, c in (ncfg.get("actions") or {}).items():
            if not _self_can_run(node, a, c):
                continue
            e = _action_entry(node, a, c)
            ops = f" (op: {', '.join(e['ops'])})" if e.get("ops") else ""
            lines.append(f"[{e['act']}] {e['desc']}{ops}")
    return "\n".join(lines)


def _compile_gemini(message: str, correction: str = "") -> Dict[str, Any]:
    """인지 프로바이더 없는 몸의 컴파일러 — Gemini flash + 자기 사전(desc 프로젝션).

    ★thinkingBudget=0 필수(engines:icon 선례) — flash-latest 는 thinking 이 출력
    토큰을 먹어 코드가 잘린다. GEMINI_API_KEY 는 맥·폰 공통 프로비저닝.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "이 몸에 컴파일 수단이 없습니다(인지 프로바이더·GEMINI_API_KEY 모두 부재)."}

    system_text = (
        "너는 IBL(IndieBiz Logic) 컴파일러다. 사용자의 자연어 명령을 아래 사전의 IBL 코드로 번역만 한다.\n"
        "문법: [node:action]{params} · 순차 파이프 >> · 병렬 & · 폴백 ?? · params 값은 JSON 스타일.\n"
        "표(items) 후처리는 table 노드(filter/sort/take/select 등)를 파이프로 잇는다.\n"
        "아래 사전에 있는 액션 이름만 사용하라. 수행 불가능한 명령이면 정확히 CANNOT 만 출력.\n"
        "IBL 코드만 출력(설명·펜스 금지).\n\n"
        f"<내 사전>\n{_own_vocab_lines()}\n</내 사전>"
    )
    user_text = f'사용자 명령: "{message}"'
    if correction:
        user_text += f"\n\n직전 번역이 실행에 실패했다. 아래 에러/힌트에 맞춰 수정 번역하라:\n{correction}"

    try:
        import httpx
        # ★gemini-flash-latest 는 2026-07 중순 이후 thinkingBudget:0 을 400 거부
        # (별칭이 새 모델로 이동). 2.5-flash 명시가 tb=0 을 받는 확인된 조합.
        model = os.environ.get("BODY_ASK_COMPILE_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": [{"parts": [{"text": user_text}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400,
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, params={"key": api_key}, json=payload,
                            headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        raw = "".join(p.get("text", "") for p in parts)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Gemini 컴파일 실패: {e}"}

    if not raw:
        return {"ok": False, "error": "번역 모델 무응답(Gemini)"}
    if "CANNOT" in raw and "[" not in raw:
        return {"ok": False, "error": "내 어휘로 수행할 수 없는 부탁입니다.", "raw": raw.strip()[:200],
                "compiler": "gemini"}
    from api_ibl import _strip_code_fence
    code = _strip_code_fence(raw)
    if not code.startswith("["):
        return {"ok": False, "error": "컴파일 실패(내 어휘로 번역되지 않음)", "raw": raw.strip()[:200],
                "compiler": "gemini"}
    return {"ok": True, "code": code, "had_references": False, "compiler": "gemini"}


def _execute(code: str) -> Any:
    """컴파일된 코드를 직접조작 표면과 같은 컨텍스트(앱모드·system_ai)로 실행."""
    from project_manager import ProjectManager
    p = ProjectManager().get_project_path("앱모드")
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
    project_path = str(p.resolve())

    from thread_context import set_current_project_id, get_current_project_id
    _prev = get_current_project_id()
    set_current_project_id("앱모드")
    try:
        from system_tools import _execute_ibl_unified
        result = _execute_ibl_unified({"code": code}, project_path, agent_id="system_ai")
    finally:
        set_current_project_id(_prev)

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return {"result": result}
    from common.currency import derive_items
    return derive_items(result)


# === 발신측: [others:ask] — 이웃 몸에 자연어 부탁 ===
_peer_mac_session = {"session": None}  # 폰→맥 부탁용 런처 세션 캐시(ibl_engine 과 독립)


def _peer_auth_headers(entry: Dict[str, Any]) -> Dict[str, str]:
    """피어 몸별 인증 헤더 — phone-class=X-Phone-Token, compute=런처 세션(캐시)."""
    h = {"Content-Type": "application/json"}
    caps = entry.get("capabilities") or []
    if entry.get("auth") == "x_phone_token" or "phone-class" in caps:
        tok = os.environ.get("INDIEBIZ_PHONE_TOKEN")
        if tok:
            h["X-Phone-Token"] = tok
    elif _peer_mac_session.get("session"):
        h["X-Launcher-Session"] = _peer_mac_session["session"]
    return h


def _peer_mac_login(url: str) -> bool:
    """compute 피어(맥) 세션 로그인 — ibl_engine._forward_to_mac 과 같은 춤(부탁 채널용)."""
    password = os.environ.get("INDIEBIZ_MAC_PASSWORD")
    if not password:
        return False
    try:
        import requests
        r = requests.post(f"{url}/launcher/auth/login", json={"password": password}, timeout=15)
        sid = (r.json() or {}).get("session_id") if r.status_code == 200 else None
        if sid:
            _peer_mac_session["session"] = sid
            return True
    except Exception:
        pass
    return False


def ask_peer(params: Dict[str, Any]) -> Dict[str, Any]:
    """[others:ask] 발신 — 이웃 몸에 자연어로 부탁. 사전은 전선을 건너지 않는다.

    상대가 자기 사전으로 컴파일·실행해 통화(items)+compiled_ibl 을 돌려준다.
    피어 해소: 프레즌스 레지스트리(라이브) 별칭 → 유일 피어 자동 → env 폴백.
    """
    message = (params.get("message") or params.get("query") or "").strip()
    if not message:
        return {"error": 'message 가 필요합니다. 예: [others:ask]{to: "폰-9f2b", message: "전면 카메라로 사진 한 장"}'}
    to = str(params.get("to") or "").strip().lstrip("@")

    entry = None
    try:
        import device_registry as dr
        live = [e for e in dr.list_live() if not e.get("self")]
        if to:
            entry = next((e for e in live
                          if e.get("alias") == to or e.get("device_id") == to), None)
        elif len(live) == 1:
            entry = live[0]
        elif len(live) > 1:
            return {"needs_node_choice": True,
                    "message": "어느 몸에 부탁할까요?",
                    "options": [e.get("alias") for e in live],
                    "hint": '[others:ask]{to: "<별칭>", message: "..."} 로 지정하세요.'}
    except Exception:
        pass

    if entry and entry.get("url"):
        url = entry["url"].rstrip("/")
        headers = _peer_auth_headers(entry)
        is_compute_peer = "phone-class" not in (entry.get("capabilities") or []) \
            and entry.get("auth") != "x_phone_token"
    else:
        # env 폴백(레지스트리 미가용/미등록): 몸-인식 — 폰의 피어=맥, 컴퓨트의 피어=폰.
        try:
            from runtime_utils import detect_body
            profile = (detect_body() or {}).get("profile")
        except Exception:
            profile = ""  # 포크-가드: PROFILE env 직접 분기 금지 — detect_body 만
        if profile == "phone":
            url = (os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/")
            headers = {"Content-Type": "application/json"}
            if _peer_mac_session.get("session"):
                headers["X-Launcher-Session"] = _peer_mac_session["session"]
            is_compute_peer = True
        else:
            url = (os.environ.get("INDIEBIZ_PHONE_URL") or "").rstrip("/")
            headers = {"Content-Type": "application/json"}
            tok = os.environ.get("INDIEBIZ_PHONE_TOKEN")
            if tok:
                headers["X-Phone-Token"] = tok
            is_compute_peer = False
        if not url:
            return {"error": (f"'{to or '이웃 몸'}'에 닿을 주소가 없습니다 — 지금 연결된 몸이 없고 "
                              "env 폴백(INDIEBIZ_MAC_URL/INDIEBIZ_PHONE_URL)도 비어 있습니다."),
                    "node_unreachable": True}

    payload = {"message": message, "from_body": _self_label(),
               "dry_run": bool(params.get("dry_run"))}
    import requests
    try:
        r = requests.post(f"{url}/nodes/ask", json=payload, headers=headers, timeout=120)
        if r.status_code in (401, 403) and is_compute_peer and _peer_mac_login(url):
            headers["X-Launcher-Session"] = _peer_mac_session["session"]
            r = requests.post(f"{url}/nodes/ask", json=payload, headers=headers, timeout=120)
    except Exception as e:  # noqa: BLE001
        return {"error": f"이웃 몸({url})에 연결할 수 없습니다 ({e.__class__.__name__}). "
                         "그 몸이 켜져 있는지 확인하세요.", "node_unreachable": True}
    if r.status_code != 200:
        return {"error": f"부탁 실패 (HTTP {r.status_code})", "detail": r.text[:300]}
    try:
        out = r.json()
    except Exception:
        return {"result": r.text[:2000]}
    if isinstance(out, dict):
        out["_asked"] = (entry or {}).get("alias") or url
    return out


def _self_label() -> str:
    try:
        from runtime_utils import detect_body
        return (detect_body() or {}).get("label") or "이웃 몸"
    except Exception:
        return "이웃 몸"


def handle_ask(message: str, dry_run: bool = False, from_body: str = "") -> Dict[str, Any]:
    t0 = time.time()
    message = (message or "").strip()
    if not message:
        return {"success": False, "error": "message 가 비었습니다."}

    comp = _compile(message)
    if not comp.get("ok"):
        out = {"success": False, "error": comp.get("error"), "raw": comp.get("raw"),
               "compiler": comp.get("compiler"),
               "elapsed_ms": int((time.time() - t0) * 1000)}
        _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": from_body,
              "message": message, "compiled": None, "success": False,
              "ms": out["elapsed_ms"]})
        return out

    code = comp["code"]
    if dry_run:
        out = {"success": True, "dry_run": True, "compiled_ibl": code,
               "had_references": comp.get("had_references"),
               "compiler": comp.get("compiler", "cockpit"),
               "elapsed_ms": int((time.time() - t0) * 1000)}
        _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": from_body,
              "message": message, "compiled": code, "success": True,
              "dry_run": True, "ms": out["elapsed_ms"]})
        return out

    try:
        result = _execute(code)
    except Exception as e:  # noqa: BLE001 — 부탁 응답은 항상 dict 로
        result = {"error": f"실행 오류: {e}"}

    def _ok(r):
        return not (isinstance(r, dict) and (r.get("error") or r.get("success") is False))

    # 1회 자가교정: 실행 실패 + 힌트(_param_hint/available_actions)가 있으면
    # 에러를 번역기에 되먹여 재컴파일·재실행. (부탁한 상대는 내 힌트를 모른다 —
    # 교정은 받는 몸의 책임. 에이전트 평가 루프의 부탁-경로판, 1라운드 고정.)
    self_corrected = False
    if not _ok(result) and isinstance(result, dict):
        hint = result.get("_param_hint") or ""
        if result.get("available_actions"):
            hint += f"\n사용 가능한 액션: {result['available_actions']}"
        if hint:
            comp2 = _compile(message, correction=f"실패 코드: {code}\n에러: {result.get('error')}\n{hint}")
            if comp2.get("ok") and comp2["code"] != code:
                try:
                    result2 = _execute(comp2["code"])
                except Exception as e:  # noqa: BLE001
                    result2 = {"error": f"실행 오류: {e}"}
                if _ok(result2):
                    code, result, self_corrected = comp2["code"], result2, True

    ok = _ok(result)
    out = {"success": ok, "compiled_ibl": code,
           "had_references": comp.get("had_references"),
           "compiler": comp.get("compiler", "cockpit"),
           "elapsed_ms": int((time.time() - t0) * 1000), "result": result}
    if self_corrected:
        out["self_corrected"] = True
    _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": from_body,
          "message": message, "compiled": code, "success": ok, "ms": out["elapsed_ms"]})
    return out
