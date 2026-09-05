"""새 낱말 2개 + 등록 스크립트 2개 + read blocks 범위 회귀 (2026-09-05, 사용자 판정 "어휘는 만들자, 2·3·4").

  S1  [sense:sqlite] query/tables/schema — 임시 DB 에서 행 items·columns·limit 절단 신고. 쓰기 SQL(INSERT/UPDATE/DELETE/DDL)은 거절.
  S2  [sense:sqlite] 없는 파일·없는 표는 정직 오류 + 힌트.
  H1  [sense:http] head/body — 로컬 http.server 상대로 status·content_type·Range(206·Content-Range)·body_preview. 404 는 success:true·ok:false.
  H2  [sense:http] 연결 실패는 success:false, 알 수 없는 op 거절.
  R1  등록 원장(data/scripts/registry.yaml)에 빌드검증·시험이 있고 파일이 실존한다. 시험.py 는 진행 줄에서 통과 수를 센다.
  B1  [self:read]{blocks:true} 가 offset/limit(start_line 흡수) 범위 안만 문단으로 나눈다(관용구 '찾아서각각읽기' 의 전제).
실 DB·실 트리 무접촉(임시 sqlite·임시 파일·로컬 서버). 실행: .venv/bin/python -m pytest backend/test_sqlite_http_words_2026_09_05.py -q
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

ROOT = os.path.dirname(BACKEND)
_ESS = os.path.join(ROOT, "data", "packages", "installed", "tools", "system_essentials")
_WEB = os.path.join(ROOT, "data", "packages", "installed", "tools", "web")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- S1/S2 sqlite
@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, ext TEXT, title TEXT)")
    c.executemany("INSERT INTO tracks (ext, title) VALUES (?, ?)", [("mp3", f"t{i}") for i in range(7)] + [("ape", "a1")])
    c.commit(); c.close()
    return str(p)


def test_s1_query_tables_schema_and_limit(db):
    S = _load(os.path.join(_ESS, "sqlite_ops.py"), "sqlite_ops_t")
    r = S.op_tables({"path": db})
    assert r["success"] and r["items"] == [{"name": "tracks", "rows": 8}]
    r = S.op_schema({"path": db, "table": "tracks"})
    assert [c["name"] for c in r["items"]] == ["id", "ext", "title"] and r["items"][0]["pk"] is True
    r = S.op_query({"path": db, "query": "SELECT ext, COUNT(*) AS n FROM tracks GROUP BY ext ORDER BY n DESC"})
    assert r["columns"] == ["ext", "n"] and r["items"][0] == {"ext": "mp3", "n": 7} and not r.get("truncated")
    r = S.op_query({"path": db, "query": "SELECT title FROM tracks WHERE ext = ?", "params": ["mp3"], "limit": 3})
    assert r["count"] == 3 and r["truncated"] is True and "limit 3" in r["note"]
    for bad in ("DELETE FROM tracks", "UPDATE tracks SET ext='x'", "DROP TABLE tracks", "INSERT INTO tracks (ext) VALUES ('x')",
                "SELECT 1; DROP TABLE tracks"):
        rr = S.op_query({"path": db, "query": bad})
        assert rr["success"] is False and "읽기 전용" in rr["error"], bad
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 8     # 무변경


def test_s2_missing_file_and_table(db, tmp_path):
    S = _load(os.path.join(_ESS, "sqlite_ops.py"), "sqlite_ops_t2")
    r = S.op_query({"path": str(tmp_path / "nope.db"), "query": "SELECT 1"})
    assert r["success"] is False and "없습니다" in r["error"] and "file_find" in r["hint"]
    r = S.op_schema({"path": db, "table": "ghost"})
    assert r["success"] is False and "tables" in r["hint"]
    r = S.op_query({"path": db, "query": ""})
    assert r["success"] is False


# ---------------------------------------------------------------- H1/H2 http
class _H(BaseHTTPRequestHandler):
    BODY = b"0123456789" * 20

    def log_message(self, *a):
        pass

    def _send(self, head_only=False):
        if self.path == "/404":
            self.send_response(404); self.send_header("Content-Type", "text/plain"); self.end_headers()
            if not head_only:
                self.wfile.write(b"nope")
            return
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, b = rng[6:].split("-"); a, b = int(a), int(b)
            chunk = self.BODY[a:b + 1]
            self.send_response(206); self.send_header("Content-Range", f"bytes {a}-{a + len(chunk) - 1}/{len(self.BODY)}")
        else:
            chunk = self.BODY
            self.send_response(200)
        self.send_header("Content-Type", "text/plain"); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(chunk))); self.end_headers()
        if not head_only:
            self.wfile.write(chunk)

    def do_GET(self):
        self._send()

    def do_HEAD(self):
        self._send(head_only=True)


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_h1_head_get_range_and_404(server):
    H = _load(os.path.join(_WEB, "tool_http.py"), "tool_http_t")
    r = H.probe({"url": server + "/x", "op": "head"})
    row = r["items"][0]
    assert r["success"] and r["status"] == 200 and row["ok"] and row["content_type"].startswith("text/plain") and row["accept_ranges"] == "bytes"
    assert "bytes" not in row                                   # head 는 본문 없음
    r = H.probe({"url": server + "/x", "op": "body", "range": "bytes=0-9", "max_preview": 5})
    row = r["items"][0]
    assert r["status"] == 206 and row["content_range"] == "bytes 0-9/200" and row["bytes"] == 10 and row["body_preview"] == "01234"
    r = H.probe({"url": server + "/404"})
    assert r["success"] is True and r["ok"] is False and r["status"] == 404 and "연결 실패가 아님" in r["note"]


def test_h2_connection_failure_and_bad_op(server):
    H = _load(os.path.join(_WEB, "tool_http.py"), "tool_http_t2")
    r = H.probe({"url": "http://127.0.0.1:9/x", "timeout": 2})
    assert r["success"] is False and "items" in r
    r = H.probe({"url": server, "op": "post"})
    assert r["success"] is False and "알 수 없는 op" in r["error"]
    assert H.probe({"url": "ftp://x"})["success"] is False


# ---------------------------------------------------------------- R1 등록 스크립트
def test_r1_registered_scripts_exist_and_test_runner_counts():
    import yaml
    reg = yaml.safe_load(open(os.path.join(ROOT, "data", "scripts", "registry.yaml"), encoding="utf-8"))
    for sid in ("빌드검증", "시험"):
        assert sid in reg and os.path.isfile(os.path.join(ROOT, "data", "scripts", reg[sid]["file"])), sid
    out = subprocess.run([sys.executable, os.path.join(ROOT, "data", "scripts", "시험.py")],
                         input=json.dumps({"files": ["backend/test_ibl_typecheck.py", "backend/없는시험.py"]}),
                         capture_output=True, text=True, cwd=ROOT, timeout=300)
    d = json.loads(out.stdout)
    by = {i["file"]: i for i in d["items"]}
    assert by["backend/test_ibl_typecheck.py"]["passed"] >= 10 and by["backend/test_ibl_typecheck.py"]["ok"]
    assert by["backend/없는시험.py"]["ok"] is False and d["ok"] is False


# ---------------------------------------------------------------- B1 read blocks 범위
def test_b1_read_blocks_respects_range(tmp_path):
    from ibl_engine import execute_ibl
    p = tmp_path / "doc.md"
    p.write_text("# 머리\n\n첫 문단\n\n둘째 문단\n\n셋째 문단\n\n넷째 문단\n", encoding="utf-8")
    out = execute_ibl({"_node": "self", "action": "read", "params": {"path": str(p), "start_line": 5, "limit": 3, "blocks": True}}, str(tmp_path))
    d = json.loads(out) if isinstance(out, str) else out
    texts = [b.get("text") for b in d["items"]]
    assert texts == ["둘째 문단", "셋째 문단"], texts
    assert d["start_line"] == 5 and d["end_line"] == 7
    out_all = execute_ibl({"_node": "self", "action": "read", "params": {"path": str(p), "blocks": True}}, str(tmp_path))
    d_all = json.loads(out_all) if isinstance(out_all, str) else out_all
    assert len(d_all["items"]) == 5 and "start_line" not in d_all


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
