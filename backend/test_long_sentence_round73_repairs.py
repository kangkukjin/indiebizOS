"""73회차(원격 하드웨어 함대) 수리 회귀 — L73-1 f문자열 리터럴 조각, L73-4 하드링크 금지 환경 발행."""
import boot_paths  # noqa: F401
import errno
import os
from pathlib import Path

import pytest

from common.expression_parser import Parser
from output_publish import publish_file


def _parts(code):
    node = Parser(code).expr()
    return [p if isinstance(p, str) else "<expr>" for p in node.data["parts"]]


@pytest.mark.parametrize("code,expected", [
    # 삼중 따옴표 f문자열의 리터럴 조각이 큰따옴표로 끝남(하달 IBL 안의 path:"${…}" 모양) — 전엔 Python SyntaxError 원문 누출
    ('f"""#!ibl edition=2\n$in=[self:write]{path:"${p}/s.json",content:${c}}\n"""',
     ['#!ibl edition=2\n$in=[self:write]{path:"', '<expr>', '/s.json",content:', '<expr>', '}\n']),
    ('f"""say "${x}"""', ['say "', '<expr>']),
    ('f"""한글 "${x}" 끝"""', ['한글 "', '<expr>', '" 끝']),
    # 기존 동작 보존
    ('f"a ${x} b"', ['a ', '<expr>', ' b']),
    ('f"탭\\t ${x} 줄\\n"', ['탭\t ', '<expr>', ' 줄\n']),
])
def test_fstring_literal_chunk_ending_with_quote(code, expected):
    assert _parts(code) == expected


def test_fstring_literal_failure_is_ibl_syntax_not_python():
    # 보간식 안의 이스케이프 따옴표는 기존 규칙대로 IBL SYNTAX(위치 포함)로 남아야 한다
    from common.expression_ir import Fault
    with pytest.raises(Fault) as info:
        Parser('f"x ${a + \\"b\\"} y"').expr()
    assert info.value.code == "SYNTAX"


def test_publish_falls_back_when_hard_link_denied(tmp_path, monkeypatch):
    def deny(src, dst):
        raise PermissionError(errno.EPERM, "Operation not permitted", str(dst))
    monkeypatch.setattr(os, "link", deny)
    _, receipt = publish_file(tmp_path / "a.jpg", lambda t: t.write_bytes(b"xyz"), if_exists="fail")
    assert Path(receipt["path"]).read_bytes() == b"xyz"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".publish-")]
    with pytest.raises(FileExistsError):
        publish_file(tmp_path / "a.jpg", lambda t: t.write_bytes(b"new"), if_exists="fail")
    assert (tmp_path / "a.jpg").read_bytes() == b"xyz"
    _, renamed = publish_file(tmp_path / "a.jpg", lambda t: t.write_bytes(b"new"), if_exists="rename")
    assert renamed["path"].endswith("a (2).jpg")


def test_publish_other_link_errors_still_raise(tmp_path, monkeypatch):
    def boom(src, dst):
        raise OSError(errno.EIO, "io")
    monkeypatch.setattr(os, "link", boom)
    with pytest.raises(OSError):
        publish_file(tmp_path / "b.txt", lambda t: t.write_text("hi"), if_exists="fail")


if __name__ == "__main__":
    pytest.main([__file__])
