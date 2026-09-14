#!/usr/bin/env python3
"""회원 졸업 ZIP → 이 설치본의 대화·심층기억·프로그램 원장. 외부 연결/코드 실행 없음."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

import yaml


def import_archive(archive, base):
    base = Path(base).resolve()
    archive = Path(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
    data = base / "data"
    destination = data / "member_imports" / digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 512 * 1024 * 1024:
            raise ValueError("아카이브 크기/파일 수 상한 초과")
        names = [i.filename for i in infos]
        if len(set(names)) != len(names):
            raise ValueError("중복 아카이브 경로")
        for i in infos:
            p = Path(i.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in i.filename or (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("아카이브 경로 이탈/심볼릭 링크")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != "indiebiz-member" or manifest.get("version") != 1:
            raise ValueError("지원하지 않는 회원 아카이브")
        tables = manifest["tables"]
        if any(not isinstance(rows, list) for rows in tables.values()):
            raise ValueError("테이블 형식 오류")
        for script in tables.get("scripts", []):
            for name in [script["path"], *(script.get("resources") or [])]:
                if name not in names or not name.startswith("programs/"):
                    raise ValueError("프로그램/자원 실물 누락")
            if script.get("interpreter") not in ("python3", "bash", "node"):
                raise ValueError("인터프리터 역할 오류")
        if not destination.exists():
            stage = Path(tempfile.mkdtemp(prefix=".import-", dir=destination.parent))
            try:
                z.extractall(stage)
                stage.rename(destination)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)

    # 파일과 DB 사이에 중단돼도 digest·source로 재시작한다. 실행 상태/열쇠는 가져오지 않는다.
    scripts_dir = data / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    registry_path = scripts_dir / "registry.yaml"
    registry = yaml.safe_load(registry_path.read_text()) if registry_path.exists() else {}
    registry = registry or {}
    for script in tables.get("scripts", []):
        sid = "member-" + digest + "-" + re.sub(r"[^\w-]", "_", str(script["id"]))
        registry[sid] = {"file": os.path.relpath(destination / script["path"], scripts_dir),
                         "interpreter": script["interpreter"], "description": script.get("description", ""),
                         "timeout": 120, "dependencies": script.get("dependencies") or [],
                         "resources": script.get("resources") or []}
    temporary = registry_path.with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(registry, allow_unicode=True, sort_keys=True))
    temporary.replace(registry_path)
    # IBL 원문도 별도 파일로 보존한다. 가져오기 중 파싱·실행·주인 해마 자동 시딩은 하지 않는다.
    sentences = destination / "sentences"
    sentences.mkdir(exist_ok=True)
    for index, row in enumerate(tables.get("sentences", [])):
        (sentences / f"{index}.ibl").write_text(row["code"])

    state = data / "system_ai_state"
    state.mkdir(parents=True, exist_ok=True)
    deep = state / "memory_system_ai.db"
    # 정본 스키마 초기화 API를 재사용하되 경로는 인자로 고정한다(테스트가 라이브 DB에 닿지 않음).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data/packages/installed/tools/memory"))
    import memory_db
    memory_db._ensure_schema(str(deep))
    db = sqlite3.connect(data / "system_ai_memory.db")
    try:
        db.execute("ATTACH DATABASE ? AS deep", (str(deep),))
        db.executescript("""CREATE TABLE IF NOT EXISTS conversations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT NOT NULL,role TEXT NOT NULL,
          content TEXT NOT NULL,summary TEXT,importance INTEGER DEFAULT 0,source TEXT,images TEXT);
          CREATE TABLE IF NOT EXISTS member_import_receipts(digest TEXT PRIMARY KEY,created TEXT);""")
        with db:
            if db.execute("SELECT 1 FROM member_import_receipts WHERE digest=?", (digest,)).fetchone():
                return {"success": True, "already_imported": True, "path": str(destination)}
            now = datetime.now().isoformat()
            for row in tables.get("conversations", []):
                for role, field in (("user", "user"), ("assistant", "assistant")):
                    db.execute("INSERT INTO conversations(timestamp,role,content,source) VALUES(?,?,?,?)",
                               (now, role, row.get(field) or "", "member-import:" + digest))
            for row in tables.get("memories", []):
                source = json.dumps({"type": "member_import", "archive": digest, "id": row["id"]})
                db.execute("INSERT INTO deep.memories(content,category,source_ref,node) VALUES(?,?,?,?)",
                           (row["content"], "회원 가져오기", source, "회원 가져오기"))
            db.execute("INSERT INTO member_import_receipts VALUES(?,?)", (digest, now))
    finally:
        db.close()
    # 원본 manifest에 episode/forage/해마까지 보존; AI가 졸업 사실과 원본 위치를 기억한다.
    return {"success": True, "path": str(destination),
            "conversations": len(tables.get("conversations", [])),
            "memories": len(tables.get("memories", [])), "programs": len(tables.get("scripts", []))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(import_archive(args.archive, args.base), ensure_ascii=False, indent=2))
