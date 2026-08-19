"""
gemini_http.py — SDK 없는 Gemini REST 프로바이더 (폰 네이티브용)

목적: google-genai SDK 는 pydantic>=2.9(Rust pydantic_core)를 요구해 폰(Chaquopy,
pydantic v1)에서 import 불가. 하지만 Gemini 의 generateContent REST 엔드포인트는
`requests` 한 줄로 호출 가능 — 그래서 "두뇌=폰" 경로의 LLM 호출을 SDK 없이 구현한다.

설계: 동기 + 도구 호출 루프(함수호출 functionCall ↔ functionResponse)를 폰에서 돌린다.
도구 실행(execute_tool)은 폰에서 일어나므로 limbs:phone 같은 폰 전용 도구가 동작한다.
캐싱/스트리밍은 생략(폰 v1). 길어지면 compaction(요약)이 먼저 돌고, 그래도 압력이 남으면
Gemini pruning 이 최후로 돈다 — 절차는 base._compact_gemini_http_shape(2026-08-19 배선).

엔드포인트는 기본 google REST. base_url 인자로 맥 게이트웨이 등으로 바꿀 수 있게 열어둠.
"""
import json
import os
import time
from typing import List, Dict, Any, Callable, Optional

import requests

from .base import BaseProvider, MAX_TOOL_ROUNDS, FINAL_TURN_INSTRUCTION


_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_TYPE_MAP = {
    "string": "STRING", "number": "NUMBER", "integer": "INTEGER",
    "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
}
# Gemini Schema 가 받아들이지 않는 JSON-Schema 키 (drop)
_SCHEMA_DROP = {"additionalProperties", "$schema", "default", "title", "examples", "format"}


class GeminiHTTPProvider(BaseProvider):
    """Gemini REST(generateContent) 동기 프로바이더 — SDK 미사용. 폰 네이티브 LLM 경로."""

    MAX_TOOL_ITERATIONS = MAX_TOOL_ROUNDS  # 전 프로바이더 공통값(base.MAX_TOOL_ROUNDS)

    # Gemini 2.5: 1M 토큰 컨텍스트 → 80% = 800K 토큰 → ~1,600,000자 (2자=1토큰 실측).
    # ★base 기본값(Claude 200K 기준)을 물려받아 자기 컨텍스트의 1/5 에서 요약하고 있었다.
    COMPACTION_CHAR_THRESHOLD = 1600000

    def __init__(self, **kwargs):
        # base_url: 직접 google REST(기본) 또는 맥 게이트웨이 프록시
        self.base_url = (kwargs.pop("base_url", None) or os.environ.get(
            "GEMINI_BASE_URL") or _DEFAULT_BASE).rstrip("/")
        super().__init__(**kwargs)
        self.temperature = 0.8

    # ── 초기화 ──────────────────────────────────────────────
    def init_client(self) -> bool:
        key = (self.api_key or "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            print(f"[GeminiHTTP] {self.agent_name}: GEMINI_API_KEY 없음")
            return False
        self.api_key = key
        self._client = True  # SDK 없음 — 준비됨 표식만
        print(f"[GeminiHTTP] {self.agent_name}: 초기화 (도구 {len(self.tools)}개, base={self.base_url})")
        return True

    # ── 스키마/도구 변환 ────────────────────────────────────
    def _clean_schema(self, schema: dict) -> dict:
        """JSON Schema → Gemini Schema(OpenAPI subset) 재귀 변환."""
        if not isinstance(schema, dict):
            return {"type": "STRING"}
        jt = schema.get("type", "string")
        out: Dict[str, Any] = {"type": _GEMINI_TYPE_MAP.get(jt, "STRING")}
        if schema.get("description"):
            out["description"] = schema["description"][:1000]
        if "enum" in schema:
            out["type"] = "STRING"
            out["enum"] = schema["enum"]
            return out
        if jt == "object":
            props = schema.get("properties") or {}
            if props:
                out["properties"] = {k: self._clean_schema(v) for k, v in props.items()}
                req = [r for r in schema.get("required", []) if r in props]
                if req:
                    out["required"] = req
            else:
                # Gemini 는 빈 properties object 를 싫어함 → 빈 객체 파라미터는 생략 신호
                out["properties"] = {}
        elif jt == "array":
            out["items"] = self._clean_schema(schema.get("items") or {"type": "string"})
        return out

    def _gemini_tools(self) -> Optional[list]:
        if not self.tools:
            return None
        decls = []
        for t in self.tools:
            params = self._clean_schema(t.get("input_schema") or {"type": "object", "properties": {}})
            decl = {"name": t["name"], "description": (t.get("description") or "")[:1000]}
            # 파라미터 없는 도구는 parameters 생략(빈 object 거부 회피)
            if params.get("properties"):
                decl["parameters"] = params
            decls.append(decl)
        return [{"function_declarations": decls}]

    # ── contents 빌드 ───────────────────────────────────────
    def _build_contents(self, message: str, history: List[Dict]) -> list:
        contents = []
        for h in (history or []):
            role = "user" if h.get("role") == "user" else "model"
            tag = "user_message" if role == "user" else "assistant_message"
            contents.append({"role": role,
                             "parts": [{"text": f"<{tag}>\n{h.get('content','')}\n</{tag}>"}]})
        contents.append({"role": "user",
                         "parts": [{"text": f"<current_user_request>\n{message}\n</current_user_request>"}]})
        return contents

    # ── REST 호출 ───────────────────────────────────────────
    def _generate(self, contents: list, tools: Optional[list]) -> dict:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        gen_config: Dict[str, Any] = {"temperature": self.temperature}
        # 원샷 계약: 2.5 flash 계열 기본 thinking 차단(ep889 부류 — gemini.py 와 대칭).
        _try_thinking_off = self.disable_thinking and not self._thinking_off_unsupported
        if _try_thinking_off:
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}
        body: Dict[str, Any] = {"contents": contents,
                                "generationConfig": gen_config}
        if self.system_prompt:
            body["system_instruction"] = {"parts": [{"text": self.system_prompt}]}
        if tools:
            body["tools"] = tools
        r = requests.post(url, json=body, timeout=120)
        if r.status_code != 200:
            # budget 0 거부 모델(flash-latest 부류) → 표식 후 1회 재시도(자가치유).
            # ★거부 응답이 범용 문구("invalid argument"만, 'thinking' 미언급 — 08-01 실측)라
            # 문구 매칭 불가 → 차단을 보낸 상태의 400이면 일단 빼고 재시도한다.
            # 다른 원인의 400이면 재시도도 같은 400 → 정상 raise (여분 요청 1회뿐).
            if _try_thinking_off and r.status_code == 400:
                print("[GeminiHTTP] thinkingBudget:0 400 거부 추정 — thinking 차단 포기 후 재시도")
                self._thinking_off_unsupported = True
                return self._generate(contents, tools)
            raise RuntimeError(f"Gemini REST {r.status_code}: {r.text[:300]}")
        return r.json()

    # ── compaction 요약 호출 (절차는 base._compact_gemini_http_shape) ─
    def _summarize_for_compaction(self, summary_input: str) -> str:
        """Gemini REST 로 요약 1회 호출. 실패하면 빈 문자열 → 프루닝 폴백.

        ★_generate 를 재사용하지 않는 이유 = 그 함수는 본 대화용이라 에이전트의
          system_prompt·도구·온도를 싣는다. 요약은 COMPACTION_PROMPT 하나로 불러야 한다.
        ★thinking 은 끈다(원샷 계약, ep889 부류). budget 0 을 거부하는 모델은 1회 재시도로
          자가치유하고, _generate 와 _thinking_off_unsupported 표식을 공유한다."""
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        for attempt in (0, 1):
            gen_config: Dict[str, Any] = {"temperature": 0.3, "maxOutputTokens": 2048}
            use_off = not self._thinking_off_unsupported
            if use_off:
                gen_config["thinkingConfig"] = {"thinkingBudget": 0}
            body: Dict[str, Any] = {
                "contents": [{"role": "user", "parts": [{"text": summary_input}]}],
                "generationConfig": gen_config,
                "system_instruction": {"parts": [{"text": self.COMPACTION_PROMPT}]},
            }
            try:
                r = requests.post(url, json=body, timeout=120)
            except Exception as e:
                print(f"[Compaction][GeminiHTTP] 요약 호출 예외: {e}")
                return ""
            if r.status_code == 200:
                cands = r.json().get("candidates") or []
                if not cands:
                    return ""
                parts = (cands[0].get("content") or {}).get("parts") or []
                return "".join(p["text"] for p in parts if isinstance(p, dict) and "text" in p)
            if use_off and r.status_code == 400 and attempt == 0:
                print("[Compaction][GeminiHTTP] thinkingBudget:0 400 거부 추정 — 차단 포기 후 재시도")
                self._thinking_off_unsupported = True
                continue
            print(f"[Compaction][GeminiHTTP] 요약 호출 {r.status_code}: {r.text[:200]}")
            return ""
        return ""

    # ── 메인 루프 ───────────────────────────────────────────
    def process_message(self, message: str, history: List[Dict] = None,
                        images: List[Dict] = None, execute_tool: Callable = None) -> str:
        if not self._client:
            return "AI가 초기화되지 않았습니다. GEMINI_API_KEY를 확인해주세요."
        contents = self._build_contents(message, history or [])
        tools = self._gemini_tools()
        accumulated = ""
        iteration = 0
        while iteration < self.MAX_TOOL_ITERATIONS:
            self._notify_round(iteration + 1, self.MAX_TOOL_ITERATIONS)
            # ★보존(요약) 먼저, 삭제는 최후 — deepseek_http 와 대칭(2026-08-19 배선).
            if iteration > 0 and self._should_compact(contents, iteration):
                contents = self._compact_gemini_http_shape(contents, "GeminiHTTP")
            # ★압력이 있을 때만 지운다(최후 수단)
            if iteration > 0 and self._should_prune(contents, iteration):
                contents = self._prune_messages_gemini(contents)
            try:
                data = self._execute_with_retry(self._generate, contents, tools)
            except Exception as e:
                return (accumulated + f"\n\n[LLM 호출 오류] {e}").strip()

            cands = data.get("candidates") or []
            if not cands:
                fb = data.get("promptFeedback", {})
                return (accumulated or f"[응답 없음] {json.dumps(fb, ensure_ascii=False)[:200]}").strip()
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p["text"] for p in parts if isinstance(p, dict) and "text" in p)
            fcs = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
            accumulated += text

            if not fcs:
                break

            # 모델 턴(functionCall 포함) 기록
            contents.append({"role": "model", "parts": parts})

            # 도구 실행 (폰에서) → functionResponse
            resp_parts = []
            for fc in fcs:
                name = fc.get("name", "")
                args = fc.get("args") or {}
                try:
                    out = execute_tool(name, args, self.project_path, self.agent_id) if execute_tool \
                        else "(도구 실행기 없음)"
                except Exception as e:
                    out = f"도구 '{name}' 실행 오류: {e}"
                out = str(out)
                if out.startswith("[[APPROVAL_REQUESTED]]"):
                    out = out.replace("[[APPROVAL_REQUESTED]]", "")
                if len(out) > 16000:
                    out = out[:16000]
                self.metrics.record_tool_call()
                resp_parts.append({"functionResponse": {"name": name, "response": {"result": out}}})
            # functionResponse 턴 (role 은 google REST 규약상 'user')
            contents.append({"role": "user", "parts": resp_parts})
            iteration += 1

        if iteration >= self.MAX_TOOL_ITERATIONS:
            # 조용한 절단 금지 — 도구를 뗀 마지막 턴으로 성과·잔여를 받아 착지.
            return self._final_turn_report(contents, accumulated)

        return accumulated.strip() or "(응답 없음)"

    def _final_turn_report(self, contents: list, accumulated: str) -> str:
        """도구 루프 상한 착지 — ★tools 없이 1회 호출해 성과·잔여 보고를 받는다."""
        limit = self.MAX_TOOL_ITERATIONS
        print(f"[GeminiHTTP] 도구 라운드 상한({limit}회) 도달 — 마무리 보고 턴 실행")
        # 마지막 턴은 functionResponse(user 역할)이므로 새 턴을 열지 않고 그 안에 이어 쓴다.
        final_contents = list(contents)
        instruction = {"text": FINAL_TURN_INSTRUCTION.format(limit=limit)}
        if final_contents and final_contents[-1].get("role") == "user":
            last = dict(final_contents[-1])
            last["parts"] = list(last.get("parts") or []) + [instruction]
            final_contents[-1] = last
        else:
            final_contents.append({"role": "user", "parts": [instruction]})

        text = ""
        try:
            data = self._generate(final_contents, None)
            cands = data.get("candidates") or []
            if cands:
                parts = (cands[0].get("content") or {}).get("parts") or []
                text = "".join(p["text"] for p in parts
                               if isinstance(p, dict) and "text" in p)
        except Exception as e:
            print(f"[GeminiHTTP] 마무리 보고 턴 실패: {str(e)[:200]}")
        return f"{accumulated}\n\n{self._final_turn_wrap(text, limit)}".strip()
