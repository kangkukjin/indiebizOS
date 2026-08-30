#!/usr/bin/env python3
"""핀이 거짓말이 되지 않게 — 정확 핀 선언과 **이 몸의 .venv** 가 어긋나면 실패 (2026-08-30 신설).

배경(실측): `websocket-client` 가 핀 없이 선언돼 로컬 .venv 는 1.9.0, 새로 설치하는 몸
(CI·신규 사용자)은 1.9.1 을 받았다. 두 버전은 소켓이 이미 없을 때 close() 의 동작이 다르고,
그 차이가 DM 발송에서 **성공한 발송을 실패로 보고**하게 만들었다. 로컬은 나흘 내내 초록이었다.
사고의 뿌리는 그 라이브러리가 아니라 **로컬 초록이 다른 몸을 대변하지 못하는 구조**다.

그래서 핀을 박았다면 이 몸도 그 핀을 신고 있어야 한다 — 아니면 핀은 문서일 뿐 사실이 아니다.
반대 방향(선언에 없는 최신판이 로컬에 있다)은 여기서 판정하지 않는다. 무핀이 이 저장소의
기본이고(requirements-core.txt 의 fastapi 주석 참조), 그 표류는 CI 가 매번 새로 설치하며 잰다.

오라클은 둘 다 기계가 준다: 선언 = requirements 파일의 `==` 줄, 사실 = pip 의 설치 메타데이터.
.venv 가 없는 몸(CI 러너·신선 클론)에서는 **판정하지 않고 정직하게 건너뛴다** — 그 몸에서는
방금 선언대로 설치했으므로 원리적으로 어긋날 수 없고, 없는 것을 실패로 부르면 관문이 무뎌진다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_REQS = ("requirements-core.txt", "requirements-tools.txt", "requirements-ml.txt")


def exact_pins(root: Path = _ROOT) -> dict[str, tuple[str, str]]:
    """{패키지: (핀 버전, 선언 파일)} — `==` 정확 핀만. 상한(`<2`)·하한은 대상이 아니다."""
    pins: dict[str, tuple[str, str]] = {}
    for fname in _REQS:
        path = root / "backend" / fname
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            m = re.fullmatch(r"([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==([^\s;]+)", line)
            if m:
                pins[m.group(1).lower()] = (m.group(2), fname)
    return pins


def installed(python: Path) -> dict[str, str]:
    out = subprocess.run([str(python), "-m", "pip", "list", "--format=json"],
                         capture_output=True, text=True, check=True).stdout
    return {p["name"].lower(): p["version"] for p in json.loads(out)}


def violations(root: Path = _ROOT, python: Path | None = None) -> tuple[list[str], int]:
    """(어긋난 줄들, 검사한 핀 수). 판정할 몸이 없으면 ([], -1).

    python 을 주면 그 인터프리터를 판정 대상으로 삼는다 — 자기검증이 .venv 없는 몸
    (CI 러너)에서도 '어긋남을 진짜로 빨갛게 만드는가'를 재기 위한 이음매다.
    """
    if python is None:
        python = root / ".venv" / "bin" / "python3"
        if not python.exists():
            python = root / ".venv" / "Scripts" / "python.exe"  # 윈도우
    pins = exact_pins(root)
    if not python.exists() or not pins:
        return [], -1
    have = installed(python)
    bad = []
    for name, (want, fname) in sorted(pins.items()):
        got = have.get(name)
        if got is None:
            bad.append(f"  ✗ {name}=={want} ({fname}) — .venv 에 없음")
        elif got != want:
            bad.append(f"  ✗ {name}: 선언 =={want} ({fname}) ≠ .venv {got}")
    return bad, len(pins)


def _self_test() -> int:
    """가드가 무뎌지지 않았는지 — 어긋난 몸을 진짜로 빨갛게 만드는가."""
    import tempfile, textwrap
    ok = True
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td)
        (fake / "backend").mkdir()
        (fake / "backend" / "requirements-core.txt").write_text(textwrap.dedent("""\
            fastapi
            mcp<2
            websocket-client==9.9.9   # 이 몸에 있을 리 없는 버전
        """), encoding="utf-8")
        pins = exact_pins(fake)
        if set(pins) != {"websocket-client"}:
            print(f"  fail 정확 핀만 골라야 하는데 {sorted(pins)}"); ok = False
        else:
            print("  ok   무핀·상한은 대상 아님, `==` 만 고른다")
        # .venv 가 없는 몸은 판정하지 않는다
        if violations(fake) != ([], -1):
            print("  fail .venv 없는 몸을 건너뛰지 않았다"); ok = False
        else:
            print("  ok   .venv 없는 몸은 정직하게 건너뛴다")
        # 판정할 몸이 있으면 어긋남은 반드시 빨강 — .venv 가 없는 CI 러너에서도 재도록
        # 지금 이 인터프리터를 판정 대상으로 준다(어느 몸에나 있다 = 관문이 안 새는 자기검증).
        bad, n = violations(fake, python=Path(sys.executable))
        if n != 1 or not bad:
            print("  fail 어긋난 핀을 통과시켰다 — 가드가 전부 통과시킨다"); ok = False
        else:
            print("  ok   어긋난 핀은 빨강")
        # 일치하면 반드시 초록 — 오탐이면 가드가 모두를 막는다(음성 대조).
        (fake / "backend" / "requirements-core.txt").write_text(
            f"pip=={installed(Path(sys.executable)).get('pip', '0')}\n", encoding="utf-8")
        bad2, n2 = violations(fake, python=Path(sys.executable))
        if n2 != 1 or bad2:
            print(f"  fail 일치하는 핀을 빨강으로 만들었다(오탐): {bad2}"); ok = False
        else:
            print("  ok   일치하는 핀은 초록")
    print("자기검증 통과" if ok else "자기검증 실패")
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()
    bad, n = violations()
    if n == -1:
        print("핀 정합 검사: .venv 가 없어 건너뜀 (신선 설치 몸 — 선언대로 설치된다)")
        return 0
    if bad:
        print(f"✗ 핀과 .venv 가 어긋남 {len(bad)}건 — 핀이 사실이 아니면 로컬 초록은 다른 몸을 대변하지 못한다:")
        print("\n".join(bad))
        print("\n처방: `.venv/bin/python3 -m pip install -r backend/requirements-<티어>.txt`\n"
              "      (핀을 올릴 생각이면 그 버전으로 관련 시험을 돌리고 선언과 함께 커밋할 것)")
        return 1
    print(f"✓ 핀 정합 OK — 정확 핀 {n}건 전부 .venv 와 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
