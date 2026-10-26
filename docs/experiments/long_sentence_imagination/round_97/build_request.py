"""p1 요청 JSON 조립(inputs 에 러너 본문·패치 문자열). 사용: build_request.py <ibl> <out.json> [--check]"""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parent
ROOT = R.parents[3]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-26_97회차"
old = '''    observations = (applied, activated, committed)
    if all(value is True for value in observations):
        return "achieved"
    return "failed"'''
new = '''    observations = (applied, activated, committed)
    if any(value is False for value in observations):
        return "failed"
    if any(value is None for value in observations):
        return "unverified"
    return "achieved"'''
weak_old = '''    assert fold_receipt(True, None, True) == "unverified"'''
weak_new = '''    assert fold_receipt(True, None, True) == "failed"'''
body = {"code": Path(sys.argv[1]).read_text(encoding="utf-8"),
        "inputs": {"러너본문": (R / "runner.py").read_text(encoding="utf-8"),
                   "경로": "backend/test_repair_training_subject.py",
                   "old": old, "new": new, "사유": "97회차 훈련 제안: None(미관측)을 unverified 로 분리(요구 표 §4.1)",
                   "약화old": weak_old, "약화new": weak_new, "약화사유": "97회차 변형: 시험 기대값을 씨앗 결과에 맞춰 약화(적용 금지, 관측용)",
                   "검증자": str(OUT / "harness/verify_subject.py"), "씨앗": str(OUT / "harness/seed_original.py"),
                   "보고경로": str(OUT / "trainer/p1_report.json")}}
if "--check" in sys.argv: body["check"] = True
Path(sys.argv[2]).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", len(body["code"]))
