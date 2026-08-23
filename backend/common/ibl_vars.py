"""ibl_vars.py — IBL `$변수` 참조 표기의 단일 진실 (2026-08-22)

같은 뜻의 두 표기:

    $이름            $이름.필드.경로          (맨몸)
    ${이름}          ${이름.필드.경로}        (괄호)

괄호형이 필요한 이유 — 이름 경계가 `\\w` 라서 한글에서는 조사·단위가 이름에 먹힌다.
`"$n건"` 은 변수 `n` 뒤의 글자 `건` 이 아니라 **변수 `n건`** 이다(파서·주입기·시그니처
3자가 일관되게 그렇게 읽는다). 영어는 공백이 경계를 대신 그어 주지만 한국어는 아니라서,
괄호가 경계를 사람이 직접 긋는 유일한 수단이다. `"${n}건"` = 변수 `n` + 글자 `건`.

★새 코드에서 `$` 를 직접 정규식으로 훑지 말 것. 방언이 갈리면 "파서는 아는데 시그니처는
모르는 변수" 가 생긴다 — 실제로 2026-08-22 이전에 이 파일의 자리들이 `\\w+` 와
`[^\\W\\d]\\w*` 로 갈려 있었다. 발견은 find_refs, 치환은 sub_ref/sub_refs 를 쓴다.
"""

import re
from typing import Callable, Iterable, List, Tuple

# 이름 = 파서의 `\w+` 와 같다(선행 숫자 허용 — 옛 문장 무회귀). 숫자 이름을 걸러야 하는
# 곳(시그니처)은 발견 후 이름으로 판단한다 — 표기 규칙과 정책을 섞지 않는다.
_NAME = r"\w+"
_PATH = r"(?:\.\w+)*"

# 발견용 — group: (괄호이름, 괄호경로, 맨몸이름, 맨몸경로)
REF_RE = re.compile(
    r"\$(?:\{\s*(" + _NAME + r")(" + _PATH + r")\s*\}"
    r"|(" + _NAME + r")(" + _PATH + r"))"
)

# 할당 좌변 — `$n = …` / `${n} = …`
ASSIGN_RE = re.compile(r"^\$(?:\{\s*(" + _NAME + r")\s*\}|(" + _NAME + r"))\s*=\s*(.+)$", re.DOTALL)

# 문장이 할당을 품고 있는지만 보는 값싼 판정 (번역기 힌트용)
HAS_ASSIGN_RE = re.compile(r"\$(?:\{\s*" + _NAME + r"\s*\}|" + _NAME + r")\s*=")


def split_ref(m: "re.Match") -> Tuple[str, str]:
    """REF_RE 매치에서 (이름, 경로) 를 꺼낸다. 경로는 없으면 ''."""
    if m.group(1) is not None:
        return m.group(1), (m.group(2) or "")
    return m.group(3), (m.group(4) or "")


def find_refs(text: str) -> List[Tuple[str, str]]:
    """텍스트 안의 모든 `$변수` 참조를 (이름, 경로) 목록으로. 등장 순서 유지, 중복 허용."""
    return [split_ref(m) for m in REF_RE.finditer(text or "")]


def find_names(text: str) -> List[str]:
    """참조된 변수 이름만 — 등장 순서, 중복 제거."""
    out: List[str] = []
    for name, _path in find_refs(text):
        if name not in out:
            out.append(name)
    return out


def ref_pattern(name: str) -> str:
    """이름이 정해진 변수 하나를 찾는 정규식 문자열.

    group(1)=괄호형 경로(괄호형이 아니면 None), group(2)=맨몸 경로.
    맨몸형에만 `(?!\\w)` 경계가 붙는다 — 괄호가 닫히면 경계는 이미 명시적이다."""
    n = re.escape(name)
    return (r"\$(?:\{\s*" + n + r"(" + _PATH + r")\s*\}"
            r"|" + n + r"(" + _PATH + r")(?!\w))")


def sub_ref(text: str, name: str, repl: Callable[[str], str]) -> str:
    """`$이름`/`${이름}` (경로 포함) 을 repl(경로) 결과로 치환. 경로는 '.a.b' 또는 ''."""
    def _r(m):
        path = m.group(1) if m.group(1) is not None else (m.group(2) or "")
        return repl(path)
    return re.sub(ref_pattern(name), _r, text)


def refs_pattern(names: Iterable[str]) -> str:
    """여러 이름 중 하나를 찾는 정규식 문자열.

    group: (괄호이름, 괄호경로, 맨몸이름, 맨몸경로) — REF_RE 와 같은 배치."""
    alt = "|".join(re.escape(n) for n in names)
    return (r"\$(?:\{\s*(" + alt + r")(" + _PATH + r")\s*\}"
            r"|(" + alt + r")(" + _PATH + r")(?!\w))")


def sub_refs(text: str, names: Iterable[str], repl: Callable[[str, str], str]) -> str:
    """이름 목록에 드는 참조를 repl(이름, 경로) 결과로 치환."""
    names = list(names)
    if not names:
        return text
    return re.sub(refs_pattern(names), lambda m: repl(*split_ref(m)), text)


# ★B33-2 (2026-08-23 상상훈련 33회차): 텍스트가 **자기 스코프에서** 할당하는 이름들.
#   M6 는 블록 *몸* 에 대해 이미 같은 판정을 내렸다("몸은 안쪽 파이프의 인덱스 공간 —
#   바깥 치환은 실행기가", 실측: `repeat 몸의 $n = $n + 1 이 늘 바깥 0 을 읽음`).
#   그런데 **코드를 나르는 자리는 블록 몸만이 아니다** — `[table:each]{do: "…"}`·
#   `[self:workflow]{op:"run", do: "…"}` 의 do 는 일반 step 의 param 문자열이라 그 처방을
#   못 받았고, 바깥에 같은 이름이 있으면 파서가 **할당 좌변까지** 치환해 `$n = $n + 1` 이
#   `0 = 0 + 1` 로 깨졌다(33회차 실측 4칸, 파싱 실패).
#   ★처방을 param 이름 목록(`do`·`steps`·`code`…)으로 적지 않는다 — 그런 열거는 반드시
#     뒤처진다. 판별을 **텍스트 자신**에 둔다: 스스로 할당하는 이름은 바깥이 못 덮는다
#     (모든 언어의 섀도잉 규칙). 통째 유예가 아니라 그 이름만이라 기존 용법은 안 깨진다.
INNER_ASSIGN_RE = re.compile(
    r"^[ \t]*\$(?:\{\s*(" + _NAME + r")\s*\}|(" + _NAME + r"))\s*=(?!=)", re.M)


def assigned_names(text: str) -> set:
    """텍스트(IBL 코드)가 스스로 할당하는 변수 이름 집합 — 바깥 치환의 섀도잉 판별."""
    return {(m.group(1) or m.group(2)) for m in INNER_ASSIGN_RE.finditer(text or "")}


def is_sole_ref(text: str, name: str) -> bool:
    """텍스트 전체가 **경로 없는** 그 변수 참조 하나뿐인가 — 통짜 참조(원시 타입 보존) 판정.

    경로가 붙으면(`${r.file}`) 통짜가 아니다 — 값을 그대로 돌려주면 `.file` 이 조용히
    사라진다. 경로 처리는 호출자의 규약이므로 여기서는 거짓을 돌려준다."""
    m = re.fullmatch(ref_pattern(name), text or "")
    if not m:
        return False
    path = m.group(1) if m.group(1) is not None else (m.group(2) or "")
    return not path
