"""
deepseek_http.py — SDK 없는 DeepSeek REST 프로바이더 (폰 네이티브용)

목적: DeepSeekProvider(deepseek.py)는 openai SDK 를 상속 사용하는데, 폰(Chaquopy)
번들엔 openai 패키지가 없다. DeepSeek API 는 OpenAI 호환 chat/completions REST 라
`requests` 만으로 호출 가능 — gemini_http.py 와 같은 원리("두뇌=폰" 경로를 SDK 없이).

설계: 동기 + 도구 호출 루프(tool_calls ↔ role:"tool")를 폰에서 돌린다. 도구 실행이
폰에서 일어나므로 limbs:phone 같은 폰 전용 도구가 동작한다. 스트리밍·캐싱 생략(폰 v1),
길어지면 compaction(요약)이 먼저 돌고, 그래도 압력이 남으면 프루닝(마스킹)이 최후로 돈다
— 절차는 base._compact_openai_shape 공유(2026-08-19 배선).

주의(딥시크 특성, deepseek.py 와 대칭):
- v4 하이브리드 thinking: max_tokens 를 추론과 본문이 나눠 쓴다 → 16384 (4096 이면
  무거운 프롬프트에서 추론이 예산을 태워 본문 0자).
- 원샷 계약(disable_thinking): body 에 {"thinking": {"type": "disabled"}} (2026-08-01 실측).
- thinking+tools 요청의 reasoning_content 는 후속 요청에 그대로 재전송한다(누락 시 400).
- 비전 없음: images 파라미터는 받되 무시(이미지 파트를 보내면 400 — 2026-08-13 실측 부류).
"""
import json
import os
from typing import List, Dict, Any, Callable, Optional

import requests

from .base import BaseProvider, MAX_TOOL_ROUNDS, build_final_turn_messages


_DEFAULT_BASE = "https://api.deepseek.com"


class DeepSeekHTTPProvider(BaseProvider):
    """DeepSeek REST(chat/completions) 동기 프로바이더 — SDK 미사용. 폰 네이티브 LLM 경로."""

    MAX_TOOL_ITERATIONS = MAX_TOOL_ROUNDS  # 전 프로바이더 공통값(base.MAX_TOOL_ROUNDS)

    # V4 공식 1M 컨텍스트의 80% × 이 시스템 실측 2자/토큰 = 1.6M자.
    COMPACTION_CHAR_THRESHOLD = 1_600_000
    DEFAULT_MAX_TOKENS = 16384  # v4 하이브리드 thinking 예산 (deepseek.py 와 동일 근거)

    def __init__(self, **kwargs):
        self.base_url = (kwargs.pop("base_url", None) or os.environ.get(
            "DEEPSEEK_BASE_URL") or _DEFAULT_BASE).rstrip("/")
        super().__init__(**kwargs)
        self.temperature = 0.8

    def _openai_compaction_ack(self):
        """합성 assistant ACK은 DeepSeek thinking 규약상 reasoning_content가 없어 금지."""
        return None

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
    def _chat(self, messages: list, tools: Optional[list], force_thinking_off: bool = False) -> dict:
        url = f"{self.base_url}/chat/completions"
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.DEFAULT_MAX_TOKENS,
            "temperature": self.temperature,
        }
        if tools:
            body["tools"] = tools
        if self.disable_thinking or force_thinking_off:
            body["thinking"] = {"type": "disabled"}
        r = requests.post(url, json=body, timeout=180,
                          headers={"Authorization": f"Bearer {self.api_key}"})
        if r.status_code != 200:
            raise RuntimeError(f"DeepSeek REST {r.status_code}: {r.text[:300]}")
        return r.json()

    # ── compaction 요약 호출 (절차는 base._compact_openai_shape) ─
    def _summarize_for_compaction(self, summary_input: str) -> str:
        """DeepSeek REST 로 요약 1회 호출. 실패하면 빈 문자열 → 프루닝 폴백.

        ★thinking 을 self.disable_thinking 과 무관하게 끈다: v4 하이브리드는 추론이
          max_tokens 를 전부 태워 본문 0자를 돌려주고, 그러면 요약이 실패해 삭제로
          폴백한다(ep1177 부류). 요약은 원샷 계약이라 추론이 필요 없다.
        ★_chat 을 재사용하지 않는 이유 = 예산(16384)·온도(0.8)·thinking 조건이 본 대화용
          이라 요약에 그대로 쓰면 안 된다."""
        try:
            body: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": 2048,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": self.COMPACTION_PROMPT},
                    {"role": "user", "content": summary_input},
                ],
                "thinking": {"type": "disabled"},
            }
            r = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=180,
                              headers={"Authorization": f"Bearer {self.api_key}"})
            if r.status_code != 200:
                print(f"[Compaction][DeepSeekHTTP] 요약 호출 {r.status_code}: {r.text[:200]}")
                return ""
            choices = r.json().get("choices") or []
            return ((choices[0].get("message") or {}).get("content") or "") if choices else ""
        except Exception as e:
            print(f"[Compaction][DeepSeekHTTP] 요약 호출 예외: {e}")
            return ""

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
        force_thinking_off = False
        while iteration < self.MAX_TOOL_ITERATIONS:
            self._notify_round(iteration + 1, self.MAX_TOOL_ITERATIONS)
            # ★보존(요약) 먼저, 삭제는 최후 — 순서가 곧 정책이다(base 의 임계값 주석 참조).
            #   2026-08-19: 그전엔 이 자리에 프루닝만 있었다. COMPACTION_CHAR_THRESHOLD 를
            #   선언해 두고도 부르는 쪽이 없어, 폰 두뇌(3 티어 전부 이 프로바이더)는 마스킹
            #   만으로 128K 컨텍스트를 버티고 있었다 = 선언-호출 분리 드리프트.
            if iteration > 0 and self._should_compact(messages, iteration):
                messages = self._compact_openai_shape(messages, "DeepSeekHTTP")
            # ★압력이 있을 때만 지운다(최후 수단)
            if iteration > 0 and self._should_prune(messages, iteration):
                messages = self._prune_messages_openai(messages)
            try:
                data = self._execute_with_retry(
                    self._chat, messages, tools, force_thinking_off)
            except Exception as e:
                if (not force_thinking_off and "reasoning_content" in str(e)
                        and "passed back" in str(e)):
                    print("[DeepSeekHTTP] reasoning_content 400 — thinking을 끄고 1회 복구")
                    force_thinking_off = True
                    try:
                        data = self._execute_with_retry(
                            self._chat, messages, tools, force_thinking_off)
                    except Exception as retry_error:
                        return (accumulated + f"\n\n[LLM 호출 오류] {retry_error}").strip()
                else:
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

            # thinking+tools 규약: 모델이 낸 추론을 도구 결과와 함께 다음 요청에 되돌린다.
            assistant_message = {"role": "assistant", "content": text or None,
                                 "tool_calls": tool_calls}
            if "reasoning_content" in msg:
                assistant_message["reasoning_content"] = msg.get("reasoning_content")
            messages.append(assistant_message)

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

        if iteration >= self.MAX_TOOL_ITERATIONS:
            # 조용한 절단 금지 — 도구를 뗀 마지막 턴으로 성과·잔여를 받아 착지.
            return self._final_turn_report(messages, accumulated)

        return accumulated.strip() or "(응답 없음)"

    def _final_turn_report(self, messages: list, accumulated: str) -> str:
        """도구 루프 상한 착지 — ★tools 없이 1회 호출해 성과·잔여 보고를 받는다."""
        limit = self.MAX_TOOL_ITERATIONS
        print(f"[DeepSeekHTTP] 도구 라운드 상한({limit}회) 도달 — 마무리 보고 턴 실행")
        text = ""
        try:
            data = self._chat(build_final_turn_messages(messages, limit), None)
            choices = data.get("choices") or []
            if choices:
                text = (choices[0].get("message") or {}).get("content") or ""
        except Exception as e:
            print(f"[DeepSeekHTTP] 마무리 보고 턴 실패: {str(e)[:200]}")
        return f"{accumulated}\n\n{self._final_turn_wrap(text, limit)}".strip()
