#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정직성 불변식 스윕 — "성공 봉투는 거짓말하지 않는다" 를 fixture 우주 전체에 강제 (2026-08-23).

왜 (상상훈련 21회차 평가): 같은 **부류**가 7자리에서 재발했다 — B8(else 위장)→B10→F14-1(each
빈 치환)→B15-1(변환자 침묵 통과)→F18-1(열 절단)→B19-1(워드 연산자 강등)→B21-1(오류문이 success
봉투에). 자리마다 고치고 "같은 부류가 더 있나"를 판정 서랍에 넣었기 때문이다. 이 스윕은 부류를
**입구 하나**(봉투)에서 본다 — 새 위반자는 어느 핸들러에서 나오든 여기서 잡힌다.

불변식 (전부 `success 가 거짓이 아닌 봉투` 에 대한 것):
  A. 거짓 성공 — 성공 봉투의 본문(message/result/summary, 또는 맨몸 문자열)이 오류문이다.
     (`Error:`·`오류:` 접두 / `Traceback` / `… 오류 발생` / `Exception:`). B21-1 부류.
  B. 통화 부재 — 선언(returns)이 items/table 인데 성공 봉투에 `items` 리스트(또는 table)가 없다.
     `items: null` 도 위반(빈손은 `[]`). V13-1·F16-2·B19-2 부류. 실패 봉투는 면제(오류 채널이 정본).
  C. 0행 거짓 — ①items:[] 인 성공 봉투의 message 가 오류문으로 시작(0행=성공 계약, `Error:` 금지)
     ②items:[] 인데 success:false 이면서 error 채널이 비어 있음(0행을 실패로 접음). F17·P14 부류.
  D. (정적·정보) 패키지 핸들러가 실패를 `Error:` **접두 문자열**로 return 하는 자리 수.
     ★부채가 아니다 — system_essentials 계열은 execute()->str 인 **텍스트 계약** 핸들러라
     접두가 곧 실패 규약이고(P1~P19 회귀가 `startswith("Error:")` 를 단언, copy_ops 주석이
     규약을 명시) 실행기 `_is_error_result` 가 그 접두를 읽는다. 문제는 *접두 없는* 실패문
     (B21-1 — media_producer 의 `FFmpeg 오류:`)이며 그건 A 가 라이브로 잡는다. D 는 이 텍스트
     계약 가족의 크기를 기록해, 새 텍스트 핸들러가 생기면 접두 규약을 따르는지 대조하는 정보.

측정 우주 = data/ibl_fixtures.json (returns_drift_sweep 과 같은 우주·같은 규율: 부작용 없는
fixture 만, agent_id=__self_check__ 로 실사용 계수와 격리, 블립 1회 재시도).
판정만 하고 고치지 않는다 — 위반은 대장장이 입력(★판정 대기가 아니라 수리 대상).

사용: .venv/bin/python scripts/honesty_invariants_sweep.py [--strict] [--static-only]
      --strict: 위반 있으면 exit 1 (CI/수동용). 번들은 @@HONESTY@@ 마커를 읽는다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from returns_drift_sweep import _load_declarations, _declared_of, _execute  # noqa: E402

# ── 오류문 판독 (휴리스틱 — _is_error_result 접두 그물 + 본문 표지) ─────────────────────
ERROR_PREFIX_RE = re.compile(r"^\s*(Error|ERROR|오류|에러|실패)\s*[:：]")
ERROR_BODY_RE = re.compile(r"Traceback \(most recent call last\)|오류 발생|Exception:|\bFFmpeg 오류")


def looks_like_error_text(s) -> bool:
    if not isinstance(s, str) or not s.strip():
        return False
    return bool(ERROR_PREFIX_RE.search(s) or ERROR_BODY_RE.search(s))


def success_claimed(env) -> bool:
    """봉투가 '성공'이라고 말하는가. dict: success 가 False 가 아니고 error 채널이 비어 있음.
    맨몸 문자열: 표지가 없으므로 소비자는 성공으로 읽는다 → True."""
    if isinstance(env, dict):
        if env.get("success") is False:
            return False
        if env.get("error"):
            return False
        return True
    return isinstance(env, str)


def error_channel_present(env) -> bool:
    if isinstance(env, dict):
        return bool(env.get("error")) or looks_like_error_text(env.get("message"))
    return looks_like_error_text(env)


def final_of(resp):
    """실행 응답에서 최종 봉투 — 파이프면 final_result, 단일 액션이면 응답 자체.
    JSON 문자열 봉투는 파싱(핸들러 라우터가 문자열로 돌려주는 부류)."""
    env = resp
    if isinstance(env, dict) and "final_result" in env:
        env = env["final_result"]
    if isinstance(env, dict) and "result" in env and len(env) == 1:
        env = env["result"]
    if isinstance(env, str):
        s = env.strip()
        if s[:1] in "{[":
            try:
                env = json.loads(s)
            except Exception:
                pass
    return env


def has_table_shape(env) -> bool:
    t = env.get("table")
    return (isinstance(t, dict) and isinstance(t.get("rows"), list)) or (
        isinstance(env.get("rows"), list) and isinstance(env.get("columns"), list))


def check_envelope(name: str, declared: str, env) -> list:
    """(불변식, 사유) 목록. 빈 목록 = 정직."""
    out = []
    claimed = success_claimed(env)
    # A. 거짓 성공
    if claimed:
        if isinstance(env, str):
            if looks_like_error_text(env):
                out.append(("A", f"맨몸 문자열이 오류문: {env[:90]!r}"))
        elif isinstance(env, dict):
            for k in ("message", "result", "summary"):
                v = env.get(k)
                if looks_like_error_text(v):
                    out.append(("A", f"success 봉투의 {k} 가 오류문: {v[:90]!r}"))
                    break
    # B. 통화 부재 (성공 봉투만)
    if claimed and isinstance(env, dict) and declared in ("items", "table"):
        if not isinstance(env.get("items"), list) and not has_table_shape(env):
            why = "items: null (빈손은 [] 로)" if "items" in env else f"items 키 없음 (키: {sorted(env)[:8]})"
            out.append(("B", f"선언 {declared} 인데 {why}"))
    # C. 0행 거짓
    if isinstance(env, dict) and env.get("items") == []:
        if claimed and looks_like_error_text(env.get("message")):
            out.append(("C", f"0행 성공의 message 가 오류문: {env.get('message')[:90]!r}"))
        if env.get("success") is False and not error_channel_present(env):
            out.append(("C", "0행을 success:false 로 접음 — error 채널 없음(0행=성공 계약)"))
    return out


# ── D. 정적 정보: 텍스트 계약(접두) 실패 return 자리 ────────────────────────────────────────────
BARE_ERROR_RETURN_RE = re.compile(r"""return\s+f?["'](Error|오류|에러|실패)\s*[:：]""")


def static_bare_error_returns() -> dict:
    """텍스트 계약(접두) 실패 return 자리 — 패키지 핸들러만(backend 의 system_ai_tools·auto_response
    문자열 return 은 IBL 봉투가 아니라 시스템 AI 도구 루프/자동응답의 텍스트라 우주 밖)."""
    hits = {}
    for base in (ROOT / "data" / "packages" / "installed",):
        for p in base.rglob("*.py"):
            if p.name.startswith("test_") or "__pycache__" in p.parts:
                continue
            try:
                n = len(BARE_ERROR_RETURN_RE.findall(p.read_text(encoding="utf-8")))
            except Exception:
                continue
            if n:
                hits[str(p.relative_to(ROOT))] = n
    return hits


def _try(code):
    try:
        return _execute(code), None
    except Exception as e:
        return None, e


def main(argv) -> int:
    strict = "--strict" in argv
    static_only = "--static-only" in argv
    violations, failed, retried, checked = [], [], [], 0
    if not static_only:
        decl, decl_op, default_op, _ = _load_declarations()
        fx = json.load(open(ROOT / "data" / "ibl_fixtures.json", encoding="utf-8"))
        for name, code in sorted(fx["fixtures"].items()):
            declared, _lvl = _declared_of(name, decl, decl_op, default_op, code)
            resp, err = _try(code)
            probs = [] if err else check_envelope(name, declared, final_of(resp))
            if err is not None or probs:
                resp2, err2 = _try(code)            # 외부 API 블립 1회 흡수 (returns_drift 선례)
                if err2 is None:
                    probs2 = check_envelope(name, declared, final_of(resp2))
                    if err is not None or len(probs2) < len(probs):
                        retried.append(name)
                    resp, err, probs = resp2, None, probs2
            if err is not None:
                failed.append((name, str(err)[:80]))
                continue
            checked += 1
            for inv, why in probs:
                violations.append({"name": name, "inv": inv, "why": why})
    static = static_bare_error_returns()

    print("==== 정직성 불변식 스윕 ====")
    if not static_only:
        print(f"실측 {checked} · 위반 {len(violations)} · 실행 불능 {len(failed)}"
              + (f" · 블립 재시도 {len(retried)}건" if retried else ""))
        for inv, label in (("A", "거짓 성공(오류문이 success 봉투에)"),
                           ("B", "통화 부재(선언 items/table 인데 items 없음)"),
                           ("C", "0행 거짓(0행=성공 계약 위반)")):
            rows = [v for v in violations if v["inv"] == inv]
            print(f"\n[{inv}] {label} — {len(rows)}건")
            for v in rows:
                print(f"  ‼️ {v['name']}: {v['why']}")
        if failed:
            print(f"\n실행 불능 {len(failed)}건 (판정 아님):")
            for name, why in failed[:8]:
                print(f"  · {name}: {why}")
    print(f"\n[D] 텍스트 계약(접두) 실패 return {sum(static.values())}자리 / {len(static)}파일 (정보 — 부채 아님)")
    for p, n in sorted(static.items(), key=lambda kv: -kv[1]):
        print(f"  · {p}: {n}")

    print("@@HONESTY@@ " + json.dumps({
        "checked": checked, "failed": len(failed), "retried": retried,
        "violations": violations,
        "prefix_contract_sites": sum(static.values()),
    }, ensure_ascii=False))
    return 1 if (strict and violations) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
