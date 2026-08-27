#!/usr/bin/env python3
"""은퇴 계약 잔재 검사 — 낱말의 뜻을 바꾸면 교재의 **모든** 표면이 따라와야 한다.

왜: 카탈로그(`ibl_actions.yaml`)와 파생물(`ibl_nodes.yaml`·`tool.json`·문서 마커)의
일치는 `build_ibl_nodes.py --check` 가 지킨다. 그러나 **같은 계약을 말하는 코드 안의
문장** — 핸들러의 오류·도움말 문자열, 독스트링, 가이드 산문 — 은 어떤 관문도 안 봤다.
2026-08-27 실측(`aa904ffc`): 47회차가 flatten 의 `each >> flatten` 계약 은퇴를
카탈로그에서만 집행해, **모델과 사용자가 실제로 읽는 런타임 오류 문구**가 은퇴한
관용구를 계속 지시하고 있었다. 카탈로그는 참인데 몸이 거짓을 말한 것이다.

교리: 사람이 고른 grep 범위는 반드시 샌다(pitfall hand-picked-sweep-leaks).
표면 목록을 사람이 기억하게 하지 않는다 — 은퇴할 때 등록부에 한 줄이면 관문이
전 표면을 대신 훑는다. 값·경로·동시성 관문과 같은 **탄생 차단** 교리다.

무엇을 잡나: `data/retired_contracts.yaml` 의 `phrases` 가 스캔 표면에 남아 있는 줄.

통과 조건: 그 줄 또는 바로 윗줄의 `retired-ok: <사유>` (사유 필수 — 동결 목록 금지,
silent_clamp 교리. 표식 위치 규약은 `check_concurrency.py` 의 `# cc-ok` 와 같다).
이행 진단·회귀 가드처럼 은퇴 문구를 **이름 불러 거절하는** 자리가 정당한 언급이다.

★관문 밖(정직 기록):
  - `backend/test_*.py` 와 이 관문 자신 — 부류상 금지 문구를 담는 자리다.
  - `data/_backups/`·`red_backups/` — 과거의 사진이지 교재가 아니다.
  - `outputs/`·`data/system_docs/changelog.log` — 사건의 기록이지 교재가 아니다.
  - "설명이 구현과 맞는가"는 여전히 기계 판정 불능이다. 이 관문이 잡는 것은
    **은퇴가 선언된 계약의 잔재**뿐 — 선언되지 않은 드리프트는 상상훈련의 몫이다.
  - 알려진 약점: 표식 문법 자체를 설명하는 산문이 금지 문구와 **같은 줄**에 있으면
    우연히 면제된다(문서가 자기를 면제). `--census` 로 면제 목록을 주기적으로 읽어
    사유가 실제로 적혀 있는지 눈으로 확인하라 — 면제는 침묵하지 않고 세어진다.

사용: 기본 = 관문 모드 · `--census` = 전수 보고.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "retired_contracts.yaml"
ALLOW_COMMENT = "retired-ok"

# 스캔 표면 — 기계가 소유한다(사람이 회차마다 떠올리지 않는다).
SCAN_GLOBS = [
    "data/packages/installed/**/*.py",
    "data/packages/installed/**/ibl_actions.yaml",
    "data/packages/installed/**/tool.json",
    "data/ibl_nodes_src/*.yaml",
    "data/ibl_nodes.yaml",
    "data/bodies/*.nodes.yaml",
    "data/guides/*.md",
    "data/common_prompts/**/*.md",
    "backend/**/*.py",
    "scripts/*.py",
]
SKIP_PARTS = {"__pycache__", "node_modules", "_backups", "red_backups",
              "_archive", ".venv", "build", "dist"}


def _load_registry():
    """등록부를 읽고 형식을 검증한다 — 사유 없는 등록은 등록이 아니다."""
    if not REGISTRY.exists():
        return [], [f"등록부 없음: {REGISTRY.relative_to(ROOT)}"]
    data = yaml.safe_load(REGISTRY.read_text()) or {}
    entries = data.get("retired") or []
    problems = []
    for i, e in enumerate(entries):
        where = f"retired[{i}] (id={e.get('id', '?')})"
        for key in ("id", "retired", "reason", "instead"):
            if not str(e.get(key) or "").strip():
                problems.append(f"{where}: '{key}' 가 비어 있다 — 은퇴는 사유와 대체를 남긴다.")
        if not e.get("phrases"):
            problems.append(f"{where}: 'phrases' 가 비어 있다 — 관문이 훑을 문구가 없다.")
    return entries, problems


def _scan_files():
    seen = set()
    for pat in SCAN_GLOBS:
        for p in ROOT.glob(pat):
            if not p.is_file() or p in seen:
                continue
            if SKIP_PARTS & set(p.parts):
                continue
            if p.name.startswith("test_") and p.parts[-2] == "backend":
                continue  # 가드 배터리는 금지 문구를 담는 자리다
            if p.name == Path(__file__).name:
                continue  # 이 관문 자신 — 등록부와 함께 금지 문구의 거처다
            seen.add(p)
    return sorted(seen)


def main() -> int:
    census = "--census" in sys.argv
    entries, problems = _load_registry()
    if problems:
        print("[FAIL] 은퇴 등록부 형식 위반:")
        for m in problems:
            print(f"  {m}")
        return 1

    phrase_owner = {}
    for e in entries:
        for ph in e["phrases"]:
            phrase_owner[ph] = e

    hits, exempt = [], []
    for p in _scan_files():
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if not any(ph in text for ph in phrase_owner):
            continue
        rel = p.relative_to(ROOT).as_posix()
        lines = text.splitlines()
        marker = f"{ALLOW_COMMENT}:"

        def _allowed(idx):
            """그 줄 또는 바로 윗줄의 사유 있는 표식 (check_concurrency 와 같은 규약)."""
            for cand in (lines[idx], lines[idx - 1] if idx > 0 else ""):
                if marker in cand and cand.split(marker, 1)[1].strip():
                    return True
            return False

        for idx, line in enumerate(lines):
            for ph, entry in phrase_owner.items():
                if ph not in line:
                    continue
                if _allowed(idx):
                    exempt.append((rel, idx + 1, entry["id"], ph))
                else:
                    hits.append((rel, idx + 1, entry, ph, line.strip()[:110]))

    if census:
        print(f"[census] 등록 계약 {len(entries)}건 · 문구 {len(phrase_owner)}개 · "
              f"스캔 파일 {len(_scan_files())}개")
        for rel, lineno, eid, ph in exempt:
            print(f"  면제 {rel}:{lineno} [{eid}] '{ph}'")
        for rel, lineno, entry, ph, snip in hits:
            print(f"  잔재 {rel}:{lineno} [{entry['id']}] '{ph}'\n      {snip}")
        print(f"총 잔재 {len(hits)}건 · 면제 {len(exempt)}건")
        return 0

    if hits:
        print("[FAIL] 은퇴한 계약을 아직 가르치는 자리 — 카탈로그만 고치면 샌다:")
        for rel, lineno, entry, ph, snip in hits[:40]:
            print(f"  {rel}:{lineno} [{entry['id']}] 금지 문구 '{ph}'")
            print(f"      {snip}")
            print(f"      → 참인 계약: {' '.join(str(entry['instead']).split())}")
        if len(hits) > 40:
            print(f"  … 외 {len(hits) - 40}자리")
        print(f"\n고치는 법: 그 문장을 참인 계약으로 고쳐라. 은퇴 문구를 이름 불러 "
              f"거절하는 자리(이행 진단·가드)라면 그 줄이나 바로 윗줄에 "
              f"`{ALLOW_COMMENT}: <사유>` "
              f"를 달아라(사유 필수).")
        return 1

    print(f"✓ 은퇴 계약 잔재 없음 — 등록 {len(entries)}건, 면제 {len(exempt)}건 "
          f"(전부 사유 보유)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
