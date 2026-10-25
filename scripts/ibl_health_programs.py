"""현행 건강 점검 프로그램과 단언. 외부 조회와 결정론적 언어 검사를 분리한다."""
import boot_paths  # noqa: F401

from ibl_v2_ir import unpack


PIPES = [
    ("naver>>filter>>take", '$r=[sense:search]{source:"naver",query:"AI"}; '
     'return $r.items >> [table:filter]{where:($row)=>$row.title != ""} '
     '>> [table:take]{n:3}', "items"),
    ("world_bank>>chart", '$r=[sense:world_bank]{indicator:"인구",country:"한국",date:"2015:2023"}; '
     'return $r.items >> [table:chart]{chart_type:"line"}', "chart"),
    ("paper>>take>>document", '$r=[sense:paper]{query:"transformer"}; '
     'return $r.items >> [table:take]{n:5} >> [table:document]{format:"html"}', "doc"),
    ("legal>>dedup>>take", '$r=[sense:legal]{query:"도로교통법"}; '
     '$unique=$r.items >> [table:dedup]{}; return $unique.items >> [table:take]{n:3}', "items"),
    ("kosis>>take", '$r=[sense:kosis]{op:"lookup",query:"인구"}; '
     'return $r.items >> [table:take]{n:5}', "items"),
]


def pipe_ok(value, kind):
    if kind == "items":
        return isinstance(value, list) and bool(value) and all(isinstance(row, dict) for row in value)
    if not isinstance(value, dict) or value.get("success") is not True:
        return False
    # Successful execution alone does not establish an output artifact.
    return bool(value.get("path") or value.get("file") or value.get("file_path")
                or value.get("output_path") or value.get("html_path"))


# The expected failure probes must reach execution. Compilation/transport failures
# never count as a successful negative test. Pure operators do not depend on APIs.
OPERATORS = [
    ("도구 실패 전파", '[self:read]{path:"__health_missing_file__.md"}', "tool_failure"),
    ("; 미처리 실패는 중단", '1/0; return 9', "runtime_failure"),
    ("; 값은 명시 전달", '$r={items:[1,2],meta:"source"}; '
     '$short=$r.items >> [table:take]{n:1}; return {source:$r,selected:$short}',
     {"source": {"items": [1, 2], "meta": "source"}, "selected": [1]}),
    (">> 실패시 중단", '[1/0] >> [table:take]{n:1}', "runtime_failure"),
    ("?? 도구 실패→폴백", '[self:read]{path:"__health_missing_file__.md"} ?? 42', 42),
    ("?? 성공→단축평가", '7 ?? (1/0)', 7),
    ("?? 빈 목록은 성공", '[] ?? 42', []),
    ("?? null은 성공", 'null ?? 42', None),
    ("catch 명시 복구", '[try]{1/0}[catch]{return 42}', 42),
    ("& 가지별 값 보존", '[1] & [2]', [[1], [2]]),
]


def operator_result(result, expected):
    if not isinstance(result, dict) or result.get("executed") is not True:
        return False, str(result)[:200]
    if isinstance(expected, str) and expected in ("runtime_failure", "tool_failure"):
        diagnostic = result.get("diagnostic") or {}
        # The adapter must report a tool fault; a type/compile error is not proof
        # that a JSON error from a handler crossed the execution boundary.
        code = diagnostic.get("code")
        wanted = "NOT_FOUND" if expected == "tool_failure" else "VALUE"
        ok = result.get("success") is False and code == wanted
        return ok, f"success={result.get('success')} code={code}"
    if result.get("success") is not True:
        return False, str(result.get("error") or result)[:200]
    wire = result.get("value_wire") or {}
    if wire.get("protocol") not in ("ibl-value/1", "ibl-value/2"):
        return False, "value_wire 프로토콜 누락"
    try:
        value = unpack(wire["data"])
    except Exception as exc:
        return False, str(exc)
    return value == expected, f"value={value!r}"
