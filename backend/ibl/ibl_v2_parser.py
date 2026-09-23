"""One token/Expr grammar for edition 2; no JSON/text substitution passes."""
import ast
from dataclasses import dataclass
from decimal import Decimal
import re
from ibl_v2_ir import Fault, Node


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    kind: str = "symbol"


TOKEN = re.compile(r'''(?P<space>[^\S\n]+)|(?P<comment>\#[^\n]*)|(?P<newline>\n)|(?P<string>f?"(?:\\.|[^"\\])*"|f?'(?:\\.|[^'\\])*')|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<name>[^\W\d]\w*)|(?P<op>=>|>>|\?\?|==|!=|<=|>=|&&|\|\||\*\*|[^\s])''', re.UNICODE)
PRECEDENCE = {"??": 1, ">>": 2, "&": 3, "or": 4, "||": 4,
              "and": 5, "&&": 5, "==": 6, "!=": 6, "<": 6, ">": 6,
              "<=": 6, ">=": 6, "in": 6, "+": 7, "-": 7,
              "*": 8, "/": 8, "%": 8, "**": 9}


def edition_of(source, requested=None):
    from ibl_edition import source_edition
    try:
        return source_edition(source, requested)
    except ValueError as exc:
        code, message = str(exc).split(": ", 1)
        raise Fault(code, message, kind="compile") from exc


class Parser:
    def __init__(self, source, offset=0):
        self.source = source
        self.tokens = [Token(m[0], m.start() + offset, m.end() + offset, m.lastgroup)
                       for m in TOKEN.finditer(source) if m.lastgroup not in ("space", "comment")]
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
            statements.append(self.statement())
            if self.t.text not in ("\n", ";", close):
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
            if op in (".", "["):
                if op == ".":
                    self.pop()
                    left = self.node("field", left.start, base=left, key=self.name())
                else:
                    self.pop()
                    key = self.expr()
                    self.pop("]")
                    left = self.node("index", left.start, base=left, key=key)
                continue
            if op == "(" and left.kind in ("ref", "builtin", "lambda"):
                self.pop()
                args = self.arguments(")")
                left = self.node("pure_call", left.start, fn=left, args=args)
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
        fields = {}
        self.nl()
        while self.t.text != "}":
            key = ast.literal_eval(self.pop().text) if self.t.kind == "string" else self.name()
            if not isinstance(key, str) or key in fields:
                self.fail("레코드 키는 중복 없는 문자열이어야 합니다.")
            self.pop(":")
            self.nl()
            fields[key] = self.expr()
            self.nl()
            if not self.accept(","):
                break
            self.nl()
        self.pop("}")
        return self.node("record", start, fields=fields)

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
            if self.tokens[self.i + 1].kind == "name" and self.tokens[self.i + 2].text in (":", "]"):
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
                return self.node("lambda", start, params=params, body=self.expr())
            self.i = saved + 1
            self.nl()
            value = self.expr()
            self.nl()
            self.pop(")")
            return value
        if token.kind == "name":
            self.pop()
            return self.node("builtin", start, name=text)
        self.fail(f"식을 읽을 수 없습니다: {text}")

    def format_text(self, token):
        # Scan balanced interpolation delimiters; never run a second substitution.
        raw = token.text[2:-1]
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
                parts.append(ast.literal_eval(token.text[1] + literal + token.text[1]))
                literal = ""
            begin, cursor, depth, quote = cursor + 2, cursor + 2, 1, None
            while cursor < len(raw) and depth:
                char = raw[cursor]
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
                self.fail("보간의 닫는 }가 없습니다.")
            source = raw[begin:cursor - 1]
            # `${name.field}` is the one documented shorthand for a Ref.
            if re.match(r"^[^\W\d]\w*(?:\.|\[|$)", source) and source not in ("true", "false", "null"):
                source = "$" + source
            parser = Parser(source, token.start + 2 + begin)
            value = parser.expr()
            parser.pop("<eof>")
            parts.append(value)
        if literal:
            parts.append(ast.literal_eval(token.text[1] + literal + token.text[1]))
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
        return self.node("call", start, node=name, action=action, params=params, body=body)

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
