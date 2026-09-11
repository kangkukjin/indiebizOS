"""제한된 산술 계산과 명시적인 시간 합산 검사. 의미·가정의 검수는 대체하지 않는다."""
import ast
import re

from common.value_semantics import numeric_value, values_equal

_DURATION = re.compile(r"(?:(\d+)\s*시간\s*(?:(\d+)\s*분)?|(\d+)\s*분)")


def duration_minutes(text):
    match = _DURATION.fullmatch(text.strip())
    if not match:
        return None
    hours, minutes, plain = match.groups()
    return (numeric_value(hours) or 0) * 60 + (numeric_value(minutes or plain) or 0)


def calculate(expression, values=None, unit=""):
    """계산 의미론은 기존 table 식 평가기를 사용하며 이 표면은 사칙연산으로 제한한다."""
    from common.safe_expr import compile_expr, eval_expr
    if not isinstance(expression, str) or not 1 <= len(expression) <= 600:
        raise ValueError("expression은 1~600자 산술식이어야 합니다")
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.UAdd, ast.USub)
    if len(nodes) > 120 or any(not isinstance(n, allowed) for n in nodes):
        raise ValueError("사칙연산·괄호·숫자 변수만 허용합니다")
    values = values or {}
    if not isinstance(values, dict) or len(values) > 30:
        raise ValueError("values는 30개 이하 숫자 변수입니다")
    observed = {k: numeric_value(v) for k, v in values.items()}
    constants = [numeric_value(n.value) for n in nodes if isinstance(n, ast.Constant)]
    if any(v is None or abs(v) > 10**18 for v in [*observed.values(), *constants]):
        raise ValueError("유한한 숫자만 계산할 수 있습니다")
    code, names, _ = compile_expr(expression)
    if any(n not in observed for n in names):
        raise ValueError("식에서 사용한 변수의 값이 없습니다")
    result = eval_expr(code, observed)
    if numeric_value(result) is None or abs(result) > 10**18:
        raise ValueError("결과가 계산 범위를 벗어났습니다")
    out = {"expression": expression, "values": observed, "value": result, "unit": unit}
    if unit == "minutes" and result >= 0 and values_equal(result % 1, 0):
        out["duration"] = f"{int(result // 60)}시간 {int(result % 60)}분"
    return out


def arithmetic_issues(text):
    """명시된 정확한 합산만 거절한다. 근사·범위·일정의 숨은 가정을 추측하지 않는다."""
    issues = []
    for paragraph in re.split(r"\n\s*\n|(?<=[.!?])\s+", text or ""):
        plain = re.sub(r"\([^)]*\)", "", paragraph).replace("*", "")
        # 예: '4시간 45분, 45분까지 더하면 ... 5시간 15분'. 단위가 있는 두 항의 합.
        parts = re.split(r"(?:까지\s*)?더하면", plain, maxsplit=1)
        if len(parts) != 2:
            continue
        before, after = parts
        terms = list(_DURATION.finditer(before))
        outputs = list(_DURATION.finditer(after))
        if len(terms) != 2 or not outputs or re.search(r"약|이상|이하|이내|정도|여유", plain):
            continue
        expected = calculate("a+b", {"a": duration_minutes(terms[0][0]),
                                     "b": duration_minutes(terms[1][0])}, "minutes")
        observed = duration_minutes(outputs[0][0])
        if not values_equal(expected["value"], observed):
            issues.append({"quote": paragraph, "expected": expected,
                           "claimed_minutes": observed})
    return issues


def duration_table(text):
    return [{"text": token, "minutes": duration_minutes(token)}
            for token in dict.fromkeys(m[0] for m in _DURATION.finditer(text or ""))][:40]
