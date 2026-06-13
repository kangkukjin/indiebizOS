#!/usr/bin/env python3
"""export_hippo_index.py — 해마 인덱스를 폰 번들용으로 추출 (폰-자아 호스팅 §6 step6).

폰엔 sentence-transformers(torch)도 sqlite-vec 도 없다. 그래서 폰-자아 해마는:
- 질의 임베딩 = 맥 /embed 엔드포인트 렌트(인코더=공유 substrate, step3).
- 문서 인덱스 = 이 스크립트가 추출한 정적 파일을 폰이 로드 → 인메모리 brute-force 코사인.
  (~2400개라 sqlite-vec 불필요. 인덱스=사적 경험이지만 *합성 코퍼스*는 공유 substrate라 배포 OK.)

출력 2종 (data/):
- ibl_hippo_index.json : {dim, count, examples:[{id,intent,ibl_code,nodes,category,difficulty,
  source,success_count,fail_count}]}  (벡터 행 순서와 1:1)
- ibl_hippo_vecs.f32   : raw float32, (count, dim) — examples[i] 의 L2정규화 임베딩.
  폰은 np.frombuffer(...).reshape(count, dim) 로 즉시 행렬화 → query_vec 와 dot = 코사인.

맥에서 1회 실행(어휘/코퍼스 갱신 시 재실행). build_ibl_nodes 처럼 정본→파생.
"""
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def main() -> int:
    from ibl_usage_db import IBLUsageDB

    db = IBLUsageDB()
    dim = IBLUsageDB.EMBEDDING_DIM
    data_dir = Path(__file__).resolve().parent.parent / "data"
    idx_path = data_dir / "ibl_hippo_index.json"
    vec_path = data_dir / "ibl_hippo_vecs.f32"

    # 1) 메타데이터 (ibl_examples)
    with db._get_connection() as conn:
        rows = conn.execute(
            """SELECT id, intent, ibl_code, nodes, category, difficulty,
                      source, success_count, fail_count
               FROM ibl_examples ORDER BY id"""
        ).fetchall()
    if not rows:
        print("[export_hippo] ibl_examples 비어있음 — rebuild_index 먼저", file=sys.stderr)
        return 1

    # 2) 벡터 (ibl_examples_vec, vec0) — rowid=id 로 매핑
    vconn = db._get_vec_connection()
    if vconn is None:
        print("[export_hippo] sqlite-vec 미가용 — 벡터 추출 불가", file=sys.stderr)
        return 1
    vec_by_id: dict[int, bytes] = {}
    try:
        db._ensure_vec_table(vconn)
        for vrow in vconn.execute("SELECT rowid, embedding FROM ibl_examples_vec").fetchall():
            rid = int(vrow["rowid"] if hasattr(vrow, "keys") else vrow[0])
            emb = vrow["embedding"] if hasattr(vrow, "keys") else vrow[1]
            # vec0 의 embedding 은 raw float32 blob (저장 시 struct.pack('768f')).
            if isinstance(emb, (bytes, bytearray, memoryview)) and len(bytes(emb)) == dim * 4:
                vec_by_id[rid] = bytes(emb)
    finally:
        vconn.close()

    # 3) 메타↔벡터 정렬, 누락(벡터 없는 예시)은 재인코딩 폴백 또는 스킵
    def _safe_int(v, default=0):
        # 일부 옛 증류 행은 difficulty 등에 비정수(예 'single' — 컬럼 어긋남)가 섞여 있다.
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    examples = []
    packed_rows: list[bytes] = []
    missing = 0
    reencoded = 0
    for row in rows:
        rid = int(row["id"])
        meta = {
            "id": rid,
            "intent": row["intent"],
            "ibl_code": row["ibl_code"],
            "nodes": row["nodes"] or "",
            "category": row["category"] or "single",
            "difficulty": _safe_int(row["difficulty"], 1),
            "source": row["source"] or "synthetic",
            "success_count": _safe_int(row["success_count"], 0),
            "fail_count": _safe_int(row["fail_count"], 0),
        }
        vec = vec_by_id.get(rid)
        if vec is None:
            # 폴백: 인덱싱과 동일 _prepare_search_text 로 재인코딩
            packed = db._generate_embedding(
                IBLUsageDB._prepare_search_text(row["intent"], row["ibl_code"])
            )
            if packed is None:
                missing += 1
                continue
            vec = packed
            reencoded += 1
        examples.append(meta)
        packed_rows.append(vec)

    if not examples:
        print("[export_hippo] 추출된 예시 0 — 중단", file=sys.stderr)
        return 1

    # 4) 쓰기
    idx_path.write_text(
        json.dumps({"dim": dim, "count": len(examples), "examples": examples},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    with open(vec_path, "wb") as f:
        for pr in packed_rows:
            f.write(pr)

    print(f"[export_hippo] {len(examples)}개 추출 "
          f"(vec0 {len(examples)-reencoded}, 재인코딩 {reencoded}, 누락 {missing})")
    print(f"[export_hippo] {idx_path} ({idx_path.stat().st_size//1024}KB)")
    print(f"[export_hippo] {vec_path} ({vec_path.stat().st_size//1024}KB, {len(examples)}x{dim} f32)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
