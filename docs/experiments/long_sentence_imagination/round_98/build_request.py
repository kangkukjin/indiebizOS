"""p1 요청 JSON 조립(98회차). 사용: build_request.py <ibl> <out.json> [--check] [--variant <json파일>] [--report <경로>]"""
import argparse, json, sys
from pathlib import Path
R = Path(__file__).resolve().parent
ROOT = R.parents[3]
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
def build_request(program, report, *, repo=ROOT, subject="backend/test_repair_training_subject_copy.py", seed=None, variant=None):
    repo = Path(repo).resolve()
    body = {"code": Path(program).read_text(encoding="utf-8"),
            "inputs": {"러너본문": (R / "runner_v2.py").read_text(encoding="utf-8"), "정본": str(repo),
                       "경로": subject,
                       "old": old, "new_correct": new_correct, "new_none_first": new_none_first, "weak_old": weak_old, "weak_new": weak_new,
                       "사유_a": "98회차 탐침 a: None(미관측)을 unverified 로 분리(요구 표)",
                       "사유_b": "98회차 탐침 b: None 을 먼저 접어 False 우선순위를 훼손(관측용, 적용 금지)",
                       "사유_c": "98회차 탐침 c: 시험 기대값을 결함 구현에 맞춰 약화(관측용, 적용 금지)",
                       "사유_d": "98회차 탐침 d: 올바른 구현 + 범위 밖 판정기 변경(관측용, 적용 금지)",
                       "판정기경로": "backend/base/repair_test_results.py", "추가내용": "\n# 98회차 훈련 탐침 d: 범위 밖 판정기 변경(사본 안, 관측용)\n",
                       "검증자": str(R / "verify_subject_v3.py"), "씨앗": str(seed) if seed else str(repo / subject),
                       "보고경로": str(report), "변형": variant}}
    body["inputs"]["러너본문"] = body["inputs"]["러너본문"].replace(
        '"/Users/kangkukjin/Desktop/AI/indiebizOS"', repr(str(repo)))
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("program", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--repo", type=Path, default=ROOT)
    ap.add_argument("--subject", default="backend/test_repair_training_subject_copy.py")
    ap.add_argument("--seed", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--variant", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    variant = json.loads(args.variant.read_text()) if args.variant else None
    body = build_request(args.program, args.report, repo=args.repo, subject=args.subject, seed=args.seed, variant=variant)
    if args.check:
        body["check"] = True
    args.output.write_text(json.dumps(body, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
