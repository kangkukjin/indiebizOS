#!/usr/bin/env python3
"""연상 회상 고정물 — 정해진 입력 묶음의 회상 산출(블록·반사 신호)을 녹화하고, 구조를 바꾼 뒤 같은 입력으로 대조한다.

왜: 네 기억(실행·심층·포식·세계)의 호출·조립·기록을 공통 흐름으로 옮기는 일은 **동작을 바꾸지 않는 구조 통합**이
먼저다(2026-09-18 판정). "같은 입력에 같은 후보·같은 순서·같은 주입·같은 반사 판단"을 사람 눈이 아니라 이 파일이
증명한다. 녹화는 손대기 *전에* 한다 — 첫 편집이 들어간 뒤의 녹화는 아무것도 증명하지 못한다.

    .venv/bin/python3 scripts/recall_golden.py record --label before     # 녹화
    .venv/bin/python3 scripts/recall_golden.py check  --label before     # 대조 (다르면 exit 1)

고정물은 심층기억 본문을 담으므로 git 밖(`data/recall_index/golden/`)에 둔다. 인코더·색인은 미리 데워
백그라운드 적재 창(unavailable/indexing)이 결과를 흔들지 않게 한다. 지연·글자 수는 보고만 하고 판정하지 않는다
(같은 기계에서도 흔들리는 값) — 판정은 블록 본문과 반사 신호다.
"""
import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

REFLEX_THRESHOLD = 0.85
TAG_RE = re.compile(r"<([a-z_]+)\b[^>]*>.*?</\1>", re.DOTALL)

_LONG_DOC = ("도로교통법 개정안에 관한 에세이. " * 60)[:1300]

# 입력 묶음 — 네 기억이 각각 깨어나는 자리를 하나씩은 담는다(실행·심층·세계·포식 단서·후속·수리 단서·긴 문서·잡담).
CASES: List[Dict[str, Any]] = [
    {"id": "ibl_schedule", "message": "오늘 일정 알려줘", "history": []},
    {"id": "ibl_report", "message": "AI 동향 보고서 만들어줘", "history": []},
    {"id": "ibl_memory", "message": "메모리 사용량 확인해봐", "history": []},
    {"id": "deep_travel", "message": "속초 호텔에서 요리할 수 있나", "history": []},
    {"id": "deep_family", "message": "아내 선물로 뭐가 좋을까", "history": []},
    {"id": "world_roster", "message": "직원 근무표를 제약을 지키며 짜야 한다", "history": []},
    {"id": "world_render", "message": "집을 3차원 렌더링으로 표현해줘", "history": []},
    {"id": "world_name", "message": "Blender", "history": []},
    {"id": "forage_cue", "message": "지난주에 찍은 사진 어디 있어", "history": []},
    {"id": "followup", "message": "그걸 이어서 해줘",
     "history": [{"role": "user", "content": "직원 근무표를 제약을 지키며 짜야 한다"},
                 {"role": "assistant", "content": "제약을 정리해 보겠습니다."}]},
    {"id": "repair_cue", "message": "backend/api.py 의 헬스체크 고쳐줘", "history": []},
    {"id": "long_doc", "message": _LONG_DOC, "history": []},
    {"id": "chat", "message": "안녕", "history": []},
    {"id": "blog", "message": "블로그 글 초안 써줘", "history": []},
]


def _golden_dir() -> str:
    import tree_recall
    d = os.path.join(tree_recall._index_dir(), "golden")
    os.makedirs(d, exist_ok=True)
    return d


def _runner():
    """시스템 AI 와 같은 설정의 가벼운 러너 — AgentRunner 의 부수효과(폴러·모델 클라이언트) 없이 회상 경로만 돈다."""
    from cognitive_recall import CognitiveRecallMixin
    from runtime_utils import get_base_path

    class R(CognitiveRecallMixin):
        config = {"id": "system_ai", "name": "시스템 AI", "_is_system_ai": True, "allowed_nodes": None}
        project_path = get_base_path()
        agent_id = "system_ai"

    return R()


def _warm(runner) -> Dict[str, str]:
    """인코더·색인을 그 자리에서 올린다. 회상 경로는 백그라운드 적재라 첫 호출이 빈손일 수 있다."""
    status = {}
    from ibl_usage_db import IBLUsageDB
    status["hippocampus"] = "ready" if IBLUsageDB._load_model_sync() else "absent"
    import tree_recall
    status["encoder"] = "ready" if tree_recall.ensure_model(block=True) else "absent"
    try:
        from runtime_utils import get_base_path
        from world_recall_store import WorldStore
        tree_recall.build_now(WorldStore(get_base_path()))
        status["world_index"] = "built"
    except Exception as e:  # noqa: BLE001
        status["world_index"] = f"failed: {e}"
    try:
        from associative_recall import deep_memory_db
        db = deep_memory_db(runner)
        if db:
            from recall_store import DeepMemoryStore
            tree_recall.build_now(DeepMemoryStore(db))
            status["deep_index"] = "built"
        else:
            status["deep_index"] = "no_db"
    except Exception as e:  # noqa: BLE001
        status["deep_index"] = f"failed: {e}"
    return status


def _blocks(text: str) -> Dict[str, str]:
    """결합 문자열을 최상위 태그별로 가른다 — 옛/새 API 모두 같은 규칙으로 정규화해 비교한다."""
    out: Dict[str, str] = {}
    for m in TAG_RE.finditer(text or ""):
        tag = m.group(1)
        out[tag] = (out[tag] + "\n" + m.group(0)) if tag in out else m.group(0)
    return out


def collect(runner, message: str, history: list) -> Dict[str, Any]:
    """한 입력의 회상 산출. 파이프라인이 실제로 밟는 순서 그대로: 1상(반사 전) → 2상(request_type 뒤, 여기선 THINK 고정)."""
    t0 = time.monotonic()
    recall = runner._associate(message, history=history, channel="pipeline")
    reflex = {"score": round(float(recall.reflex.score or 0.0), 4), "code": recall.reflex.code or ""}
    recall.route(request_type="THINK")
    text = recall.text()
    ms = round((time.monotonic() - t0) * 1000)
    return {
        "reflex": reflex,
        "reflex_fires": bool(reflex["score"] >= REFLEX_THRESHOLD and reflex["code"]),
        "text": text,
        "blocks": _blocks(text),
        "chars": len(text),
        "ms": ms,
    }


def record(label: str) -> str:
    runner = _runner()
    warm = _warm(runner)
    print("데우기:", json.dumps(warm, ensure_ascii=False))
    out = {"label": label, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "warm": warm, "cases": {}}
    for c in CASES:
        r = collect(runner, c["message"], c["history"])
        out["cases"][c["id"]] = r
        print(f"  {c['id']:<14} reflex={r['reflex']['score']:.3f}{'★' if r['reflex_fires'] else ' '} "
              f"blocks={','.join(r['blocks'].keys()) or '-'} chars={r['chars']} ms={r['ms']}")
    path = os.path.join(_golden_dir(), f"{label}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"녹화: {path}")
    return path


def check(label: str) -> int:
    path = os.path.join(_golden_dir(), f"{label}.json")
    with open(path, encoding="utf-8") as f:
        golden = json.load(f)
    runner = _runner()
    warm = _warm(runner)
    print("데우기:", json.dumps(warm, ensure_ascii=False))
    failures = 0
    print(f"{'case':<14} {'reflex':>8} {'chars(전→후)':>16} {'ms(전→후)':>14}  판정")
    for c in CASES:
        g = golden["cases"].get(c["id"])
        if g is None:
            print(f"{c['id']:<14} 고정물에 없음 — 다시 녹화하라")
            failures += 1
            continue
        r = collect(runner, c["message"], c["history"])
        problems = []
        if r["reflex"] != g["reflex"]:
            problems.append(f"반사 {g['reflex']} → {r['reflex']}")
        if r["text"] != g["text"]:
            gb, rb = g["blocks"], r["blocks"]
            for tag in sorted(set(gb) | set(rb)):
                if gb.get(tag) != rb.get(tag):
                    problems.append(f"<{tag}> {'추가' if tag not in gb else '소실' if tag not in rb else '본문 변경'}")
            if list(gb.keys()) != list(rb.keys()) and not problems:
                problems.append(f"순서 {list(gb.keys())} → {list(rb.keys())}")
            if not problems:
                problems.append("태그 밖 텍스트 변경")
        verdict = "OK" if not problems else "✗ " + "; ".join(problems)
        failures += bool(problems)
        print(f"{c['id']:<14} {r['reflex']['score']:>8.3f} {g['chars']:>7}→{r['chars']:<8} {g['ms']:>6}→{r['ms']:<7} {verdict}")
    print("결과:", "동일" if not failures else f"불일치 {failures}건")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("mode", choices=["record", "check"])
    ap.add_argument("--label", default="before")
    a = ap.parse_args()
    if a.mode == "record":
        record(a.label)
        return 0
    return check(a.label)


if __name__ == "__main__":
    sys.exit(main())
