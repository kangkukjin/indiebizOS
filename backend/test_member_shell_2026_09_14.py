"""공통 renderer를 실제 JavaScript로 검사한다(로컬 승인 경계의 HTML 주입 방어)."""
import boot_paths
import json
import re
import shutil
import subprocess
import pytest


def test_common_markdown_does_not_make_attribute_injection():
    from launcher_app_common import LAUNCHER_COMMON_JS
    if not shutil.which("node"):
        pytest.skip("node가 필요합니다")
    function = LAUNCHER_COMMON_JS.split("function mdChat(t){", 1)[1].split("\n}", 1)[0]
    node = "function esc(s){return s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}\n"
    node += "function mdChat(t){" + function + "\n}\n"
    payload = '[누르기](https://example.invalid/"onclick="alert(1))'
    node += "process.stdout.write(mdChat(" + json.dumps(payload) + "));"
    out = subprocess.run(["node", "-e", node], capture_output=True, text=True, check=True).stdout
    assert 'href="https://example.invalid/"onclick=' not in out
    assert '<script' not in out


def test_bundled_shell_and_scripts_parse():
    from pathlib import Path
    from member_shell import member_html
    root = Path(__file__).parents[1]
    assert (root / "helper/member_app.html").read_text() == member_html()
    if not shutil.which("node"):
        pytest.skip("node가 필요합니다")
    for code in re.findall(r"<script[^>]*>(.*?)</script>", member_html(), re.S):
        subprocess.run(["node", "--check"], input=code, text=True, capture_output=True, check=True)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
