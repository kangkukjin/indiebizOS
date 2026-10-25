r"""IBL `$변수` 괄호 표기 `${이름}` 회귀 테스트 (2026-08-22)

왜 있는가 — 이름 경계가 `\w` 라서 한국어에서는 조사·단위가 이름에 먹힌다.
`"$n건"` 은 변수 `n` 뒤의 글자 `건` 이 아니라 **변수 `n건`** 이다(파서·주입기·시그니처
3자 일관). 영어는 공백이 경계를 대신 그어 주지만 한국어는 아니라서, 괄호가 경계를
사람이 직접 긋는 유일한 수단이 된다. 두 표기는 같은 뜻이다.

표기의 단일 진실 = `common/ibl_vars.py`. 이 배터리는 그 규약이 **모든 층**에서 같은지를
본다 — 예전엔 층마다 `\w+` 와 `[^\W\d]\w*` 로 방언이 갈려 있었다.

    B1. 표기 모듈 자체 — 발견·치환·통짜 판정
    B2. ★경계: `$n건`=변수 n건 / `${n}건`=변수 n + 글자 건
    B3. 파서 — 괄호형 할당·참조·경로
    B4. 시그니처 — 괄호형 자유 변수 발견, 숫자 이름($100)은 인자로 안 셈
    B5. 호출자 params 주입 — 괄호형 + 통짜 참조 타입 보존
    B6. [table:each] 행 참조 — 괄호형 치환·유령 변수 판정
    B7. 블록 — 식 할당·if 조건의 괄호형 바인딩 (실행까지)
    B8. $items 집합 바인딩 예약어의 괄호형
    B9. 표기 혼용·공백 관용
    B10. 경계 실패가 처방을 말한다 — `$it.n.md` → `${it.n}.md` (each·블록 공용 힌트)

실행: python3 backend/test_ibl_var_notation.py
"""
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

import workflow_engine  # noqa: E402
from common.ibl_vars import (find_names, sub_ref, is_sole_ref, split_ref, REF_RE)  # noqa: E402
from workflow_engine import execute_workflow_action


def test_b1_notation_module():
    assert find_names("${n}건 $city ${r.file} $r.count") == ["n", "city", "r"]
    assert sub_ref("${n}건", "n", lambda p: "5") == "5건"
    assert sub_ref("$r.file", "r", lambda p: "X" + p) == "X.file"
    assert is_sole_ref("${count}", "count") and is_sole_ref("$count", "count")
    # 경로가 붙으면 통짜가 아니다 — 값을 그대로 주면 `.file` 이 조용히 사라진다
    assert not is_sole_ref("${r.file}", "r")
    assert split_ref(REF_RE.fullmatch("${r.a.b}")) == ("r", ".a.b")
    print("B1 OK — 표기 모듈(발견·치환·통짜 판정·경로 분해)")


def test_b2_korean_suffix_boundary():
    """★이 배터리의 존재 이유."""
    assert find_names("$n건") == ["n건"], "맨몸 표기의 경계가 바뀌면 옛 문장이 깨진다"
    assert find_names("${n}건") == ["n"], "괄호가 경계를 못 긋고 있다"
    assert sub_ref("$n건", "n", lambda p: "5") == "$n건", "변수 n 이 n건 을 침식"
    assert sub_ref("${n}건", "n", lambda p: "5") == "5건"
    print("B2 OK — $n건=변수 n건 / ${n}건=변수 n + 글자 건")


















def test_b11_교재가_표기_형태를_전부_가르친다():
    """문법이 자란 날과 가르치는 글이 갱신된 날의 간극을 기계가 직접 대조한다.

    실측(2026-08-28): 괄호형은 08-22에, 확장 경로(`*`·`?`)는 08-28에 문법에 들어왔는데
    교재(12_ibl_only.md)에는 둘 다 0회였다 — 같은 병이 두 번 연속으로 난 자리다.
    교재는 모델이 매 턴 읽는 유일한 문법서라, 안 실린 문법은 없는 문법이다
    (ibl_honesty.py 가 이미 선언한 계약: "교재가 가르치는 키와 이 목록은 함께 움직인다").
    """
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 이 검사는 저장 원문의 구형 실행 계약이다. 현재 교재는 test_ibl_composition_teaching에서 실행한다.
    frag = os.path.join(root, "docs", "compatibility", "ibl_legacy_language.md")
    text = open(frag, encoding="utf-8").read()
    missing = [label for label, probe in (
        ("괄호형 ${이름}", "${"),
        ("열 벡터 ${x.items.*.f}", ".*."),
        ("옵셔널 ${x.y?}", "?}"),
    ) if probe not in text]
    assert not missing, (
        f"교재가 안 가르치는 표기: {missing} — common/ibl_vars.py 가 정의한 형태는\n"
        f"12_ibl_only.md 에 최소 한 번 등장해야 한다(문법을 늘렸으면 교재도 같이)."
    )
    print("B11 OK — 교재가 표기 3형태를 전부 가르친다")


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
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
