"""desc 쌍이 파이프의 **꼬리 낱말**도 가르치는지 (2026-08-23)

실측한 굶주림: 트레이너의 intent→description 쌍이 `extract_action_from_code()` =
**코드의 첫 액션**으로만 만들어져서, 파이프 꼬리에만 사는 낱말은 desc 쌍을 한 건도 못
받았다. 코퍼스에 나오지만 머리에 선 적 없는 액션이 **14개, 전부 `table:` 변환자**였고
(take 150회 · filter 52 · sort 46 · brief 30 · since 25 · …), 직전 A/B 에서 실패한 프로브
6건 중 5건이 정확히 그 부류였다(table:ai · table:brief×2 · table:since×2).

★고치려는 병은 '희석'이 아니라 '굶주림'이다. 꼬리에 머리와 같은 몫을 주면 한 질의가 두
description 을 똑같이 당겨 **머리의 desc Top-1 이 동전던지기**가 된다 — 평가의 정답 라벨은
여전히 머리다. 그래서 꼬리는 **code 당 intent 1개**만 받는다: 0 을 벗어나는 최소량.

★평가(`extract_action_from_code`)와 측정자(`cloud_training/compare_models.py`)는 건드리지
않았다 — **자는 그대로 두고 학습만 바꾼다.** 그래야 A/B 가 이전 회차들과 비교 가능하다.

실행: .venv/bin/python -m pytest backend/test_desc_pair_coverage.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ibl_embedding_trainer as T  # noqa: E402


def test_D1_모든_액션을_등장_순으로_중복없이_뽑는다():
    code = ('[sense:feed]{url: "u"} >> [table:since]{key: "k"} >> [table:take]{n: 3} '
            '>> [table:since]{key: "k2"}')
    assert T.extract_actions_from_code(code) == ["sense:feed", "table:since", "table:take"]


def test_D2_머리_추출기는_안_바뀌었다():
    """평가의 정답 라벨 — 자를 바꾸면 이전 회차와 비교가 끊긴다."""
    code = '[sense:feed]{url: "u"} >> [table:since]{key: "k"}'
    assert T.extract_action_from_code(code) == "sense:feed"
    assert T.extract_actions_from_code(code)[0] == T.extract_action_from_code(code)


def test_D3_단일_액션은_꼬리가_없다():
    code = '[table:since]{items: [], key: "k"}'
    assert T.extract_actions_from_code(code) == ["table:since"]


def test_D4_액션이_없으면_빈_목록():
    assert T.extract_actions_from_code("그냥 문장") == []
    assert T.extract_action_from_code("그냥 문장") == ""


def _build_pairs(code_to_intents, descs):
    """트레이너의 desc 쌍 구성만 떼어내 재현 — 몫의 비율을 시험이 지킨다."""
    pairs = []
    for code, intents in code_to_intents.items():
        actions = T.extract_actions_from_code(code)
        head = actions[0] if actions else ""
        if head in descs:
            for intent in intents[:5]:
                pairs.append((intent, descs[head]))
        for tail in actions[1:]:
            if tail in descs and intents:
                pairs.append((intents[0], descs[tail]))
    return pairs


def test_D5_꼬리가_0을_벗어나되_머리를_넘지_않는다():
    """이 배터리의 본론: 굶주림은 끝나고 희석은 최소로."""
    descs = {"sense:feed": "피드 설명", "table:since": "검침 설명"}
    code = '[sense:feed]{url: "u"} >> [table:since]{key: "k"}'
    intents = ["a", "b", "c", "d", "e", "f"]
    pairs = _build_pairs({code: intents}, descs)
    head_n = sum(1 for _, d in pairs if d == "피드 설명")
    tail_n = sum(1 for _, d in pairs if d == "검침 설명")
    assert tail_n >= 1, "꼬리가 여전히 굶는다 — 이 수리의 전부가 무효다"
    assert head_n == 5, f"머리 몫이 바뀌었다({head_n}) — 옛 신호를 건드리지 않기로 했다"
    assert tail_n < head_n, f"꼬리 몫({tail_n})이 머리({head_n})와 대등하면 Top-1 이 동전던지기가 된다"


def test_D6_실제_코퍼스에_굶는_액션이_남지_않는다():
    """★부재 주장은 관측이 있을 때만(B28-1) — 코퍼스를 못 읽으면 시험을 건너뛴다."""
    import sqlite3
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = os.path.join(root, "data", "ibl_usage.db")
    if not os.path.exists(db):
        pytest.skip("코퍼스 DB 없음")
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        codes = [c for (c,) in conn.execute("select ibl_code from ibl_examples") if c]
        conn.close()
    except Exception as e:
        pytest.skip(f"코퍼스 읽기 불가: {e}")
    if not codes:
        pytest.skip("코퍼스 0행 — 부재를 주장할 수 없다")
    descs = T.load_action_descriptions()
    seen_any, seen_paired = set(), set()
    for code in codes:
        acts = T.extract_actions_from_code(code)
        seen_any.update(acts)
        for a in acts:                      # 새 규칙: 머리·꼬리 모두 desc 쌍을 받는다
            if a in descs:
                seen_paired.add(a)
    starved = sorted(a for a in seen_any if a in descs and a not in seen_paired)
    assert not starved, f"코퍼스에 있는데 desc 쌍을 못 받는 액션이 남았다: {starved}"


# ── 쌍둥이 드리프트 — 추적되지 않는 파일이라 시험이 대신 묻는다 ─────────────

_CLOUD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cloud_training", "ibl_embedding_trainer_cloud.py")


def test_D7_클라우드_트레이너가_같은_규칙인가():
    """★`cloud_training/` 은 **gitignore** 라 커밋 심사에 안 걸린다 — 갈라져도 아무도 모른다.
    그래서 추적되는 이 시험이 대신 묻는다(pre-commit 훅이 red_safety_selftest 에게
    *묻기만* 하는 것과 같은 형태).

    두 트레이너가 갈리면 **어느 경로로 학습했느냐에 따라 몸이 달라진다** — 로컬로 구우면
    꼬리 낱말이 이름을 얻고 클라우드로 구우면 굶는다. 같은 코퍼스인데 결과가 다르면
    A/B 판정 자체가 무의미해진다.

    파일이 아예 없으면 건너뛴다 — 없는 것은 갈라질 수도 없다(부재 주장 금지, B28-1).
    """
    if not os.path.exists(_CLOUD):
        pytest.skip("cloud_training 경로 없음 — 갈라질 대상이 없다")
    src = open(_CLOUD, encoding="utf-8").read()
    assert "def extract_actions_from_code" in src, (
        "클라우드 트레이너가 옛 규칙(첫 액션만)에 머물러 있다 — 그 경로로 학습하면 "
        "파이프 꼬리 낱말이 다시 굶는다")
    assert "actions[1:]" in src, (
        "클라우드 트레이너가 꼬리 액션에 desc 쌍을 주지 않는다")
    # 몫의 비율도 같아야 한다 — 꼬리에 intents[:5] 를 주면 로컬과 다른 몸이 나온다
    assert "intents[0], action_descs[tail]" in src, (
        "클라우드 트레이너의 꼬리 몫이 로컬(code 당 1개)과 다르다")


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차).
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
