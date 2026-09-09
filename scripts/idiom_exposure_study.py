#!/usr/bin/env python3
"""Paired randomized comparison of the current three always-exposed idioms.

prepare (no model calls), validate, then run. Immutable prompts, live body snapshot,
fresh model process per attempt, fresh seeded data per execution, serial timing.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import subprocess
import tempfile
import time
from idiom_exposure_cases import CASES, GOLD, INLINE

ARMS = ("hidden", "exposed")
DEFAULT = ROOT / "outputs/idiom_exposure_2026_09_09_v1"


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out):
    if (out / "manifest.json").exists():
        raise ValueError("Existing experiment is immutable; use another --out")
    from ibl_access import build_environment, _idioms_block
    from model_resolver import resolve
    from providers.claude_code import find_claude_binary

    con = sqlite3.connect(f"file:{ROOT}/data/ibl_usage.db?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    registry = [
        dict(r)
        for r in con.execute(
            "SELECT id,alias,ibl_code,intent,signature,returns FROM ibl_examples WHERE always_on=1 AND COALESCE(alias,'')!='' ORDER BY id"
        )
    ]
    assert {r["alias"] for r in registry} == {
        "원장에누적",
        "위치마다읽기",
        "최신범위읽기",
    }
    current = _idioms_block(None)
    full = build_environment()
    assert current in full
    base = (
        (ROOT / "data/common_prompts/base_prompt_v6.md").read_text()
        + "\n"
        + full.replace(current, "")
    )
    # This is a code-composition test, not the entire autonomous application.
    header = (
        '주어진 작업을 수행하는 IBL 프로그램을 작성하라. 응답은 JSON {"code":"IBL 코드"} 하나다. '
        "정답에 특정 함수나 작성 방식은 없다. 요구를 충족하는 코드를 자유롭게 구성하라. "
        "코드는 외부 실행기가 실행하며, 첫 실패 때 실행 결과를 받고 한 번 수정할 수 있다. "
        "작업 파일은 격리 폴더 안에 있다. 상대 경로를 사용하고 내용을 지어내지 말고 읽어서 처리하라. "
        "실행 가능한 기본 액션은 self:read, self:file_find, self:grep, self:list, self:edit, self:write, "
        "self:ledger와 table의 결정론적 변환·each다. 함수·변수·조건·반복 등 기존 IBL 문법도 사용 가능하다. "
        "외부 네트워크·셸·AI 호출·운영 기억 검색은 이 격리 실험에서 실행되지 않는다. "
        "아래 전체 참고서의 다른 액션이 이 범위를 넓히지 않는다. "
        "JSON 결과 파일은 행 배열 또는 items 봉투 모두 허용한다.\n\n"
    )
    for arm in ARMS:
        p = out / "prompts" / f"{arm}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            header + base + ("\n" + current if arm == "exposed" else ""),
            encoding="utf-8",
        )
    config = resolve("execution")
    assert config["provider"] == "claude_code"
    rng = random.Random(2026090901)
    pairs = [
        {"case": c["id"], "repeat": rep, "seed": 2026090900 + rep * 101 + i}
        for rep in range(3)
        for i, c in enumerate(CASES)
    ]
    rng.shuffle(pairs)
    schedule = []
    for i, pair in enumerate(pairs):
        order = list(ARMS if i % 2 == 0 else reversed(ARMS))
        schedule.extend([dict(pair, arm=arm) for arm in order])
    manifest = {
        "version": 1,
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider": config["provider"],
        "model": config["model"],
        "effort": "high",
        "repeats": 3,
        "max_repairs": 1,
        "model_timeout_s": 180,
        "worker_timeout_s": 30,
        "cli_version": subprocess.check_output(
            [find_claude_binary(), "--version"], text=True
        ).strip(),
        "arms": list(ARMS),
        "cases": CASES,
        "schedule": schedule,
        "seed": 2026090901,
        "registry_policy": "Same three callable bodies in BOTH arms; only the live introduction block differs. No stored-memory retrieval.",
        "scope": "Single IBL program generation with full current grammar/catalog plus base prompt; fresh-session one repair. Not the complete app agent loop.",
        "primary": "Intention-to-treat paired exposed-minus-hidden: quality, total wall time, all-model output tokens, input/cache buckets. No conditioning on observed use.",
        "subgroups": "direct, embedded, counter separate; applicable=direct+embedded; counter measures inappropriate use and exposure tax.",
        "timing": "One model process at a time; adjacent paired conditions; order counterbalanced; startup and API duration separately retained.",
        "inference": "Paired descriptive estimates and task-cluster bootstrap; 9 task templates are not a population workload sample.",
        "frozen_rules": "Do not tune tasks, prompts, engine or idioms after model generation starts. Missing usage is not zero. Transport failures remain in results.",
        "prompt_chars": {
            a: len((out / "prompts" / f"{a}.txt").read_text()) for a in ARMS
        },
        "prompt_sha256": {a: sha(out / "prompts" / f"{a}.txt") for a in ARMS},
        "source_sha256": {
            p.name: sha(p)
            for p in [
                Path(__file__),
                ROOT / "scripts/idiom_exposure_cases.py",
                ROOT / "scripts/idiom_exposure_worker.py",
            ]
        },
    }
    dump(out / "registry.json", registry)
    dump(out / "manifest.json", manifest)
    return manifest


def execute(out, code, case_id, seed):
    start = time.perf_counter()
    req = {
        "code": code,
        "case_id": case_id,
        "seed": seed,
        "registry": json.loads((out / "registry.json").read_text()),
    }
    try:
        p = subprocess.run(
            [sys.executable, str(ROOT / "scripts/idiom_exposure_worker.py")],
            input=json.dumps(req),
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=30,
        )
        result = (
            json.loads(p.stdout)
            if p.returncode == 0
            else {
                "quality_ok": False,
                "verdict": "worker_error",
                "error": p.stderr[-1600:],
            }
        )
    except (subprocess.TimeoutExpired, ValueError) as exc:
        result = {
            "quality_ok": False,
            "verdict": "worker_error",
            "error": type(exc).__name__,
        }
    result["worker_wall_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return result


def validate(out):
    rows = []
    for case in CASES:
        for label, code in [
            ("named", GOLD[case["id"]]),
            ("inline", INLINE[case["id"]]),
        ]:
            result = execute(out, code, case["id"], 2026090911)
            rows.append(
                {
                    "case": case["id"],
                    "solution": label,
                    "code": code,
                    "execution": result,
                }
            )
            print(
                case["id"],
                label,
                result["quality_ok"],
                result["verdict"][:350],
                flush=True,
            )
    # Deliberately wrong answers check that the oracle detects semantic mismatches.
    negative = [
        ("counter_latest", GOLD["direct_latest"]),
        ("direct_context", '[self:read]{path:"locations.json"}'),
        (
            "counter_ledger",
            '[self:ledger]{op:"append",path:"registry.json",target:"records",items_file:"updates.json"}',
        ),
    ]
    for case, code in negative:
        result = execute(out, code, case, 2026090911)
        rows.append(
            {
                "case": case,
                "solution": "wrong",
                "code": code,
                "execution": result,
            }
        )
        print(case, "wrong", result["quality_ok"], flush=True)
    ok = all(
        r["execution"]["quality_ok"] == (r["solution"] != "wrong")
        for r in rows
    )
    dump(out / "validation.json", {"ok": ok, "rows": rows})
    return ok


def call_model(out, manifest, arm, user):
    from providers.claude_code import (
        find_claude_binary,
        load_oauth_token_from_central_config,
    )

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    token = load_oauth_token_from_central_config()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="exposure_model_") as cwd:
        cmd = [
            find_claude_binary(),
            "-p",
            "--safe-mode",
            "--tools",
            "",
            "--no-session-persistence",
            "--output-format",
            "json",
            "--model",
            manifest["model"],
            "--effort",
            manifest["effort"],
            "--system-prompt-file",
            str(out / "prompts" / f"{arm}.txt"),
        ]
        try:
            p = subprocess.run(
                cmd,
                input=user,
                text=True,
                capture_output=True,
                cwd=cwd,
                env=env,
                timeout=manifest["model_timeout_s"],
            )
            data = json.loads(p.stdout)
            result = {
                k: data.get(k)
                for k in (
                    "result",
                    "usage",
                    "modelUsage",
                    "duration_ms",
                    "duration_api_ms",
                    "total_cost_usd",
                    "is_error",
                    "subtype",
                    "num_turns",
                )
            }
            result["returncode"] = p.returncode
        except (subprocess.TimeoutExpired, ValueError) as exc:
            result = {"error": type(exc).__name__}
    result["wall_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return result


def trial(out, manifest, spec):
    key = f'{spec["case"]}_{spec["repeat"]}_{spec["arm"]}'
    path = out / "trials" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    case = next(c for c in manifest["cases"] if c["id"] == spec["case"])
    user = "작업: " + case["task"]
    record = dict(
        spec,
        id=key,
        group=case["group"],
        attempts=[],
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )
    from runtime_utils import parse_first_json

    start = time.perf_counter()
    for attempt in range(manifest["max_repairs"] + 1):
        model = call_model(out, manifest, spec["arm"], user)
        code = ""
        if (
            model.get("error")
            or model.get("is_error")
            or model.get("returncode")
        ):
            ex = {"quality_ok": False, "verdict": "model_transport_error"}
        else:
            try:
                payload = parse_first_json(model.get("result") or "")
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("code"), str
                ):
                    raise ValueError("JSON code missing")
                code = payload["code"]
                ex = execute(out, code, spec["case"], spec["seed"])
            except (ValueError, TypeError) as exc:
                ex = {"quality_ok": False, "verdict": str(exc)}
        a = {
            "model": model,
            "code": code,
            "execution": ex,
            "written_aliases": re.findall(r"\[fn:\s*([^\]\s]+)\]", code),
        }
        record["attempts"].append(a)
        dump(out / "attempts" / f"{key}_{attempt}.json", a)
        if ex["quality_ok"] or ex["verdict"] == "model_transport_error":
            break
        feedback = json.dumps(
            {"verdict": ex["verdict"], "result": ex.get("result")},
            ensure_ascii=False,
        )[:6500]
        user += (
            "\n직전 코드:\n"
            + code
            + "\n실행 결과:\n"
            + feedback
            + "\n같은 초기 파일에서 다시 실행한다. 요구를 충족하도록 전체 프로그램 JSON을 수정하라."
        )
    record["quality_ok"] = record["attempts"][-1]["execution"]["quality_ok"]
    record["total_wall_ms"] = round((time.perf_counter() - start) * 1000, 3)
    dump(path, record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["prepare", "validate", "run"])
    p.add_argument("--out", type=Path, default=DEFAULT)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    out = a.out.resolve()
    if a.mode == "prepare":
        m = prepare(out)
        print(
            json.dumps(
                {
                    "out": str(out),
                    "prompts": m["prompt_chars"],
                    "trials": len(m["schedule"]),
                },
                ensure_ascii=False,
            )
        )
        return
    if a.mode == "validate":
        sys.exit(0 if validate(out) else 1)
    m = json.loads((out / "manifest.json").read_text())
    assert json.loads((out / "validation.json").read_text())["ok"]
    for filename, digest in m["source_sha256"].items():
        assert (
            sha(ROOT / "scripts" / filename) == digest
        ), f"Source drift: {filename}"
    for arm, digest in m["prompt_sha256"].items():
        assert sha(out / "prompts" / f"{arm}.txt") == digest
    todo = m["schedule"][: a.limit] if a.limit else m["schedule"]
    for i, spec in enumerate(todo, 1):
        r = trial(out, m, spec)
        print(
            json.dumps(
                {
                    "n": i,
                    "of": len(todo),
                    "id": r["id"],
                    "ok": r["quality_ok"],
                    "attempts": len(r["attempts"]),
                    "written": r["attempts"][0]["written_aliases"],
                    "wall_s": round(r["total_wall_ms"] / 1000, 2),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
