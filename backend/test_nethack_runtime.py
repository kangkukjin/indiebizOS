"""Experiment regressions: interruption, observation reuse and terminal evidence."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path

import pytest


def load(name):
    path = Path(__file__).resolve().parents[1] / "data/scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load("nethack_runtime")
client_module = load("nethack_client")


def observation(hp=41, turn=10, msg="", depth=16, conditions="", terminal=False):
    text = f"message:\n{msg}\n\nlanguage observation:\nroom\n\ncursor:\nYourself (x=5, y=5)\n\nmap:\n @ \n"
    if not terminal:
        text += f"Dlvl:{depth} HP:{hp}(41) Xp:5/189 T:{turn} {conditions}\n"
    return {"text": {"long_term_context": text, "short_term_context": "inventory"}}


class Environment:
    max_steps = 100

    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.current = observation()

    def reset(self, seed):
        return self.current, {}

    def get_stats(self):
        s = runtime.state(self.current)
        return {"depth": s["depth"] or 0, "time": s["turn"] or 0, "score": 123}

    def check_action_validity(self, action):
        return "esc" if action == "unknown" else action

    def step(self, action):
        self.calls.append(action)
        self.current, done = self.responses.pop(0)
        return self.current, 0, done, False, {}


def game(tmp_path, responses):
    return runtime.Game(Environment(responses), 0, tmp_path / "run")


@pytest.mark.parametrize("obs,reason", [
    (observation(hp=30, turn=11), "damage"),
    (observation(msg="In what direction?"), "prompt"),
    (observation(msg="It's solid stone."), "blocked"),
    (observation(turn=11, conditions="Blind"), "status_change"),
])
def test_batch_stops_before_next_action(tmp_path, obs, reason):
    g = game(tmp_path, [(obs, False)])
    result = g.step(["east", "east", "east"])
    assert result["stop_reason"] == reason
    assert result["remaining"] == ["east", "east"]
    assert g.env.calls == ["east"]
    g.log.close()


def test_prompt_sequence_still_stops_on_damage(tmp_path):
    g = game(tmp_path, [(observation(msg="In what direction?"), False),
                        (observation(hp=30, turn=11), False)])
    result = g.step(["fight", "east", "east"], stop_on=["damage", "blocked", "status_change"])
    assert g.env.calls == ["fight", "east"]
    assert result["remaining"] == ["east"]
    g.log.close()


def test_invalid_and_known_blocked_do_not_advance_game(tmp_path):
    g = game(tmp_path, [(observation(msg="It's solid stone."), False)])
    assert g.step(["unknown"])["stop_reason"] == "invalid_action"
    assert g.step(["east"])["stop_reason"] == "blocked"
    assert g.step(["east"])["stop_reason"] == "known_blocked"
    assert g.env.calls == ["east"]
    assert g.invalid == 1
    g.log.close()


def test_terminal_preserves_live_state_and_refuses_stale_action(tmp_path):
    g = game(tmp_path, [(observation(hp=9, turn=11), False),
                        (observation(msg="Killed by a raven", terminal=True), True)])
    old = g.revision
    g.step(["east"])
    assert g.step(["east"], expected_revision=old)["stop_reason"] == "stale_observation"
    result = g.step(["east", "south"])
    assert result["stop_reason"] == "done" and result["remaining"] == ["south"]
    final = json.loads((g.run_dir / "final.json").read_text())
    assert final["last_live"]["state"]["hp"] == 9
    assert final["last_live"]["state"]["turn"] == 11
    assert final["progress"]["time"] == 0
    assert not g.step(["east"])["executed"]
    with pytest.raises(FileExistsError):
        runtime.Game(Environment([]), 0, g.run_dir)
    g.log.close()


def test_blind_look_and_recent_prayer_require_explicit_risk(tmp_path):
    g = game(tmp_path, [(observation(hp=41, turn=13, msg="You begin praying"), False)])
    g.step(["y"])
    assert g.step(["pray"])["stop_reason"] == "recent_prayer_requires_explicit_risk"
    g.obs = observation(hp=9, turn=14, conditions="Blind")
    assert g.step(["look"])["stop_reason"] == "blind_look_costs_turn_use_observe"
    assert len(g.env.calls) == 1
    g.env.responses = [(observation(hp=4, turn=15, conditions="Blind"), False)]
    assert g.step(["look"], allow_risk=True)["stop_reason"] == "damage"
    g.log.close()


def connect(client, g, monkeypatch):
    requests = []
    def request(payload):
        requests.append(payload)
        if payload["op"] == "observe":
            return g.view()
        return g.step(payload["actions"], payload.get("tag", ""),
                      expected_revision=payload.get("expected_revision"),
                      stop_on=payload.get("stop_on"), allow_risk=payload.get("allow_risk", False))
    monkeypatch.setattr(client, "request", request)
    return requests


def test_cached_observation_and_external_change_conflict(tmp_path, monkeypatch):
    g = game(tmp_path, [(observation(turn=11), False)])
    client = client_module.Client(tmp_path / "cache.json")
    requests = connect(client, g, monkeypatch)
    client.observe()
    assert client.observe()["cached"]
    assert len(requests) == 1
    g.step(["east"])  # Another client changes the game.
    result = client.step(["south"])
    assert result["stop_reason"] == "stale_observation"
    assert g.env.calls == ["east"]
    assert client.observe()["status"]["revision"] == g.revision
    g.log.close()


def test_rest_checks_low_hp_before_acting_and_damage_before_reengraving(tmp_path, monkeypatch):
    g = game(tmp_path, [(observation(hp=3, turn=11), False)])
    g.obs = observation(hp=9)
    client = client_module.Client(tmp_path / "cache.json")
    connect(client, g, monkeypatch)
    client.rest(41, hpmin=12, engrave=True)
    assert not g.env.calls
    g.obs = observation(hp=20)
    client.observe(fresh=True)
    result = client.rest(41, hpmin=12, engrave=True)
    assert result["stop_reason"] == "damage"
    assert g.env.calls == ["look"]
    g.log.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
