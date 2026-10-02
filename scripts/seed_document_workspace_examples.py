"""Seed owner document-session idioms through the canonical batch entry point."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_usage_db import IBLUsageDB  # noqa: E402

EXAMPLES = [
    {"intent": "보고서 Markdown을 문서 앱에 등록하고 원본과 작업 초안을 분리한다",
     "ibl_code": '[self:document]{op:"open", path:"보고서.md"}'},
    {"intent": "등록한 문서의 원형 편집과 저장 지원 여부를 먼저 확인한다",
     "ibl_code": '[self:document]{op:"capabilities", args:{document_id:"{{document_id}}"}}'},
    {"intent": "문서 앱의 확정 저장 버전 이력을 조회한다",
     "ibl_code": '[self:document]{op:"versions", args:{document_id:"{{document_id}}"}}'},
]


def main():
    count = IBLUsageDB().add_examples_batch([
        dict(example, nodes="self", source="synthetic", tags="system_essentials,document_workspace")
        for example in EXAMPLES
    ])
    path = ROOT / "data/training/ibl_distilled.json"
    rows = json.loads(path.read_text())
    known = {(r.get("intent"), r.get("ibl_code")) for r in rows}
    additions = [r for r in EXAMPLES if (r["intent"], r["ibl_code"]) not in known]
    if additions:
        path.write_text(json.dumps(rows + additions, ensure_ascii=False, indent=2) + "\n")
    print(f"document examples: DB added {count}; training added {len(additions)}")


if __name__ == "__main__":
    main()
