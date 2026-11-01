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
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_109회차"
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


BASELINE = load("ls109_baseline", "baseline_research_planning.py")
CANDIDATE = load("ls109_candidate", "candidate_research_planning.py")
META = read(HERE / "start.json")
CASES = read(HERE / "cases.json")
DEADLINE = datetime.fromisoformat(META["deadline"]).timestamp()
for name, expected in META["frozen_files"].items():
    assert sha(HERE / name) == expected
assert sha(HERE / "candidate_research_planning.py") == META["candidate_sha256"]
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
    task = "training_ls109_" + directory.name
    agent_id = "ls109_" + directory.name
    controller = None
    with (directory / "console.log").open("w") as console, contextlib.redirect_stdout(console), contextlib.redirect_stderr(console), actor_context(agent_id=agent_id, task_id=task, origin="training"), capture_usage() as usage:
        EpisodeLogger.start_episode("상상훈련109 " + directory.name, case["request"], task_id=task)
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
                phase = ("review" if index == 0 else "correction") if arm == "C" else "correction" if arm == "C_recovered" else "plan_completion" if completion else "initial_framing"
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
    module = BASELINE if arm == "A" else CANDIDATE
    return module.prepare(agent, copy.deepcopy(frame), text, supervisor=controller,
                          project_path=str(directory), previous_plan=previous,
                          validate_framing=validate_framing_focus)


def review(case, agent, controller, directory):
    source = OUTPUT / (case["id"] + "_B")
    original = read(source / "framing.json")
    candidate = {k: v for k, v in original.items() if k != "_research_plan"}
    candidate["research_plan"] = original["_research_plan"]["body"]
    payload = {"user_request": case["request"], "prior_user_request": case.get("prior_request"), "candidate": candidate}
    dump(directory / "review_input.json", payload)
    failed = OUTPUT / (case["id"] + "_C")
    if directory.name.endswith("_C_recovered"):
        raw = (failed / "call_0_response.txt").read_text()
        dump(directory / "reused_review.json", {"source": str(failed), "response_sha256": sha(failed / "call_0_response.txt")})
    else:
        raw = controller.plan(json.dumps(payload, ensure_ascii=False), (HERE / "review_system.txt").read_text(), completion=True)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    result = json.loads(cleaned)
    assert isinstance(result, dict) and isinstance(result.get("issues"), list)
    assert len(result["issues"]) <= 4
    text = json.dumps(candidate, ensure_ascii=False)
    for issue in result["issues"]:
        assert all(isinstance(issue.get(k), str) and issue[k].strip() for k in ["field", "quote", "basis", "reason", "correction"])
        # Quotes may contain newlines, so compare to actual values, not JSON escape representation.
        assert issue["quote"] in text or issue["quote"] in candidate["research_plan"]
    dump(directory / "review.json", result)
    if not result["issues"]:
        return original
    prompt = (source / "call_0_input.txt").read_text()
    prompt += "\n\n아래는 방금 작성한 초안과 별도 검토의 지적이다. 지적도 오류일 수 있으니 원문과 대조하라.\n"
    prompt += "성립하는 지적과 그에 의존하는 필드만 고치고 나머지 유효한 목적·방법·범위를 보존한다. 새 조사나 요구를 추가하지 않는다.\n"
    prompt += "형식은 앞서 요구한 전체 계획 JSON이다. research_plan은 최종 본문만, 저장 영수증은 반환하지 않는다.\n"
    prompt += json.dumps({"candidate": candidate, "review": result}, ensure_ascii=False)
    raw = controller.plan(prompt, agent._supervisor_prompt, completion=True)
    corrected = agent._parse_response(raw)
    validate_framing_focus(corrected)
    assert corrected.get("deep_research") is True and not corrected.get("needs_clarification")
    body = corrected.pop("research_plan")
    assert isinstance(body, str) and 0 < len(body) <= 32000
    assert BASELINE.GUIDE not in json.dumps(corrected, ensure_ascii=False) + body
    corrected["_research_plan"] = BASELINE.persist(body, (HERE / "deep_research.md").read_text(), str(directory), original["_research_plan"])
    return corrected


recover = "--recover" in sys.argv
selected = set(x for x in sys.argv[1:] if x != "--recover") or {c["id"] for c in CASES}
for index, case in enumerate(CASES):
    if case["id"] not in selected:
        continue
    if recover:
        run(case, "C_recovered", lambda a, c, d: review(case, a, c, d))
        continue
    run(case, "S", lambda a, c, d: seed(case, a, c, d))
    for arm in (["A", "B"] if index % 2 == 0 else ["B", "A"]):
        run(case, arm, lambda a, c, d, arm=arm: planning(case, arm, a, c, d))
    run(case, "C", lambda a, c, d: review(case, a, c, d))
