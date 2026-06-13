"""
claude_code_remote.py - 폰-자아가 맥의 claude_code LLM 추론을 원격 렌트하는 provider.

폰-자아 호스팅(PHONE_SELF_HOSTING_HANDOFF §6.5):
- claude_code 는 에이전트(자기 루프)라 맥 CLI 에서만 돈다 — 폰은 단발 호출 불가, 원격 렌트만 가능.
- 이 provider 는 폰의 인지 하네스(중급·본격 티어)가 LLM 한 턴이 필요할 때 호출한다. 맥의
  `/providers/claude_code/remote_turn` 엔드포인트로 (system_prompt + 메시지 + history) 를 POST 하면,
  맥이 claude_code 를 돌리되 system_prompt 는 폰이 보낸 것(=폰 정체성)을 쓰고 execute_ibl 은 폰
  백엔드로 라우팅한다 → IBL 실행은 폰(폰-자아의 몸), LLM 추론(substrate)만 맥에서 빌림.
- "모델은 어디서 렌트하든 정체성과 무관"(§2.6) 의 구현: 추론 자아의 정체성은 system_prompt 가
  실어 나르고(폰 world_pulse.md), 모델 위치(맥)는 무관하다.

인증=맥 원격 런처 세션(_forward_to_mac 과 동일 패턴: INDIEBIZ_MAC_URL + INDIEBIZ_MAC_PASSWORD).
도달=집 LAN 또는 터널(INDIEBIZ_MAC_URL). 맥은 상시 가동이라 신뢰할 substrate.
"""

import os
from typing import List, Dict, Callable, Optional

from .base import BaseProvider


# 맥 위임 세션 캐시(원격 런처 인증) — 프로세스 전역. ibl_engine._mac_session_cache 와 동형.
_mac_session_cache = {"session": None}


class ClaudeCodeRemoteProvider(BaseProvider):
    """맥의 claude_code 를 원격 렌트하는 provider (폰 전용 — 폰엔 claude CLI 없음)."""

    DEFAULT_TIMEOUT_SEC = 600  # claude_code 한 턴(도구 루프 포함)은 길 수 있음

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._mac_url: Optional[str] = None

    def init_client(self) -> bool:
        """맥 위임 대상(INDIEBIZ_MAC_URL) 확인. 맥=두뇌 substrate."""
        self._mac_url = (os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/") or None
        if not self._mac_url:
            print("[ClaudeCodeRemoteProvider] INDIEBIZ_MAC_URL 미설정 — 맥(두뇌)에 연결 불가.")
            return False
        # is_ready 만족 마커
        self._client = {"mac_url": self._mac_url}
        print(f"[ClaudeCodeRemoteProvider] {self.agent_name}: 맥 렌트 준비 ({self._mac_url}, model={self.model or '기본'})")
        return True

    # ---- 맥 원격 런처 인증 (_forward_to_mac 패턴) ----
    def _login(self) -> bool:
        password = os.environ.get("INDIEBIZ_MAC_PASSWORD")
        if not password:
            return False
        try:
            import requests
            r = requests.post(f"{self._mac_url}/launcher/auth/login",
                              json={"password": password}, timeout=15)
            if r.status_code == 200:
                sid = (r.json() or {}).get("session_id")
                if sid:
                    _mac_session_cache["session"] = sid
                    return True
        except Exception:
            pass
        return False

    def process_message(
        self,
        message: str,
        history: List[Dict] = None,
        images: List[Dict] = None,
        execute_tool: Callable = None,
    ) -> str:
        """맥에 claude_code 한 턴을 렌트. execute_tool 은 무관(맥의 claude_code 가 MCP→폰으로 IBL 실행)."""
        if not self._mac_url and not self.init_client():
            return "맥(두뇌)에 연결되어 있지 않습니다. (INDIEBIZ_MAC_URL 미설정 — 집 PC가 켜져 있어야 추론을 빌릴 수 있습니다.)"

        import requests
        payload = {
            "message": message,
            "system_prompt": self.system_prompt or "",
            "history": history or [],
            "images": images or [],
            "agent_id": self.agent_id,
            "model": self.model or "",
            # backend_url 미동봉 → 맥이 자기 INDIEBIZ_PHONE_URL 로 폰을 가리킨다(맥이 폰 위치의 진실원).
        }

        def _post():
            headers = {"Content-Type": "application/json"}
            sess = _mac_session_cache.get("session")
            if sess:
                headers["X-Launcher-Session"] = sess
            return requests.post(f"{self._mac_url}/providers/claude_code/remote_turn",
                                 json=payload, headers=headers, timeout=self.DEFAULT_TIMEOUT_SEC)

        try:
            r = _post()
            if r.status_code in (401, 403):  # 세션 만료/미로그인 → 1회 재로그인
                if self._login():
                    r = _post()
        except Exception as e:
            return (f"맥(두뇌)에 추론을 빌리지 못했습니다 — {self._mac_url} 에 연결할 수 없습니다. "
                    f"집 PC가 켜져 있는지 확인하세요. ({e.__class__.__name__})")
        if r.status_code != 200:
            detail = ""
            try:
                detail = (r.json() or {}).get("detail", "")
            except Exception:
                detail = r.text[:200]
            return f"맥 추론 렌트 실패 (HTTP {r.status_code}) {detail}"
        try:
            data = r.json()
        except Exception:
            return r.text
        return data.get("response", "")
