"""IBL 문자열 경계의 공통 스캔. 값을 해석하거나 원문을 다시 쓰지 않는다.

괄호의 종류·오류·JSON5 주석 허용은 각 문법 소비자가 결정한다.
"""
from dataclasses import dataclass


def quoted_end(text, start, quote):
    """따옴표 뒤 start부터 스캔해 (닫힘 직후 위치, 닫혔는지)를 반환한다."""
    i = start
    while i < len(text):
        char = text[i]
        if char == '\\':
            i += 2
        elif char == quote:  # vj-ok: 렉서 인용부호 경계
            return i + 1, True
        else:
            i += 1
    return len(text), False


@dataclass
class QuoteState:
    in_string: bool = False
    quote: str | None = None

    def outside(self, text, start=0, *, hash_comments=False):
        """문자열 밖의 (원문 위치, 문자)를 순회한다. 미닫힘 상태는 다음 줄에 승계한다.

        hash_comments일 때 # 자체는 내보내고 주석 본문만 건너뛴다. 따라서
        주석 제거와 깊이 관측은 같은 경계를 쓰면서 원문 슬라이스를 유지한다.
        """
        i = start
        while i < len(text):
            if self.in_string:
                i, closed = quoted_end(text, i, self.quote)
                if closed:
                    self.in_string, self.quote = False, None
                continue
            char = text[i]
            if char in '\"\'':
                self.in_string, self.quote = True, char
                i += 1
                continue
            yield i, char
            if hash_comments and char == '#':
                end = text.find('\n', i)
                i = len(text) if end < 0 else end
            else:
                i += 1


def split_operator(text, operator):
    """문자열·중괄호·괄호 분기 밖에서 분리해 (본문, 뒤 연산자)를 반환한다."""
    segments = []
    depth = paren = start = consumed = 0
    for i, char in QuoteState().outside(text):
        if i < consumed:
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        elif char == '(' and depth == 0:
            paren += 1
        elif char == ')' and depth == 0:
            paren = max(0, paren - 1)
        elif depth == 0 and paren == 0 and text.startswith(operator, i):
            # 기존 && 처리도 유지: 첫 &는 분리하지 않고 다음 문자에서 계속 읽는다.
            if operator == '&' and text.startswith('&&', i):
                continue
            segment = text[start:i].strip()
            if segment:
                segments.append((segment, operator))
            start = consumed = i + len(operator)
    segment = text[start:].strip()
    if segment:
        segments.append((segment, None))
    return segments


def source_heads(text):
    """문자열·주석 밖의 호출 머리. 실행 횟수가 아닌 작성된 구문을 센다.

    SQL/보고서 속 [fn:] 예시와 인자 객체의 데이터는 호출이 아니다. 지연 do 문자열도
    이 지표에는 포함하지 않는다. 실제 분기·반복 횟수는 실행 원장에서 읽어야 한다.
    """
    import re
    visible = [' '] * len(text)
    for pos, char in QuoteState().outside(text, hash_comments=True):
        visible[pos] = char
    return re.findall(r'\[([a-z_]+):\s*([^\]\s]+)\]', ''.join(visible))
