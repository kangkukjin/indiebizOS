"""
deepseek_http.py — SDK 없는 DeepSeek REST 프로바이더 (폰 네이티브용)

목적: DeepSeekProvider(deepseek.py)는 openai SDK 를 상속 사용하는데, 폰(Chaquopy)
번들엔 openai 패키지가 없다. DeepSeek API 는 OpenAI 호환 chat/completions REST 라
`requests` 만으로 호출 가능 — gemini_http.py 와 같은 원리("두뇌=폰" 경로를 SDK 없이).

설계: 동기 + 도구 호출 루프(tool_calls ↔ role:"tool")를 폰에서 돌린다. 도구 실행이
폰에서 일어나므로 limbs:phone 같은 폰 전용 도구가 동작한다. 스트리밍·캐싱 생략(폰 v1),
길어지면 base 의 _prune_messages_openai 적용.

주의(딥시크 특성, deepseek.py 와 대칭):
- v4 하이브리드 thinking: max_tokens 를 추론과 본문이 나눠 쓴다 → 16384 (4096 이면
  무거운 프롬프트에서 추론이 예산을 태워 본문 0자).
- 원샷 계약(disable_thinking): body 에 {"thinking": {"type": "disabled"}} (2026-08-01 실측).
- reasoning_content 는 다음 턴에 재전송하지 않는다(DeepSeek 규약).
- 비전 없음: images 파라미터는 받되 무시(이미지 파트를 보내면 400 — 2026-08-13 실측 부류).
"""
import json
import os
from typing import List, Dict, Any, Callable, Optional

import requests

from .base import BaseProvider


_DEFAULT_BASE = "https://api.deepseek.com"


class DeepSeekHTTPProvider(BaseProvider):
    """DeepSeek REST(chat/completions) 동기 프로바이더 — SDK 미사용. 폰 네이티브 LLM 경로."""

    MAX_TOOL_ITERATIONS = 70
    DEFAULT_MAX_TOKENS = 16384  # v4 하이브리드 thinking 예산 (deepseek.py 와 동일 근거)

    def __init__(self, **kwargs):
        self.base_url = (kwargs.pop("base_url", None) or os.environ.get(
            "DEEPSEEK_BASE_URL") or _DEFAULT_BASE).rstrip("/")
        super().__init__(**kwargs)
        self.temperature = 0.8

    # ── 초기화 ──────────────────────────────────────────────
    def init_client(self) -> bool:
        key = (self.api_key or "").strip() or os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not key:
            print(f"[DeepSeekHTTP] {self.agent_name}: DEEPSEEK_API_KEY 없음")
            return False
        self.api_key = key
        self._client = True  # SDK 없음 — 준비됨 표식만
        print(f"[DeepSeekHTTP] {self.agent_name}: 초기화 (도구 {len(self.tools)}개, base={self.base_url})")
        return True

    # ── 도구 변환 (OpenAI function 포맷 — JSON Schema 그대로) ─
    def _openai_tools(self) -> Optional[list]:
        if not self.tools:
            return None
        return [{
            "type": "function",
            "function": {
                "name": t["name"],
                "description": (t.get("description") or "")[:1000],
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        } for t in self.tools]

    # ── messages 빌드 ───────────────────────────────────────
    def _build_messages(self, message: str, history: List[Dict]) -> list:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        for h in (history or []):
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": message})
        return messages

    # ── REST 호출 ───────────────────────────────────────────
    def _chat(self, messages: list, tools: Optional[list]) -> dict:
        url = f"{self.base_url}/chat/completions"
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.DEFAULT_MAX_TOKENS,
            "temperature": self.temperature,
        }
        if tools:
            body["tools"] = tools
        if self.disable_thinking:
            body["thinking"] = {"type": "disabled"}
        r = requests.post(url, json=body, timeout=180,
                          headers={"Authorization": f"Bearer {self.api_key}"})
        if r.status_code != 200:
            raise RuntimeError(f"DeepSeek REST {r.status_code}: {r.text[:300]}")
        return r.json()

    # ── 메인 루프 ───────────────────────────────────────────
    def process_message(self, message: str, history: List[Dict] = None,
                        images: List[Dict] = None, execute_tool: Callable = None) -> str:
        # images 는 무시 — 딥시크 비전 없음(이미지 파트=400). gemini_http v1 과 동급.
        if not self._client:
            return "AI가 초기화되지 않았습니다. DEEPSEEK_API_KEY를 확인해주세요."
        messages = self._build_messages(message, history or [])
        tools = self._openai_tools()
        accumulated = ""
        iteration = 0
        while iteration < self.MAX_TOOL_ITERATIONS:
            self._notify_round(iteration + 1, self.MAX_TOOL_ITERATIONS)
            if iteration > 0:
                messages = self._prune_messages_openai(messages)
            try:
                data = self._execute_with_retry(self._chat, messages, tools)
            except Exception as e:
                return (accumulated + f"\n\n[LLM 호출 오류] {e}").strip()

            choices = data.get("choices") or []
            if not choices:
                return (accumulated or "[응답 없음]").strip()
            msg = choices[0].get("message") or {}
            text = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []
            accumulated += text

            if not tool_calls:
                break

            # 어시스턴트 턴 기록 — reasoning_content 는 재전송 금지(규약)라 제외
            messages.append({"role": "assistant", "content": text or None,
                             "tool_calls": tool_calls})

            # 도구 실행 (폰에서) → role:"tool" 응답
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                try:
                    out = execute_tool(name, args, self.project_path, self.agent_id) \
                        if execute_tool else "(도구 실행기 없음)"
                except Exception as e:
                    out = f"도구 '{name}' 실행 오류: {e}"
                if isinstance(out, dict):
                    # 수확 관문의 {content, images, details} 봉투 — 비전 없는 모델이라
                    # 본문만 취한다(base64 가 str() 로 컨텍스트에 쏟아지는 것 방지).
                    out = str(out.get("content") or out)
                out = str(out)
                if out.startswith("[[APPROVAL_REQUESTED]]"):
                    out = out.replace("[[APPROVAL_REQUESTED]]", "")
                if len(out) > 16000:
                    out = out[:16000]
                self.metrics.record_tool_call()
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": out})
            iteration += 1

        return accumulated.strip() or "(응답 없음)"
