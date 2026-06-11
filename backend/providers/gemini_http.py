"""
gemini_http.py — SDK 없는 Gemini REST 프로바이더 (폰 네이티브용)

목적: google-genai SDK 는 pydantic>=2.9(Rust pydantic_core)를 요구해 폰(Chaquopy,
pydantic v1)에서 import 불가. 하지만 Gemini 의 generateContent REST 엔드포인트는
`requests` 한 줄로 호출 가능 — 그래서 "두뇌=폰" 경로의 LLM 호출을 SDK 없이 구현한다.

설계: 동기 + 도구 호출 루프(함수호출 functionCall ↔ functionResponse)를 폰에서 돌린다.
도구 실행(execute_tool)은 폰에서 일어나므로 limbs:phone 같은 폰 전용 도구가 동작한다.
캐싱/스트리밍/compaction 은 생략(폰 v1) — 길어지면 base 의 Gemini pruning 만 적용.

엔드포인트는 기본 google REST. base_url 인자로 맥 게이트웨이 등으로 바꿀 수 있게 열어둠.
"""
import json
import os
import time
from typing import List, Dict, Any, Callable, Optional

import requests

from .base import BaseProvider


_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
_GEMINI_TYPE_MAP = {
    "string": "STRING", "number": "NUMBER", "integer": "INTEGER",
    "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
}
# Gemini Schema 가 받아들이지 않는 JSON-Schema 키 (drop)
_SCHEMA_DROP = {"additionalProperties", "$schema", "default", "title", "examples", "format"}


class GeminiHTTPProvider(BaseProvider):
    """Gemini REST(generateContent) 동기 프로바이더 — SDK 미사용. 폰 네이티브 LLM 경로."""

    MAX_TOOL_ITERATIONS = 70

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
        body: Dict[str, Any] = {"contents": contents,
                                "generationConfig": {"temperature": self.temperature}}
        if self.system_prompt:
            body["system_instruction"] = {"parts": [{"text": self.system_prompt}]}
        if tools:
            body["tools"] = tools
        r = requests.post(url, json=body, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"Gemini REST {r.status_code}: {r.text[:300]}")
        return r.json()

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
            if iteration > 0:
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

        return accumulated.strip() or "(응답 없음)"
