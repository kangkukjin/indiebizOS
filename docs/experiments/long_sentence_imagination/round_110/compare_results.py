"""사전 기준을 수동 판정과 전체 경로 실측치에 적용한다. 모델은 다시 호출하지 않는다."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


review = read("review.json")
evidence = read("evidence.json")
cases = read("cases.json")
rows = {(r["case"], r["arm"]): r for r in review["rows"]}
ranks = {"미충족": 0, "부분": 1, "충족": 2}
changes = []
for case in cases:
    cid = case["id"]
    a, r = rows[(cid, "A")], rows[(cid, "R")]
    old, new = ({x["id"] for x in row["defects"]} for row in [a, r])
    regression = [i + 1 for i, (x, y) in enumerate(zip(a["checks"], r["checks"]))
                  if ranks[y] < ranks[x]]
    principle_regression = [k for k in a["principles"]
                            if ranks[r["principles"][k]] < ranks[a["principles"][k]]]
    outcome = read("results/" + cid + "_R/gate_outcome.json")
    changes.append({"case": cid, "new_in_this_round": cid in {"N1", "N2"},
                    "removed": sorted(old - new), "added": sorted(new - old),
                    "remaining": sorted(old & new), "check_regression": regression,
                    "principle_regression": principle_regression,
                    "release_allowed": outcome["release_allowed"],
                    "improved": bool(old - new) and not new - old and not regression
                    and not principle_regression and outcome["release_allowed"]})
a, r = evidence["paths"]["A"], evidence["paths"]["R"]
token_ratio = (r["usage"]["input"] + r["usage"]["output"]) / (a["usage"]["input"] + a["usage"]["output"])
time_ratio = r["median_seconds"] / a["median_seconds"]
contracts = read("validation/gate_contract_tests.json")
gates = {
    "contract_tests": contracts["passed"] == 22,
    "four_results_recovered": len(changes) == 4,
    "improved_at_least_two": sum(c["improved"] for c in changes) >= 2,
    "improved_at_least_one_new": any(c["improved"] and c["new_in_this_round"] for c in changes),
    "no_new_important_regression": not any(c["added"] or c["check_regression"]
                                         or c["principle_regression"] for c in changes),
    "token_limit_2_5": token_ratio <= 2.5,
    "median_time_limit_2_5": time_ratio <= 2.5,
}
result = {"R_vs_A": {"cases": changes, "input_output_ratio": token_ratio,
                     "median_time_ratio": time_ratio, "gates": gates,
                     "decision": "eligible_for_confirmation" if all(gates.values()) else "reject"},
          "important_false_pass_cases": review["false_pass_cases"],
          "adoption": "none" if not all(gates.values()) else "pending_new_case_confirmation",
          "limits": "새 요청은 사전 task.md의 N1/N2만이다. 원문 대조는 비맹검 수동 판정이다. 미통과 차단은 사용 가능한 계획 개선으로 세지 않는다."}
(HERE / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
