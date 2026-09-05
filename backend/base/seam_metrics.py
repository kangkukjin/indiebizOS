"""seam_metrics.py — 셸↔IBL 이음매 관측 (2026-09-05, 사용자 정식화).

> "셸로 되는 일을 굳이 IBL 로 하는 게 핵심이 아니다. 문제는 IBL 어휘와 셸이 만나는 자리다 — 둘은 조합이 안 되니
>  결국 모델 소환으로 갈라진다. 그런 자리에서는 IBL 이 합리적이다."

그래서 재는 것은 Bash 비중이 아니라 **이음매**다:
  · seam    = 셸 도구(Bash·shell·run_command) 호출과 IBL(execute_ibl) 호출이 인접한 쌍.
  · carried = 그 이음매에서 앞 호출의 **결과**에 나온 값(숫자·경로·긴 토큰)이 뒤 호출의 입력(IBL 문장·셸 명령)에
              다시 나타난 것 — 데이터가 모델의 컨텍스트를 거쳐 손으로 되찍힌 자리. 파일로 건네면 사라질 왕복.
  인접만으로는 세지 않는다 — grep 으로 자리를 찾고 아는 파일을 read 하는 것은 판단만 건너간 것이라 IBL 로 옮길 이유가 없다.

왜 여기(base 층)인가: 값이 온전한 자리는 프로바이더가 tool_result 전문을 받는 순간뿐이다(episode_log 는 300자에서
절단 — 사후 로그로는 하한밖에 못 센다, 09-05 실측 ep2821 의 id 되찍기가 절단 뒤에 있었다). 프로바이더(호스트)와
지표 스크립트가 같은 판정기를 쓰도록 잎 모듈로 둔다(형제 import 없음).
"""
import re
from typing import Any, Dict, List, Optional, Set

SHELL_TOOLS = {"Bash", "shell", "run_command", "bash"}
_VALUE_RE = re.compile(
    r"(?<![\w/.-])(?:\d{3,}|/[\w./~-]{6,}|[A-Za-z_][\w-]{7,}\d[\w-]*|[\w-]*\d[\w-]*\.(?:json|md|py|db|txt|csv|yaml|log))(?![\w/.-])")
_NOISE = {"success", "message", "items", "true", "false", "null"}
MAX_TEXT = 400_000        # 값 추출 상한 — 거대한 결과는 앞부분만(관측이지 분석이 아니다)


def is_ibl_tool(name: Any) -> bool:
    return "execute_ibl" in str(name or "")


def is_shell_tool(name: Any) -> bool:
    return str(name or "") in SHELL_TOOLS


def extract_values(text: Any) -> Set[str]:
    """되찍힐 만한 값 — 3자리 이상 숫자(줄 번호 포함)·경로·숫자 섞인 긴 토큰·데이터 파일 이름. 소문자 정규화."""
    if not isinstance(text, str):
        try:
            import json
            text = json.dumps(text, ensure_ascii=False)
        except Exception:
            text = str(text)
    out: Set[str] = set()
    for v in _VALUE_RE.findall(text[:MAX_TEXT]):
        v = v.strip("/.").lower()
        if len(v) >= 3 and v not in _NOISE:     # 줄 번호(3자리)도 되찍기의 단골 — ep2835 grep→read{start_line: 236}
            out.add(v)
    return out


def crossed_values(prev_result: Any, prev_input: Any, next_input: Any) -> List[str]:
    """앞 결과 → 뒤 입력으로 건너간 값(앞 입력에도 있던 값은 모델이 이미 알던 것이라 제외)."""
    crossed = (extract_values(prev_result) & extract_values(next_input)) - extract_values(prev_input)
    return sorted(crossed)


class SeamTracker:
    """프로바이더가 도구 호출을 볼 때마다 먹인다 — on_tool_use 가 이음매면 관측 dict 를 돌려준다(아니면 None)."""

    def __init__(self):
        self._prev: Optional[Dict[str, Any]] = None       # {"tool", "input", "result"}
        self.seams = 0
        self.carried = 0
        self.carried_values = 0

    def on_tool_use(self, tool_name: Any, tool_input: Any) -> Optional[Dict[str, Any]]:
        cur_kind = "ibl" if is_ibl_tool(tool_name) else ("shell" if is_shell_tool(tool_name) else "other")
        obs = None
        prev = self._prev
        if prev is not None and {prev["kind"], cur_kind} == {"ibl", "shell"}:
            self.seams += 1
            crossed = crossed_values(prev.get("result", ""), prev.get("input", ""), tool_input)
            obs = {"from": prev["kind"], "to": cur_kind, "carried": bool(crossed), "values": len(crossed),
                   "sample": crossed[:5]}
            if crossed:
                self.carried += 1
                self.carried_values += len(crossed)
        self._prev = {"kind": cur_kind, "tool": str(tool_name or ""), "input": tool_input, "result": ""}
        return obs

    def on_tool_result(self, result_text: Any) -> None:
        if self._prev is not None:
            self._prev["result"] = result_text if isinstance(result_text, str) else str(result_text)

    def summary(self) -> Dict[str, int]:
        return {"seams": self.seams, "carried": self.carried, "carried_values": self.carried_values}
