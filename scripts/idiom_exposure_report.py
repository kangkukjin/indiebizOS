"""Analyze immutable exposure trials without selecting only successful/use cases."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict


def known_sum(values):
    return (
        sum(values)
        if values and all(isinstance(v, (int, float)) for v in values)
        else None
    )


def tokens(model):
    usage = model.get("modelUsage")
    if (
        isinstance(usage, dict)
        and usage
        and all(isinstance(v, dict) for v in usage.values())
    ):
        fields = {
            "output_tokens": "outputTokens",
            "thinking_tokens": "thinkingTokens",
            "input_new": "inputTokens",
            "input_cache_create": "cacheCreationInputTokens",
            "input_cache_read": "cacheReadInputTokens",
        }
        result = {
            label: known_sum([u.get(key) for u in usage.values()])
            for label, key in fields.items()
        }
        result["usage_source"] = "modelUsage sum; distinct models"
    else:
        u = model.get("usage") or {}
        fields = {
            "output_tokens": "output_tokens",
            "input_new": "input_tokens",
            "input_cache_create": "cache_creation_input_tokens",
            "input_cache_read": "cache_read_input_tokens",
        }
        result = {label: u.get(key) for label, key in fields.items()}
        result["thinking_tokens"] = (u.get("output_tokens_details") or {}).get(
            "thinking_tokens"
        )
        result["usage_source"] = "provider aggregate; model split unavailable"
    result["input_total"] = known_sum(
        [
            result[k]
            for k in ["input_new", "input_cache_create", "input_cache_read"]
        ]
    )
    return result


def flatten(trial, names):
    attempts = trial["attempts"]
    usages = [tokens(a["model"]) for a in attempts]
    raw_aliases = [
        set(
            re.findall(r"\[fn:\s*([^\]\s]+)\]", a["model"].get("result") or "")
        )
        & names
        for a in attempts
    ]
    result = {k: trial[k] for k in ["id", "case", "group", "repeat", "arm"]}
    result.update(
        first_ok=bool(attempts[0]["execution"]["quality_ok"]),
        final_ok=bool(trial["quality_ok"]),
        repairs=len(attempts) - 1,
        first_named=bool(set(attempts[0]["written_aliases"]) & names),
        first_raw_named=bool(raw_aliases[0]),
        first_code_parsed=bool(attempts[0]["code"]),
        first_executed_named=bool(
            set(
                attempts[0]["execution"]
                .get("observed", {})
                .get("fn_calls", [])
            )
            & names
        ),
        any_named=any(set(a["written_aliases"]) & names for a in attempts),
        any_raw_named=any(raw_aliases),
        any_executed_named=any(
            set(a["execution"].get("observed", {}).get("fn_calls", [])) & names
            for a in attempts
        ),
        wall_s=trial["total_wall_ms"] / 1000,
        model_wall_s=sum(a["model"]["wall_ms"] for a in attempts) / 1000,
        api_s=known_sum([a["model"].get("duration_api_ms") for a in attempts]),
        engine_ms=known_sum(
            [a["execution"].get("runtime_ms") for a in attempts]
        ),
        first_output_tokens=usages[0]["output_tokens"],
        first_wall_s=attempts[0]["model"]["wall_ms"] / 1000,
        first_input_total=usages[0]["input_total"],
        reported_cost_usd=known_sum(
            [a["model"].get("total_cost_usd") for a in attempts]
        ),
        first_code_chars=len(attempts[0]["code"]),
        final_verdict=attempts[-1]["execution"]["verdict"],
    )
    if result["api_s"] is not None:
        result["api_s"] /= 1000
    for key in (
        "output_tokens",
        "thinking_tokens",
        "input_total",
        "input_new",
        "input_cache_create",
        "input_cache_read",
    ):
        result[key] = known_sum([u[key] for u in usages])
    result["nonthinking_output_tokens"] = (
        result["output_tokens"] - result["thinking_tokens"]
        if result["output_tokens"] is not None
        and result["thinking_tokens"] is not None
        else None
    )
    return result


def group_stats(rows):
    result = {
        "n": len(rows),
        "first_ok": sum(r["first_ok"] for r in rows),
        "final_ok": sum(r["final_ok"] for r in rows),
        "first_named": sum(r["first_named"] for r in rows),
        "first_executed_named": sum(r["first_executed_named"] for r in rows),
        "first_raw_named": sum(r["first_raw_named"] for r in rows),
        "first_code_parsed": sum(r["first_code_parsed"] for r in rows),
        "any_named": sum(r["any_named"] for r in rows),
        "any_executed_named": sum(r["any_executed_named"] for r in rows),
        "any_raw_named": sum(r["any_raw_named"] for r in rows),
        "repairs": sum(r["repairs"] for r in rows),
    }
    for key in (
        "wall_s",
        "model_wall_s",
        "api_s",
        "first_wall_s",
        "output_tokens",
        "thinking_tokens",
        "nonthinking_output_tokens",
        "first_output_tokens",
        "first_code_chars",
        "first_input_total",
        "input_total",
        "input_new",
        "input_cache_create",
        "input_cache_read",
        "reported_cost_usd",
    ):
        values = [r[key] for r in rows if r[key] is not None]
        result[key] = {
            "known_n": len(values),
            "sum": sum(values),
            "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
        }
    return result


def attempt_totals(trials):
    """Known usage is a lower bound when a killed process returned no usage."""
    usages = [tokens(a["model"]) for t in trials for a in t["attempts"]]
    result = {"attempts": len(usages)}
    for key in (
        "output_tokens",
        "thinking_tokens",
        "input_total",
        "input_new",
        "input_cache_create",
        "input_cache_read",
    ):
        values = [u[key] for u in usages if u[key] is not None]
        result[key] = {
            "known_attempts": len(values),
            "unknown_attempts": len(usages) - len(values),
            "known_sum_lower_bound": sum(values),
            "exact_total": sum(values) if len(values) == len(usages) else None,
        }
    return result


def paired(rows):
    pairs = defaultdict(dict)
    for r in rows:
        pairs[(r["case"], r["repeat"])][r["arm"]] = r
    complete = [v for v in pairs.values() if set(v) == {"hidden", "exposed"}]
    result = {"pairs": len(complete)}
    for key in ("first_ok", "final_ok"):
        result[key] = {
            label: sum(
                bool(p["hidden"][key]) == h and bool(p["exposed"][key]) == e
                for p in complete
            )
            for label, h, e in [
                ("both", True, True),
                ("hidden_only", True, False),
                ("exposed_only", False, True),
                ("neither", False, False),
            ]
        }
    for key in (
        "wall_s",
        "first_wall_s",
        "output_tokens",
        "input_total",
        "first_output_tokens",
        "first_input_total",
    ):
        usable = [
            p
            for p in complete
            if p["hidden"][key] is not None and p["exposed"][key] is not None
        ]
        changes = [p["exposed"][key] - p["hidden"][key] for p in usable]
        by_case = defaultdict(list)
        for p, delta in zip(usable, changes):
            by_case[p["hidden"]["case"]].append(delta)
        estimates = []
        rng = random.Random(902109)
        cases = list(by_case)
        if cases:
            for _ in range(5000):
                sampled = [rng.choice(cases) for _ in cases]
                estimates.append(
                    statistics.mean([x for c in sampled for x in by_case[c]])
                )
            estimates.sort()
        h = sum(p["hidden"][key] for p in usable)
        e = sum(p["exposed"][key] for p in usable)
        result[key] = {
            "known_pairs": len(usable),
            "mean_exposed_minus_hidden": (
                statistics.mean(changes) if changes else None
            ),
            "median_difference": (
                statistics.median(changes) if changes else None
            ),
            "aggregate_ratio": e / h if h else None,
            "task_cluster_bootstrap_95_mean_difference": (
                [estimates[125], estimates[4874]] if estimates else None
            ),
        }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    out = a.out
    trials = [
        json.loads(f.read_text())
        for f in sorted((out / "trials").glob("*.json"))
    ]
    names = {
        r["alias"] for r in json.loads((out / "registry.json").read_text())
    }
    rows = [flatten(t, names) for t in trials]
    manifest = json.loads((out / "manifest.json").read_text())
    summary = {
        "completed_trials": len(rows),
        "planned_trials": len(manifest["schedule"]),
        "groups": {},
        "cases": {},
        "idioms": {},
        "models": sorted(
            {
                name
                for t in trials
                for x in t["attempts"]
                for name in (x["model"].get("modelUsage") or {})
            }
        ),
    }
    for group in ("all", "applicable", "direct", "embedded", "counter"):
        subset = [
            r
            for r in rows
            if group == "all"
            or (group == "applicable" and r["group"] != "counter")
            or r["group"] == group
        ]
        summary["groups"][group] = {
            "arms": {
                arm: group_stats([r for r in subset if r["arm"] == arm])
                for arm in ("hidden", "exposed")
            },
            "paired": paired(subset),
        }
        ids = {r["id"] for r in subset}
        summary["groups"][group]["attempt_usage"] = {
            arm: attempt_totals(
                [t for t in trials if t["id"] in ids and t["arm"] == arm]
            )
            for arm in ("hidden", "exposed")
        }
    for case in sorted({r["case"] for r in rows}):
        subset = [r for r in rows if r["case"] == case]
        summary["cases"][case] = {
            "arms": {
                arm: group_stats([r for r in subset if r["arm"] == arm])
                for arm in ("hidden", "exposed")
            },
            "paired": paired(subset),
        }
    for name in sorted(names):
        cases = {c["id"] for c in manifest["cases"] if c["relevant"] == name}
        subset = [r for r in rows if r["case"] in cases]
        summary["idioms"][name] = {
            "arms": {
                arm: group_stats([r for r in subset if r["arm"] == arm])
                for arm in ("hidden", "exposed")
            },
            "paired": paired(subset),
        }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    # Preserve generated programs, usage and artifact verdicts without copying
    # the large nested engine transcript or any private reasoning text.
    evidence = []
    for trial in trials:
        row = {k: v for k, v in trial.items() if k != "attempts"}
        row["attempts"] = []
        for attempt in trial["attempts"]:
            model = {
                k: v for k, v in attempt["model"].items() if k != "result"
            }
            execution = {
                k: v for k, v in attempt["execution"].items() if k != "result"
            }
            raw = attempt["execution"].get("result")
            if isinstance(raw, dict):
                execution["runtime_success"] = raw.get("success")
                execution["runtime_error"] = raw.get("error")
            raw_aliases = re.findall(
                r"\[fn:\s*([^\]\s]+)\]", attempt["model"].get("result") or ""
            )
            if not attempt["code"]:
                model["unparsed_response"] = attempt["model"].get("result")
            row["attempts"].append(
                {
                    "code": attempt["code"],
                    "written_aliases": attempt["written_aliases"],
                    "raw_response_aliases": raw_aliases,
                    "model": model,
                    "execution": execution,
                }
            )
        evidence.append(row)
    (out / "compact_trials.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    if rows:
        with (out / "trial_metrics.csv").open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=list(rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
    compact = {
        g: {
            arm: {
                k: s[k]
                for k in [
                    "n",
                    "first_ok",
                    "final_ok",
                    "first_named",
                    "repairs",
                ]
            }
            for arm, s in data["arms"].items()
        }
        for g, data in summary["groups"].items()
    }
    print(
        json.dumps(
            {"n": len(rows), "groups": compact}, ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
