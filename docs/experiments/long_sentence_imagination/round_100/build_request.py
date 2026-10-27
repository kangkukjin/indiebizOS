"""p1 요청 JSON 조립(100회차). 사용: build_request.py <ibl> <out.json> [--check] [--parallel N] [--variant 표지] [--n N] [--report 절대경로]
99회차 조립기와 같되 출력 폴더가 100회차이고 S7(스크립트 없는 순수 each) 입력 `목록`(1..N)·`N` 을 더 준다."""
import argparse, json
from pathlib import Path
R = Path(__file__).resolve().parent
ROOT = R.parents[3]
SUBJ = ROOT / "outputs/long_sentence_imagination/2026-10-28_100회차/subjects"
ap = argparse.ArgumentParser(); ap.add_argument("ibl"); ap.add_argument("out"); ap.add_argument("--check", action="store_true")
ap.add_argument("--parallel", type=int, default=1); ap.add_argument("--variant", default="기본"); ap.add_argument("--n", type=int, default=3000)
ap.add_argument("--report", default=None)
a = ap.parse_args()
names = ["s1_sequential.ibl", "s2_parallel.ibl", "s3_fail_midway.ibl", "s4_reuse.ibl", "s5_long_single.ibl", "s6_each_in_fn.ibl", "s7_reuse_pure.ibl"]
subjects = {f"s{n}": (SUBJ / name).read_text(encoding="utf-8").replace("parallel:$병렬", f"parallel:{a.parallel}") for n, name in enumerate(names, 1)}
body = {"code": Path(a.ibl).read_text(encoding="utf-8"),
        "inputs": {"러너본문": (R / "runner.py").read_text(encoding="utf-8"), "잠들기본문": (SUBJ / "sleeper.py").read_text(encoding="utf-8"),
                   "주제": subjects, "파일": str(SUBJ / "fixture.txt"), "병렬": a.parallel, "변형": a.variant,
                   "목록": list(range(1, a.n + 1)), "N": a.n,
                   "보고경로": a.report or str(ROOT / f"outputs/long_sentence_imagination/2026-10-28_100회차/trainer/p1_report_{a.variant}.json")}}
if a.check: body["check"] = True
Path(a.out).write_text(json.dumps(body, ensure_ascii=False))
print(a.out, len(body["code"]), "chars", "N", a.n)
