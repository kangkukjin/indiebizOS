#!/usr/bin/env python3
"""빌드검증 — 몸(indiebizOS)의 커밋 전 관문 배터리를 한 번에 돌려 items 통화로 보고.
why: 개발 주행이 build --check·층 관문·동등성 관문을 매번 Bash 로 따로 돌렸다(새 요청 2주 Bash 2,735회 중 python 원라이너 ≈610).
     같은 명령의 되풀이는 어휘가 아니라 등록 스크립트의 자리(반-어휘-증식) — [self:script]{op:"run", id:"빌드검증"} 한 낱말로.
args (stdin JSON, 전부 선택):
  gates   ["build", "layers", "parity", "typecheck_parity", "items", "paths", "size"] 중 골라 순서대로 (기본 전부)
  timeout 관문 하나의 시한(초, 기본 240)
산출: {"items": [{"gate", "ok", "exit", "seconds", "summary"}], "ok": 전부 통과, "message": 한 줄}
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # indiebizOS/
PY = sys.executable
GATES = {
    "build": [PY, "scripts/build_ibl_nodes.py", "--check"],
    "layers": [PY, "scripts/check_backend_layers.py"],
    "parity": [PY, "scripts/check_validate_parity.py"],
    "typecheck_parity": [PY, "scripts/check_validate_parity.py", "--typecheck"],
    "items": [PY, "scripts/check_items_injection.py"],
    "paths": [PY, "scripts/check_field_path.py"],
    "size": [PY, "scripts/check_file_size.py"],
}


def _args():
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        return json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        return {}


def main():
    a = _args()
    names = a.get("gates") or list(GATES)
    timeout = float(a.get("timeout") or 240)
    items = []
    for g in names:
        cmd = GATES.get(g)
        if not cmd:
            items.append({"gate": g, "ok": False, "exit": None, "seconds": 0, "summary": f"알 수 없는 관문(가능: {', '.join(GATES)})"})
            continue
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
            out = (p.stdout + "\n" + p.stderr).strip().splitlines()
            bad = [l for l in out if "✗" in l or "FAIL" in l or "실패" in l]
            summary = (bad[-1] if (p.returncode != 0 and bad) else (out[-1] if out else ""))[:220]
            items.append({"gate": g, "ok": p.returncode == 0, "exit": p.returncode,
                          "seconds": round(time.time() - t0, 1), "summary": summary})
        except subprocess.TimeoutExpired:
            items.append({"gate": g, "ok": False, "exit": None, "seconds": round(time.time() - t0, 1), "summary": f"시한 {timeout:.0f}초 초과"})
    ok = all(i["ok"] for i in items)
    failed = [i["gate"] for i in items if not i["ok"]]
    print(json.dumps({"items": items, "ok": ok,
                      "message": "관문 전부 통과" if ok else f"관문 실패: {', '.join(failed)}"}, ensure_ascii=False))
    return 0          # 시험·관문 실패는 *결과*(ok:false·items)이지 스크립트 고장이 아니다 — exit 1 이면 [self:script] 가 "스크립트 실패" 로 봉해 items 가 안 흐른다(ep2862 실측)


if __name__ == "__main__":
    sys.exit(main())
