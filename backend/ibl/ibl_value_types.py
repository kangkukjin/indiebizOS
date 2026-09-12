"""IBL 값의 구조: 표시 문자열과 분리된 직렬화 가능한 형, 실제 값에서의 보수적 추론.

cols는 행의 열, envelope는 그 행을 담은 바깥 객체다. 병렬 분기를 행과 혼동하지 않는다.
관측 예산을 넘긴 하위 구조는 unknown으로 남긴다. 값·세계의 필드 이름을 코드에 넣지 않는다.
"""
import json

KINDS = ("items", "prose", "scalar", "effect", "bundle", "unknown")


class T:
    __slots__ = ("kind", "cols", "closed", "branches", "conditional", "fields", "envelope", "empty")

    def __init__(self, kind="unknown", cols=None, closed=False, branches=None,
                 conditional=False, fields=None, envelope=None, empty=False):
        self.kind = kind if kind in KINDS else "unknown"
        self.cols = list(dict.fromkeys(cols)) if cols is not None else None
        self.closed = bool(closed) if cols is not None else False
        self.branches = list(branches or [])
        self.conditional = bool(conditional)
        self.fields = dict(fields or {})
        self.envelope = envelope
        self.empty = bool(empty)

    def copy(self, **kw):
        t = T(self.kind, self.cols, self.closed, self.branches, self.conditional,
              self.fields, self.envelope, self.empty)
        for key, value in kw.items():
            setattr(t, key, value)
        return t

    def __repr__(self):
        return describe(self)

    def to_data(self):
        out = {"kind": self.kind, "cols": self.cols, "closed": self.closed}
        for key in ("conditional", "empty"):
            if getattr(self, key):
                out[key] = True
        if self.branches:
            out["branches"] = [t.to_data() for t in self.branches]
        if self.fields:
            out["fields"] = {key: t.to_data() for key, t in self.fields.items()}
        if self.envelope is not None:
            out["envelope"] = self.envelope.to_data()
        return out

    @classmethod
    def from_data(cls, data, depth=0):
        if not isinstance(data, dict) or depth > 12:
            return cls()
        cols = data.get("cols")
        if cols is not None and (not isinstance(cols, list) or not all(isinstance(c, str) for c in cols)):
            return cls()
        return cls(data.get("kind"), cols, data.get("closed", False),
                   [cls.from_data(v, depth + 1) for v in data.get("branches", [])],
                   data.get("conditional", False),
                   {k: cls.from_data(v, depth + 1) for k, v in data.get("fields", {}).items()},
                   cls.from_data(data["envelope"], depth + 1) if data.get("envelope") else None,
                   data.get("empty", False))


def unknown():
    return T()


def describe(t):
    if t is None:
        return "?"
    if t.kind == "items":
        if t.cols:
            body = "·".join(t.cols[:10]) + ("·…" if len(t.cols) > 10 or not t.closed else "")
            return f"items⟨{body}⟩"
        return "items⟨열 미상⟩"
    if t.kind == "bundle":
        return "bundle[" + ", ".join(describe(b) for b in t.branches[:12]) + (", …" if len(t.branches) > 12 else "") + "]"
    return "?" if t.kind == "unknown" else t.kind


def decode(value):
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def merge_rows(types):
    """이미 존재하는 행들의 합집합. 모르는 행이 있으면 열을 닫지 않는다."""
    if not types:
        return T("items", [], closed=True, empty=True)
    cols = list(dict.fromkeys(c for t in types for c in (t.cols or [])))
    fields = {}
    for key in cols:
        children = [t.fields[key] for t in types if key in t.fields]
        if children:
            fields[key] = merge_values(children)
    return T("items", cols or None, closed=all(t.closed for t in types), fields=fields,
             empty=all(t.empty for t in types))


def merge_values(types):
    if not types or len({t.kind for t in types}) != 1:
        return unknown()
    if types[0].kind in ("items", "scalar") and any(t.cols is not None for t in types):
        merged = merge_rows(types)
        return merged.copy(kind=types[0].kind)
    return types[0].copy() if len(types) == 1 else T(types[0].kind)


def infer_value(value):
    """전체 값에서 형을 얻는다. 큰/깊은 값은 제한 안에서만 확정하며 표본을 닫힌 형으로 만들지 않는다."""
    budget = [20000]

    def walk(v, depth=0, currency=False):
        budget[0] -= 1
        if budget[0] < 0 or depth > 6:
            return unknown()
        if currency:
            v = decode(v)
        if isinstance(v, list):
            if len(v) > budget[0]:
                return T("items")
            decoded = [decode(row) for row in v] if currency else v
            if currency and decoded and all(isinstance(row, (dict, list)) for row in decoded) and (
                    any(isinstance(row, str) for row in v) or
                    all(isinstance(row, dict) and isinstance(row.get("items"), list) for row in decoded)):
                branches = [walk(row, depth + 1, True) for row in decoded]
                return T("bundle", branches=branches)
            rows = [walk(row, depth + 1) for row in decoded]
            if any(not isinstance(row, dict) for row in decoded):
                return T("items")
            return merge_rows(rows)
        if isinstance(v, dict):
            if len(v) > 200 or any(not isinstance(k, str) for k in v):
                return unknown()
            fields = {k: walk(z, depth + 1) for k, z in v.items()}
            envelope = T("scalar", list(v), closed=True, fields=fields)
            if currency and isinstance(v.get("items"), list):
                return fields["items"].copy(envelope=envelope)
            if currency and isinstance(v.get("table"), dict):
                table = v["table"]
                if isinstance(table.get("columns"), list):
                    return T("items", table["columns"], closed=True, envelope=envelope,
                             empty=not table.get("rows"))
            return envelope.copy(envelope=envelope) if currency else envelope
        return T("scalar")

    return walk(value, currency=True)


def bundle_rows(t):
    """단항 변환자가 실제로 받는 것은 각 분기의 바깥 봉투다."""
    if t.kind != "bundle":
        return t
    return merge_rows([b.envelope or unknown() for b in t.branches])


def display_type(t, depth=0, omit_items=False):
    """다음 문장을 작성할 때 필요한 구조만 표시한다. 저장 형의 무손실 직렬화와 별개다."""
    out = {"type": t.kind}
    if t.cols is not None:
        out.update(columns=t.cols[:40], closed=t.closed)
        if len(t.cols) > 40:
            out["columns_omitted"] = len(t.cols) - 40
    if depth < 3:
        nested = {k: display_type(v, depth + 1) for k, v in t.fields.items()
                  if (v.cols is not None or v.branches) and not (omit_items and k == "items")}
        if nested:
            out["nested"] = nested
        if t.envelope is not None:
            out["envelope"] = display_type(t.envelope, depth + 1, omit_items=True)
        if t.branches:
            groups = []
            for branch in t.branches:
                shape = display_type(branch, depth + 1)
                if groups and groups[-1]["shape"] == shape:
                    groups[-1]["count"] += 1
                else:
                    groups.append({"count": 1, "shape": shape})
            out["branches"] = groups[:8]
            out["branch_count"] = len(t.branches)
            if len(groups) > 8:
                out["branch_groups_omitted"] = len(groups) - 8
    return out


def declared_type(definition, params):
    """사전이 보장한 출력 구조. 동적 변이 축에는 기본/다른 소스의 열을 빌려주지 않는다."""
    shape = definition.get("result_shape")
    for key, variant in definition.get("result_shape_variants", {}).items():
        param, _, expected = key.partition("=")
        value = params.get(param)
        if isinstance(value, str) and ("$" in value or "{{" in value):
            return None
        if value is not None and str(value) == expected:
            shape = variant
            break
    for rule in definition.get("result_shape_rules", []):
        matched = True
        for param, expected in rule.get("when", {}).items():
            value = params.get(param)
            if isinstance(value, str) and ("$" in value or "{{" in value):
                matched = False
            elif isinstance(expected, dict):
                if "nonempty" in expected:
                    matched = matched and (bool(value) == expected["nonempty"])
                else:
                    matched = matched and ((param in params) == expected.get("present"))
            else:
                matched = matched and value == expected
        if matched:
            shape = rule.get("shape")
    return T.from_data(shape) if isinstance(shape, dict) else None


def field_type(t, path):
    """행 필드 경로. 기존의 점이 들어간 리터럴 키는 우선 보존한다."""
    if path in t.fields:
        return t.fields[path]
    from common.field_path import parse_path
    cur = t
    for part in parse_path(path):
        cur = cur.fields.get(str(part), unknown())
    return cur


def flattened_type(t, path, keep):
    child = field_type(t, path)
    if child.kind == "scalar" and "items" in child.fields:
        child = child.fields["items"]
    if child.kind not in ("items", "scalar") or child.cols is None:
        return T("items")
    cols = list(child.cols)
    fields = dict(child.fields)
    for key in keep:
        name = key
        suffix = 2
        while name in cols:
            name = f"{key}_{suffix}"
            suffix += 1
        cols.append(name)
        fields[name] = field_type(t, key)
    return T("items", cols, child.closed, fields=fields, empty=child.empty)


def may_have_source_field(t, field):
    if t.kind == "unknown" or (t.kind == "items" and (not t.closed or field in (t.cols or []))):
        return True
    return any(may_have_source_field(child, field) for child in t.fields.values())


def replace_rows(source, rows):
    """비파괴 변환 뒤 봉투의 items 형도 새 행으로 교체한다. 옛 열을 복구 후보로 남기지 않는다."""
    if source.envelope is None:
        return rows
    fields = {**source.envelope.fields, "items": rows.copy(envelope=None)}
    return rows.copy(envelope=source.envelope.copy(fields=fields))
