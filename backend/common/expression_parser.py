"""One token/Expr grammar for edition 2; no JSON/text substitution passes."""
import ast
from dataclasses import dataclass
from decimal import Decimal
import re
from common.expression_ir import Fault, Node


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    kind: str = "symbol"


TOKEN = re.compile('(?P<space>[^\\S\\n]+)|(?P<comment>\\#[^\\n]*)|(?P<newline>\\n)|(?P<string>f?"""(?:\\\\[\\s\\S]|(?!""")[^\\\\])*"""|f?\\\'\\\'\\\'(?:\\\\[\\s\\S]|(?!\\\'\\\'\\\')[^\\\\])*\\\'\\\'\\\'|f?"(?:\\\\.|[^"\\\\])*"|f?\'(?:\\\\.|[^\'\\\\])*\')|(?P<number>\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)|(?P<name>[^\\W\\d]\\w*)|(?P<op>=>|>>|\\?\\?|==|!=|<=|>=|&&|\\|\\||\\*\\*|//|[^\\s])', re.UNICODE)
PRECEDENCE = {"??": 1, ">>": 2, "&": 3, "or": 4, "||": 4,
              "and": 5, "&&": 5, "==": 6, "!=": 6, "<": 6, ">": 6,
              "<=": 6, ">=": 6, "in": 6, "+": 7, "-": 7,
              "*": 8, "/": 8, "//": 8, "%": 8, "**": 9}


def edition_of(source, requested=None):
    from ibl_edition import source_edition
    try:
        return source_edition(source, requested)
    except ValueError as exc:
        code, message = str(exc).split(": ", 1)
        raise Fault(code, message, kind="compile") from exc


# 조건 값 `조건 ? 값1 : 값2`(언어 개정 2026-09-29, 사용자 판정 — 상상훈련 73회차 G73-1). `or`(4)와 같은
# 층에서 오른쪽으로 묶는다: `a or b ? x : y` = `(a or b) ? x : y`, `c1 ? "A" : c2 ? "B" : "C"` 는 가지 사슬.
# `>>`·`&`·`??` 보다 강하게 묶어 `c ? $a : $b >> [t:x]` 는 고른 값을 파이프로 넘긴다.
TERNARY = 4

# 줄 머리에 오면 앞 식의 계속으로 읽는 연산자(언어 개정 2026-09-26, 사용자 판정). 4083 실측: 여러 줄 병렬
# `A\n& B\n& C` 가 SYNTAX 로 거절됐다 — 문장을 시작할 수 없는 연산자이므로 줄바꿈이 분리자일 수 없다.
# `?` 도 문장을 시작할 수 없다(조건 값의 여러 줄 표기, 2026-09-29).
CONTINUATION = {"&", ">>", "??", "?"}
# 끝이 `}`로 닫히는 제어 블록 문장 — 뒤에 구분자 없이 다음 문장이 올 수 있다.
BLOCK_STATEMENTS = {"if", "case", "repeat", "def", "try"}


class Parser:
    def __init__(self, source, offset=0, *, interpolation=False):
        self.interpolation = interpolation
        self.source = source
        raw = [Token(m[0], m.start() + offset, m.end() + offset, m.lastgroup)
               for m in TOKEN.finditer(source) if m.lastgroup not in ("space", "comment")]
        for token in raw:
            if (token.kind == "string" and not token.text.startswith("f")
                    and not token.text.startswith((chr(34) * 3, chr(39) * 3))
                    and ("\n" in token.text or "\r" in token.text)):
                raise Fault("STRING_LITERAL", "일반 문자열의 줄바꿈은 \\n 이스케이프 또는 삼중 따옴표를 사용하세요.",
                            Node("token", token.start, token.end), kind="compile")
        self.tokens = []
        for idx, tok in enumerate(raw):
            if tok.text == "\n":
                j = idx + 1
                while j < len(raw) and raw[j].text == "\n":
                    j += 1
                if j < len(raw) and raw[j].kind == "op" and raw[j].text in CONTINUATION:
                    continue
            self.tokens.append(tok)
        self.tokens.append(Token("<eof>", len(source) + offset, len(source) + offset))
        self.i = 0

    @property
    def t(self):
        return self.tokens[self.i]

    def fail(self, message):
        raise Fault("SYNTAX", message, Node("token", self.t.start, self.t.end), kind="compile")

    def pop(self, text=None):
        token = self.t
        if text is not None and token.text != text:
            self.fail(f"'{text}'가 필요합니다: {token.text}")
        self.i += 1
        return token

    def accept(self, text):
        if self.t.text == text:
            return self.pop()
        return None

    def nl(self):
        while self.t.text == "\n":
            self.pop()

    def node(self, kind, start, **data):
        return Node(kind, start, self.tokens[self.i - 1].end, data)

    def program(self, close="<eof>"):
        start, statements = self.t.start, []
        self.nl()
        while self.t.text != close:
            if self.t.text == "<eof>":
                self.fail(f"닫는 {close}가 없습니다.")
            # A signed value on a new statement used to be silently discarded
            # after a binding, although it looked like a continued sum.
            if (statements and self.t.text in {"+", "-", "*", "/", "//", "%", "**"}
                    and self.tokens[self.i - 1].text == "\n"):
                self.fail("줄 첫 산술 연산자는 앞 식의 계속이 아닙니다. "
                          "연산자를 앞줄 끝에 두세요($합 = 1 +\\n  2). "
                          "독립된 부호 값은 return -2 또는 ; -2처럼 명시하세요.")
            statement = self.statement()
            statements.append(statement)
            if self.t.text in ("else", "elif", "catch", "finally"):
                # 다른 언어의 맨 낱말 가지는 예측 가능한 실수다 — 고치는 형태를 말한다 (71회차 T13).
                fix = "[else] { [if:조건] {...} }" if self.t.text == "elif" else f"[{self.t.text}] {{ ... }}"
                self.fail(f"'{self.t.text}' 가지는 대괄호 표지로 씁니다: {fix}")
            # 제어 블록은 `}`에서 끝난다 — 같은 줄의 다음 문장과 헷갈릴 것이 없다(긴문장 9·10회차 SYNTAX 3회).
            block_end = statement.kind in BLOCK_STATEMENTS and self.tokens[self.i - 1].text == "}"
            if self.t.text not in ("\n", ";", close) and not block_end:
                self.fail("문장 사이에는 줄바꿈 또는 ;이 필요합니다.")
            while self.t.text in ("\n", ";"):
                self.pop()
        return self.node("sequence", start, statements=statements)

    def block(self):
        self.pop("{")
        body = self.program("}")
        self.pop("}")
        return body

    def statement(self):
        start = self.t.start
        if self.t.text == "assert":
            self.pop()
            condition = self.expr()
            message = self.expr() if self.accept(",") else None
            details = self.expr() if self.accept(",") else None
            return self.node("assert", start, condition=condition, message=message, details=details)
        if self.t.text == "return":
            self.pop()
            value = None if self.t.text in ("\n", ";", "}", "<eof>") else self.expr()
            return self.node("return", start, value=value)
        if self.t.text == "$" and self.tokens[self.i + 2].text == "=":
            self.pop()
            name = self.name()
            self.pop("=")
            self.nl()
            return self.node("bind", start, name=name, value=self.expr())
        return self.expr()

    def name(self):
        if self.t.kind != "name":
            self.fail("이름이 필요합니다.")
        return self.pop().text

    def expr(self, minimum=0):
        left = self.primary()
        while True:
            op = self.t.text
            if op in (".", "[") and left.kind in BLOCK_STATEMENTS:
                break  # 제어 블록 뒤의 `[`는 그 값의 인덱싱이 아니라 다음 문장이다.
            if op in (".", "["):
                if op == ".":
                    self.pop()
                    if self.t.kind != "name":
                        # `$x.9월` — 숫자로 시작하거나 기호가 든 필드 이름은 점 접근의 이름이 아니다(76회차 T04·F72-2).
                        self.fail(f"필드 이름이 필요합니다: '{self.t.text}'. 목록 위치는 $값[0], 숫자로 시작하거나 "
                                  f"기호가 든 필드는 get($값, \"필드\", null) 또는 $값[\"필드\"]로 읽으세요.")
                    left = self.node("field", left.start, base=left, key=self.name())
                else:
                    self.pop()
                    key = None if self.t.text == ":" else self.expr()
                    if self.accept(":"):
                        stop = None if self.t.text in (":", "]") else self.expr()
                        step = None
                        if self.accept(":"):
                            step = None if self.t.text == "]" else self.expr()
                        self.pop("]")
                        left = self.node("slice", left.start, base=left, lower=key, upper=stop, stride=step)
                    else:
                        self.pop("]")
                        left = self.node("index", left.start, base=left, key=key)
                continue
            if op == "(" and left.kind in ("ref", "builtin", "lambda"):
                self.pop()
                args = self.arguments(")")
                left = self.node("pure_call", left.start, fn=left, args=args)
                continue
            if op == "?" and minimum <= TERNARY:
                self.pop()
                self.nl()
                yes = self.expr(TERNARY)
                self.nl()
                if self.t.text != ":":
                    if self.t.text in (">>", "&", "??"):
                        raise Fault("PURE_EXPRESSION", "조건 값의 가지에는 순수 식만 씁니다. "
                                    "호출 결과를 먼저 $이름=[...]으로 받거나 [if] 블록을 쓰세요.",
                                    Node("token", self.t.start, self.t.end), kind="compile")
                    self.fail("조건 값은 `조건 ? 참일 때 값 : 거짓일 때 값` 형태입니다. ':'가 필요합니다.")
                self.pop()
                self.nl()
                no = self.expr(TERNARY)
                left = self.node("conditional", left.start, condition=left, yes=yes, no=no)
                continue
            priority = PRECEDENCE.get(op, -1)
            if priority < minimum:
                break
            self.pop()
            self.nl()
            right = self.expr(priority if op == "**" else priority + 1)
            kind = {">>": "pipe", "&": "parallel", "??": "fallback"}.get(op, "binary")
            left = self.node(kind, left.start, op=op, left=left, right=right)
        return left

    def arguments(self, close):
        self.nl()
        out = []
        while self.t.text != close:
            out.append(self.expr())
            self.nl()
            if not self.accept(","):
                break
            self.nl()
        self.pop(close)
        return out

    def record(self):
        start = self.pop("{").start
        fields, entries, has_spread = {}, [], False
        self.nl()
        while self.t.text != "}":
            if self.accept("**"):
                entries.append((None, self.expr()))
                has_spread = True
            else:
                if self.t.kind == "number":
                    # 1면·3월처럼 숫자로 시작하는 업무 키는 흔하다 — 고치는 법을 오류가 말한다(70회차 F70-3).
                    after = self.tokens[self.i + 1]
                    text = self.t.text + (after.text if after.kind == "name" and after.start == self.t.end else "")
                    self.fail(f'레코드 키는 이름이나 따옴표 문자열입니다. 숫자로 시작하는 키는 따옴표로 쓰세요: {{"{text}": …}}')
                if self.t.text == "[":
                    # {[$k]: 값} — 값으로 정한 키는 문법에 없다(긴문장 33회차 L33-1). 고치는 법을 오류가 말한다.
                    self.fail("레코드 키는 이름이나 따옴표 문자열입니다. 값으로 정한 키({[$k]: …})는 지원하지 않습니다 — "
                              "from_entries([[$k, 값]])로 만들거나 {key:$k, value:…} 행 목록으로 두세요. "
                              "레코드는 keys/values/entries 로 읽으세요.")
                key = ast.literal_eval(self.pop().text) if self.t.kind == "string" else self.name()
                if not isinstance(key, str) or key in fields:
                    self.fail("레코드 키는 중복 없는 문자열이어야 합니다.")
                self.pop(":")
                self.nl()
                fields[key] = self.expr()
                entries.append((key, fields[key]))
            self.nl()
            if not self.accept(","):
                break
            self.nl()
        self.pop("}")
        return self.node("record", start, fields=fields, **({"entries": entries} if has_spread else {}))

    def primary(self):
        token = self.t
        start, text = token.start, token.text
        if text in ("-", "+", "!", "not"):
            self.pop()
            return self.node("unary", start, op=text, value=self.expr(9))
        if text == "$":
            self.pop()
            return self.node("ref", start, name=self.name())
        if token.kind == "number":
            self.pop()
            value = Decimal(text) if any(c in text for c in ".eE") else int(text)
            return self.node("literal", start, value=value)
        if token.kind == "string":
            self.pop()
            if text.startswith("f"):
                return self.format_text(token)
            return self.node("literal", start, value=ast.literal_eval(text))
        if text in ("true", "false", "null"):
            self.pop()
            return self.node("literal", start, value={"true": True, "false": False, "null": None}[text])
        if text == "{":
            return self.record()
        if text == "[":
            head, following = self.tokens[self.i + 1:self.i + 3]
            # Only try is a standalone colon-free control head here.
            # A singleton literal/builtin is still a list, just like [1].
            if head.kind == "name" and (following.text == ":" or
                                         (head.text == "try" and following.text == "]")):
                return self.call_or_control()
            self.pop()
            return self.node("list", start, values=self.arguments("]"))
        if text == "(":
            saved = self.i
            self.pop()
            params = []
            while self.accept("$"):
                params.append(self.name())
                if not self.accept(","):
                    break
            if self.accept(")") and self.accept("=>"):
                self.nl()
                return self.node("lambda", start, params=params, body=self.expr())
            self.i = saved + 1
            self.nl()
            value = self.expr()
            self.nl()
            self.pop(")")
            return value
        if token.kind == "name":
            self.pop()
            return self.node("ref" if self.interpolation and self.t.text != "(" else "builtin", start, name=text)
        if text in ("**", "*"):
            self.fail(f"식을 읽을 수 없습니다: {text}. 목록 펼침은 없습니다 — 목록은 $a + [값]으로 잇고, "
                      "레코드는 {**$r, 키:값}으로 펼칩니다.")
        self.fail(f"식을 읽을 수 없습니다: {text}")

    def format_text(self, token):
        # Scan balanced interpolation delimiters; never run a second substitution.
        quoted = token.text[1:]
        delimiter = quoted[:3] if quoted.startswith((chr(34) * 3, chr(39) * 3)) else quoted[:1]
        prefix = 1 + len(delimiter)
        raw = quoted[len(delimiter):-len(delimiter)]
        parts, cursor, literal = [], 0, ""
        while cursor < len(raw):
            if raw[cursor:cursor + 2] != "${":
                if raw[cursor] == "\\" and cursor + 1 < len(raw):
                    literal += raw[cursor:cursor + 2]
                    cursor += 2
                else:
                    literal += raw[cursor]
                    cursor += 1
                continue
            if literal:
                parts.append(ast.literal_eval(delimiter + literal + delimiter))
                literal = ""
            begin, cursor, depth, quote = cursor + 2, cursor + 2, 1, None
            while cursor < len(raw) and depth:
                char = raw[cursor]
                if not quote and char == "\\" and cursor + 1 < len(raw) and raw[cursor + 1] in "\"'":
                    self.fail("보간식 안의 이스케이프 따옴표는 해석할 수 없습니다. 바깥과 다른 따옴표 또는 삼중 따옴표를 사용하세요.")
                if quote:
                    if char == "\\":
                        cursor += 2
                        continue
                    if char == quote:
                        quote = None
                elif char in "\"'":
                    quote = char
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                cursor += 1
            if depth:
                self.fail("보간의 닫는 }가 없거나 안쪽 따옴표가 바깥 문자열을 닫았습니다. }를 확인하고 안쪽에는 다른 따옴표 또는 바깥에 삼중 따옴표를 사용하세요.")
            source = raw[begin:cursor - 1]
            parser = Parser(source, token.start + prefix + begin, interpolation=True)
            value = parser.expr()
            parser.pop("<eof>")
            parts.append(value)
        if literal:
            parts.append(ast.literal_eval(delimiter + literal + delimiter))
        return Node("format", token.start, token.end, {"parts": parts})

    def call_or_control(self):
        start = self.pop("[").start
        name = self.name()
        if name == "def":
            self.pop(":")
            fn = self.name()
            self.pop("]")
            self.pop("(")
            params = {}
            self.nl()
            while self.t.text != ")":
                self.pop("$")
                p = self.name()
                if p in params:
                    self.fail("중복 함수 인자입니다.")
                params[p] = self.expr() if self.accept("=") else None
                if not self.accept(","):
                    break
                self.nl()
            self.pop(")")
            self.nl()
            return self.node("def", start, name=fn, params=params, body=self.block())
        if name in ("if", "case", "repeat"):
            self.pop(":")
            mode = self.pop().text if name == "repeat" and self.t.text in ("while", "until") else "count"
            self.accept(":") if mode != "count" else None
            value = self.expr()
            self.pop("]")
            self.nl()
            if name == "case":
                self.pop("{")
                self.nl()
                branches, otherwise = [], None
                while self.t.text != "}":
                    self.pop("[")
                    label = self.name()
                    if label == "when":
                        self.pop(":")
                        condition = self.expr()
                        self.pop("]")
                        self.nl()
                        branches.append((condition, self.block()))
                    elif label == "else" and otherwise is None:
                        self.pop("]")
                        self.nl()
                        otherwise = self.block()
                    else:
                        self.fail("case에는 [when:식]과 하나의 [else]를 씁니다.")
                    self.nl()
                self.pop("}")
                return self.node("case", start, value=value, branches=branches, otherwise=otherwise)
            body = self.block()
            otherwise = self.attached("else") if name == "if" else None
            return self.node(name, start, value=value, body=body, otherwise=otherwise, mode=mode)
        if name == "try":
            self.pop("]")
            self.nl()
            body = self.block()
            catch, final = self.attached("catch"), self.attached("finally")
            if catch is None and final is None:
                self.fail("try에는 catch 또는 finally가 필요합니다.")
            return self.node("try", start, body=body, catch=catch, final=final)
        self.pop(":")
        action = self.name()
        self.pop("]")
        has_record = self.t.text == "{"
        if has_record and name == "table" and action == "each":
            j = self.i + 1
            while self.tokens[j].text == "\n":
                j += 1
            if self.tokens[j].text == "}":
                after = j + 1
                while self.tokens[after].text == "\n":
                    after += 1
                has_record = self.tokens[after].text == "{"
            else:
                has_record = self.tokens[j + 1].text == ":"
        params = self.record() if has_record else Node("record", start, self.tokens[self.i - 1].end, {"fields": {}})
        body = None
        if name == "table" and action == "each":
            self.nl()
            body = self.block()
        # 노드 지정 `[node:action]{…}@별칭`(판본 1 문법의 이월, 2026-10-05 표면 바인딩 ① 잔여): 이 호출을 어느 몸에서
        # 실행할지(@hub=주 컴퓨트 노드, @폰2 …). 값 자리의 @(이메일 등)와 충돌하지 않는다 — 인자 블록 밖, 호출 직후만.
        target = None
        if self.t.text == "@" and self.tokens[self.i + 1].kind == "name":
            self.pop()
            target = self.name()
        return self.node("call", start, node=name, action=action, params=params, body=body,
                         **({"target": target} if target else {}))

    def attached(self, name):
        saved = self.i
        self.nl()
        if self.t.text == "[" and self.tokens[self.i + 1].text == name:
            self.pop("[")
            self.pop(name)
            self.pop("]")
            self.nl()
            return self.block()
        self.i = saved
        return None


def parse(source):
    try:
        return Parser(source).program()
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise Fault("SYNTAX", str(exc), kind="compile") from exc
