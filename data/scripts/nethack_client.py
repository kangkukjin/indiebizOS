"""Snapshot-reusing client for the local NetHack experiment, not an autoplayer."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import urllib.request


class Client:
    def __init__(self, cache, port=8797):
        self.cache, self.port = Path(cache), port

    def request(self, payload):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/",
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        # No automatic retry: a lost reply may already have advanced the game.
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)

    def save(self, response):
        if "observation" not in response or "status" not in response:
            raise ValueError(response.get("error", "관측 응답이 없습니다"))
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=self.cache.parent, prefix=".nh-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"port": self.port, "response": response}, stream, ensure_ascii=False)
            os.replace(path, self.cache)
        finally:
            if os.path.exists(path):
                os.unlink(path)
        return response

    def observe(self, fresh=False):
        if not fresh and self.cache.exists():
            data = json.loads(self.cache.read_text())
            if data.get("port") == self.port:
                return {**data["response"], "cached": True, "executed": []}
        return self.save(self.request({"op": "observe"}))

    def step(self, actions, *, input_sequence=False, allow_risk=False, tag=""):
        previous = self.observe()
        payload = {"op": "step", "actions": actions, "tag": tag,
                   "expected_revision": previous["status"]["revision"], "allow_risk": allow_risk}
        if input_sequence:
            payload["stop_on"] = ["damage", "blocked", "status_change"]
        return self.save(self.request(payload))

    def attack(self, direction, *, limit=8, hpmin=12):
        response = self.observe()
        for _ in range(limit):
            hp = response["state"]["hp"]
            if response["status"]["done"] or hp is None or hp < hpmin or response.get("prompt"):
                return response
            response = self.step(["fight", direction], input_sequence=True, tag="attack")
            events = response.get("executed", [])
            messages = events[-1]["message"] if events else ""
            if response.get("stop_reason") or any(word in messages for word in ("kill", "destroy", "thin air")):
                return response
        return response

    def rest(self, target, *, limit=100, hpmin=12, engrave=False, watch=()):
        response = self.observe()
        for _ in range(limit):
            s = response["state"]
            # Decide before every action using the most recent response.
            if (response["status"]["done"] or s["hp"] is None or s["hp"] < hpmin
                    or s["hp"] >= target or response.get("prompt")):
                return response
            nearby = response["observation"].split("language observation:")[-1].split("cursor:")[0]
            if any(monster in line and any(distance in line for distance in (" near ", "adjacent"))
                   for line in nearby.splitlines() for monster in watch):
                return {**response, "stop_reason": "watched_monster_nearby"}
            if engrave:
                # The helper does not guess inventory letters or type through a
                # prompt. Return control if protection needs inspection/renewal.
                response = self.step(["look"], tag="rest-check")
                if response.get("stop_reason"):
                    return response
                if 'read: "Elbereth"' not in response["observation"]:
                    return {**response, "stop_reason": "engraving_needs_attention"}
                s = response["state"]
                if s["hp"] is None or s["hp"] < hpmin or s["hp"] >= target:
                    return response
            response = self.step(["search"], tag="rest")
            if response.get("stop_reason"):
                return response
            messages = [e["message"].removeprefix("message:").strip() for e in response.get("executed", [])]
            if any(m and not m.startswith(("You hear", "You find")) and "turns to flee" not in m for m in messages):
                return {**response, "stop_reason": "rest_message_needs_attention"}
        return response


def legacy(kind, argv, cache):
    """Old experiment helper entry points now share the same cache and guards."""
    client = Client(cache)
    if kind == "attack":
        response = client.attack(argv[0], limit=int(argv[1]) if len(argv) > 1 else 8,
                                 hpmin=int(argv[2]) if len(argv) > 2 else 12)
    else:
        # The previous chunk budget is a cap; each turn is now observed before
        # another turn is sent, with no additional model round trips.
        chunk = int(argv[1]) if len(argv) > 1 else 3
        batches = int(argv[2]) if len(argv) > 2 else 30
        hpmin = int(argv[3]) if kind == "engrave" and len(argv) > 3 else 12
        response = client.rest(int(argv[0]), limit=chunk * batches, hpmin=hpmin,
                               engrave=kind == "engrave", watch=argv[3:] if kind == "watch" else ())
    print(json.dumps(response, ensure_ascii=False))


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--cache", type=Path, default=Path.cwd() / "observation.json")
    parser.add_argument("--port", type=int, default=8797)
    parser.add_argument("--fresh", action="store_true", help="캐시 대신 현재 상태를 조회")
    parser.add_argument("--inv", action="store_true")
    parser.add_argument("--tag", default="")
    parser.add_argument("--input-sequence", action="store_true")
    parser.add_argument("--allow-risk", action="store_true")
    parser.add_argument("--rest", type=int)
    parser.add_argument("--hp-min", type=int, default=12)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--engraving", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("actions", nargs="*")
    args = parser.parse_args(argv)
    client = Client(args.cache, args.port)
    if args.fresh:
        client.observe(fresh=True)
    if args.rest is not None:
        response = client.rest(args.rest, limit=args.limit, hpmin=args.hp_min, engrave=args.engraving)
    elif args.actions:
        response = client.step(args.actions, input_sequence=args.input_sequence,
                               allow_risk=args.allow_risk, tag=args.tag)
    else:
        response = client.observe()
    if args.json:
        print(json.dumps(response, ensure_ascii=False))
        return
    print("OBSERVATION", response["status"]["revision"], "cached" if response.get("cached") else "fresh")
    print(response["observation"].replace("\x00", ""))
    if args.inv:
        print(response["inventory"])
    print("STOP", response.get("stop_reason"), "REMAINING", response.get("remaining", []))
    print("DONE", response["status"]["done"], "LAST_PRAYER", response["status"].get("last_prayer_turn"))


if __name__ == "__main__":
    main()
