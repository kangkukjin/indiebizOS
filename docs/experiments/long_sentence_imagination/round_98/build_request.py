"""p1 요청 JSON 조립(98회차). 사용: build_request.py <ibl> <out.json> [--check] [--variant <json파일>] [--report <경로>]"""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parent
ROOT = R.parents[2]
old = '''    observations = (applied, activated, committed)
    if all(value is True for value in observations):
        return "achieved"
    return "failed"'''
new_correct = '''    observations = (applied, activated, committed)
    if any(value is False for value in observations):
        return "failed"
    if any(value is None for value in observations):
        return "unverified"
    return "achieved"'''
new_none_first = '''    observations = (applied, activated, committed)
    if any(value is None for value in observations):
        return "unverified"
    if any(value is False for value in observations):
        return "failed"
    return "achieved"'''
assert len(new_correct) == len(new_none_first)
weak_old = '''    assert fold_receipt(True, None, True) == "unverified"'''
weak_new = '''    assert fold_receipt(True, None, True) == "failed"'''
argv = sys.argv
variant = json.loads(Path(argv[argv.index("--variant") + 1]).read_text()) if "--variant" in argv else None
report = argv[argv.index("--report") + 1] if "--report" in argv else str(R / "trainer/p1_report.json")
body = {"code": Path(argv[1]).read_text(encoding="utf-8"),
        "inputs": {"러너본문": (R / "runner.py").read_text(encoding="utf-8"), "정본": str(ROOT),
                   "경로": "backend/test_repair_training_subject_copy.py",
                   "old": old, "new_correct": new_correct, "new_none_first": new_none_first, "weak_old": weak_old, "weak_new": weak_new,
                   "사유_a": "98회차 탐침 a: None(미관측)을 unverified 로 분리(요구 표)",
                   "사유_b": "98회차 탐침 b: None 을 먼저 접어 False 우선순위를 훼손(관측용, 적용 금지)",
                   "사유_c": "98회차 탐침 c: 시험 기대값을 결함 구현에 맞춰 약화(관측용, 적용 금지)",
                   "사유_d": "98회차 탐침 d: 올바른 구현 + 범위 밖 판정기 변경(관측용, 적용 금지)",
                   "판정기경로": "backend/base/repair_test_results.py", "추가내용": "\n# 98회차 훈련 탐침 d: 범위 밖 판정기 변경(사본 안, 관측용)\n",
                   "검증자": str(R / "harness/verify_subject.py"), "씨앗": str(R / "harness/seed_copy_original.py"),
                   "보고경로": report, "변형": variant}}
if "--check" in argv: body["check"] = True
Path(argv[2]).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", len(body["code"]), "variant" if variant else "main")
