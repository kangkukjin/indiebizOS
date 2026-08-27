"""[self:struct] 파이프 본문 이음매 — 외부화 봉투를 따라가고, 안내문을 원문으로 오독하지 않는다 (2026-08-27)

실측 사고(51회차 후속, "자막 증류를 문장으로" 실험):
  ①transcript 는 10,000자 초과분을 파일로 내리고(saved_to_file+file_path) 봉투엔
    preview·안내 message 만 남긴다. struct 의 본문 사슬(text/content/summary/message)은
    transcript 도 preview 도 몰라, **사용 안내문(message)을 원문으로 삼아 추출**하는
    조용한 품질 실패가 있었다.
  ②외부화 파일은 `[MM:SS] 문장` 병기 포맷이라, 정규화 없이 넘기면 grounded 대조
    (_quote 원문 부분열 검사)가 구조적으로 전멸한다(실측: 추출 16건 전원 탈락).

수리: 외부화 봉투(saved_to_file+file_path)는 파일 전문을 따라가 읽고 타임스탬프·헤더를
걷어 흐르는 본문으로 정규화한다. 본문 필드 사슬에 transcript(자막 전문)·preview 를
편입하고 message 는 최후 폴백으로만 남긴다.

실행: .venv/bin/python -m pytest backend/test_struct_body_seam.py
"""
import importlib.util
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HANDLER = os.path.join(_REPO, "data", "packages", "installed", "tools", "ai-ops", "handler.py")


@pytest.fixture()
def aiops(monkeypatch, tmp_path):
    """ai-ops handler 를 원샷·원문추출 스텁과 함께 로드 — 모델 호출 없이 이음매만 본다."""
    seen = {}

    stub_oneshot = types.ModuleType("oneshot_facade")

    def oneshot_json(prompt, system):
        seen["prompt"] = prompt
        seen["system"] = system
        return [{"tip": "스텁 팁", "_quote": "본문 발췌"}], None

    stub_oneshot.oneshot_json = oneshot_json
    stub_oneshot.records_gate = lambda parsed: (parsed, None)
    stub_oneshot.grounded_filter = lambda records, text: (records, 0)
    stub_oneshot.mark_ai = lambda records: [{**r, "_ai": True} for r in records]
    stub_oneshot.execution_oneshot = lambda *a, **k: "스텁"

    stub_ingest = types.ModuleType("ingest_engine")

    def extract_source(path=None, text=None):
        if path:
            with open(path, encoding="utf-8") as f:
                return {"ok": True, "kind": "text", "text": f.read(), "images": None,
                        "label": os.path.basename(path)}
        return {"ok": True, "kind": "text", "text": text or "", "images": None, "label": "text"}

    stub_ingest.extract_source = extract_source

    monkeypatch.setitem(sys.modules, "oneshot_facade", stub_oneshot)
    monkeypatch.setitem(sys.modules, "ingest_engine", stub_ingest)

    spec = importlib.util.spec_from_file_location("aiops_handler_under_test", _HANDLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, seen


def _body_of(seen):
    """스텁이 받은 프롬프트에서 [원문] 본문을 꺼낸다."""
    return seen["prompt"].split("[원문]\n", 1)[1]


def test_S1_외부화_봉투는_파일_전문을_따라간다(aiops, tmp_path):
    mod, seen = aiops
    tr = tmp_path / "transcript_x.txt"
    tr.write_text("# 제목\n# Video ID: x\n\n[00:12] 첫 번째 팁은 녹음이다\n[00:34] 두 번째 팁은 변환이다\n",
                  encoding="utf-8")
    out = json.loads(mod._struct({
        "schema": "팁(tip)",
        "_prev_result": {"success": True, "saved_to_file": True, "file_path": str(tr),
                         "preview": "첫 번째", "message": "자막이 길어서 파일로 저장했습니다 ★통째로 읽지 마세요"},
    }))
    assert out.get("success") is not False
    body = _body_of(seen)
    # 전문이 갔고(두 세그먼트 모두), 안내문은 안 갔다.
    assert "첫 번째 팁은 녹음이다" in body and "두 번째 팁은 변환이다" in body
    assert "통째로 읽지 마세요" not in body
    # 타임스탬프·헤더가 걷혀 흐르는 본문 — grounded 발췌가 부분열이 될 수 있는 모양.
    assert "[00:12]" not in body and "# 제목" not in body


def test_S2_transcript_필드가_안내문을_이긴다(aiops):
    mod, seen = aiops
    json.loads(mod._struct({
        "schema": "팁(tip)",
        "_prev_result": {"success": True, "transcript": "자막 전문이다 " * 30,
                         "message": "자막을 성공적으로 가져왔습니다"},
    }))
    body = _body_of(seen)
    assert "자막 전문이다" in body and "성공적으로 가져왔습니다" not in body


def test_S3_기존_경로는_그대로다(aiops):
    """crawl 류(text=본문+items=부속) — ep1325 수리로 열린 대표 용례가 안 죽었는지."""
    mod, seen = aiops
    out = json.loads(mod._struct({
        "schema": "기록(항목)",
        "_prev_result": {"text": "본문 문단이다. " * 40, "items": [{"url": "http://x"}]},
    }))
    assert out.get("success") is not False
    assert "본문 문단이다" in _body_of(seen)
    assert "부속" in (out.get("note") or "")


def test_S4_외부화_파일이_사라졌으면_봉투_본문으로_폴백(aiops):
    """따라간 파일이 없다고 빈손 죽음이 되면 안 된다 — preview 라도 원문으로."""
    mod, seen = aiops
    out = json.loads(mod._struct({
        "schema": "팁(tip)",
        "_prev_result": {"saved_to_file": True, "file_path": "/없는/경로.txt",
                         "preview": "미리보기 본문이다 " * 20},
    }))
    # 스텁 extract_source 는 없는 파일에서 예외 — 실제 구현은 ok:false 를 낸다.
    # 어느 쪽이든 struct 가 preview 폴백 또는 정직 에러로 끝나야 한다(침묵 금지).
    assert out.get("success") is not False or out.get("error")


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
