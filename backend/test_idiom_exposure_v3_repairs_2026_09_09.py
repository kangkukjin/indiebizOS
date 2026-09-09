"""노출 실험 v3(2026-09-09) 비노출 조건 실패 29건 전수 분류에서 나온 바인딩 결함 셋의 관문.

① 옵셔널 `?` 결측을 따옴표 안 보간이 "None" 글자로 찍어 `"${it.줄번호?}${it.line?}"` 이 "4None" 이 되던 자리
② `[줄 11-22 …]` 머리로 시작하는 읽기 산문이 JSON 으로 오인돼 `.text`/`.message` 산문 규칙이 안 돌던 자리
③ `content` 도 산문의 이름([self:write]{content} 와 같은 이름=같은 것)
격리 실행기(실 파서·바인더·파일 핸들러)로 돈다.
"""
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from idiom_exposure_worker import run  # noqa: E402

REG = json.loads((ROOT / "docs/experiments/idiom_exposure_2026_09_09_v3/registry.json").read_text())


def execute(code):
    return run({"code": code, "case_id": "direct_context", "seed": 1, "registry": REG})["result"]


def test_optional_missing_interpolates_as_empty_not_None():
    r = execute('$r = [self:read]{path:"locations.json"}\n$x = $r >> [table:each]{limit:1} {\n'
                '  $ln = "${it.줄번호?}${it.line?}${it.line_no?}"\n  $end = $ln + 4\n  $return = [{ln: $ln, end: $end}]\n}\n$x')
    assert r["success"], r.get("error")
    row = json.loads(r["final_result"])["items"][0]
    assert row == {"ln": "4", "end": 8}


def test_read_prose_with_line_header_answers_text_message_content():
    r = execute('$doc = [self:read]{path:"drafts/report_2026-08-11.md", start_line: 11, end_line: 12}\n'
                '$a = "${doc.text?}"\n$b = "${doc.content?}"\n$c = "${doc.message?}"\n$out = [{text: $a, content: $b, message: $c}]\n$out')
    assert r["success"], r.get("error")
    row = json.loads(r["final_result"])["items"][0]
    assert row["text"] == row["content"] == row["message"] and "LINE-11" in row["text"]


def test_write_content_from_read_prose_content_path():
    r = execute('$doc = [self:read]{path:"drafts/report_2026-08-11.md", start_line: 11, end_line: 12}\n'
                '[self:write]{path:"outputs/x.txt", content: "${doc.content}"}')
    assert r["success"], r.get("error")
    assert json.loads(r["final_result"])["size"] > 0


def test_other_field_on_prose_is_still_an_honest_error():
    r = execute('$doc = [self:read]{path:"drafts/report_2026-08-11.md", start_line: 11, end_line: 12}\n$z = "${doc.body}"')
    assert not r["success"] and "body" in str(r["error"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
