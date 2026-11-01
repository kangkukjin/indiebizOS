"""현재 실제 의식과 계획 저장 경로를 이용한 고정 A/B/C 비교. 운영 파일 변경 없음."""
import contextlib
import copy
import hashlib
import importlib.util
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_110회차"
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import research_planning as live_planning  # noqa: E402
from consciousness_agent import ConsciousnessAgent, validate_framing_focus  # noqa: E402
from conscious_supervisor import Supervisor  # noqa: E402
from episode_logger import EpisodeLogger  # noqa: E402
from model_call_context import capture_usage, summarize_usage  # noqa: E402
from model_resolver import resolve  # noqa: E402
from thread_context import actor_context  # noqa: E402


def read(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = load("ls110_baseline", "baseline_research_planning.py")
GATE = load("ls110_gate", "five_principle_gate.py")
META = read(HERE / "start.json")
CASES = read(HERE / "cases.json")
DEADLINE = datetime.fromisoformat(META["deadline"]).timestamp()
for name, expected in META["frozen_files"].items():
    assert sha(HERE / name) == expected
assert sha(HERE / "five_principle_gate.py") == META["candidate_sha256"]
for name, expected in META["source_sha256"].items():
    assert sha(ROOT / name) == expected


def forbidden(*args, **kwargs):
    raise RuntimeError("실험은 규정·계획 작성뿐이며 실행 도구는 연결하지 않음")


def make_prior(directory):
    frame = read(HERE / "prior_framing.json")
    plan = frame["_research_plan"]
    path = directory / "outputs/research_plans/prior/research_plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan["body"])
    plan["path"] = str(path)
    assert sha(path) == plan["sha256"]
    return frame


def run(case, arm, action):
    directory = OUTPUT / (case["id"] + "_" + arm)
    directory.mkdir(exist_ok=False)
    record = {"case": case["id"], "arm": arm, "started": time.time(),
              "status": "running", "origin": "training", "runner_sha256": sha(Path(__file__))}
    dump(directory / "receipt.json", record)
    task = "training_ls110_" + directory.name
    agent_id = "ls110_" + directory.name
    controller = None
    with (directory / "console.log").open("w") as console, contextlib.redirect_stdout(console), contextlib.redirect_stderr(console), actor_context(agent_id=agent_id, task_id=task, origin="training"), capture_usage() as usage:
        EpisodeLogger.start_episode("상상훈련110 " + directory.name, case["request"], task_id=task)
        record["episode_id"] = EpisodeLogger.current().episode_id
        try:
            agent = ConsciousnessAgent()
            descriptor = resolve("consciousness")
            record["model"] = {k: descriptor.get(k) for k in ["provider", "model", "tier", "source"]}
            ai = SimpleNamespace(agent_id=agent_id, project_path=str(directory), tools=[], _custom_execute_tool=forbidden)
            controller = Supervisor(SimpleNamespace(ai=ai), case["request"], [], agent_id, task, directory=directory / "supervision")
            original = controller.plan
            calls = []

            def observed(prompt, system, revision=None, *, completion=False):
                if time.time() + 180 > DEADLINE:
                    raise RuntimeError("상한 잔여 부족: 새 모델 호출 거절")
                index = len(calls)
                phase = getattr(controller, "experiment_phase", "plan_completion" if completion else "initial_framing")
                row = {"index": index, "phase": phase, "started": time.time(),
                       "input_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                       "system_sha256": hashlib.sha256(system.encode()).hexdigest()}
                calls.append(row)
                (directory / f"call_{index}_input.txt").write_text(prompt)
                (directory / f"call_{index}_system.txt").write_text(system)
                dump(directory / "calls.json", calls)
                response = original(prompt, system, revision, completion=completion)
                (directory / f"call_{index}_response.txt").write_text(response)
                row.update(ended=time.time(), response_sha256=hashlib.sha256(response.encode()).hexdigest())
                dump(directory / "calls.json", calls)
                return response

            controller.plan = observed
            result = action(agent, controller, directory)
            dump(directory / "framing.json", result)
            plan = result.get("_research_plan")
            if plan:
                assert Path(plan["path"]).read_text() == plan["body"]
                (directory / "research_plan.md").write_text(plan["body"])
                assert sha(directory / "research_plan.md") == plan["sha256"]
            record.update(status="completed", calls=len(calls), has_plan=bool(plan))
        except Exception as exc:
            record.update(status="failed", error=str(exc), traceback=traceback.format_exc())
        finally:
            if controller:
                controller.close()
            record["usage"] = summarize_usage(usage)
            record["ended"] = time.time()
            record["seconds"] = record["ended"] - record["started"]
            dump(directory / "receipt.json", record)
            EpisodeLogger.end_episode()
    print(json.dumps({k: record.get(k) for k in ["case", "arm", "status", "seconds", "calls", "error"]}, ensure_ascii=False), flush=True)
    if record["status"] != "completed":
        raise RuntimeError(record["error"])


def seed(case, agent, controller, directory):
    history = []
    previous = None
    if case.get("prior_request"):
        prior = make_prior(directory)
        previous = prior["_research_plan"]
        history = [{"role": "user", "content": case["prior_request"]},
                   {"role": "assistant", "content": json.dumps(prior, ensure_ascii=False)}]

    def intercept(agent_, framing, input_text, **kwargs):
        (directory / "base_input.txt").write_text(input_text)
        return framing

    original = live_planning.prepare
    live_planning.prepare = intercept
    try:
        result = agent.process(case["request"], history, "", agent_name="연구계획 비교",
                               agent_role="사용자 요청의 문제·목적·연구계획을 구성한다.",
                               supervisor=controller, project_path=str(directory), previous_research_plan=previous)
        assert result and result.get("deep_research") is True and not result.get("needs_clarification")
        return result
    finally:
        live_planning.prepare = original


def planning(case, arm, agent, controller, directory):
    source = OUTPUT / (case["id"] + "_S")
    frame = read(source / "framing.json")
    text = (source / "base_input.txt").read_text()
    previous = None
    if case.get("prior_request"):
        previous = make_prior(directory)["_research_plan"]
        text = text.replace(str(source), str(directory))
        frame = json.loads(json.dumps(frame, ensure_ascii=False).replace(str(source), str(directory)))
    module = BASELINE
    return module.prepare(agent, copy.deepcopy(frame), text, supervisor=controller,
                          project_path=str(directory), previous_plan=previous,
                          validate_framing=validate_framing_focus)


def gate(case, agent, controller, directory):
    source = OUTPUT / (case["id"] + "_A")
    original = read(source / "framing.json")
    candidate = {k: v for k, v in original.items() if not k.startswith("_")}
    candidate["research_plan"] = original["_research_plan"]["body"].split("\n", 1)[1].rstrip()
    dump(directory / "initial_candidate.json", candidate)

    def payload(value):
        return {"user_request": case["request"], "prior_user_request": case.get("prior_request"), "candidate": value}

    def review_fn(value, revision):
        controller.experiment_phase = "five_principles_" + str(revision)
        return controller.plan(json.dumps(payload(value), ensure_ascii=False),
                               (HERE / "audit_system.txt").read_text(), completion=True)

    def validate(value):
        assert isinstance(value, dict) and value.get("deep_research") is True
        assert not value.get("needs_clarification") and not value.get("needs_repair")
        body = value.get("research_plan")
        assert isinstance(body, str) and body.strip() and len(body) <= 32000
        assert BASELINE.GUIDE not in json.dumps(value, ensure_ascii=False)
        validate_framing_focus(value)

    def repair_fn(value, audit):
        controller.experiment_phase = "repair"
        data = {**payload(value), "audit": audit}
        prompt = (HERE / "repair_instruction.txt").read_text()
        prompt += "\n<research_planning_guide>\n" + (HERE / "deep_research.md").read_text()
        prompt += "\n</research_planning_guide>\n" + json.dumps(data, ensure_ascii=False)
        raw = controller.plan(prompt, agent._supervisor_prompt, completion=True)
        result = agent._parse_response(raw)
        if isinstance(result, dict) and isinstance(result.get("research_plan"), str):
            result["research_plan"] = result["research_plan"].rstrip()
        dump(directory / "repaired_candidate.json", result)
        return result

    events = []
    def record(kind, value):
        events.append({"kind": kind, "at": time.time(), "value": value})
        dump(directory / "gate_events.json", events)

    outcome = GATE.run(candidate, [case["request"], case.get("prior_request", "")],
                       review_fn, repair_fn, validate, record)
    dump(directory / "gate_outcome.json", outcome)
    final = copy.deepcopy(outcome["candidate"])
    body = final.pop("research_plan")
    (directory / "candidate_plan.md").write_text(body)
    if outcome["release_allowed"]:
        assert GATE.releasable(outcome["candidate"], outcome["audits"][-1])
        final["_research_plan"] = BASELINE.persist(body, (HERE / "deep_research.md").read_text(),
                                                   str(directory), original["_research_plan"])
    final["_plan_review"] = {k: v for k, v in outcome.items() if k != "candidate"}
    return final


selected = set(sys.argv[1:] or [c["id"] for c in CASES])
for case in CASES:
    if case["id"] not in selected:
        continue
    run(case, "S", lambda a, c, d: seed(case, a, c, d))
    run(case, "A", lambda a, c, d: planning(case, "A", a, c, d))
    run(case, "R", lambda a, c, d: gate(case, a, c, d))
