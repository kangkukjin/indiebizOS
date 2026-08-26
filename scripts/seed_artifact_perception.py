"""산출물 지각·반성 어휘 시딩 + render_html→render 코퍼스 이관 (2026-08-26).

[engines:render](html/pdf/svg 투영) 신설과 [engines:image_read]{op:"critic", criteria:…}
취향 파일 개통에 맞춰: ① 구 render_html 용례를 후계어로 이관(해마 DB UPDATE+재색인,
ibl_distilled 동기), ② 지각→심사 조합 문형 시딩.

실행: .venv/bin/python3 scripts/seed_artifact_perception.py
(system python3 은 sqlite_vec 가 없다 — .venv 필수)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ".worktrees" in ROOT.parts:                       # 시딩은 라이브 원장에만 — 워크트리 사본 금지
    ROOT = Path(*ROOT.parts[:ROOT.parts.index(".worktrees")])
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("INDIEBIZ_BASE_PATH", str(ROOT))
import boot_paths  # noqa: F401
from ibl_usage_db import IBLUsageDB

NEW = [
    # ── 단문: render 세 형식 ──
    ("이 HTML 파일 렌더링해서 어떻게 보이는지 보자",
     '[engines:render]{path: "index.html"}',
     "engines", "single", "render,html,지각"),
    ("홈페이지 시안 데스크톱이랑 모바일 두 화면으로 찍어봐",
     '[engines:render]{path: "site/index.html", viewports: ["1280x800", "390x844"]}',
     "engines", "single", "render,viewports,웹검수"),
    ("보고서 PDF 앞 세 쪽만 이미지로 뽑아줘",
     '[engines:render]{op: "pdf", path: "보고서.pdf", pages: [1, 2, 3]}',
     "engines", "single", "render,pdf"),
    ("로고 SVG를 PNG로 변환해줘",
     '[engines:render]{op: "svg", path: "logo.svg"}',
     "engines", "single", "render,svg"),
    ("Render this landing page at desktop and mobile widths",
     '[engines:render]{path: "landing.html", viewports: ["1440x900", "390x844"]}',
     "engines", "single", "render,english"),
    # ── 파이프 싱크 승계 (V21-1) ──
    ("비트코인 시세 요약해서 이미지 한 장으로 만들어",
     '[sense:crypto]{symbol: "BTC"} >> [table:brief]{instruction: "한 문장 시세 요약"} >> [engines:render]',
     "sense,table,engines", "pipeline", "파이프싱크,render,brief"),
    # ── 심사: criteria 취향 파일 ──
    ("이 스크린샷 웹 디자인 기준으로 평가해봐",
     '[engines:image_read]{op: "critic", image_path: "screenshot.png", intent: "랜딩 페이지 첫 화면 품질", criteria: "web"}',
     "engines", "single", "critic,criteria,취향파일"),
    # ── 지각→심사 조합 (반성 문장의 골격) ──
    ("index.html 두 뷰포트로 찍어서 웹 기준으로 심사해줘",
     '[engines:render]{path: "index.html", viewports: ["1280x800", "390x844"]} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'랜딩 페이지가 $it.label 폭에서 성립하고 위계가 읽히는가\', criteria: \'web\'}"}',
     "engines,table", "pipeline", "검수,critic,criteria,each"),
    ("슬라이드 PDF 를 쪽마다 심사해서 문제 있는 쪽 알려줘",
     '[engines:render]{op: "pdf", path: "슬라이드.pdf"} >> '
     '[table:each]{do: "[engines:image_read]{op: \'critic\', image_path: \'$it.path\', '
     'intent: \'슬라이드 $it.page 쪽이 깨짐 없이 읽히는가\', criteria: \'visual_base\'}"}',
     "engines,table", "pipeline", "검수,pdf,critic,each"),
    ("만든 차트 HTML 이 제대로 보이는지 눈으로 확인해봐",
     '[engines:render]{path: "chart.html"} >> '
     '[table:each]{do: "[engines:image_read]{op: \'read\', image_path: \'$it.path\', '
     'question: \'차트 축과 데이터가 정상적으로 그려져 있는가\'}"}',
     "engines,table", "pipeline", "render,read,확인"),
    # ── 얼린 문장(워크플로우)과 루프 두 형태 ──
    ("화면검수 워크플로우로 이 페이지 검사해줘",
     '[self:workflow]{op: "run", name: "화면검수", params: {path: "index.html", intent: "포트폴리오 랜딩 페이지"}}',
     "self", "single", "workflow,검수"),
    ("홈페이지 시안이 검수를 통과할 때까지 다듬어줘",
     '[goal: "홈페이지 시안 검수 통과"]{success_condition: "두 뷰포트 렌더의 critic 심사가 전부 passed", '
     'resources: ["web", "화면검수"], max_rounds: 3, report_to: "사용자"}',
     "goal", "single", "goal,검수루프,반성"),
    ("렌더가 실패하면 한 번 더 시도하고 그래도 안 되면 알려줘",
     '$tries = 0\n$ok = 0\n[repeat: while $ok == 0 and $tries < 2, max: 2]{$tries = $tries + 1\n'
     '[try]{[engines:render]{path: "index.html"}\n$ok = 1} '
     '[catch]{[self:notify_user]{message: "$tries 번째 렌더 실패: $error.summary"}}}',
     "engines,self", "pipeline", "repeat,try,재시도"),
]

# 구 어휘 → 후계어 치환 (해마 DB + distilled 동기 이관)
OLD, NEWWORD = "[engines:render_html]", "[engines:render]"


def migrate(db):
    import sqlite3
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    rows = conn.execute(
        "SELECT id, intent, ibl_code FROM ibl_examples WHERE ibl_code LIKE ?",
        (f"%{OLD}%",)).fetchall()
    for rid, intent, code in rows:
        conn.execute("UPDATE ibl_examples SET ibl_code = ? WHERE id = ?",
                     (code.replace(OLD, NEWWORD), rid))
        # vec0 은 UPDATE/UPSERT 불가 — DELETE→INSERT 만 된다 (sqlite_vec 부류).
        conn.execute("DELETE FROM ibl_examples_vec WHERE rowid = ?", (rid,))
    conn.commit()
    conn.close()
    for rid, intent, code in rows:               # 벡터 재색인 (행+임베딩 동기)
        db._index_single(rid, intent, code.replace(OLD, NEWWORD))
    dist_path = ROOT / "data" / "training" / "ibl_distilled.json"
    with open(dist_path, encoding="utf-8") as f:
        dist = json.load(f)
    moved = 0
    for d in dist:
        if OLD in d.get("ibl_code", ""):
            d["ibl_code"] = d["ibl_code"].replace(OLD, NEWWORD)
            moved += 1
    if moved:
        with open(dist_path, "w", encoding="utf-8") as f:
            json.dump(dist, f, ensure_ascii=False, indent=2)
    print(f"이관: 해마 {len(rows)}건 재색인, distilled {moved}건 치환")


if __name__ == "__main__":
    db = IBLUsageDB()
    assert db._load_model_sync(), "임베딩 모델 로드 실패 - 시딩 중단(_index_batch 는 실패를 삼킨다)"
    migrate(db)
    import sqlite3
    conn = sqlite3.connect(str(ROOT / "data" / "ibl_usage.db"))
    existing = {r[0] for r in conn.execute("SELECT intent FROM ibl_examples")}
    conn.close()
    batch = [{"intent": i, "ibl_code": c, "nodes": n, "category": cat, "difficulty": 2,
              "source": "manual_seed", "tags": t} for i, c, n, cat, t in NEW if i not in existing]
    print(f"시드 추가: {db.add_examples_batch(batch) if batch else 0}건 (중복 스킵 {len(NEW) - len(batch)}건)")
    dist_path = ROOT / "data" / "training" / "ibl_distilled.json"
    with open(dist_path, encoding="utf-8") as f:
        dist = json.load(f)
    have = {d.get("intent") for d in dist}
    added = 0
    for i, c, n, cat, t in NEW:
        if i not in have:
            dist.append({"intent": i, "ibl_code": c, "nodes": n, "category": cat,
                         "difficulty": 2, "source": "manual_seed"})
            added += 1
    if added:
        with open(dist_path, "w", encoding="utf-8") as f:
            json.dump(dist, f, ensure_ascii=False, indent=2)
    print(f"ibl_distilled: +{added}건 -> {len(dist)}건")
