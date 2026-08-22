r"""[self:edit] 근접 실패 진단 회귀 (2026-08-22)

ep1395·ep1393 에서 "교체할 문자열을 찾을 수 없습니다. 파일 내용을 다시 확인하세요."
가 두 번 났다. 파서 결함이 아니었다(옛·새 파서가 같은 old_string 을 낸다 — 확인함).
진짜 원인은 **AI 가 파일 모양을 잘못 짐작한 것**이고, 둘 다 *근접 실패*였다:
내용은 맞는데 들여쓰기·공백이 달랐다(ep1395 는 압축 JSON 으로 썼는데 파일은 6칸
들여쓰기). 옛 신고는 사유가 없어 매번 grep 한 번을 더 쓰게 했다.

    M1. 공백·들여쓰기만 다르면 그렇게 말하고 파일의 실제 모양을 준다
    M2. 이미 적용된 편집을 다시 걸면 그렇게 말한다
    M3. 첫 줄만 맞으면 어디서 갈렸는지 짚는다
    M4. 정말 없는 것은 옛 문구 그대로 (추측으로 오도하지 않는다)

실행: python3 backend/test_edit_miss_diagnosis.py
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

_MOD = (Path(__file__).resolve().parent.parent
        / "data/packages/installed/tools/system_essentials/fs_edit.py")
_HANDLER = _MOD.parent / "handler.py"


def _diag():
    spec = importlib.util.spec_from_file_location("fs_edit_test", _MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.miss_diagnosis


def test_m0_handler_actually_delegates():
    """M0: handler 가 이 모듈을 실제로 부르는지 — 배선이 끊기면 진단이 죽는다."""
    t = _HANDLER.read_text(encoding="utf-8")
    assert 'fs_edit' in t and 'miss_diagnosis' in t, "handler 가 fs_edit 를 안 부른다"
    assert "교체할 문자열을 찾을 수 없습니다. 파일 내용을 다시 확인하세요." not in t, \
        "handler 에 옛 고정 문구가 남아 있다(진단을 우회한다)"


# ep1395 의 실제 파일 모양(6칸 들여쓰기 pretty JSON)
ROTATION = '''{
  "built": "2026-08-10",
  "queue": [
    {
      "slug": "cheongju-ne",
      "name": "청주 상당·청원구",
      "unit": "구묶음",
      "last_visited": null,
      "visits": 0,
      "verdict": "미판정"
    }
  ]
}'''
# ep1395 가 실제로 보낸 old_string (압축 JSON)
COMPACT = ('{"slug":"cheongju-ne","name":"청주 상당·청원구","unit":"구묶음",'
           '"last_visited":null,"visits":0,"verdict":"미판정"}')


def test_m1_whitespace_only_says_so():
    msg = _diag()(ROTATION, COMPACT, "x")
    assert "공백" in msg or "들여쓰기" in msg, "근접 실패를 못 알아본다: %s" % msg
    # 파일의 실제 모양을 줘야 한다 — 그대로 복사할 수 있게
    assert '"slug": "cheongju-ne"' in msg, "실제 모양을 안 준다: %s" % msg
    assert "행부터" in msg, "어디인지 안 알려준다: %s" % msg


def test_m2_already_applied():
    content = 'IBL의 151개 액션은'
    msg = _diag()(content, 'IBL의 145개 액션은', 'IBL의 151개 액션은')
    assert "이미" in msg, "이미 적용된 편집을 못 알아본다: %s" % msg


def test_m3_first_line_matches_only():
    content = "가\n첫 줄\n실제 둘째 줄\n나"
    msg = _diag()(content, "첫 줄\n다른 둘째 줄", "x")
    assert "첫 줄은 2행" in msg, "갈린 자리를 못 짚는다: %s" % msg


def test_m4_genuinely_absent_stays_plain():
    msg = _diag()("전혀 상관없는 내용", "있지도 않은 문자열", "x")
    assert msg.endswith("파일 내용을 다시 확인하세요."), "없는 것을 있다고 추측한다: %s" % msg
    assert "공백" not in msg and "이미" not in msg, msg


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__, "-q"] + _sys.argv[1:]))
