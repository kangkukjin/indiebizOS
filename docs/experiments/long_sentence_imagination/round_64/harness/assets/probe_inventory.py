import json, locale, sys
from pathlib import Path
from vocabulary_state import inventory
root=Path(__file__).parent
print(json.dumps({"encoding":locale.getencoding(),"utf8_mode":sys.flags.utf8_mode}))
v=inventory(root)
print(json.dumps({"packages":list(v["packages"]),"tools":v["tools"],"actions":v["actions"]},ensure_ascii=False))
