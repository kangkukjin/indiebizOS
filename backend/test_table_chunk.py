"""[table:chunk] 회귀 — 긴 문자열 하나를 덩이 items 로 (어휘 개정 2026-09-05, 개정 후보 5).

  C1  평문 prev·text 파라미터·봉투(text 계열 필드/field 지정) 세 입구가 같은 결과. items 통화는 정직 거절(each 안내).
  C2  chars: size/overlap 대로, 마지막 덩이까지 빠짐없이, start 오프셋 정확. overlap ≥ size 는 거절.
  C3  paragraph: 문단 경계로 나눠 size 안에서 이어 붙임 — 문단 하나가 size 를 넘으면 글자로 내려가고, 경계 없는 통짜 본문은 줄→글자로.
  C4  execute 진입: _prev_result 가 JSON 아닌 평문이어도 chunk 는 받는다(다른 변환자는 종전대로).
실행: .venv/bin/python -m pytest backend/test_table_chunk.py -q
"""
import importlib.util
import json
import os
import sys
import types

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401


@pytest.fixture(scope="module")
def H():
    p = os.path.join(BACKEND, "..", "data", "packages", "installed", "tools", "data-ops", "handler.py")
    sys.path.insert(0, os.path.dirname(p))          # 패키지 하위 모듈(chunk_ops·where_dsl)은 라이브 로더처럼 폴더 경로로 import
    spec = importlib.util.spec_from_file_location("dataops_handler", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctx(name):
    return types.SimpleNamespace(tool_name=name, output_dir=lambda: "/tmp")


def test_c1_three_entrances_and_items_rejected(H):
    text = "가나다라마바사아자차카타파하" * 10        # 140자
    a = H._op_chunk(text, {"size": 50, "by": "chars"})
    b = H._op_chunk(None, {"size": 50, "by": "chars", "text": text})
    c = H._op_chunk({"transcript": text, "video_id": "v1"}, {"size": 50, "by": "chars"})
    d = H._op_chunk({"본문": text}, {"size": 50, "by": "chars", "field": "본문"})
    assert a["items"] == b["items"] == c["items"] == d["items"] and a["count"] == 3
    assert c["video_id"] == "v1"                                   # 봉투의 식별 필드는 승계
    # items 통화(자막 구간·검색 결과) — 행 경계를 지키며 size 안에 담는다. 라이브 실측: transcript 는 문자열이 아니라 1,252행 items 였다.
    segs = [{"start": i, "text": f"구간 {i} 자막 문장"} for i in range(10)]
    r = H._op_chunk({"items": segs, "video_id": "v2"}, {"size": 40})
    assert r["success"] and r["by"] == "rows" and r["source_rows"] == 10 and r["video_id"] == "v2"
    assert all(it["chars"] <= 40 for it in r["items"]) and sum(it["rows"] for it in r["items"]) == 10
    assert r["items"][0]["start"] == 0 and r["items"][1]["start"] == r["items"][0]["rows"]
    assert not H._op_chunk({"items": [{"k": 1}]}, {"size": 5})["success"]          # 본문 키 없음 → 정직 거절
    r = H._op_chunk({"message": "자막이 길어서 파일로 저장했습니다", "items": segs}, {"size": 40})
    assert r["by"] == "rows" and r["source_rows"] == 10                             # 봉투 message(안내문)보다 items 가 본문
    r = H._op_chunk({"items": [{"본문": "가" * 30}]}, {"size": 10, "field": "본문"})
    assert r["count"] == 3                                                          # 행 하나가 size 초과 → 글자로


def test_c2_chars_overlap_and_coverage(H):
    text = "".join(chr(ord("a") + i % 26) for i in range(1000))
    r = H._op_chunk(text, {"size": 300, "overlap": 50, "by": "chars"})
    starts = [it["start"] for it in r["items"]]
    assert starts == [0, 250, 500, 750] and r["items"][-1]["chars"] == 250
    assert "".join(it["text"][(50 if i else 0):] for i, it in enumerate(r["items"])) == text   # 겹침 빼면 원문 전부
    assert not H._op_chunk(text, {"size": 100, "overlap": 100, "by": "chars"})["success"]
    assert not H._op_chunk(text, {"size": 0})["success"]


def test_c3_paragraph_packing_and_fallbacks(H):
    paras = ["첫 문단 " * 5, "둘째 문단 " * 5, "셋째 문단 " * 5, "넷째 문단 " * 5]   # 각 ~30자
    text = "\n\n".join(paras)
    r = H._op_chunk(text, {"size": 70})
    assert r["by"] == "paragraph" and r["count"] == 2
    assert r["items"][0]["text"].count("문단") == 10 and r["items"][0]["start"] == 0 and r["items"][1]["start"] == 2
    big = "한 문단이 너무 길다 " * 20                        # 문단 하나가 size 초과 → 글자로
    r = H._op_chunk("짧은 문단\n\n" + big, {"size": 60})
    assert r["count"] >= 4 and all(it["chars"] <= 60 for it in r["items"])
    flat = "경계없는통짜본문" * 50                          # 문단·줄 경계 없음 → 글자로 내려감
    r = H._op_chunk(flat, {"size": 100})
    assert r["by"] == "chars" and r["count"] == 4


def test_c4_execute_accepts_plain_prev_only_for_chunk(H):
    out = H.execute({"_prev_result": "평문 " * 100, "size": 100, "by": "chars"}, _ctx("data_chunk"))
    assert out["success"] and out["count"] == 3 and out["source_chars"] == 300
    out = H.execute({"_prev_result": json.dumps({"text": "a\n\nb\n\nc"}), "size": 3}, _ctx("data_chunk"))
    assert out["success"] and out["count"] == 3
    out = H.execute({"items": [{"text": "a\n\nb\n\nc"}], "size": 3}, _ctx("data_chunk"))
    assert out["success"] and out["count"] == 3 and out["by"] == "rows"     # 파이프 머리의 items: [{text}] 꼴
    out = H.execute({"_prev_result": "평문", "n": 2}, _ctx("data_take"))
    assert not out["success"]                                      # 다른 변환자는 종전대로 통화 요구


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
