"""NetHack experiment boundary: guarded batches and durable terminal observations.

Game rules belong to this experiment, never to the IBL interpreter. The underlying
BALROG environment still owns actions, observations and scoring.
"""
import copy
import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path


DEFAULT_STOPS = frozenset({"damage", "prompt", "blocked", "status_change"})
BLOCKED = ("It's solid stone.", "It's a wall.", "This door is locked.",
           "You try to move the boulder, but in vain.", "You see no door there.",
           "You can't go down here.", "Nothing happens.", "You attack thin air.")


def state(obs):
    """Only observed state; no guessed HP/coordinates when terminal text replaces it."""
    text = obs["text"]["long_term_context"]
    hp = re.search(r"HP:(\d+)\((\d+)\)", text)
    turn = re.search(r"\bT:(\d+)([^\n]*)", text)
    xy = re.search(r"\(x=(\d+), y=(\d+)\)", text)
    depth = re.search(r"Dlvl:(\d+)", text)
    return {"hp": int(hp[1]) if hp else None, "max_hp": int(hp[2]) if hp else None,
            "turn": int(turn[1]) if turn else None,
            "conditions": turn[2].strip() if turn else None,
            "position": [int(xy[1]), int(xy[2])] if xy else None,
            "depth": int(depth[1]) if depth else None}


def message(obs):
    return obs["text"]["long_term_context"].split("language observation:")[0].removeprefix("message:").strip()


def prompt(obs):
    raw = obs.get("obs", {})
    misc = raw.get("misc", ()) if hasattr(raw, "get") else ()
    if len(misc) >= 3 and any(misc[:3]):
        return True
    msg = message(obs)
    return bool(re.search(r"In what direction\?|What do you want|\[[ynq]+\]|--More--|Pick .*:", msg))


class Game:
    def __init__(self, env, seed, run_dir):
        self.env, self.seed = env, seed
        self.run_dir = Path(run_dir)
        # Never append a new game to an old game's action ledger.
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.obs, _ = env.reset(seed=seed)
        self.run_id = uuid.uuid4().hex
        self.step_no = self.batch_no = self.invalid = 0
        self.done, self.episode_return = False, 0.0
        self.started_at = time.time()
        self.lock = threading.RLock()
        self.max_steps = env.max_steps
        self.last_live = self.live()
        self.last_prayer_turn = None
        self.blocked = set()
        self.log = (self.run_dir / "steps.jsonl").open("x", encoding="utf-8")

    @property
    def revision(self):
        return f"{self.run_id}:{self.step_no}"

    def live(self):
        return {"state": state(self.obs), "progress": copy.deepcopy(self.env.get_stats()),
                "observation": self.obs["text"]["long_term_context"],
                "inventory": self.obs["text"]["short_term_context"]}

    def status(self):
        with self.lock:
            return {"seed": self.seed, "run_id": self.run_id, "revision": self.revision,
                    "steps": self.step_no, "batches": self.batch_no, "done": self.done,
                    "episode_return": self.episode_return, "invalid_actions": self.invalid,
                    "max_steps": self.max_steps, "progress": copy.deepcopy(self.env.get_stats()),
                    "last_prayer_turn": self.last_prayer_turn,
                    "last_live": copy.deepcopy(self.last_live) if self.done else None}

    def view(self):
        with self.lock:
            return {"observation": self.obs["text"]["long_term_context"],
                    "inventory": self.obs["text"]["short_term_context"],
                    "state": state(self.obs), "prompt": prompt(self.obs), "status": self.status()}

    def block_key(self, action):
        # A changed visible world permits a fresh attempt; the last error message
        # and the mere passage of turns do not erase knowledge of a blocked move.
        text = self.obs["text"]["long_term_context"]
        world = text.split("language observation:")[-1].split("cursor:")[0]
        s = state(self.obs)
        return hashlib.sha256(json.dumps([s["depth"], s["position"], world, action]).encode()).hexdigest()

    def step(self, actions, tag="", *, expected_revision=None, stop_on=None, allow_risk=False):
        if not isinstance(actions, list) or not 1 <= len(actions) <= 50 or any(not isinstance(a, str) for a in actions):
            raise ValueError("actions는 1~50개 문자열 목록이어야 합니다")
        stops = DEFAULT_STOPS if stop_on is None else frozenset(stop_on)
        if stops - DEFAULT_STOPS:
            raise ValueError("알 수 없는 stop_on 조건")
        with self.lock:
            executed, reason = [], None
            if expected_revision is not None and expected_revision != self.revision:
                return {**self.view(), "done": self.done, "executed": [], "remaining": actions,
                        "stop_reason": "stale_observation"}
            if self.done:
                return {**self.view(), "done": True, "executed": [], "remaining": actions,
                        "stop_reason": "done"}
            self.batch_no += 1
            for requested in actions:
                before = state(self.obs)
                key = self.block_key(requested)
                action = self.env.check_action_validity(requested)
                if action != requested:
                    self.invalid += 1
                    reason = "invalid_action"
                    break  # An invalid request must not press Esc on the player's behalf.
                if not allow_risk and key in self.blocked:
                    reason = "known_blocked"
                    break
                if not allow_risk and requested == "look" and "Blind" in (before["conditions"] or ""):
                    reason = "blind_look_costs_turn_use_observe"
                    break
                if (not allow_risk and requested == "pray" and self.last_prayer_turn is not None
                        and before["turn"] is not None and before["turn"] - self.last_prayer_turn < 300):
                    reason = "recent_prayer_requires_explicit_risk"
                    break
                previous_live = self.live()
                obs, reward, terminated, truncated, _ = self.env.step(action)
                self.obs = obs
                self.step_no += 1
                self.episode_return += reward
                self.done = bool(terminated or truncated or self.step_no >= self.max_steps)
                after, msg = state(obs), message(obs)
                self.last_live = previous_live if self.done else self.live()
                if "You begin praying" in msg:
                    self.last_prayer_turn = after["turn"] if after["turn"] is not None else before["turn"]
                reasons = []
                if before["hp"] is not None and after["hp"] is not None and after["hp"] < before["hp"]:
                    reasons.append("damage")
                if prompt(obs):
                    reasons.append("prompt")
                if any(part in msg for part in BLOCKED):
                    reasons.append("blocked")
                    if before["position"] == after["position"] and before["depth"] == after["depth"]:
                        if len(self.blocked) >= 256:
                            self.blocked.clear()
                        self.blocked.add(self.block_key(requested))
                if before["conditions"] != after["conditions"] or before["depth"] != after["depth"]:
                    reasons.append("status_change")
                row = {"step": self.step_no, "batch": self.batch_no, "tag": tag,
                       "requested": requested, "action": action, "valid": True, "reward": reward,
                       "done": self.done, "message": "message:\n" + msg, "time": time.time(),
                       "before": before, "after": after, "events": reasons}
                self.log.write(json.dumps(row, ensure_ascii=False) + "\n")
                self.log.flush()
                executed.append(row)
                reason = "done" if self.done else next((r for r in reasons if r in stops), None)
                if reason:
                    break
            out = {**self.view(), "done": self.done, "executed": executed,
                   "remaining": actions[len(executed):], "stop_reason": reason}
            if self.done:
                (self.run_dir / "final.json").write_text(json.dumps(
                    {**self.status(), "elapsed_s": time.time() - self.started_at},
                    ensure_ascii=False, indent=2), encoding="utf-8")
            return out
