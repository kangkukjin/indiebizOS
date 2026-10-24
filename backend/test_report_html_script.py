"""보고서 Markdown → HTML의 표 보존과 저장 전 검사 계약."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from bs4 import BeautifulSoup


@pytest.fixture
def renderer(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "data/scripts/보고서HTML.py"
    spec = importlib.util.spec_from_file_location("report_html_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    return module


@pytest.mark.parametrize("theme", ["plain", "card", "briefing"])
def test_missing_boundary_preserves_cells_links_and_source(renderer, tmp_path, theme):
    source = (
        "# 보고서\n\n## 변동\n\n**8월 이후 바뀐 것**\n"
        "| 축 | 이전 | 현재 |\n|---|:---:|---:|\n"
        "| 예산 | 1.5~3억 | **2~4억** |\n"
        "| 매물 | 3건 | [49건](https://example.com/list) |\n\n"
        "다른 표\n\n| 항목 | 값 |\n|---|---|\n| 결과 | 유지 |\n"
    )
    src = tmp_path / "report.md"
    src.write_text(source)
    result = renderer.render({"src": str(src), "dst": "report.html", "theme": theme})
    html = BeautifulSoup((tmp_path / "report.html").read_text(), "html.parser")
    assert src.read_text() == source
    assert result["items"][0]["tables"] == 2
    assert result["items"][0]["table_structure"] == {
        "status": "preserved", "expected": 2, "boundaries_fixed": 1,
    }
    assert [[c.get_text() for c in row.select("th,td")]
            for row in html.select("table")[0].select("tr")] == [
        ["축", "이전", "현재"], ["예산", "1.5~3억", "2~4억"], ["매물", "3건", "49건"],
    ]
    assert html.select_one("table a")["href"] == "https://example.com/list"
    assert html.select_one("table strong").get_text() == "2~4억"


@pytest.mark.parametrize('drop', ['제외', ['제외'], None])
def test_registered_contract_preserves_supported_inputs_and_actual_result(renderer, tmp_path, drop):
    import yaml
    from ibl_callable_contract import checked_values
    from ibl_v2_adapters import validate_contract
    from ibl_v2_types import guard
    path = Path(__file__).resolve().parents[1]/'data/scripts/registry.yaml'
    contract = yaml.safe_load(path.read_text())['보고서HTML']['callable_contract']
    validate_contract(contract)
    (tmp_path/'source.md').write_text('# 제목\n\n제외할 줄\n\n유지할 줄')
    selected, args = checked_values(contract, {'src': 'source.md', 'dst': 'result.html', 'drop_lines': drop})
    result = renderer.render(args)
    guard(result, selected['result'], '보고서HTML 결과')
    assert (tmp_path/'result.html').is_file()
    assert result['items'][0]['dropped_lines'] == (0 if drop is None else 1)
    with pytest.raises(ValueError, match='알 수 없는 인자'):
        checked_values(contract, {**args, 'definitely_wrong': True})
    with pytest.raises(ValueError, match='필수 인자 누락'):
        checked_values(contract, {'src': 'source.md'})


@pytest.mark.parametrize("example", [
    "```markdown\n제목\n| 가 | 나 |\n|---|---|\n| 1 | 2 |\n```",
    "~~~\n제목\n| 가 | 나 |\n|---|---|\n| 1 | 2 |\n~~~",
    "    제목\n    | 가 | 나 |\n    |---|---|\n    | 1 | 2 |",
    "<pre>\n제목\n| 가 | 나 |\n|---|---|\n| 1 | 2 |\n</pre>",
])
def test_code_examples_are_not_converted_to_tables(renderer, example):
    html, counts = renderer._render_markdown(example)
    soup = BeautifulSoup(html, "html.parser")
    assert not soup.select("table")
    assert "|---|---|" in soup.select_one("pre").get_text()
    assert counts == {"expected": 0, "boundaries_fixed": 0}


@pytest.mark.parametrize("header,separator,row,expected", [
    ("가 | 나", "--- | ---", "1 | 2", ["1", "2"]),
    ("| 값 |", "|---|", "| 1 |", ["1"]),
    (r"| 가\|나 | `다|라` |", "|---|---|", r"| 값\|값 | `x|y` |", ["값|값", "x|y"]),
])
def test_table_dialect_uses_existing_cell_parser(renderer, header, separator, row, expected):
    html, counts = renderer._render_markdown(f"설명\n{header}\n{separator}\n{row}")
    assert [c.get_text() for c in BeautifulSoup(html, "html.parser").select("td")] == expected
    assert counts == {"expected": 1, "boundaries_fixed": 1}


def test_plain_pipes_and_horizontal_rule_stay_prose(renderer):
    html, counts = renderer._render_markdown("A | B\n값 | 값\n\n---\n\n`a|b`")
    assert "<table>" not in html
    assert counts["expected"] == 0


def test_drop_lines_runs_before_boundary_repair(renderer, tmp_path):
    (tmp_path / "report.md").write_text(
        "설명\n비공개\n| 가 | 나 |\n|---|---|\n| 1 | 2 |")
    result = renderer.render({"src": "report.md", "dst": "report.html", "drop_lines": ["비공개"]})
    assert result["items"][0]["tables"] == 1
    assert result["items"][0]["dropped_lines"] == 1


def test_lost_table_stops_before_replacing_existing_output(renderer, tmp_path, monkeypatch):
    from markdown.extensions.tables import TableProcessor
    (tmp_path / "report.md").write_text("설명\n| 가 | 나 |\n|---|---|\n| 1 | 2 |")
    dst = tmp_path / "report.html"
    dst.write_text("existing published bytes")
    # 구조를 인식했어도 렌더러가 잃어버리면 성공으로 발행하지 않는다.
    monkeypatch.setattr(TableProcessor, "run", lambda self, parent, blocks: blocks.pop(0))
    with pytest.raises(ValueError, match="표 구조가 보존되지"):
        renderer.render({"src": "report.md", "dst": "report.html"})
    assert dst.read_text() == "existing published bytes"


def test_normal_tables_remain_unchanged(renderer):
    import markdown
    source = "# 보고서\n\n설명\n\n| 가 | 나 |\n|---|---|\n| 1 | 2 |\n"
    html, counts = renderer._render_markdown(source)
    assert html == markdown.markdown(source, extensions=["tables", "sane_lists", "nl2br"])
    assert counts["boundaries_fixed"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
