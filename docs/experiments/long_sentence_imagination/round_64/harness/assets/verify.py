import json,sys
from pathlib import Path
r=Path(__file__).parent
a=json.loads((r/"samples.json").read_text(encoding="utf-8")); cfg=json.loads((r/"config.json").read_text(encoding="utf-8")); b=json.loads((r/cfg["output"]/"result.json").read_text(encoding="utf-8"))
assert b["items"]==a and b["count"]==12 and b["note"]=="preserve-me"
print(json.dumps({"verified":True,"count":12,"runs":(r/"runs.log").read_text(encoding="utf-8").splitlines(),"old_preserved":(r/"out/result.json").exists()}))
